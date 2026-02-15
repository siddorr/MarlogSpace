from __future__ import annotations

from datetime import date, datetime, timedelta

from app.constants import REQUEST_SLOTS, SLOT_AM, SLOT_FULL, SLOT_PM, WORKDAYS


def utcnow() -> datetime:
    return datetime.utcnow()


def is_workday(value: date) -> bool:
    return value.weekday() in WORKDAYS


def in_booking_window(value: date, today: date | None = None) -> bool:
    current = today or datetime.utcnow().date()
    return current <= value <= (current + timedelta(days=6))


def expand_request_slot(slot: str) -> list[str]:
    if slot not in REQUEST_SLOTS:
        raise ValueError(f"Unsupported slot: {slot}")
    if slot == SLOT_FULL:
        return [SLOT_AM, SLOT_PM]
    return [slot]


def normalize_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False
