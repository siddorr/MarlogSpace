from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.deps import auth, repo, require_user, service
from app.models import (
    AdminDeskUpsert,
    AdminFloorUpsert,
    AdminLocationUpsert,
    AdminUserUpsert,
    AuthRequest,
    AuthToken,
    BookingCreate,
    BookingRecord,
    DeskAvailability,
    DeskRecord,
    FloorRecord,
    LocationRecord,
    ManualReleaseUpsert,
    OTPVerifyRequest,
    PreferredPartnerRecord,
    PreferredPartnerUpsert,
    RecurringReleaseRecord,
    RecurringReleaseUpsert,
    StatsResponse,
    UserRecord,
    WhitelistEntry,
    WhitelistUpsert,
)


app = FastAPI(title="MarlogSpace API", version="0.2.0")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def on_startup() -> None:
    repo.init_storage()
    repo.ensure_seed_admin()


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/app")


@app.get("/app")
def app_shell() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/request-otp")
def request_otp(payload: AuthRequest) -> dict[str, str]:
    return service.request_otp(str(payload.email))


@app.post("/api/auth/verify-otp", response_model=AuthToken)
def verify_otp(payload: OTPVerifyRequest) -> AuthToken:
    return service.verify_otp(str(payload.email), payload.code)


@app.get("/api/auth/session", response_model=UserRecord)
def auth_session(user: UserRecord = Depends(require_user)) -> UserRecord:
    return user


@app.post("/api/auth/logout")
def logout(
    user: UserRecord = Depends(require_user),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, str]:
    _ = user
    token = (authorization or "").split(" ", 1)[1].strip()
    service.logout(token)
    return {"status": "ok"}


@app.get("/api/me", response_model=UserRecord)
def me(user: UserRecord = Depends(require_user)) -> UserRecord:
    return user


@app.get("/api/locations", response_model=list[LocationRecord])
def list_locations(user: UserRecord = Depends(require_user)) -> list[LocationRecord]:
    _ = user
    return service.list_locations()


@app.get("/api/floors", response_model=list[FloorRecord])
def list_floors(
    location_id: str | None = Query(default=None),
    user: UserRecord = Depends(require_user),
) -> list[FloorRecord]:
    _ = user
    return service.list_floors(location_id)


@app.get("/api/desks", response_model=list[DeskAvailability])
def list_desks(
    date_value: date = Query(alias="date"),
    location_id: str | None = Query(default=None),
    floor_id: str | None = Query(default=None),
    user: UserRecord = Depends(require_user),
) -> list[DeskAvailability]:
    return service.list_desks(user, date_value, location_id, floor_id)


@app.get("/api/bookings", response_model=list[BookingRecord])
def list_bookings(user: UserRecord = Depends(require_user)) -> list[BookingRecord]:
    return service.list_bookings(user)


@app.post("/api/bookings", response_model=BookingRecord)
def create_booking(payload: BookingCreate, user: UserRecord = Depends(require_user)) -> BookingRecord:
    return service.create_booking(user, payload)


@app.post("/api/bookings/{booking_id}/approve", response_model=BookingRecord)
def approve_booking(booking_id: str, user: UserRecord = Depends(require_user)) -> BookingRecord:
    return service.approve_booking(user, booking_id)


@app.post("/api/bookings/{booking_id}/reject", response_model=BookingRecord)
def reject_booking(booking_id: str, user: UserRecord = Depends(require_user)) -> BookingRecord:
    return service.reject_booking(user, booking_id)


@app.post("/api/bookings/{booking_id}/cancel", response_model=BookingRecord)
def cancel_booking(booking_id: str, user: UserRecord = Depends(require_user)) -> BookingRecord:
    return service.cancel_booking(user, booking_id)


@app.post("/api/desk-releases/manual")
def upsert_manual_release(payload: ManualReleaseUpsert, user: UserRecord = Depends(require_user)) -> dict[str, str]:
    return service.upsert_manual_release(user, payload)


