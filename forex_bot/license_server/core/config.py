"""
Cấu hình toàn bộ hệ thống - chỉnh sửa trước khi deploy
"""

import os
from pathlib import Path
from typing import List


def load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # Server
    PORT: int = int(os.getenv("PORT", 8000))

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_THIS_TO_RANDOM_64_CHAR_STRING_BEFORE_DEPLOY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 6     # Bot phải ping lại sau 6 giờ
    ADMIN_TOKEN_EXPIRE_HOURS: int = 24

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./forex_license.db")

    # Admin mặc định (đổi ngay sau lần đầu chạy)
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "Admin@2024!Strong")

    # Key dùng để mã hóa mật khẩu MT5 khi admin lưu account trên web.
    # Production bắt buộc đặt MT5_CREDENTIAL_KEY riêng, dài và ngẫu nhiên.
    MT5_CREDENTIAL_KEY: str = os.getenv("MT5_CREDENTIAL_KEY", SECRET_KEY)

    # CORS - chỉ cho phép domain của bạn
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        os.getenv("FRONTEND_URL", "https://your-dashboard.com"),
    ]

    # Telegram notification cho admin
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_ADMIN_CHAT_ID: str = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")

    # Email OTP cho user portal
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Forex Bot")
    SMTP_USE_TLS: bool = env_bool("SMTP_USE_TLS", True)
    SMTP_USE_SSL: bool = env_bool("SMTP_USE_SSL", False)
    EMAIL_CODE_EXPIRE_MINUTES: int = int(os.getenv("EMAIL_CODE_EXPIRE_MINUTES", "10"))
    EMAIL_CODE_RESEND_SECONDS: int = int(os.getenv("EMAIL_CODE_RESEND_SECONDS", "60"))
    EMAIL_CODE_MAX_ATTEMPTS: int = int(os.getenv("EMAIL_CODE_MAX_ATTEMPTS", "5"))

    # Giới hạn ping: bot phải ping mỗi N giây, nếu không ping quá timeout → cảnh báo
    BOT_PING_INTERVAL_SECONDS: int = 300   # 5 phút
    BOT_PING_TIMEOUT_SECONDS: int = 600    # 10 phút không ping → alert


settings = Settings()
