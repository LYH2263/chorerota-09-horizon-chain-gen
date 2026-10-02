"""视野（horizon_weeks）设置：登记一次连续生成几周。

只负责视野长度本身的校验与读写，不触碰周相位/落库——跨周相位在
``app.engines.rota``，批量落库在 ``app.modules.week_batch``。
"""

KEY = "horizon_weeks"
DEFAULT = 1
MIN = 1
MAX = 52  # 防御性上限：避免误登记一个巨大数字一次生成几百周


class HorizonError(ValueError):
    """视野非法（<1、非整数或超上限）。"""


def validate_horizon(value) -> int:
    """校验视野：必须是 >=1 的整数。布尔值按非整数拒绝。

    视野 <=0 拒写设置；小数、空串、无法解析的值同样拒绝。
    """
    if isinstance(value, bool):
        raise HorizonError("horizon_weeks 必须是 >=1 的整数")
    if isinstance(value, int):
        horizon = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            horizon = int(text)  # "3.5"/"abc" 会抛错，杜绝小数被截断
        except (TypeError, ValueError):
            raise HorizonError("horizon_weeks 必须是 >=1 的整数")
    else:
        raise HorizonError("horizon_weeks 必须是 >=1 的整数")
    if horizon < MIN:
        raise HorizonError("horizon_weeks 必须 >=1")
    if horizon > MAX:
        raise HorizonError(f"horizon_weeks 不能超过 {MAX}")
    return horizon


def get_horizon(conn) -> int:
    """从 settings 表读取视野；缺失/脏值时回退为 1。"""
    row = conn.execute("SELECT value FROM settings WHERE key=?", (KEY,)).fetchone()
    if row is None:
        return DEFAULT
    try:
        return validate_horizon(row["value"])
    except HorizonError:
        return DEFAULT


def set_horizon(conn, value) -> int:
    """校验后写入 settings；非法值抛 HorizonError 且不写库。"""
    horizon = validate_horizon(value)
    conn.execute(
        "INSERT INTO settings(key,value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (KEY, str(horizon)),
    )
    return horizon
