"""跳过周：只负责周的 skipped 状态切换。

中途遇到 skipped 周时如何推进相位、是否落格，由
``app.modules.week_batch`` 在批量生成时处理；本模块只做状态闸门。

规则：
- 仅 draft 周可标记 skipped；ready 周已钉格位，锁定不可跳（400）；
- 取消 skip 时清掉钉位相位，使下次生成按当前游标重新落格——跳过与正常
  落格推进的相位相同，因此不影响其后已生成周的钉位。
"""

SKIPPED = "skipped"
DRAFT = "draft"
READY = "ready"


class SkipError(ValueError):
    pass


def mark_skipped(conn, week_id: int) -> dict:
    week = conn.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if not week:
        raise SkipError("week not found")
    if week["status"] == SKIPPED:
        return {"id": week_id, "status": SKIPPED}
    if week["status"] == READY:
        raise SkipError("ready_week_locked")
    conn.execute("UPDATE weeks SET status=? WHERE id=?", (SKIPPED, week_id))
    return {"id": week_id, "status": SKIPPED}


def unskip(conn, week_id: int) -> dict:
    week = conn.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if not week:
        raise SkipError("week not found")
    if week["status"] != SKIPPED:
        return {"id": week_id, "status": week["status"]}
    conn.execute("UPDATE weeks SET status=?,start_phase=NULL,end_phase=NULL WHERE id=?",
                 (DRAFT, week_id))
    return {"id": week_id, "status": DRAFT}
