from app.engines.rota import build_week_slots, build_horizon_slots, swap_legal, apply_swap

def test_round_robin_covers_grid():
    slots = build_week_slots([1, 2, 3], [10, 20], days=7)
    assert len(slots) == 14
    assert slots[0]["member_id"] == 1
    assert slots[1]["member_id"] == 2
    assert slots[3]["member_id"] == 1  # wraps

def test_swap_rejects_same_assignee():
    slots = [{"day": 0, "task_id": 1, "member_id": 9}, {"day": 1, "task_id": 1, "member_id": 9}]
    r = swap_legal(slots, 0, 1, 1, 1)
    assert r["ok"] is False and r["reason"] == "same_assignee"

def test_apply_swap_exchanges():
    slots = build_week_slots([1, 2], [10], days=2)
    out = apply_swap(slots, 0, 10, 1, 10)
    assert out[0]["member_id"] == 2 and out[1]["member_id"] == 1

def test_horizon1_matches_legacy_single_week():
    # horizon=1 与改造前单周生成完全一致：从成员列表头重启
    legacy = build_week_slots([1, 2, 3], [10, 20], days=7)
    horizon = build_horizon_slots([1, 2, 3], [10, 20], weeks=1, days=7)
    assert horizon[0]["slots"] == legacy
    assert horizon[0]["start_phase"] == 0
    assert horizon[0]["end_phase"] == 14 % 3

def test_phase_is_continuous_across_weeks():
    # 后一周相位紧接前一周末格，不得每周从头重启
    weeks = build_horizon_slots([1, 2, 3], [10, 20], weeks=3, days=7)
    per_week = 7 * 2
    for prev, nxt in zip(weeks, weeks[1:]):
        assert nxt["start_phase"] == prev["end_phase"]
        assert prev["end_phase"] == (prev["start_phase"] + per_week) % 3
    # 第二周首格成员 = 前一周末格的下一顺位（旧实现此处会错误地回到成员 1）
    assert weeks[0]["slots"][-1]["member_id"] == 2  # 格 13 -> idx 13 % 3
    assert weeks[1]["slots"][0]["member_id"] == 3   # idx 14 % 3
    assert weeks[1]["start_phase"] == 14 % 3

def test_skipped_week_advances_phase_but_has_no_slots():
    # skipped：不落格，但仍按整周格数推进相位
    weeks = build_horizon_slots([1, 2, 3], [10, 20], weeks=3, days=7, skipped_weeks={1})
    assert weeks[1]["skipped"] is True and weeks[1]["slots"] == []
    normal = build_horizon_slots([1, 2, 3], [10, 20], weeks=3, days=7)
    # 跳过周之后那一周的相位，与没有跳过时完全相同
    assert weeks[2]["start_phase"] == normal[2]["start_phase"]
    assert weeks[2]["slots"] == normal[2]["slots"]
