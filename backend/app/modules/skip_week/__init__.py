"""skip_week: take a week out of the rota without disturbing the rotation.

拍板 (decided tradeoff): skipping clears the week's slots but keeps its
pinned phase window — the global rotation cadence is preserved, so members
of the surrounding weeks are never reshuffled by a skip. A skipped week
that was never generated gets its window pinned on the next generate run.
Unskipping returns the week to draft; the next generate re-fills it at the
carried phase, which is its original window as long as neighbours stayed pinned.
"""


def skip_week(conn, week_id):
    row = conn.execute("SELECT id FROM weeks WHERE id=?", (week_id,)).fetchone()
    if row is None:
        raise LookupError("week not found")
    conn.execute("DELETE FROM assignments WHERE week_id=?", (week_id,))
    conn.execute("UPDATE weeks SET status='skipped' WHERE id=?", (week_id,))
    conn.commit()


def unskip_week(conn, week_id):
    row = conn.execute("SELECT id FROM weeks WHERE id=?", (week_id,)).fetchone()
    if row is None:
        raise LookupError("week not found")
    conn.execute("UPDATE weeks SET status='draft' WHERE id=? AND status='skipped'",
                 (week_id,))
    conn.commit()
