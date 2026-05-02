from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook

from app.config import settings
from app.constants import BOOKING_APPROVED, ROLE_ADMIN, ROLE_USER
from app.models import (
    AuditEntry,
    BookingRecord,
    DeskRecord,
    FloorRecord,
    LocationRecord,
    NotificationRecord,
    PreferredPartnerRecord,
    RecurringReleaseRecord,
    UserRecord,
    WhitelistEntry,
)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _iso_now() -> str:
    return _utcnow().isoformat()


class SQLiteRepository:
    def __init__(self, db_file: Path | None = None, legacy_excel_file: Path | None = None) -> None:
        self.db_file = db_file or settings.db_file
        self.legacy_excel_file = legacy_excel_file or settings.legacy_excel_file

    @contextmanager
    def connect(self):
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_storage(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    location TEXT,
                    department TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_whitelist (
                    whitelist_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    user_id TEXT,
                    added_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS otp_codes (
                    email TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    attempts_left INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS locations (
                    location_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS floors (
                    floor_id TEXT PRIMARY KEY,
                    location_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(location_id, name),
                    FOREIGN KEY(location_id) REFERENCES locations(location_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS desks (
                    desk_id TEXT PRIMARY KEY,
                    floor_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    owner_user_id TEXT,
                    is_blocked INTEGER NOT NULL DEFAULT 0,
                    x INTEGER NOT NULL DEFAULT 0,
                    y INTEGER NOT NULL DEFAULT 0,
                    zone TEXT,
                    equipment_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(floor_id) REFERENCES floors(floor_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS manual_releases (
                    manual_release_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    desk_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    released INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(desk_id, date, slot),
                    FOREIGN KEY(owner_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(desk_id) REFERENCES desks(desk_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS recurring_releases (
                    recurring_release_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    desk_id TEXT NOT NULL,
                    weekday INTEGER NOT NULL,
                    slot TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(desk_id, weekday, slot),
                    FOREIGN KEY(owner_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(desk_id) REFERENCES desks(desk_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS preferred_partners (
                    preferred_partner_id TEXT PRIMARY KEY,
                    desk_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    partner_user_id TEXT NOT NULL,
                    auto_approve INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(desk_id, partner_user_id),
                    FOREIGN KEY(desk_id) REFERENCES desks(desk_id) ON DELETE CASCADE,
                    FOREIGN KEY(owner_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(partner_user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS booking_requests (
                    booking_id TEXT PRIMARY KEY,
                    requested_by TEXT NOT NULL,
                    desk_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approval_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    acted_at TEXT,
                    acted_by TEXT,
                    FOREIGN KEY(requested_by) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(desk_id) REFERENCES desks(desk_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS booking_slots (
                    booking_slot_id TEXT PRIMARY KEY,
                    booking_id TEXT NOT NULL,
                    desk_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    FOREIGN KEY(booking_id) REFERENCES booking_requests(booking_id) ON DELETE CASCADE,
                    FOREIGN KEY(desk_id) REFERENCES desks(desk_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    read_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    details TEXT NOT NULL
                );
                """
            )
        self._seed_defaults()
        self.import_legacy_excel_if_needed()

    def _seed_defaults(self) -> None:
        if self.list_locations():
            return
        location = self.upsert_location("Haifa")
        self.upsert_floor(location.location_id, "2")

    def import_legacy_excel_if_needed(self) -> None:
        if not self.legacy_excel_file.exists():
            return
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
            if row["c"]:
                return

        wb = load_workbook(self.legacy_excel_file)
        location = self.list_locations()[0]
        floor = self.list_floors(location.location_id)[0]

        users_sheet = wb["users"] if "users" in wb.sheetnames else None
        desks_sheet = wb["desks"] if "desks" in wb.sheetnames else None
        reservations_sheet = wb["reservations"] if "reservations" in wb.sheetnames else None
        absences_sheet = wb["absences"] if "absences" in wb.sheetnames else None
        user_map: dict[str, str] = {}

        if users_sheet:
            rows = list(users_sheet.iter_rows(values_only=True))
            headers = [str(v) for v in rows[0]] if rows else []
            for values in rows[1:]:
                row = dict(zip(headers, values))
                if not row.get("user_id") or not row.get("email"):
                    continue
                user = self.upsert_user(
                    user_id=str(row["user_id"]),
                    name=str(row.get("name") or row["email"]).split("@")[0].replace(".", " ").title(),
                    email=str(row["email"]),
                    enabled=bool(row.get("enabled", True)),
                    is_admin=bool(row.get("is_admin", False)),
                )
                user_map[str(row["user_id"])] = user.user_id
                self.upsert_whitelist(user.email, user.user_id, "legacy-import")

        if desks_sheet:
            rows = list(desks_sheet.iter_rows(values_only=True))
            headers = [str(v) for v in rows[0]] if rows else []
            index = 0
            for values in rows[1:]:
                row = dict(zip(headers, values))
                if not row.get("desk_id"):
                    continue
                self.upsert_desk(
                    desk_id=str(row["desk_id"]),
                    floor_id=floor.floor_id,
                    label=str(row.get("label") or f"Desk {index + 1}"),
                    enabled=bool(row.get("enabled", True)),
                    owner_user_id=user_map.get(str(row.get("owner_user_id"))) if row.get("owner_user_id") else None,
                    is_blocked=False,
                    x=(index % 4) * 22 + 10,
                    y=(index // 4) * 24 + 12,
                    zone=None,
                    equipment={},
                )
                index += 1

        if reservations_sheet:
            rows = list(reservations_sheet.iter_rows(values_only=True))
            headers = [str(v) for v in rows[0]] if rows else []
            grouped: dict[tuple[str, str, str], list[str]] = {}
            for values in rows[1:]:
                row = dict(zip(headers, values))
                if not row.get("reservation_id"):
                    continue
                user_id = user_map.get(str(row.get("user_id")))
                if not user_id:
                    continue
                date_value = str(row["date"])
                grouped.setdefault((user_id, str(row["desk_id"]), date_value), []).append(str(row["slot"]))
            for (user_id, desk_id, date_value), slots in grouped.items():
                slot = "FULL" if sorted(set(slots)) == ["AM", "PM"] else slots[0]
                self.create_booking_request(
                    requested_by=user_id,
                    desk_id=desk_id,
                    value_date=date.fromisoformat(date_value),
                    request_slot=slot,
                    status=BOOKING_APPROVED,
                    approval_type="legacy_import",
                )

        if absences_sheet:
            rows = list(absences_sheet.iter_rows(values_only=True))
            headers = [str(v) for v in rows[0]] if rows else []
            for values in rows[1:]:
                row = dict(zip(headers, values))
                if not row.get("desk_id") or not row.get("owner_user_id"):
                    continue
                owner_user_id = user_map.get(str(row["owner_user_id"]))
                if not owner_user_id:
                    continue
                self.upsert_manual_release(
                    owner_user_id=owner_user_id,
                    desk_id=str(row["desk_id"]),
                    value_date=date.fromisoformat(str(row["date"])),
                    slot=str(row["slot"]),
                    released=True,
                )

        self.create_audit_log("system", "legacy_import", "system", "legacy_excel", "Imported legacy workbook")

    def _fetchone(self, query: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(query, tuple(params)).fetchone()

    def _fetchall(self, query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(query, tuple(params)).fetchall()

    def _bool(self, value: Any) -> bool:
        return bool(int(value)) if value is not None else False

    def _user_from_row(self, row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            user_id=row["user_id"],
            name=row["name"],
            email=row["email"],
            enabled=self._bool(row["enabled"]),
            is_admin=self._bool(row["is_admin"]),
            location=row["location"],
            department=row["department"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _location_from_row(self, row: sqlite3.Row) -> LocationRecord:
        return LocationRecord(
            location_id=row["location_id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _floor_from_row(self, row: sqlite3.Row) -> FloorRecord:
        return FloorRecord(
            floor_id=row["floor_id"],
            location_id=row["location_id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _desk_from_row(self, row: sqlite3.Row) -> DeskRecord:
        return DeskRecord(
            desk_id=row["desk_id"],
            floor_id=row["floor_id"],
            label=row["label"],
            enabled=self._bool(row["enabled"]),
            owner_user_id=row["owner_user_id"],
            is_blocked=self._bool(row["is_blocked"]),
            x=int(row["x"]),
            y=int(row["y"]),
            zone=row["zone"],
            equipment=json.loads(row["equipment_json"] or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def list_users(self, include_disabled: bool = False) -> list[UserRecord]:
        query = "SELECT * FROM users"
        if not include_disabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY name"
        return [self._user_from_row(row) for row in self._fetchall(query)]

    def get_user(self, user_id: str) -> UserRecord | None:
        row = self._fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self._user_from_row(row) if row else None

    def get_user_by_email(self, email: str) -> UserRecord | None:
        row = self._fetchone("SELECT * FROM users WHERE lower(email) = lower(?)", (email,))
        return self._user_from_row(row) if row else None

    def upsert_user(
        self,
        name: str,
        email: str,
        enabled: bool = True,
        is_admin: bool = False,
        location: str | None = None,
        department: str | None = None,
        user_id: str | None = None,
    ) -> UserRecord:
        existing = self.get_user_by_email(email)
        target_id = user_id or (existing.user_id if existing else uuid.uuid4().hex)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, name, email, enabled, is_admin, location, department, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name = excluded.name,
                    email = excluded.email,
                    enabled = excluded.enabled,
                    is_admin = excluded.is_admin,
                    location = excluded.location,
                    department = excluded.department
                """,
                (
                    target_id,
                    name,
                    email.lower(),
                    int(enabled),
                    int(is_admin),
                    location,
                    department,
                    existing.created_at.isoformat() if existing else _iso_now(),
                ),
            )
        return self.get_user(target_id)  # type: ignore[return-value]

    def list_whitelist(self) -> list[WhitelistEntry]:
        rows = self._fetchall("SELECT * FROM auth_whitelist ORDER BY email")
        return [
            WhitelistEntry(
                whitelist_id=row["whitelist_id"],
                email=row["email"],
                user_id=row["user_id"],
                added_by=row["added_by"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def email_allowed(self, email: str) -> bool:
        row = self._fetchone(
            "SELECT whitelist_id FROM auth_whitelist WHERE lower(email) = lower(?)",
            (email,),
        )
        return row is not None

    def upsert_whitelist(self, email: str, user_id: str | None, added_by: str) -> WhitelistEntry:
        existing = self._fetchone(
            "SELECT * FROM auth_whitelist WHERE lower(email) = lower(?)", (email,)
        )
        whitelist_id = existing["whitelist_id"] if existing else uuid.uuid4().hex
        created_at = existing["created_at"] if existing else _iso_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_whitelist (whitelist_id, email, user_id, added_by, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(whitelist_id) DO UPDATE SET
                    email = excluded.email,
                    user_id = excluded.user_id,
                    added_by = excluded.added_by
                """,
                (whitelist_id, email.lower(), user_id, added_by, created_at),
            )
        row = self._fetchone("SELECT * FROM auth_whitelist WHERE whitelist_id = ?", (whitelist_id,))
        assert row is not None
        return WhitelistEntry(
            whitelist_id=row["whitelist_id"],
            email=row["email"],
            user_id=row["user_id"],
            added_by=row["added_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def delete_whitelist(self, whitelist_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM auth_whitelist WHERE whitelist_id = ?", (whitelist_id,))
            return cur.rowcount > 0

    def save_otp(self, email: str, code: str, expires_at: datetime, attempts_left: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO otp_codes (email, code, expires_at, attempts_left)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    code = excluded.code,
                    expires_at = excluded.expires_at,
                    attempts_left = excluded.attempts_left
                """,
                (email.lower(), code, expires_at.isoformat(), attempts_left),
            )

    def get_otp(self, email: str) -> sqlite3.Row | None:
        return self._fetchone("SELECT * FROM otp_codes WHERE lower(email) = lower(?)", (email,))

    def decrement_otp_attempts(self, email: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE otp_codes SET attempts_left = attempts_left - 1 WHERE lower(email) = lower(?)",
                (email,),
            )

    def delete_otp(self, email: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM otp_codes WHERE lower(email) = lower(?)", (email,))

    def create_session(self, token: str, user_id: str, expires_at: datetime) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (token, user_id, expires_at.isoformat(), _iso_now()),
            )

    def get_session(self, token: str) -> sqlite3.Row | None:
        return self._fetchone("SELECT * FROM sessions WHERE token = ?", (token,))

    def delete_session(self, token: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def list_locations(self) -> list[LocationRecord]:
        return [self._location_from_row(row) for row in self._fetchall("SELECT * FROM locations ORDER BY name")]

    def upsert_location(self, name: str, location_id: str | None = None) -> LocationRecord:
        existing_by_name = self._fetchone("SELECT * FROM locations WHERE name = ?", (name,))
        target_id = location_id or (existing_by_name["location_id"] if existing_by_name else uuid.uuid4().hex)
        existing = self._fetchone("SELECT * FROM locations WHERE location_id = ?", (target_id,))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO locations (location_id, name, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(location_id) DO UPDATE SET
                    name = excluded.name
                """,
                (target_id, name, existing["created_at"] if existing else _iso_now()),
            )
        row = self._fetchone("SELECT * FROM locations WHERE location_id = ?", (target_id,))
        assert row is not None
        return self._location_from_row(row)

    def list_floors(self, location_id: str | None = None) -> list[FloorRecord]:
        if location_id:
            rows = self._fetchall(
                "SELECT * FROM floors WHERE location_id = ? ORDER BY name", (location_id,)
            )
        else:
            rows = self._fetchall("SELECT * FROM floors ORDER BY name")
        return [self._floor_from_row(row) for row in rows]

    def get_floor(self, floor_id: str) -> FloorRecord | None:
        row = self._fetchone("SELECT * FROM floors WHERE floor_id = ?", (floor_id,))
        return self._floor_from_row(row) if row else None

    def upsert_floor(self, location_id: str, name: str, floor_id: str | None = None) -> FloorRecord:
        existing_by_name = self._fetchone(
            "SELECT * FROM floors WHERE location_id = ? AND name = ?",
            (location_id, name),
        )
        target_id = floor_id or (existing_by_name["floor_id"] if existing_by_name else uuid.uuid4().hex)
        existing = self._fetchone("SELECT * FROM floors WHERE floor_id = ?", (target_id,))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO floors (floor_id, location_id, name, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(floor_id) DO UPDATE SET
                    location_id = excluded.location_id,
                    name = excluded.name
                """,
                (target_id, location_id, name, existing["created_at"] if existing else _iso_now()),
            )
        row = self._fetchone("SELECT * FROM floors WHERE floor_id = ?", (target_id,))
        assert row is not None
        return self._floor_from_row(row)

    def list_desks(self, location_id: str | None = None, floor_id: str | None = None) -> list[DeskRecord]:
        query = """
            SELECT d.* FROM desks d
            JOIN floors f ON f.floor_id = d.floor_id
            JOIN locations l ON l.location_id = f.location_id
            WHERE 1 = 1
        """
        params: list[Any] = []
        if floor_id:
            query += " AND d.floor_id = ?"
            params.append(floor_id)
        if location_id:
            query += " AND l.location_id = ?"
            params.append(location_id)
        query += " ORDER BY d.label"
        return [self._desk_from_row(row) for row in self._fetchall(query, params)]

    def get_desk(self, desk_id: str) -> DeskRecord | None:
        row = self._fetchone("SELECT * FROM desks WHERE desk_id = ?", (desk_id,))
        return self._desk_from_row(row) if row else None

    def upsert_desk(
        self,
        floor_id: str,
        label: str,
        enabled: bool,
        owner_user_id: str | None,
        is_blocked: bool,
        x: int,
        y: int,
        zone: str | None,
        equipment: dict[str, Any],
        desk_id: str | None = None,
    ) -> DeskRecord:
        target_id = desk_id or uuid.uuid4().hex
        existing = self._fetchone("SELECT * FROM desks WHERE desk_id = ?", (target_id,))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO desks (
                    desk_id, floor_id, label, enabled, owner_user_id, is_blocked, x, y, zone, equipment_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(desk_id) DO UPDATE SET
                    floor_id = excluded.floor_id,
                    label = excluded.label,
                    enabled = excluded.enabled,
                    owner_user_id = excluded.owner_user_id,
                    is_blocked = excluded.is_blocked,
                    x = excluded.x,
                    y = excluded.y,
                    zone = excluded.zone,
                    equipment_json = excluded.equipment_json
                """,
                (
                    target_id,
                    floor_id,
                    label,
                    int(enabled),
                    owner_user_id,
                    int(is_blocked),
                    x,
                    y,
                    zone,
                    json.dumps(equipment),
                    existing["created_at"] if existing else _iso_now(),
                ),
            )
        return self.get_desk(target_id)  # type: ignore[return-value]

    def list_manual_releases(self, desk_id: str | None = None, value_date: date | None = None) -> list[sqlite3.Row]:
        query = "SELECT * FROM manual_releases WHERE 1 = 1"
        params: list[Any] = []
        if desk_id:
            query += " AND desk_id = ?"
            params.append(desk_id)
        if value_date:
            query += " AND date = ?"
            params.append(value_date.isoformat())
        return self._fetchall(query, params)

    def upsert_manual_release(
        self,
        owner_user_id: str,
        desk_id: str,
        value_date: date,
        slot: str,
        released: bool,
    ) -> None:
        existing = self._fetchone(
            "SELECT * FROM manual_releases WHERE desk_id = ? AND date = ? AND slot = ?",
            (desk_id, value_date.isoformat(), slot),
        )
        manual_release_id = existing["manual_release_id"] if existing else uuid.uuid4().hex
        created_at = existing["created_at"] if existing else _iso_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO manual_releases (manual_release_id, owner_user_id, desk_id, date, slot, released, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(desk_id, date, slot) DO UPDATE SET
                    owner_user_id = excluded.owner_user_id,
                    released = excluded.released
                """,
                (manual_release_id, owner_user_id, desk_id, value_date.isoformat(), slot, int(released), created_at),
            )

    def list_recurring_releases(self, desk_id: str | None = None, owner_user_id: str | None = None) -> list[RecurringReleaseRecord]:
        query = "SELECT * FROM recurring_releases WHERE 1 = 1"
        params: list[Any] = []
        if desk_id:
            query += " AND desk_id = ?"
            params.append(desk_id)
        if owner_user_id:
            query += " AND owner_user_id = ?"
            params.append(owner_user_id)
        rows = self._fetchall(query, params)
        return [
            RecurringReleaseRecord(
                recurring_release_id=row["recurring_release_id"],
                owner_user_id=row["owner_user_id"],
                desk_id=row["desk_id"],
                weekday=int(row["weekday"]),
                slot=row["slot"],
                is_active=self._bool(row["is_active"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def upsert_recurring_release(
        self,
        owner_user_id: str,
        desk_id: str,
        weekday: int,
        slot: str,
        is_active: bool,
        recurring_release_id: str | None = None,
    ) -> RecurringReleaseRecord:
        existing = self._fetchone(
            "SELECT * FROM recurring_releases WHERE recurring_release_id = ?",
            (recurring_release_id,),
        ) if recurring_release_id else None
        target_id = recurring_release_id or uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO recurring_releases (
                    recurring_release_id, owner_user_id, desk_id, weekday, slot, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(recurring_release_id) DO UPDATE SET
                    owner_user_id = excluded.owner_user_id,
                    desk_id = excluded.desk_id,
                    weekday = excluded.weekday,
                    slot = excluded.slot,
                    is_active = excluded.is_active
                """,
                (
                    target_id,
                    owner_user_id,
                    desk_id,
                    weekday,
                    slot,
                    int(is_active),
                    existing["created_at"] if existing else _iso_now(),
                ),
            )
        return self.list_recurring_releases()[0] if False else next(
            item for item in self.list_recurring_releases(desk_id=desk_id, owner_user_id=owner_user_id) if item.recurring_release_id == target_id
        )

    def list_preferred_partners(
        self,
        desk_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> list[PreferredPartnerRecord]:
        query = "SELECT * FROM preferred_partners WHERE 1 = 1"
        params: list[Any] = []
        if desk_id:
            query += " AND desk_id = ?"
            params.append(desk_id)
        if owner_user_id:
            query += " AND owner_user_id = ?"
            params.append(owner_user_id)
        rows = self._fetchall(query, params)
        return [
            PreferredPartnerRecord(
                preferred_partner_id=row["preferred_partner_id"],
                desk_id=row["desk_id"],
                owner_user_id=row["owner_user_id"],
                partner_user_id=row["partner_user_id"],
                auto_approve=self._bool(row["auto_approve"]),
                priority=self._bool(row["priority"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def create_preferred_partner(
        self,
        desk_id: str,
        owner_user_id: str,
        partner_user_id: str,
        auto_approve: bool,
        priority: bool,
    ) -> PreferredPartnerRecord:
        existing = self._fetchone(
            "SELECT * FROM preferred_partners WHERE desk_id = ? AND partner_user_id = ?",
            (desk_id, partner_user_id),
        )
        preferred_partner_id = existing["preferred_partner_id"] if existing else uuid.uuid4().hex
        created_at = existing["created_at"] if existing else _iso_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO preferred_partners (
                    preferred_partner_id, desk_id, owner_user_id, partner_user_id, auto_approve, priority, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(desk_id, partner_user_id) DO UPDATE SET
                    owner_user_id = excluded.owner_user_id,
                    auto_approve = excluded.auto_approve,
                    priority = excluded.priority
                """,
                (
                    preferred_partner_id,
                    desk_id,
                    owner_user_id,
                    partner_user_id,
                    int(auto_approve),
                    int(priority),
                    created_at,
                ),
            )
        return next(
            item
            for item in self.list_preferred_partners(desk_id=desk_id, owner_user_id=owner_user_id)
            if item.preferred_partner_id == preferred_partner_id
        )

    def delete_preferred_partner(self, preferred_partner_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM preferred_partners WHERE preferred_partner_id = ?",
                (preferred_partner_id,),
            )
            return cur.rowcount > 0

    def create_booking_request(
        self,
        requested_by: str,
        desk_id: str,
        value_date: date,
        request_slot: str,
        status: str,
        approval_type: str,
        acted_by: str | None = None,
    ) -> BookingRecord:
        booking_id = uuid.uuid4().hex
        created_at = _utcnow()
        acted_at = created_at if status != "pending" else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO booking_requests (
                    booking_id, requested_by, desk_id, date, slot, status, approval_type, created_at, acted_at, acted_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    booking_id,
                    requested_by,
                    desk_id,
                    value_date.isoformat(),
                    request_slot,
                    status,
                    approval_type,
                    created_at.isoformat(),
                    acted_at.isoformat() if acted_at else None,
                    acted_by,
                ),
            )
            from app.domain import expand_request_slot

            for slot in expand_request_slot(request_slot):
                conn.execute(
                    """
                    INSERT INTO booking_slots (booking_slot_id, booking_id, desk_id, date, slot)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, booking_id, desk_id, value_date.isoformat(), slot),
                )
        return self.get_booking_request(booking_id)  # type: ignore[return-value]

    def get_booking_request(self, booking_id: str) -> BookingRecord | None:
        row = self._fetchone("SELECT * FROM booking_requests WHERE booking_id = ?", (booking_id,))
        if not row:
            return None
        return BookingRecord(
            booking_id=row["booking_id"],
            requested_by=row["requested_by"],
            desk_id=row["desk_id"],
            date=date.fromisoformat(row["date"]),
            slot=row["slot"],
            status=row["status"],
            approval_type=row["approval_type"],
            created_at=datetime.fromisoformat(row["created_at"]),
            acted_at=datetime.fromisoformat(row["acted_at"]) if row["acted_at"] else None,
            acted_by=row["acted_by"],
        )

    def list_booking_requests(
        self,
        requested_by: str | None = None,
        status: str | None = None,
    ) -> list[BookingRecord]:
        query = "SELECT * FROM booking_requests WHERE 1 = 1"
        params: list[Any] = []
        if requested_by:
            query += " AND requested_by = ?"
            params.append(requested_by)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY date, created_at"
        rows = self._fetchall(query, params)
        return [self.get_booking_request(row["booking_id"]) for row in rows if self.get_booking_request(row["booking_id"])]  # type: ignore[list-item]

    def update_booking_status(self, booking_id: str, status: str, acted_by: str, approval_type: str) -> BookingRecord | None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE booking_requests
                SET status = ?, acted_by = ?, approval_type = ?, acted_at = ?
                WHERE booking_id = ?
                """,
                (status, acted_by, approval_type, _iso_now(), booking_id),
            )
        return self.get_booking_request(booking_id)

    def approved_slots_for_date(self, value_date: date, floor_id: str | None = None) -> list[sqlite3.Row]:
        query = """
            SELECT bs.*, br.requested_by
            FROM booking_slots bs
            JOIN booking_requests br ON br.booking_id = bs.booking_id
            JOIN desks d ON d.desk_id = bs.desk_id
            WHERE br.status = ? AND bs.date = ?
        """
        params: list[Any] = [BOOKING_APPROVED, value_date.isoformat()]
        if floor_id:
            query += " AND d.floor_id = ?"
            params.append(floor_id)
        return self._fetchall(query, params)

    def pending_requests_for_date(self, value_date: date, floor_id: str | None = None) -> list[sqlite3.Row]:
        query = """
            SELECT br.* FROM booking_requests br
            JOIN desks d ON d.desk_id = br.desk_id
            WHERE br.status = 'pending' AND br.date = ?
        """
        params: list[Any] = [value_date.isoformat()]
        if floor_id:
            query += " AND d.floor_id = ?"
            params.append(floor_id)
        return self._fetchall(query, params)

    def list_notifications(self, user_id: str) -> list[NotificationRecord]:
        rows = self._fetchall(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [
            NotificationRecord(
                notification_id=row["notification_id"],
                user_id=row["user_id"],
                type=row["type"],
                message=row["message"],
                read_at=datetime.fromisoformat(row["read_at"]) if row["read_at"] else None,
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def create_notification(self, user_id: str, type_: str, message: str) -> NotificationRecord:
        notification_id = uuid.uuid4().hex
        created_at = _iso_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO notifications (notification_id, user_id, type, message, read_at, created_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (notification_id, user_id, type_, message, created_at),
            )
        return self.list_notifications(user_id)[0]

    def mark_notification_read(self, notification_id: str, user_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE notifications SET read_at = ? WHERE notification_id = ? AND user_id = ?",
                (_iso_now(), notification_id, user_id),
            )
            return cur.rowcount > 0

    def create_audit_log(self, actor_user_id: str, action: str, entity_type: str, entity_id: str, details: str) -> AuditEntry:
        audit_id = uuid.uuid4().hex
        timestamp = _iso_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (audit_id, timestamp, actor_user_id, action, entity_type, entity_id, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (audit_id, timestamp, actor_user_id, action, entity_type, entity_id, details),
            )
        return AuditEntry(
            audit_id=audit_id,
            timestamp=datetime.fromisoformat(timestamp),
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )

    def list_audit_log(self, limit: int = 200) -> list[AuditEntry]:
        rows = self._fetchall(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [
            AuditEntry(
                audit_id=row["audit_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                actor_user_id=row["actor_user_id"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                details=row["details"],
            )
            for row in rows
        ]

    def stats(self) -> dict[str, int]:
        with self.connect() as conn:
            total_bookings = conn.execute("SELECT COUNT(*) AS c FROM booking_requests").fetchone()["c"]
            active_users = conn.execute("SELECT COUNT(*) AS c FROM users WHERE enabled = 1").fetchone()["c"]
            enabled_desks = conn.execute("SELECT COUNT(*) AS c FROM desks WHERE enabled = 1").fetchone()["c"]
            pending_bookings = conn.execute(
                "SELECT COUNT(*) AS c FROM booking_requests WHERE status = 'pending'"
            ).fetchone()["c"]
            locations = conn.execute("SELECT COUNT(*) AS c FROM locations").fetchone()["c"]
        return {
            "total_bookings": int(total_bookings),
            "active_users": int(active_users),
            "enabled_desks": int(enabled_desks),
            "pending_bookings": int(pending_bookings),
            "locations": int(locations),
        }

    def ensure_seed_admin(self) -> UserRecord:
        existing = self.get_user_by_email("admin@company.com")
        if existing:
            return existing
        user = self.upsert_user(
            name="Admin Ops",
            email="admin@company.com",
            enabled=True,
            is_admin=True,
            location="Haifa",
            department="Facilities",
        )
        self.upsert_whitelist(user.email, user.user_id, "system")
        self.create_audit_log("system", "seed_admin", "user", user.user_id, "Created default admin account")
        return user
