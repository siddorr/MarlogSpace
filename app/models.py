from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


SlotType = Literal["AM", "PM"]
RequestSlotType = Literal["AM", "PM", "FULL"]


class UserRecord(BaseModel):
    user_id: str
    email: EmailStr
    enabled: bool = True
    is_admin: bool = False
    created_at: datetime


class DeskRecord(BaseModel):
    desk_id: str
    label: str
    enabled: bool = True
    owner_user_id: str | None = None


class ReservationRecord(BaseModel):
    reservation_id: str
    user_id: str
    desk_id: str
    date: DateType
    slot: SlotType
    created_at: datetime
    updated_at: datetime
    auto: bool = False


class AbsenceRecord(BaseModel):
    absence_id: str
    owner_user_id: str
    desk_id: str
    date: DateType
    slot: SlotType
    created_at: datetime


class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class AuthToken(BaseModel):
    token: str
    user: UserRecord


class ReservationCreate(BaseModel):
    desk_id: str
    date: DateType
    slot: RequestSlotType


class ReservationUpdate(BaseModel):
    desk_id: str | None = None
    date: DateType | None = None
    slot: RequestSlotType | None = None


class ReservationsQuery(BaseModel):
    start_date: DateType | None = None
    end_date: DateType | None = None


class AbsenceUpsert(BaseModel):
    desk_id: str
    date: DateType
    slot: RequestSlotType
    released: bool


class AdminUserUpsert(BaseModel):
    email: EmailStr
    enabled: bool = True
    is_admin: bool = False


class AdminDeskUpsert(BaseModel):
    desk_id: str | None = None
    label: str
    enabled: bool = True
    owner_user_id: str | None = None


class ForceCancelRequest(BaseModel):
    reservation_id: str


class StatsResponse(BaseModel):
    total_reservations: int
    active_users: int
    enabled_desks: int
