"""Horizon setting: how many weeks one generate click covers.

horizon_weeks is stored in the settings table; it must be an integer >= 1.
horizon=1 reproduces the legacy single-week generate. Values <= 0 (or
non-numeric) are rejected and never written.
"""

KEY = "horizon_weeks"
DEFAULT = 1


def validate(value) -> int:
    """Return value as a valid horizon, or raise ValueError (<=0 / non-numeric)."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{KEY} must be an integer, got {value!r}")
    if n < 1:
        raise ValueError(f"{KEY} must be >= 1, got {n}")
    return n


def get_horizon(conn) -> int:
    """Read the setting; missing or corrupt rows fall back to DEFAULT."""
    row = conn.execute("SELECT value FROM settings WHERE key=?", (KEY,)).fetchone()
    if row is None:
        return DEFAULT
    try:
        return validate(row["value"])
    except ValueError:
        return DEFAULT


def set_horizon(conn, value) -> int:
    """Validate then persist; invalid values are rejected (nothing written)."""
    n = validate(value)
    conn.execute(
        "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (KEY, str(n)),
    )
    return n
