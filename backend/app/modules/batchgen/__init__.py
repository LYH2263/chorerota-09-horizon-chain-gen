"""Batch persistence for horizon generation: one click, many weeks, one commit.

Window: the target week plus the following weeks (by id), `horizon` weeks in
total; missing weeks are created as drafts. Phase windows come from
app.engines.phase.plan_horizon and are pinned on each week row together with
its slots, so later reads (week list / board) and later generates see the
same pinned layout regardless of the current horizon length.
"""
import re

from app.engines.phase import plan_horizon
from app.engines.rota import build_week_slots


def _load_roster(conn):
    mids = [r["id"] for r in conn.execute(
        "SELECT id FROM members WHERE active=1 AND data_quality='clean' ORDER BY id")]
    tids = [r["id"] for r in conn.execute(
        "SELECT id FROM tasks WHERE data_quality='clean' AND weight>0 ORDER BY id")]
    return mids, tids


def _next_label(conn):
    labels = [r["label"] for r in conn.execute("SELECT label FROM weeks")]
    nums = [int(m.group(1)) for lb in labels if (m := re.fullmatch(r"第(\d+)周", lb or ""))]
    nxt = max(nums) if nums else len(labels)
    return f"第{nxt + 1}周"


def _window_weeks(conn, week_id, horizon):
    """The `horizon` weeks of the window starting at week_id, creating drafts as needed."""
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM weeks WHERE id>=? ORDER BY id LIMIT ?", (week_id, horizon))]
    while len(rows) < horizon:
        cur = conn.execute("INSERT INTO weeks(label,status) VALUES (?,?)",
                           (_next_label(conn), "draft"))
        rows.append(dict(conn.execute(
            "SELECT * FROM weeks WHERE id=?", (cur.lastrowid,)).fetchone()))
    return rows


def _start_phase(conn, week_id):
    """Chain from the previous week's pinned end; 0 when there is none (legacy single week)."""
    prev = conn.execute(
        "SELECT phase_end FROM weeks WHERE id<? AND phase_end IS NOT NULL ORDER BY id DESC LIMIT 1",
        (week_id,)).fetchone()
    return prev["phase_end"] if prev else 0


def generate_window(conn, week_id, horizon, *, days=7):
    """Generate (or keep) `horizon` consecutive weeks from week_id. Single transaction.

    Raises LookupError if the start week does not exist.
    """
    target = conn.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if target is None:
        raise LookupError("week not found")
    mids, tids = _load_roster(conn)
    weeks = _window_weeks(conn, week_id, horizon)
    plans = plan_horizon(weeks, days=days, task_count=len(tids),
                         start_phase=_start_phase(conn, week_id))
    out = []
    for plan in plans:
        wid, ps, pe = plan["week_id"], plan["phase_start"], plan["phase_end"]
        if plan["action"] == "fill":
            slots = build_week_slots(mids, tids, days, phase=ps)
            conn.execute("DELETE FROM assignments WHERE week_id=?", (wid,))
            for s in slots:
                conn.execute(
                    "INSERT INTO assignments(week_id,day,task_id,member_id) VALUES (?,?,?,?)",
                    (wid, s["day"], s["task_id"], s["member_id"]))
            conn.execute(
                "UPDATE weeks SET status='ready', phase_start=?, phase_end=? WHERE id=?",
                (ps, pe, wid))
        elif plan["action"] == "skip":
            # Skipped week: no slots land, but its window stays pinned so the
            # phase keeps advancing for the weeks after it.
            conn.execute("DELETE FROM assignments WHERE week_id=?", (wid,))
            conn.execute("UPDATE weeks SET phase_start=?, phase_end=? WHERE id=?",
                         (ps, pe, wid))
        else:
            conn.execute("UPDATE weeks SET phase_start=?, phase_end=? WHERE id=?",
                         (ps, pe, wid))
        out.append({**plan, "slots": conn.execute(
            "SELECT COUNT(*) c FROM assignments WHERE week_id=?", (wid,)).fetchone()["c"]})
    conn.commit()
    return {"horizon": horizon, "days": days, "weeks": out}
