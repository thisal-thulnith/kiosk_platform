from collections.abc import Sequence
from datetime import datetime, time
from typing import Any


def _parse(hhmm: str) -> time:
    hours, minutes = hhmm.split(":")
    return time(int(hours), int(minutes))


def in_windows(windows: Sequence[dict[str, Any]], local_now: datetime) -> bool:
    """True when local_now falls in any window. No windows means always on.

    A window whose end is before its start runs past midnight (e.g. 22:00-02:00), and
    the part after midnight counts for the previous day.
    """
    if not windows:
        return True
    weekday, now = local_now.weekday(), local_now.time()
    for w in windows:
        days = w.get("days") or list(range(7))
        start, end = _parse(w["start"]), _parse(w["end"])
        if start <= end:
            if weekday in days and start <= now < end:
                return True
        else:
            if weekday in days and now >= start:
                return True
            if (weekday - 1) % 7 in days and now < end:
                return True
    return False


def validate_windows(windows: Sequence[dict[str, Any]]) -> None:
    for w in windows:
        _parse(w["start"])
        _parse(w["end"])
        for d in w.get("days") or []:
            if not 0 <= int(d) <= 6:
                raise ValueError("days must be 0 (Monday) to 6 (Sunday)")
