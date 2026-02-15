from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.deps import auth_store, repo, require_user, service
from app.models import (
    AbsenceUpsert,
    AdminDeskUpsert,
    AdminUserUpsert,
    AuthToken,
    DeskRecord,
    ForceCancelRequest,
    OTPRequest,
    OTPVerify,
    ReservationCreate,
    ReservationUpdate,
    StatsResponse,
    UserRecord,
)
from app.security import send_otp_email

app = FastAPI(title="Desk Reservation API", version="0.1.0")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def on_startup() -> None:
    repo.init_storage()


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/app")


@app.get("/app")
def app_shell() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/me", response_model=UserRecord)
def me(user: UserRecord = Depends(require_user)) -> UserRecord:
    return user


@app.get("/api/desks", response_model=list[DeskRecord])
def list_desks(user: UserRecord = Depends(require_user)) -> list[DeskRecord]:
    _ = user
    return service.list_desks()


@app.get("/api/users", response_model=list[UserRecord])
def list_users(user: UserRecord = Depends(require_user)) -> list[UserRecord]:
    _ = user
    return service.list_users()


@app.post("/api/auth/request-otp")
def request_otp(payload: OTPRequest) -> dict[str, str]:
    try:
        code = auth_store.issue_otp(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    send_otp_email(str(payload.email), code)
    return {"status": "ok"}


@app.post("/api/auth/verify-otp", response_model=AuthToken)
def verify_otp(payload: OTPVerify) -> AuthToken:
    ok = auth_store.verify_otp(str(payload.email), payload.code)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid OTP")

    user = service.ensure_user_for_email(str(payload.email))
    token = auth_store.create_session(user.user_id)
    return AuthToken(token=token, user=user)


@app.post("/api/auth/logout")
def logout(
    user: UserRecord = Depends(require_user),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, str]:
    _ = user
    parts = (authorization or "").split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        auth_store.logout(parts[1].strip())
    return {"status": "ok"}


@app.post("/api/reservations")
def create_reservation(payload: ReservationCreate, user: UserRecord = Depends(require_user)):
    return service.create_reservation(
        user=user,
        desk_id=payload.desk_id,
        value_date=payload.date,
        request_slot=payload.slot,
    )


@app.patch("/api/reservations/{reservation_id}")
def patch_reservation(
    reservation_id: str,
    payload: ReservationUpdate,
    user: UserRecord = Depends(require_user),
):
    return service.update_reservation(
        user=user,
        reservation_id=reservation_id,
        desk_id=payload.desk_id,
        value_date=payload.date,
        request_slot=payload.slot,
    )


@app.delete("/api/reservations/{reservation_id}")
def delete_reservation(reservation_id: str, user: UserRecord = Depends(require_user)) -> dict[str, str]:
    service.cancel_reservation(actor=user, reservation_id=reservation_id)
    return {"status": "ok"}


@app.get("/api/reservations")
def list_reservations(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: UserRecord = Depends(require_user),
):
    _ = user
    return service.list_effective_reservations(start_date=start_date, end_date=end_date)


@app.put("/api/named-desk/absences")
def upsert_absence(payload: AbsenceUpsert, user: UserRecord = Depends(require_user)):
    return service.upsert_absence(
        owner=user,
        desk_id=payload.desk_id,
        value_date=payload.date,
        request_slot=payload.slot,
        released=payload.released,
    )


@app.post("/api/admin/users")
def admin_upsert_user(payload: AdminUserUpsert, user: UserRecord = Depends(require_user)):
    return service.admin_upsert_user(
        actor=user,
        email=str(payload.email),
        enabled=payload.enabled,
        is_admin=payload.is_admin,
    )


@app.post("/api/admin/desks")
def admin_upsert_desk(payload: AdminDeskUpsert, user: UserRecord = Depends(require_user)):
    return service.admin_upsert_desk(
        actor=user,
        label=payload.label,
        enabled=payload.enabled,
        owner_user_id=payload.owner_user_id,
        desk_id=payload.desk_id,
    )


@app.post("/api/admin/force-cancel")
def admin_force_cancel(payload: ForceCancelRequest, user: UserRecord = Depends(require_user)) -> dict[str, str]:
    service.admin_force_cancel(actor=user, reservation_id=payload.reservation_id)
    return {"status": "ok"}


@app.get("/api/admin/stats", response_model=StatsResponse)
def admin_stats(user: UserRecord = Depends(require_user)) -> StatsResponse:
    return StatsResponse(**service.admin_stats(actor=user))
