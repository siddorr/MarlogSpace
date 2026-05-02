from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from fastapi import HTTPException, status

from app.constants import (
    BOOKING_APPROVED,
    BOOKING_CANCELLED,
    BOOKING_PENDING,
    BOOKING_REJECTED,
    REQUEST_SLOTS,
    SLOT_FULL,
    SLOTS,
    STATE_BLOCKED,
    STATE_BOOKED,
    STATE_FREE,
    STATE_OWNED,
    STATE_PENDING,
)
from app.domain import expand_request_slot, in_booking_window, is_workday
from app.models import (
    AdminDeskUpsert,
    AdminFloorUpsert,
    AdminLocationUpsert,
    AdminUserUpsert,
    AuthToken,
    BookingCreate,
    BookingRecord,
    DeskAvailability,
    DeskRecord,
    FloorRecord,
    LocationRecord,
    ManualReleaseUpsert,
    PreferredPartnerRecord,
    PreferredPartnerUpsert,
    RecurringReleaseRecord,
    RecurringReleaseUpsert,
    StatsResponse,
    UserRecord,
    WhitelistEntry,
    WhitelistUpsert,
)
from app.repository import SQLiteRepository
from app.security import AuthManager


@dataclass
class MarlogService:
    repo: SQLiteRepository
    auth: AuthManager

    def request_otp(self, email: str) -> dict[str, str]:
        self.auth.issue_otp(email)
        return {"status": "ok"}

    def verify_otp(self, email: str, code: str) -> AuthToken:
        token = self.auth.verify_otp(email, code)
        if not token:
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")
        user = self.get_user_from_token(token)
        assert user is not None
        self.repo.create_audit_log(user.user_id, "login", "session", token, "User authenticated with OTP")
        return AuthToken(token=token, user=user)

    def logout(self, token: str) -> None:
        user = self.get_user_from_token(token)
        self.auth.logout(token)
        if user:
            self.repo.create_audit_log(user.user_id, "logout", "session", token, "User logged out")

    def get_user_from_token(self, token: str) -> UserRecord | None:
        user_id = self.auth.get_session_user_id(token)
        if not user_id:
            return None
        user = self.repo.get_user(user_id)
        if not user or not user.enabled:
            return None
        return user

    def list_users(self, actor: UserRecord) -> list[UserRecord]:
        self._require_admin(actor)
        return self.repo.list_users(include_disabled=True)

    def list_locations(self) -> list[LocationRecord]:
        return self.repo.list_locations()

    def list_floors(self, location_id: str | None = None) -> list[FloorRecord]:
        return self.repo.list_floors(location_id)

    def list_desks(
        self,
        actor: UserRecord,
        value_date: date,
        location_id: str | None = None,
        floor_id: str | None = None,
    ) -> list[DeskAvailability]:
        desks = self.repo.list_desks(location_id=location_id, floor_id=floor_id)
        approved = self.repo.approved_slots_for_date(value_date, floor_id=floor_id)
        pending = self.repo.pending_requests_for_date(value_date, floor_id=floor_id)
        manual_releases = self.repo.list_manual_releases(value_date=value_date)
        recurring_releases = self.repo.list_recurring_releases()

        approved_by_desk_slot = {(row["desk_id"], row["slot"]): row for row in approved}
        pending_count: dict[str, int] = {}
        for row in pending:
            pending_count[str(row["desk_id"])] = pending_count.get(str(row["desk_id"]), 0) + 1

        release_keys = {
            (str(row["desk_id"]), str(row["slot"])): bool(int(row["released"]))
            for row in manual_releases
        }
        recurring_keys = {
            (item.desk_id, item.slot, item.weekday)
            for item in recurring_releases
            if item.is_active
        }

        result: list[DeskAvailability] = []
        for desk in desks:
            state = STATE_FREE
            booking_user_id = None
            booking_request_id = None
            if desk.is_blocked:
                state = STATE_BLOCKED
            else:
                booked = None
                for slot in SLOTS:
                    match = approved_by_desk_slot.get((desk.desk_id, slot))
                    if match:
                        booked = match
                        break
                if booked:
                    state = STATE_BOOKED
                    booking_user_id = str(booked["requested_by"])
                    booking_request_id = str(booked["booking_id"])
                elif desk.owner_user_id and not self._is_released(desk, value_date, release_keys, recurring_keys):
                    state = STATE_OWNED
                    booking_user_id = desk.owner_user_id
                elif pending_count.get(desk.desk_id):
                    state = STATE_PENDING
            result.append(
                DeskAvailability(
                    desk_id=desk.desk_id,
                    floor_id=desk.floor_id,
                    label=desk.label,
                    owner_user_id=desk.owner_user_id,
                    state=state,
                    x=desk.x,
                    y=desk.y,
                    zone=desk.zone,
                    equipment=desk.equipment,
                    booking_user_id=booking_user_id,
                    booking_request_id=booking_request_id,
                    pending_request_count=pending_count.get(desk.desk_id, 0),
                )
            )
        return result

    def list_bookings(self, actor: UserRecord) -> list[BookingRecord]:
        if actor.is_admin:
            return self.repo.list_booking_requests()
        return self.repo.list_booking_requests(requested_by=actor.user_id)

    def create_booking(self, actor: UserRecord, payload: BookingCreate) -> BookingRecord:
        desk = self._get_enabled_desk_or_404(payload.desk_id)
        slots = expand_request_slot(payload.slot)
        self._validate_slots(payload.date, slots)
        self._ensure_requester_free(actor.user_id, payload.date, slots)
        self._ensure_desk_available_for_slots(desk, payload.date, slots, requester_user_id=actor.user_id)

        if desk.owner_user_id and desk.owner_user_id != actor.user_id:
            if not self._is_available_named_desk(desk, payload.date, slots):
                raise HTTPException(status_code=409, detail="Named desk is not released")
            partner = next(
                (item for item in self.repo.list_preferred_partners(desk_id=desk.desk_id) if item.partner_user_id == actor.user_id),
                None,
            )
            if partner and partner.auto_approve:
                status_value = BOOKING_APPROVED
                approval_type = "preferred_partner_auto_approve"
            else:
                status_value = BOOKING_PENDING
                approval_type = "owner_review_pending"
        else:
            status_value = BOOKING_APPROVED
            approval_type = "open_desk_auto_approve"

        booking = self.repo.create_booking_request(
            requested_by=actor.user_id,
            desk_id=desk.desk_id,
            value_date=payload.date,
            request_slot=payload.slot,
            status=status_value,
            approval_type=approval_type,
            acted_by=actor.user_id if status_value == BOOKING_APPROVED else None,
        )
        self.repo.create_audit_log(
            actor.user_id,
            "booking_created",
            "booking",
            booking.booking_id,
            f"{payload.slot} booking for {desk.label} on {payload.date.isoformat()}",
        )
        if desk.owner_user_id and desk.owner_user_id != actor.user_id:
            self.repo.create_notification(
                desk.owner_user_id,
                "booking_request",
                f"{actor.name} requested {desk.label} on {payload.date.isoformat()} ({payload.slot}).",
            )
        if status_value == BOOKING_APPROVED:
            self.repo.create_notification(
                actor.user_id,
                "booking_approved",
                f"Booking approved for {desk.label} on {payload.date.isoformat()} ({payload.slot}).",
            )
        return booking

    def approve_booking(self, actor: UserRecord, booking_id: str) -> BookingRecord:
        booking = self._get_booking_or_404(booking_id)
        desk = self._get_enabled_desk_or_404(booking.desk_id)
        if not actor.is_admin and desk.owner_user_id != actor.user_id:
            raise HTTPException(status_code=403, detail="Only the desk owner or admin can approve")
        if booking.status != BOOKING_PENDING:
            raise HTTPException(status_code=400, detail="Only pending bookings can be approved")
        slots = expand_request_slot(booking.slot)
        self._ensure_requester_free(booking.requested_by, booking.date, slots, exclude_booking_id=booking.booking_id)
        self._ensure_desk_available_for_slots(
            desk,
            booking.date,
            slots,
            exclude_booking_id=booking.booking_id,
            requester_user_id=booking.requested_by,
        )
        updated = self.repo.update_booking_status(booking.booking_id, BOOKING_APPROVED, actor.user_id, "owner_approved")
        assert updated is not None
        requester = self.repo.get_user(booking.requested_by)
        if requester:
            self.repo.create_notification(
                requester.user_id,
                "booking_approved",
                f"Your booking for {desk.label} on {booking.date.isoformat()} was approved.",
            )
        self.repo.create_audit_log(actor.user_id, "booking_approved", "booking", booking.booking_id, "Booking approved")
        return updated

    def reject_booking(self, actor: UserRecord, booking_id: str) -> BookingRecord:
        booking = self._get_booking_or_404(booking_id)
        desk = self._get_enabled_desk_or_404(booking.desk_id)
        if not actor.is_admin and desk.owner_user_id != actor.user_id:
            raise HTTPException(status_code=403, detail="Only the desk owner or admin can reject")
        if booking.status != BOOKING_PENDING:
            raise HTTPException(status_code=400, detail="Only pending bookings can be rejected")
        updated = self.repo.update_booking_status(booking.booking_id, BOOKING_REJECTED, actor.user_id, "owner_rejected")
        assert updated is not None
        requester = self.repo.get_user(booking.requested_by)
        if requester:
            self.repo.create_notification(
                requester.user_id,
                "booking_rejected",
                f"Your booking for {desk.label} on {booking.date.isoformat()} was rejected.",
            )
        self.repo.create_audit_log(actor.user_id, "booking_rejected", "booking", booking.booking_id, "Booking rejected")
        return updated

    def cancel_booking(self, actor: UserRecord, booking_id: str) -> BookingRecord:
        booking = self._get_booking_or_404(booking_id)
        desk = self._get_enabled_desk_or_404(booking.desk_id)
        if booking.requested_by != actor.user_id and not actor.is_admin and desk.owner_user_id != actor.user_id:
            raise HTTPException(status_code=403, detail="Cannot cancel this booking")
        updated = self.repo.update_booking_status(booking.booking_id, BOOKING_CANCELLED, actor.user_id, "cancelled")
        assert updated is not None
        self.repo.create_audit_log(actor.user_id, "booking_cancelled", "booking", booking.booking_id, "Booking cancelled")
        if booking.requested_by != actor.user_id:
            requester = self.repo.get_user(booking.requested_by)
            if requester:
                self.repo.create_notification(
                    requester.user_id,
                    "booking_cancelled",
                    f"Your booking for {desk.label} on {booking.date.isoformat()} was cancelled.",
                )
        return updated

    def upsert_manual_release(self, actor: UserRecord, payload: ManualReleaseUpsert) -> dict[str, str]:
        desk = self._get_enabled_desk_or_404(payload.desk_id)
        if desk.owner_user_id != actor.user_id and not actor.is_admin:
            raise HTTPException(status_code=403, detail="Only the desk owner or admin can release it")
        for slot in expand_request_slot(payload.slot):
            self._validate_slots(payload.date, [slot])
            self.repo.upsert_manual_release(actor.user_id, desk.desk_id, payload.date, slot, payload.released)
        self.repo.create_audit_log(actor.user_id, "manual_release_upserted", "desk", desk.desk_id, "Manual release updated")
        return {"status": "ok"}

    def upsert_recurring_release(self, actor: UserRecord, payload: RecurringReleaseUpsert) -> RecurringReleaseRecord:
        desk = self._get_enabled_desk_or_404(payload.desk_id)
        if desk.owner_user_id != actor.user_id and not actor.is_admin:
            raise HTTPException(status_code=403, detail="Only the desk owner or admin can update recurring release")
        last: RecurringReleaseRecord | None = None
        for slot in expand_request_slot(payload.slot):
            last = self.repo.upsert_recurring_release(
                owner_user_id=desk.owner_user_id or actor.user_id,
                desk_id=desk.desk_id,
                weekday=payload.weekday,
                slot=slot,
                is_active=payload.is_active,
                recurring_release_id=payload.recurring_release_id,
            )
        assert last is not None
        self.repo.create_audit_log(actor.user_id, "recurring_release_upserted", "desk", desk.desk_id, "Recurring release updated")
        return last

    def list_recurring_releases(self, actor: UserRecord) -> list[RecurringReleaseRecord]:
        return self.repo.list_recurring_releases(owner_user_id=None if actor.is_admin else actor.user_id)

    def create_preferred_partner(self, actor: UserRecord, payload: PreferredPartnerUpsert) -> PreferredPartnerRecord:
        desk = self._get_enabled_desk_or_404(payload.desk_id)
        if desk.owner_user_id != actor.user_id and not actor.is_admin:
            raise HTTPException(status_code=403, detail="Only the desk owner or admin can manage partners")
        partner = self.repo.get_user(payload.partner_user_id)
        if not partner:
            raise HTTPException(status_code=404, detail="Partner user not found")
        created = self.repo.create_preferred_partner(
            desk_id=desk.desk_id,
            owner_user_id=desk.owner_user_id or actor.user_id,
            partner_user_id=partner.user_id,
            auto_approve=payload.auto_approve,
            priority=payload.priority,
        )
        self.repo.create_audit_log(actor.user_id, "preferred_partner_upserted", "desk", desk.desk_id, "Preferred partner updated")
        return created

    def list_preferred_partners(self, actor: UserRecord) -> list[PreferredPartnerRecord]:
        return self.repo.list_preferred_partners(owner_user_id=None if actor.is_admin else actor.user_id)

    def delete_preferred_partner(self, actor: UserRecord, preferred_partner_id: str) -> dict[str, str]:
        partner = next(
            (item for item in self.repo.list_preferred_partners() if item.preferred_partner_id == preferred_partner_id),
            None,
        )
        if not partner:
            raise HTTPException(status_code=404, detail="Preferred partner not found")
        if partner.owner_user_id != actor.user_id and not actor.is_admin:
            raise HTTPException(status_code=403, detail="Cannot delete this preferred partner")
        self.repo.delete_preferred_partner(preferred_partner_id)
        self.repo.create_audit_log(actor.user_id, "preferred_partner_deleted", "preferred_partner", preferred_partner_id, "Preferred partner deleted")
        return {"status": "ok"}

    def list_notifications(self, actor: UserRecord):
        return self.repo.list_notifications(actor.user_id)

    def mark_notification_read(self, actor: UserRecord, notification_id: str) -> dict[str, str]:
        if not self.repo.mark_notification_read(notification_id, actor.user_id):
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"status": "ok"}

    def list_audit_log(self, actor: UserRecord):
        self._require_admin(actor)
        return self.repo.list_audit_log()

    def admin_upsert_user(self, actor: UserRecord, payload: AdminUserUpsert) -> UserRecord:
        self._require_admin(actor)
        user = self.repo.upsert_user(
            user_id=payload.user_id,
            name=payload.name,
            email=str(payload.email),
            enabled=payload.enabled,
            is_admin=payload.is_admin,
            location=payload.location,
            department=payload.department,
        )
        self.repo.create_audit_log(actor.user_id, "user_upserted", "user", user.user_id, "Admin updated user")
        return user

    def admin_upsert_whitelist(self, actor: UserRecord, payload: WhitelistUpsert) -> WhitelistEntry:
        self._require_admin(actor)
        entry = self.repo.upsert_whitelist(str(payload.email), payload.user_id, actor.user_id)
        self.repo.create_audit_log(actor.user_id, "whitelist_upserted", "whitelist", entry.whitelist_id, "Whitelist updated")
        return entry

    def admin_delete_whitelist(self, actor: UserRecord, whitelist_id: str) -> dict[str, str]:
        self._require_admin(actor)
        if not self.repo.delete_whitelist(whitelist_id):
            raise HTTPException(status_code=404, detail="Whitelist entry not found")
        self.repo.create_audit_log(actor.user_id, "whitelist_deleted", "whitelist", whitelist_id, "Whitelist deleted")
        return {"status": "ok"}

    def admin_upsert_location(self, actor: UserRecord, payload: AdminLocationUpsert) -> LocationRecord:
        self._require_admin(actor)
        location = self.repo.upsert_location(payload.name, payload.location_id)
        self.repo.create_audit_log(actor.user_id, "location_upserted", "location", location.location_id, "Location updated")
        return location

    def admin_upsert_floor(self, actor: UserRecord, payload: AdminFloorUpsert) -> FloorRecord:
        self._require_admin(actor)
        if not any(location.location_id == payload.location_id for location in self.repo.list_locations()):
            raise HTTPException(status_code=404, detail="Location not found")
        floor = self.repo.upsert_floor(payload.location_id, payload.name, payload.floor_id)
        self.repo.create_audit_log(actor.user_id, "floor_upserted", "floor", floor.floor_id, "Floor updated")
        return floor

    def admin_upsert_desk(self, actor: UserRecord, payload: AdminDeskUpsert) -> DeskRecord:
        self._require_admin(actor)
        if not self.repo.get_floor(payload.floor_id):
            raise HTTPException(status_code=404, detail="Floor not found")
        if payload.owner_user_id and not self.repo.get_user(payload.owner_user_id):
            raise HTTPException(status_code=404, detail="Owner not found")
        desk = self.repo.upsert_desk(
            desk_id=payload.desk_id,
            floor_id=payload.floor_id,
            label=payload.label,
            enabled=payload.enabled,
            owner_user_id=payload.owner_user_id,
            is_blocked=payload.is_blocked,
            x=payload.x,
            y=payload.y,
            zone=payload.zone,
            equipment=payload.equipment,
        )
        self.repo.create_audit_log(actor.user_id, "desk_upserted", "desk", desk.desk_id, "Desk updated")
        return desk

    def admin_stats(self, actor: UserRecord) -> StatsResponse:
        self._require_admin(actor)
        return StatsResponse(**self.repo.stats())

    def list_whitelist(self, actor: UserRecord) -> list[WhitelistEntry]:
        self._require_admin(actor)
        return self.repo.list_whitelist()

    def _get_booking_or_404(self, booking_id: str) -> BookingRecord:
        booking = self.repo.get_booking_request(booking_id)
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        return booking

    def _require_admin(self, actor: UserRecord) -> None:
        if not actor.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")

    def _get_enabled_desk_or_404(self, desk_id: str) -> DeskRecord:
        desk = self.repo.get_desk(desk_id)
        if not desk:
            raise HTTPException(status_code=404, detail="Desk not found")
        if not desk.enabled:
            raise HTTPException(status_code=400, detail="Desk disabled")
        return desk

    def _validate_slots(self, value_date: date, slots: list[str]) -> None:
        if not in_booking_window(value_date):
            raise HTTPException(status_code=400, detail="Date outside booking window")
        if not is_workday(value_date):
            raise HTTPException(status_code=400, detail="Only Sun-Thu reservations are allowed")
        for slot in slots:
            if slot not in SLOTS:
                raise HTTPException(status_code=400, detail="Unsupported slot")

    def _ensure_requester_free(
        self,
        user_id: str,
        value_date: date,
        slots: list[str],
        exclude_booking_id: str | None = None,
    ) -> None:
        for booking in self.repo.list_booking_requests(status=BOOKING_APPROVED):
            if booking.requested_by != user_id or booking.date != value_date:
                continue
            if exclude_booking_id and booking.booking_id == exclude_booking_id:
                continue
            existing_slots = set(expand_request_slot(booking.slot))
            if existing_slots.intersection(slots):
                raise HTTPException(status_code=409, detail="User already has a desk in this slot")

    def _ensure_desk_available_for_slots(
        self,
        desk: DeskRecord,
        value_date: date,
        slots: list[str],
        exclude_booking_id: str | None = None,
        requester_user_id: str | None = None,
    ) -> None:
        if desk.is_blocked:
            raise HTTPException(status_code=409, detail="Desk is blocked")
        for booking in self.repo.list_booking_requests(status=BOOKING_APPROVED):
            if booking.desk_id != desk.desk_id or booking.date != value_date:
                continue
            if exclude_booking_id and booking.booking_id == exclude_booking_id:
                continue
            existing_slots = set(expand_request_slot(booking.slot))
            if existing_slots.intersection(slots):
                raise HTTPException(status_code=409, detail="Desk already reserved")
        if desk.owner_user_id and desk.owner_user_id != requester_user_id and not self._is_available_named_desk(desk, value_date, slots):
            raise HTTPException(status_code=409, detail="Named desk is not released")

    def _is_available_named_desk(self, desk: DeskRecord, value_date: date, slots: list[str]) -> bool:
        if not desk.owner_user_id:
            return True
        releases = {
            (str(row["slot"]), bool(int(row["released"])))
            for row in self.repo.list_manual_releases(desk_id=desk.desk_id, value_date=value_date)
        }
        recurring = {
            (item.slot, item.weekday)
            for item in self.repo.list_recurring_releases(desk_id=desk.desk_id)
            if item.is_active
        }
        for slot in slots:
            if (slot, True) in releases:
                continue
            if (slot, value_date.weekday()) in recurring:
                continue
            return False
        return True

    def _is_released(
        self,
        desk: DeskRecord,
        value_date: date,
        manual_keys: dict[tuple[str, str], bool],
        recurring_keys: set[tuple[str, str, int]],
    ) -> bool:
        if not desk.owner_user_id:
            return True
        for slot in SLOTS:
            if manual_keys.get((desk.desk_id, slot)):
                return True
            if (desk.desk_id, slot, value_date.weekday()) in recurring_keys:
                return True
        return False
