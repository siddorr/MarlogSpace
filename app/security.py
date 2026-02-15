from __future__ import annotations

import random
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage

from app.config import settings
from app.constants import ALLOWED_DOMAIN


@dataclass
class OTPState:
    code: str
    expires_at: datetime
    attempts_left: int


@dataclass
class SessionState:
    user_id: str
    expires_at: datetime


class AuthStore:
    def __init__(self) -> None:
        self._otp_by_email: dict[str, OTPState] = {}
        self._sessions: dict[str, SessionState] = {}

    def validate_email_domain(self, email: str) -> None:
        if not email.lower().endswith(ALLOWED_DOMAIN):
            raise ValueError("Only @ide-tech.com emails are allowed")

    def issue_otp(self, email: str) -> str:
        self.validate_email_domain(email)
        code = "".join(random.choice("0123456789") for _ in range(settings.otp_length))
        self._otp_by_email[email.lower()] = OTPState(
            code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=settings.otp_ttl_minutes),
            attempts_left=settings.otp_max_attempts,
        )
        return code

    def verify_otp(self, email: str, code: str) -> bool:
        self.validate_email_domain(email)
        key = email.lower()
        state = self._otp_by_email.get(key)
        if state is None:
            return False
        if datetime.utcnow() > state.expires_at:
            self._otp_by_email.pop(key, None)
            return False
        if state.attempts_left <= 0:
            self._otp_by_email.pop(key, None)
            return False
        if state.code != code:
            state.attempts_left -= 1
            return False
        self._otp_by_email.pop(key, None)
        return True

    def create_session(self, user_id: str) -> str:
        token = uuid.uuid4().hex
        self._sessions[token] = SessionState(
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(hours=settings.session_ttl_hours),
        )
        return token

    def get_session_user(self, token: str) -> str | None:
        state = self._sessions.get(token)
        if state is None:
            return None
        if datetime.utcnow() > state.expires_at:
            self._sessions.pop(token, None)
            return None
        return state.user_id

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)


def send_otp_email(recipient: str, code: str) -> None:
    if not settings.smtp_host:
        print(f"[WARN] SMTP not configured; OTP for {recipient}: {code}")
        return

    msg = EmailMessage()
    msg["Subject"] = "Your Desk Reservation OTP"
    msg["From"] = settings.smtp_from
    msg["To"] = recipient
    msg.set_content(
        f"Your OTP code is {code}. It expires in {settings.otp_ttl_minutes} minutes."
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls(context=context)
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)
