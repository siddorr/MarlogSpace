from __future__ import annotations

from fastapi import Header, HTTPException

from app.repository import SQLiteRepository
from app.security import AuthManager
from app.services import MarlogService


repo = SQLiteRepository()
repo.init_storage()
repo.ensure_seed_admin()
auth = AuthManager(repo=repo)
service = MarlogService(repo=repo, auth=auth)


def require_user(token: str | None = Header(default=None, alias="Authorization")):
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = token.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    session_token = parts[1].strip()
    user = service.get_user_from_token(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user
