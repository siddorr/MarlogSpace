from __future__ import annotations

from datetime import time


WORKDAYS = {6, 0, 1, 2, 3}  # Sun..Thu with Python weekday mapping (Mon=0)
ALLOWED_DOMAIN = "@ide-tech.com"

ROLE_USER = "user"
ROLE_ADMIN = "admin"

STATE_FREE = "free"
STATE_PENDING = "pending"
STATE_BOOKED = "booked"
STATE_OWNED = "owned"
STATE_BLOCKED = "blocked"

BOOKING_PENDING = "pending"
BOOKING_APPROVED = "approved"
BOOKING_REJECTED = "rejected"
BOOKING_CANCELLED = "cancelled"
BOOKING_EXPIRED = "expired"
BOOKING_STATUSES = {
    BOOKING_PENDING,
    BOOKING_APPROVED,
    BOOKING_REJECTED,
    BOOKING_CANCELLED,
    BOOKING_EXPIRED,
}

SLOT_AM = "AM"
SLOT_PM = "PM"
SLOT_FULL = "FULL"
SLOTS = {SLOT_AM, SLOT_PM}
REQUEST_SLOTS = {SLOT_AM, SLOT_PM, SLOT_FULL}

SLOT_LABELS = {
    SLOT_AM: (time(hour=8), time(hour=12, minute=30)),
    SLOT_PM: (time(hour=12, minute=30), time(hour=17)),
}
