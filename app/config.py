from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_file: Path = Path(os.getenv("MARLOGSPACE_DB_FILE", "data/marlogspace.db"))
    legacy_excel_file: Path = Path(
        os.getenv("MARLOGSPACE_LEGACY_EXCEL_FILE", "data/reservations.xlsx")
    )
    otp_ttl_minutes: int = int(os.getenv("MARLOGSPACE_OTP_TTL_MINUTES", "10"))
    otp_max_attempts: int = int(os.getenv("MARLOGSPACE_OTP_MAX_ATTEMPTS", "5"))
    otp_length: int = int(os.getenv("MARLOGSPACE_OTP_LENGTH", "6"))
    session_ttl_hours: int = int(os.getenv("MARLOGSPACE_SESSION_TTL_HOURS", "12"))
    smtp_host: str | None = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_from: str = os.getenv("SMTP_FROM", "noreply@ide-tech.com")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"


settings = Settings()
