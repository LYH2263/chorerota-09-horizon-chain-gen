"""批量落库：按视野从锚定周起连续生成多周。

职责边界——本模块只管"取哪些周、各周是什么状态、如何写库"：
- 视野长度的校验/读取在 ``app.modules.horizon``；
- 跨周相位如何落到成员是纯函数，在 ``app.engines.rota``；
本模块把两者缝进一个事务，并保证已生成周的格位与起止相位被钉住，
只改视野长度不会重排它们。
"""

import re

from app.engines.rota import build_horizon_slots
from app.modules.horizon import get_horizon

SKIPPED = "skipped"
READY = "ready"


class BatchError(ValueError):
    pass


def _roster(conn):
    mids = [r["id"] for r in conn.execute(
        "SELECT id FROM members WHERE active=1 AND data_quality='clean' ORDER BY id")]
    tids = [r["id"] for r in conn.execute(
        "SELECT id FROM tasks WHERE data_quality='clean' AND weight>0 ORDER BY id")]
    return mids, tids


def _next_label(conn) -> str:
    labels = [r["label"] or "" for r in conn.execute("SELECT label FROM weeks")]
    nums = [int(m.group(1)) for s in labels for m in (re.search(r"(\d+)", s),) if m]
    n = (max(nums) if nums else 0) + 1
    return f"第{n}周"


def _ensure_weeks(conn, start_week_id: int, horizon: int) -> list:
    """取从锚定周起按 id 排序的 horizon 行，不足则自动补建。"""
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM weeks WHERE id>=? ORDER BY id LIMIT ?", (start_week_id, horizon))]
    while len(rows) < horizon:
        cur = conn.execute("INSERT INTO weeks(label,status,start_phase,end_phase) VALUES (?,?,?,?)",
                           (_next_label(conn), "draft", None, None))
        rows.append(dict(conn.execute("SELECT * FROM weeks WHERE id=?", (cur.lastrowid,)).fetchone()))
    return rows


def generate_horizon(conn, start_week_id: int, days: int = 7, horizon: int | None = None) -> list[dict]:
    """从 ``start_week_id`` 起按视野连续生成，返回每周落库结果。

    每周三种状态：
    - *pinned*：已生成（end_phase 已钉，或已有 assignments 的旧数据），格位
      与相位原样保留，游标跳到其 end_phase；
    - *skipped*：status='skipped'，不写 assignment，但相位推进整周格数，
      推进后同样钉住起止相位；
    - *fresh*：空周，按当前游标相位落格并钉相位、置 ready。
    """
    week = conn.execute("SELECT * FROM weeks WHERE id=?", (start_week_id,)).fetchone()
    if not week:
        raise BatchError("week not found")
    mids, tids = _roster(conn)
    if not mids or not tids:
        raise BatchError("roster_empty")
    horizon = get_horizon(conn) if horizon is None else horizon
    rows = _ensure_weeks(conn, start_week_id, horizon)

    per_week = days * len(tids)
    n = len(mids)
    cursor = 0  # 成员环上的相位；周间只依赖 mod n
    results = []
    for row in rows:
        wid = row["id"]
        start_phase = cursor % n
        existing = conn.execute(
            "SELECT COUNT(*) c FROM assignments WHERE week_id=?", (wid,)).fetchone()["c"]

        if row["end_phase"] is not None:
            # 已钉周（含此前已处理过的 skipped 周）：格位、相位同钉
            cursor = int(row["end_phase"])
            results.append(_summary(wid, row, start_phase, cursor, existing,
                                    pinned=True, skipped=(row["status"] == SKIPPED)))
            continue

        if existing:
            # 改造前落库的旧周：旧单周生成恒从头起算，占满整周格数，补钉相位
            cursor = per_week % n
            conn.execute("UPDATE weeks SET start_phase=?,end_phase=? WHERE id=?",
                         (0, cursor, wid))
            results.append(_summary(wid, row, 0, cursor, existing, pinned=True, skipped=False))
            continue

        if row["status"] == SKIPPED:
            # 跳过落格，但仍推进整周相位（与 skip_week 规则兼容的取舍）
            cursor = (cursor + per_week) % n
            conn.execute("DELETE FROM assignments WHERE week_id=?", (wid,))
            conn.execute("UPDATE weeks SET start_phase=?,end_phase=? WHERE id=?",
                         (start_phase, cursor, wid))
            results.append(_summary(wid, row, start_phase, cursor, 0,
                                    pinned=False, skipped=True))
            continue

        plan = build_horizon_slots(mids, tids, weeks=1, days=days, start_phase=cursor)[0]
        slots = plan["slots"]
        for s in slots:
            conn.execute(
                "INSERT INTO assignments(week_id,day,task_id,member_id) VALUES (?,?,?,?)",
                (wid, s["day"], s["task_id"], s["member_id"]))
        conn.execute("UPDATE weeks SET status=?,start_phase=?,end_phase=? WHERE id=?",
                     (READY, start_phase, plan["end_phase"], wid))
        cursor = plan["end_phase"]
        results.append(_summary(wid, row, start_phase, cursor, len(slots),
                                pinned=False, skipped=False))
    return results


def _summary(week_id, row, start_phase, end_phase, count, pinned, skipped) -> dict:
    return {
        "week_id": week_id,
        "label": row["label"],
        "start_phase": start_phase,
        "end_phase": end_phase,
        "assignment_count": count,
        "pinned": pinned,
        "skipped": skipped,
    }