@app.get("/api/desk-releases/recurring", response_model=list[RecurringReleaseRecord])
def list_recurring_releases(user: UserRecord = Depends(require_user)) -> list[RecurringReleaseRecord]:
    return service.list_recurring_releases(user)


@app.post("/api/desk-releases/recurring", response_model=RecurringReleaseRecord)
def upsert_recurring_release(
    payload: RecurringReleaseUpsert,
    user: UserRecord = Depends(require_user),
) -> RecurringReleaseRecord:
    return service.upsert_recurring_release(user, payload)


@app.get("/api/preferred-partners", response_model=list[PreferredPartnerRecord])
def list_preferred_partners(user: UserRecord = Depends(require_user)) -> list[PreferredPartnerRecord]:
    return service.list_preferred_partners(user)


@app.post("/api/preferred-partners", response_model=PreferredPartnerRecord)
def create_preferred_partner(
    payload: PreferredPartnerUpsert,
    user: UserRecord = Depends(require_user),
) -> PreferredPartnerRecord:
    return service.create_preferred_partner(user, payload)


@app.delete("/api/preferred-partners/{preferred_partner_id}")
def delete_preferred_partner(preferred_partner_id: str, user: UserRecord = Depends(require_user)) -> dict[str, str]:
    return service.delete_preferred_partner(user, preferred_partner_id)


@app.get("/api/notifications")
def list_notifications(user: UserRecord = Depends(require_user)):
    return service.list_notifications(user)


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, user: UserRecord = Depends(require_user)) -> dict[str, str]:
    return service.mark_notification_read(user, notification_id)


@app.get("/api/admin/users", response_model=list[UserRecord])
def admin_list_users(user: UserRecord = Depends(require_user)) -> list[UserRecord]:
    return service.list_users(user)


@app.post("/api/admin/users", response_model=UserRecord)
def admin_upsert_user(payload: AdminUserUpsert, user: UserRecord = Depends(require_user)) -> UserRecord:
    return service.admin_upsert_user(user, payload)


@app.get("/api/admin/whitelist", response_model=list[WhitelistEntry])
def admin_list_whitelist(user: UserRecord = Depends(require_user)) -> list[WhitelistEntry]:
    return service.list_whitelist(user)


@app.post("/api/admin/whitelist", response_model=WhitelistEntry)
def admin_upsert_whitelist(payload: WhitelistUpsert, user: UserRecord = Depends(require_user)) -> WhitelistEntry:
    return service.admin_upsert_whitelist(user, payload)


@app.delete("/api/admin/whitelist/{whitelist_id}")
def admin_delete_whitelist(whitelist_id: str, user: UserRecord = Depends(require_user)) -> dict[str, str]:
    return service.admin_delete_whitelist(user, whitelist_id)


@app.post("/api/admin/locations", response_model=LocationRecord)
def admin_upsert_location(payload: AdminLocationUpsert, user: UserRecord = Depends(require_user)) -> LocationRecord:
    return service.admin_upsert_location(user, payload)


@app.post("/api/admin/floors", response_model=FloorRecord)
def admin_upsert_floor(payload: AdminFloorUpsert, user: UserRecord = Depends(require_user)) -> FloorRecord:
    return service.admin_upsert_floor(user, payload)


@app.post("/api/admin/desks", response_model=DeskRecord)
def admin_upsert_desk(payload: AdminDeskUpsert, user: UserRecord = Depends(require_user)) -> DeskRecord:
    return service.admin_upsert_desk(user, payload)


@app.get("/api/admin/stats", response_model=StatsResponse)
def admin_stats(user: UserRecord = Depends(require_user)) -> StatsResponse:
    return service.admin_stats(user)


@app.get("/api/admin/audit-log")
def admin_audit_log(user: UserRecord = Depends(require_user)):
    return service.list_audit_log(user)
