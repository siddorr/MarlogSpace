from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


SlotType = Literal["AM", "PM"]
RequestSlotType = Literal["AM", "PM", "FULL"]
BookingStatus = Literal["pending", "approved", "rejected", "cancelled", "expired"]


class UserRecord(BaseModel):
    user_id: str
    name: str = Field(min_length=1, max_length=64)
    email: EmailStr
    enabled: bool = True
    is_admin: bool = False
    location: str | None = None
    department: str | None = None
    created_at: datetime


class WhitelistEntry(BaseModel):
    whitelist_id: str
    email: EmailStr
    user_id: str | None = None
    added_by: str
    created_at: datetime


class LocationRecord(BaseModel):
    location_id: str
    name: str
    created_at: datetime


class FloorRecord(BaseModel):
    floor_id: str
    location_id: str
    name: str
    created_at: datetime


class DeskRecord(BaseModel):
    desk_id: str
    floor_id: str
    label: str
    enabled: bool = True
    owner_user_id: str | None = None
    is_blocked: bool = False
    x: int = 0
    y: int = 0
    zone: str | None = None
    equipment: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DeskAvailability(BaseModel):
    desk_id: str
    floor_id: str
    label: str
    owner_user_id: str | None = None
    state: str
    x: int = 0
    y: int = 0
    zone: str | None = None
    equipment: dict[str, Any] = Field(default_factory=dict)
    booking_user_id: str | None = None
    booking_request_id: str | None = None
    pending_request_count: int = 0


class AuthRequest(BaseModel):
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class AuthToken(BaseModel):
    token: str
    user: UserRecord


class BookingCreate(BaseModel):
    desk_id: str
    date: DateType
    slot: RequestSlotType = "FULL"


class BookingRecord(BaseModel):
    booking_id: str
    requested_by: str
    desk_id: str
    date: DateType
    slot: RequestSlotType
    status: BookingStatus
    approval_type: str
    created_at: datetime
    acted_at: datetime | None = None
    acted_by: str | None = None


class ManualReleaseUpsert(BaseModel):
    desk_id: str
    date: DateType
    slot: RequestSlotType = "FULL"
    released: bool = True


class RecurringReleaseUpsert(BaseModel):
    recurring_release_id: str | None = None
    desk_id: str
    weekday: int = Field(ge=0, le=6)
    slot: RequestSlotType = "FULL"
    is_active: bool = True


class RecurringReleaseRecord(BaseModel):
    recurring_release_id: str
    owner_user_id: str
    desk_id: str
    weekday: int
    slot: RequestSlotType
    is_active: bool
    created_at: datetime


class PreferredPartnerUpsert(BaseModel):
    desk_id: str
    partner_user_id: str
    auto_approve: bool = True
    priority: bool = True


class PreferredPartnerRecord(BaseModel):
    preferred_partner_id: str
    desk_id: str
    owner_user_id: str
    partner_user_id: str
    auto_approve: bool
    priority: bool
    created_at: datetime


class NotificationRecord(BaseModel):
    notification_id: str
    user_id: str
    type: str
    message: str
    read_at: datetime | None = None
    created_at: datetime


class AuditEntry(BaseModel):
    audit_id: str
    timestamp: datetime
    actor_user_id: str
    action: str
    entity_type: str
    entity_id: str
    details: str


class AdminUserUpsert(BaseModel):
    user_id: str | None = None
    name: str = Field(min_length=1, max_length=64)
    email: EmailStr
    enabled: bool = True
    is_admin: bool = False
    location: str | None = None
    department: str | None = None


class AdminLocationUpsert(BaseModel):
    location_id: str | None = None
    name: str = Field(min_length=1, max_length=64)


class AdminFloorUpsert(BaseModel):
    floor_id: str | None = None
    location_id: str
    name: str = Field(min_length=1, max_length=32)


class AdminDeskUpsert(BaseModel):
    desk_id: str | None = None
    floor_id: str
    label: str
    enabled: bool = True
    owner_user_id: str | None = None
    is_blocked: bool = False
    x: int = 0
    y: int = 0
    zone: str | None = None
    equipment: dict[str, Any] = Field(default_factory=dict)


class DeskBlockRequest(BaseModel):
    is_blocked: bool


class WhitelistUpsert(BaseModel):
    email: EmailStr
    user_id: str | None = None


class StatsResponse(BaseModel):
    total_bookings: int
    active_users: int
    enabled_desks: int
    pending_bookings: int
    locations: int
