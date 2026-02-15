from __future__ import annotations

from datetime import time

WORKDAYS = {6, 0, 1, 2, 3}  # Sun..Thu with Python weekday mapping (Mon=0)
ALLOWED_DOMAIN = "@ide-tech.com"

SLOT_AM = "AM"
SLOT_PM = "PM"
SLOT_FULL = "FULL"
SLOTS = {SLOT_AM, SLOT_PM}
REQUEST_SLOTS = {SLOT_AM, SLOT_PM, SLOT_FULL}

SLOT_LABELS = {
    SLOT_AM: (time(hour=8), time(hour=12, minute=30)),
    SLOT_PM: (time(hour=12, minute=30), time(hour=17)),
}

SHEETS = ["users", "desks", "reservations", "absences", "meta"]

USERS_HEADERS = ["user_id", "name", "email", "enabled", "is_admin", "created_at"]
DESKS_HEADERS = ["desk_id", "label", "enabled", "owner_user_id"]
RESERVATIONS_HEADERS = [
    "reservation_id",
    "user_id",
    "desk_id",
    "date",
    "slot",
    "created_at",
    "updated_at",
]
ABSENCES_HEADERS = [
    "absence_id",
    "owner_user_id",
    "desk_id",
    "date",
    "slot",
    "created_at",
]
META_HEADERS = ["key", "value"]
