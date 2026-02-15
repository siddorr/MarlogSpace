from __future__ import annotations

from fastapi import Header, HTTPException

from app.repository import ExcelRepository
from app.security import AuthStore
from app.services import ReservationService

repo = ExcelRepository()
auth_store = AuthStore()
service = ReservationService(repo=repo)
def require_user(token: str | None = Header(default=None, alias="Authorization")):
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = token.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    session_token = parts[1].strip()
    user_id = auth_store.get_session_user(session_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = service.get_user_or_404(user_id)
    return user
