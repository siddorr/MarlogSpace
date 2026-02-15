from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status

from app.constants import SLOT_FULL
from app.domain import expand_request_slot, in_booking_window, is_workday
from app.models import AbsenceRecord, DeskRecord, ReservationRecord, UserRecord
from app.repository import ExcelRepository


@dataclass
class ReservationService:
    repo: ExcelRepository

    def list_users(self) -> list[UserRecord]:
        return [user for user in self.repo.list_users() if user.enabled]

    def list_desks(self) -> list[DeskRecord]:
        return [desk for desk in self.repo.list_desks() if desk.enabled]

    def ensure_user_for_name(self, name: str) -> UserRecord:
        user = self.repo.get_user_by_name(name)
        if user:
            if not user.enabled:
                raise HTTPException(status_code=403, detail="User disabled")
            return user
        return self.repo.upsert_user(name=name, enabled=True, is_admin=False)

    def get_user_or_404(self, user_id: str) -> UserRecord:
        user = self.repo.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not user.enabled:
            raise HTTPException(status_code=403, detail="User disabled")
        return user

    def list_effective_reservations(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ReservationRecord]:
        today = datetime.utcnow().date()
        start = start_date or today
        end = end_date or (today + timedelta(days=6))
        explicit_rows = self.repo.list_reservations(start, end)
        desks = [d for d in self.repo.list_desks() if d.enabled]
        absences = self.repo.list_absences()

        explicit_index = {
            (item.desk_id, item.date, item.slot): item for item in explicit_rows
        }
        absent_keys = {
            (a.owner_user_id, a.desk_id, a.date, a.slot)
            for a in absences
            if start <= a.date <= end
        }

        result = list(explicit_rows)
        cursor = start
        while cursor <= end:
            for desk in desks:
                if not desk.owner_user_id:
                    continue
                for slot in ["AM", "PM"]:
                    key = (desk.desk_id, cursor, slot)
                    if key in explicit_index:
                        continue
                    if (desk.owner_user_id, desk.desk_id, cursor, slot) in absent_keys:
                        continue
                    result.append(
                        ReservationRecord(
                            reservation_id=f"auto-{desk.desk_id}-{cursor.isoformat()}-{slot}",
                            user_id=desk.owner_user_id,
                            desk_id=desk.desk_id,
                            date=cursor,
                            slot=slot,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                            auto=True,
                        )
                    )
            cursor += timedelta(days=1)
        return result

    def create_reservation(
        self,
        user: UserRecord,
        desk_id: str,
        value_date: date,
        request_slot: str,
    ) -> list[ReservationRecord]:
        slots = expand_request_slot(request_slot)
        desk = self._get_enabled_desk_or_404(desk_id)
        for slot in slots:
            self._validate_date_slot(value_date, slot)
            self._validate_named_desk_release(desk, user.user_id, value_date, slot)
            self._validate_slot_conflicts(user.user_id, desk.desk_id, value_date, slot)

        created: list[ReservationRecord] = []
        for slot in slots:
            try:
                created.append(
                    self.repo.create_reservation(
                        user_id=user.user_id,
                        desk_id=desk_id,
                        value_date=value_date,
                        slot=slot,
                    )
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return created

    def update_reservation(
        self,
        user: UserRecord,
        reservation_id: str,
        desk_id: str | None,
        value_date: date | None,
        request_slot: str | None,
    ) -> ReservationRecord:
        existing = self.repo.get_reservation(reservation_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Reservation not found")
        if existing.user_id != user.user_id and not user.is_admin:
            raise HTTPException(status_code=403, detail="Cannot edit other users reservations")

        if request_slot == SLOT_FULL:
            raise HTTPException(
                status_code=400,
                detail="Patch supports AM or PM reservation records only",
            )

        target_desk_id = desk_id or existing.desk_id
        target_date = value_date or existing.date
        target_slot = request_slot or existing.slot
        desk = self._get_enabled_desk_or_404(target_desk_id)

        self._validate_date_slot(target_date, target_slot)
        self._validate_named_desk_release(desk, existing.user_id, target_date, target_slot)
        self._validate_slot_conflicts(
            existing.user_id,
            desk.desk_id,
            target_date,
            target_slot,
            exclude_reservation_id=existing.reservation_id,
        )

        try:
            updated = self.repo.update_reservation(
                reservation_id=existing.reservation_id,
                user_id=existing.user_id,
                desk_id=target_desk_id,
                value_date=target_date,
                slot=target_slot,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return updated

    def cancel_reservation(self, actor: UserRecord, reservation_id: str) -> None:
        reservation = self.repo.get_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        if reservation.user_id != actor.user_id and not actor.is_admin:
            raise HTTPException(status_code=403, detail="Cannot cancel other users reservations")
        deleted = self.repo.delete_reservation(reservation_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Reservation not found")

    def upsert_absence(
        self,
        owner: UserRecord,
        desk_id: str,
        value_date: date,
        request_slot: str,
        released: bool,
    ) -> list[AbsenceRecord]:
        desk = self._get_enabled_desk_or_404(desk_id)
        if desk.owner_user_id != owner.user_id:
            raise HTTPException(status_code=403, detail="Only the desk owner can release a named desk")
        slots = expand_request_slot(request_slot)
        for slot in slots:
            self._validate_date_slot(value_date, slot)
            self.repo.upsert_absence(
                owner_user_id=owner.user_id,
                desk_id=desk_id,
                value_date=value_date,
                slot=slot,
                released=released,
            )
        return [a for a in self.repo.list_absences() if a.owner_user_id == owner.user_id]

    def admin_upsert_user(self, actor: UserRecord, name: str, enabled: bool, is_admin: bool) -> UserRecord:
        self._require_admin(actor)
        return self.repo.upsert_user(name=name, enabled=enabled, is_admin=is_admin)

    def admin_upsert_desk(
        self,
        actor: UserRecord,
        label: str,
        enabled: bool,
        owner_user_id: str | None,
        desk_id: str | None = None,
    ) -> DeskRecord:
        self._require_admin(actor)
        if owner_user_id and not self.repo.get_user(owner_user_id):
            raise HTTPException(status_code=404, detail="Desk owner user not found")
        return self.repo.upsert_desk(
            label=label,
            enabled=enabled,
            owner_user_id=owner_user_id,
            desk_id=desk_id,
        )

    def admin_force_cancel(self, actor: UserRecord, reservation_id: str) -> None:
        self._require_admin(actor)
        deleted = self.repo.delete_reservation(reservation_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Reservation not found")

    def admin_stats(self, actor: UserRecord) -> dict[str, int]:
        self._require_admin(actor)
        return self.repo.stats()

    def _require_admin(self, user: UserRecord) -> None:
        if not user.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")

    def _get_enabled_desk_or_404(self, desk_id: str) -> DeskRecord:
        desk = self.repo.get_desk(desk_id)
        if not desk:
            raise HTTPException(status_code=404, detail="Desk not found")
        if not desk.enabled:
            raise HTTPException(status_code=400, detail="Desk disabled")
        return desk

    def _validate_date_slot(self, value_date: date, slot: str) -> None:
        if not in_booking_window(value_date):
            raise HTTPException(status_code=400, detail="Date outside booking window")
        if not is_workday(value_date):
            raise HTTPException(status_code=400, detail="Only Sun-Thu reservations are allowed")
        if slot not in {"AM", "PM"}:
            raise HTTPException(status_code=400, detail="Unsupported slot")

    def _validate_named_desk_release(
        self,
        desk: DeskRecord,
        requester_user_id: str,
        value_date: date,
        slot: str,
    ) -> None:
        if not desk.owner_user_id:
            return
        if desk.owner_user_id == requester_user_id:
            return
        absences = self.repo.list_absences()
        released = any(
            item.owner_user_id == desk.owner_user_id
            and item.desk_id == desk.desk_id
            and item.date == value_date
            and item.slot == slot
            for item in absences
        )
        if not released:
            raise HTTPException(status_code=409, detail="Named desk is not released by owner")

    def _validate_slot_conflicts(
        self,
        user_id: str,
        desk_id: str,
        value_date: date,
        slot: str,
        exclude_reservation_id: str | None = None,
    ) -> None:
        effective = self.list_effective_reservations(start_date=value_date, end_date=value_date)
        for item in effective:
            if item.reservation_id == exclude_reservation_id:
                continue
            if item.date != value_date or item.slot != slot:
                continue
            if item.desk_id == desk_id:
                raise HTTPException(status_code=409, detail="Desk already reserved")
            if item.user_id == user_id:
                raise HTTPException(status_code=409, detail="User already has a desk in this slot")
