from __future__ import annotations

import random
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from app.config import settings
from app.constants import ALLOWED_DOMAIN
from app.repository import SQLiteRepository


class AuthManager:
    def __init__(self, repo: SQLiteRepository) -> None:
        self.repo = repo

    def validate_email(self, email: str) -> str:
        normalized = email.strip().lower()
        if not normalized.endswith(ALLOWED_DOMAIN) and normalized != "admin@company.com":
            raise ValueError("Only approved company emails are allowed")
        if not self.repo.email_allowed(normalized):
            raise ValueError("Email is not in the whitelist")
        return normalized

    def issue_otp(self, email: str) -> str:
        normalized = self.validate_email(email)
        code = "".join(random.choice("0123456789") for _ in range(settings.otp_length))
        expires_at = datetime.utcnow() + timedelta(minutes=settings.otp_ttl_minutes)
        self.repo.save_otp(normalized, code, expires_at, settings.otp_max_attempts)
        self._send_otp_email(normalized, code)
        return code

    def verify_otp(self, email: str, code: str) -> str | None:
        normalized = self.validate_email(email)
        row = self.repo.get_otp(normalized)
        if not row:
            return None
        if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            self.repo.delete_otp(normalized)
            return None
        if int(row["attempts_left"]) <= 0:
            self.repo.delete_otp(normalized)
            return None
        if row["code"] != code:
            self.repo.decrement_otp_attempts(normalized)
            return None
        self.repo.delete_otp(normalized)
        token = secrets.token_urlsafe(32)
        user = self.repo.get_user_by_email(normalized)
        if not user:
            user = self.repo.upsert_user(
                name=normalized.split("@")[0].replace(".", " ").replace("_", " ").title(),
                email=normalized,
                enabled=True,
                is_admin=False,
            )
        self.repo.create_session(
            token=token,
            user_id=user.user_id,
            expires_at=datetime.utcnow() + timedelta(hours=settings.session_ttl_hours),
        )
        return token

    def get_session_user_id(self, token: str) -> str | None:
        row = self.repo.get_session(token)
        if not row:
            return None
        if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            self.repo.delete_session(token)
            return None
        return str(row["user_id"])

    def logout(self, token: str) -> None:
        self.repo.delete_session(token)

    def _send_otp_email(self, recipient: str, code: str) -> None:
        if not settings.smtp_host:
            print(f"[OTP] {recipient}: {code}")
            return
        msg = EmailMessage()
        msg["Subject"] = "Your MarlogSpace sign-in code"
        msg["From"] = settings.smtp_from
        msg["To"] = recipient
        msg.set_content(f"Your MarlogSpace verification code is {code}.")

        context = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls(context=context)
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
