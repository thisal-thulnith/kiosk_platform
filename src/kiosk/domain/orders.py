"""Order state machine.

Order status and payment status are separate on purpose:

    status:          PLACED -> IN_KITCHEN -> READY -> COMPLETED
                     PLACED -> CANCELLED | EXPIRED
                     IN_KITCHEN | READY -> VOIDED
    payment_status:  UNPAID -> PENDING -> PAID -> REFUNDED

Release rule A: the kitchen only gets the order once it is PAID.
Release rule B: the kitchen gets it immediately; it cannot be COMPLETED until PAID.
"""

from enum import StrEnum


class Status(StrEnum):
    PLACED = "placed"
    IN_KITCHEN = "in_kitchen"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    VOIDED = "voided"


class PaymentStatus(StrEnum):
    UNPAID = "unpaid"
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"


class ItemStatus(StrEnum):
    HELD = "held"  # hold and fire: waits for the waiter/cashier to fire it (course timing)
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    VOIDED = "voided"


TERMINAL = {Status.COMPLETED, Status.CANCELLED, Status.EXPIRED, Status.VOIDED}
OPEN_KITCHEN = {Status.IN_KITCHEN, Status.READY}

TRANSITIONS: dict[Status, set[Status]] = {
    Status.PLACED: {Status.IN_KITCHEN, Status.CANCELLED, Status.EXPIRED},
    Status.IN_KITCHEN: {Status.READY, Status.VOIDED},
    Status.READY: {Status.COMPLETED, Status.IN_KITCHEN, Status.VOIDED},
    Status.COMPLETED: set(),
    Status.CANCELLED: set(),
    Status.EXPIRED: set(),
    Status.VOIDED: set(),
}


class TransitionError(Exception):
    def __init__(self, current: str, target: str, reason: str | None = None) -> None:
        self.current, self.target = current, target
        super().__init__(reason or f"Cannot move order from {current} to {target}")


def check_transition(current: str, target: Status) -> None:
    if target not in TRANSITIONS[Status(current)]:
        raise TransitionError(current, target)


def should_release_on_place(release_rule: str) -> bool:
    return release_rule == "B"


def should_release_on_payment(status: str, release_rule: str) -> bool:
    return release_rule == "A" and status == Status.PLACED


def can_complete(payment_status: str) -> bool:
    return payment_status == PaymentStatus.PAID


def all_items_done(item_statuses: list[str]) -> bool:
    live = [s for s in item_statuses if s != ItemStatus.VOIDED]
    return bool(live) and all(s == ItemStatus.DONE for s in live)


# Kitchen queue order: rush first, then VIP, then everyone else by promised time.
PRIORITY_RANK = {"rush": 0, "vip": 1, "normal": 2}
REMAKE_REASONS = ("burnt", "dropped", "wrong_item", "guest_complaint", "quality", "other")


def estimate_minutes(prep_minutes: list[int], open_before: int, cooks: int) -> int:
    """Promised time for a new kitchen order: its slowest item, plus a queue delay of
    about 2 minutes for every full round of orders ahead of it per cook."""
    slowest = max(prep_minutes) if prep_minutes else 10
    return slowest + 2 * (open_before // max(1, cooks))


def congestion(
    open_tickets: int, avg_prep_seconds: float, cooks: int, warn_min: int, late_min: int
) -> dict[str, object]:
    """Full Plan: congestion score = open tickets x average prep time / cooks (in minutes)."""
    score = open_tickets * avg_prep_seconds / max(1, cooks) / 60
    level = "normal" if score < warn_min else "busy" if score < late_min else "overloaded"
    return {"score_minutes": round(score, 1), "level": level}


def format_token(prefix: str, number: int) -> str:
    return f"{prefix}{number:03d}"
