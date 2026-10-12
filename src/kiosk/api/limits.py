"""Stop guessing: after too many wrong setup codes or passwords from one address, wait a while.

In memory, per server process: enough for one cloud instance or a hub. (With several cloud
instances, move the counters to Redis.)
"""

import time
from collections import defaultdict, deque

from fastapi import Request

from kiosk.errors import AppError

WINDOW_SECONDS = 300
MAX_FAILURES = 10

_failures: dict[str, deque[float]] = defaultdict(deque)


def _key(request: Request, what: str) -> str:
    return f"{what}:{request.client.host if request.client else '?'}"


def check(request: Request, what: str) -> None:
    q = _failures[_key(request, what)]
    now = time.monotonic()
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()
    if len(q) >= MAX_FAILURES:
        raise AppError("too_many_attempts", "Too many wrong attempts. Wait 5 minutes and try again", 429)


def failed(request: Request, what: str) -> None:
    _failures[_key(request, what)].append(time.monotonic())


def reset() -> None:
    _failures.clear()
