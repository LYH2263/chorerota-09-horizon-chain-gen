"""Cross-week phase planning for multi-week horizon generation.

Phase is the global rotation offset: a week occupying phase window [s, e)
hands e to the next week, so consecutive weeks never restart from the head
of the member list. One week consumes days * task_count slots of phase.
"""


def week_span(days: int, task_count: int) -> int:
    return max(0, int(days)) * max(0, int(task_count))


def plan_horizon(weeks: list[dict], *, days: int, task_count: int, start_phase: int = 0) -> list[dict]:
    """Plan actions and pinned phase windows for a consecutive run of weeks.

    Each week gets a window [phase_start, phase_end); the next week starts at
    the previous end. Already-pinned weeks (both phase columns set) keep their
    window and it still feeds the chain, so changing the horizon length never
    rearranges a generated week.

    Actions:
      ready   -> "keep": leave existing slots untouched;
      skipped -> "skip": no slots are landed, but the window is still consumed;
      other   -> "fill": (re)generate slots at the carried phase.
    """
    span = week_span(days, task_count)
    plans = []
    phase = start_phase
    for w in weeks:
        ps = w.get("phase_start")
        pe = w.get("phase_end")
        pinned = ps is not None and pe is not None
        status = w.get("status")
        if status == "ready":
            if not pinned:
                ps, pe = phase, phase + span
            plans.append({"week_id": w["id"], "action": "keep", "phase_start": ps, "phase_end": pe})
        elif status == "skipped":
            # 拍板 (decided tradeoff): a skipped week lands no slots yet still
            # consumes its phase window, so the global rotation cadence and the
            # members of neighbouring weeks stay put.
            if not pinned:
                ps, pe = phase, phase + span
            plans.append({"week_id": w["id"], "action": "skip", "phase_start": ps, "phase_end": pe})
        else:
            ps, pe = phase, phase + span
            plans.append({"week_id": w["id"], "action": "fill", "phase_start": ps, "phase_end": pe})
        phase = pe
    return plans
