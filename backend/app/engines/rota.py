"""Round-robin weekly chore assignments + swap legality.

相位（phase）= 本轮转游标在成员环上的绝对格位。一周有
``len(task_ids) * days`` 个格位（任务为内环、天为外环），因此跨周连续
生成时，后一周的起始相位 = 前一周结束相位，不会每周从成员列表头重启。
"""

def build_week_slots(member_ids: list[int], task_ids: list[int], days: int = 7) -> list[dict]:
    """Assign each (day, task) to members in round-robin by task then day.

    horizon=1 单周生成的语义保持不变：总是从相位 0（成员列表头）起算。
    """
    if not member_ids or not task_ids:
        return []
    slots = []
    idx = 0
    for day in range(days):
        for tid in task_ids:
            mid = member_ids[idx % len(member_ids)]
            slots.append({"day": day, "task_id": tid, "member_id": mid})
            idx += 1
    return slots


def build_horizon_slots(
    member_ids: list[int],
    task_ids: list[int],
    weeks: int,
    days: int = 7,
    start_phase: int = 0,
    skipped_weeks: set[int] | None = None,
) -> list[dict]:
    """连续生成 ``weeks`` 周：后一周相位紧接前一周末格，逐周钉起止相位。

    返回每周一条 ``{"index","start_phase","end_phase","skipped","slots"}``：
    相位按成员环取模（``% n``）做钉位，底层用绝对格位计数器，因此钉下的
    起止相位与成员增减解耦——只改视野长度重算时格位不再漂移。

    skipped 周（``skipped_weeks`` 含其 0 基周序）**不落格**（slots 为空），
    但相位仍按整周格数 ``days*len(task_ids)`` 推进——跳过只是本周不登记，
    跨周节奏不断档。
    """
    if not member_ids or not task_ids:
        return []
    skipped_weeks = skipped_weeks or set()
    per_week = days * len(task_ids)
    n = len(member_ids)
    absolute = start_phase  # 绝对格位计数器（不随成员数取模）
    results = []
    for w in range(weeks):
        sp = absolute % n
        if w in skipped_weeks:
            # 跳过落格，但仍推进相位（兼容 skip_week 规则）
            absolute += per_week
            results.append({
                "index": w,
                "start_phase": sp,
                "end_phase": absolute % n,
                "skipped": True,
                "slots": [],
            })
            continue
        slots = []
        for day in range(days):
            for tid in task_ids:
                mid = member_ids[absolute % n]
                slots.append({"day": day, "task_id": tid, "member_id": mid})
                absolute += 1
        results.append({
            "index": w,
            "start_phase": sp,
            "end_phase": absolute % n,
            "skipped": False,
            "slots": slots,
        })
    return results


def swap_legal(slots: list[dict], a_day: int, a_task: int, b_day: int, b_task: int) -> dict:
    """Two slots may swap only if both exist, different assignees, same week grid."""
    def find(day, task):
        for s in slots:
            if s["day"] == day and s["task_id"] == task:
                return s
        return None
    sa, sb = find(a_day, a_task), find(b_day, b_task)
    if sa is None or sb is None:
        return {"ok": False, "reason": "slot_missing"}
    if sa["member_id"] == sb["member_id"]:
        return {"ok": False, "reason": "same_assignee"}
    if a_day == b_day and a_task == b_task:
        return {"ok": False, "reason": "same_slot"}
    return {
        "ok": True,
        "reason": "",
        "a_member": sa["member_id"],
        "b_member": sb["member_id"],
    }


def apply_swap(slots: list[dict], a_day: int, a_task: int, b_day: int, b_task: int) -> list[dict]:
    check = swap_legal(slots, a_day, a_task, b_day, b_task)
    if not check["ok"]:
        raise ValueError(check["reason"])
    out = [dict(s) for s in slots]
    ia = next(i for i, s in enumerate(out) if s["day"] == a_day and s["task_id"] == a_task)
    ib = next(i for i, s in enumerate(out) if s["day"] == b_day and s["task_id"] == b_task)
    out[ia]["member_id"], out[ib]["member_id"] = out[ib]["member_id"], out[ia]["member_id"]
    return out
