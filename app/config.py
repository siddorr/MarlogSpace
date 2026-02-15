from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_file: Path = Path(os.getenv("DESK_APP_DATA_FILE", "data/reservations.xlsx"))
    backup_dir: Path = Path(os.getenv("DESK_APP_BACKUP_DIR", "data/backups"))
    lock_file: Path = Path(os.getenv("DESK_APP_LOCK_FILE", "data/reservations.lock"))
    otp_ttl_minutes: int = int(os.getenv("DESK_APP_OTP_TTL_MINUTES", "10"))
    otp_max_attempts: int = int(os.getenv("DESK_APP_OTP_MAX_ATTEMPTS", "5"))
    otp_length: int = int(os.getenv("DESK_APP_OTP_LENGTH", "6"))
    session_ttl_hours: int = int(os.getenv("DESK_APP_SESSION_TTL_HOURS", "12"))
    smtp_host: str | None = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_from: str = os.getenv("SMTP_FROM", "noreply@ide-tech.com")


settings = Settings()
