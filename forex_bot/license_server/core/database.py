"""
Database: SQLAlchemy async + SQLite
Models: Admin, User, License, MT5Account, BotSession, TradeLog, BotCommand, BotRuntimeStatus
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, DateTime, Integer, Float, ForeignKey, Text
from datetime import datetime, timezone
from typing import Optional, List
import uuid

from core.config import settings


engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ─── Models ──────────────────────────────────────────────────────────────────

class Admin(Base):
    """Tài khoản admin (chỉ bạn dùng)"""
    __tablename__ = "admins"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    username:     Mapped[str]           = mapped_column(String(64), unique=True, nullable=False)
    password_hash:Mapped[str]           = mapped_column(String(256), nullable=False)
    created_at:   Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login:   Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class User(Base):
    """Người dùng được admin cấp quyền"""
    __tablename__ = "users"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    username:     Mapped[str]           = mapped_column(String(64), unique=True, nullable=False)
    email:        Mapped[str]           = mapped_column(String(128), unique=True, nullable=False)
    password_hash:Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    note:         Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active:    Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at:   Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at:   Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    licenses:     Mapped[List["License"]]    = relationship(back_populates="user", cascade="all, delete")
    mt5_accounts: Mapped[List["MT5Account"]] = relationship(back_populates="user", cascade="all, delete")
    sessions:     Mapped[List["BotSession"]] = relationship(back_populates="user", cascade="all, delete")


class License(Base):
    """License key gắn với 1 user + 1 IP duy nhất"""
    __tablename__ = "licenses"

    id:            Mapped[int]           = mapped_column(Integer, primary_key=True)
    license_key:   Mapped[str]           = mapped_column(String(64), unique=True, nullable=False,
                                            default=lambda: str(uuid.uuid4()).replace("-", "").upper())
    user_id:       Mapped[int]           = mapped_column(ForeignKey("users.id"), nullable=False)
    allowed_ip:    Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # None = chưa lock IP
    is_active:     Mapped[bool]          = mapped_column(Boolean, default=True)
    mt_account:    Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # MT4/MT5 account number
    created_at:    Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at:    Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_verified: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verify_count:  Mapped[int]           = mapped_column(Integer, default=0)

    user:          Mapped["User"]        = relationship(back_populates="licenses")


class MT5Account(Base):
    """Tài khoản MT5 do admin quản lý để runner trên VPS có thể chạy bot thay khách."""
    __tablename__ = "mt5_accounts"

    id:                    Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:               Mapped[int]           = mapped_column(ForeignKey("users.id"), nullable=False)
    license_key:           Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    label:                 Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    broker:                Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    mt_login:              Mapped[str]           = mapped_column(String(32), nullable=False)
    mt_server:             Mapped[str]           = mapped_column(String(96), nullable=False)
    mt_password_encrypted: Mapped[str]           = mapped_column(Text, nullable=False)
    symbol_mode:           Mapped[str]           = mapped_column(String(16), default="XAU")
    symbols:               Mapped[str]           = mapped_column(String(128), default="XAUUSDm")
    timeframe:             Mapped[str]           = mapped_column(String(8), default="M1")
    lot_size:              Mapped[float]         = mapped_column(Float, default=0.01)
    max_positions:         Mapped[int]           = mapped_column(Integer, default=10)
    max_total_positions:   Mapped[int]           = mapped_column(Integer, default=10)
    max_spread_points:     Mapped[int]           = mapped_column(Integer, default=350)
    dry_run:               Mapped[bool]          = mapped_column(Boolean, default=True)
    is_active:             Mapped[bool]          = mapped_column(Boolean, default=False)
    run_status:            Mapped[str]           = mapped_column(String(24), default="stopped")
    created_by:            Mapped[str]           = mapped_column(String(16), default="admin")
    last_error:            Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note:                  Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:            Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at:            Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_started_at:       Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_stopped_at:       Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user:                  Mapped["User"]        = relationship(back_populates="mt5_accounts")


class PortalDeviceLock(Base):
    """Thiết bị đầu tiên đăng nhập user portal cho mỗi license."""
    __tablename__ = "portal_device_locks"

    id:            Mapped[int]           = mapped_column(Integer, primary_key=True)
    license_key:   Mapped[str]           = mapped_column(String(64), unique=True, nullable=False)
    user_id:       Mapped[int]           = mapped_column(ForeignKey("users.id"), nullable=False)
    device_id:     Mapped[str]           = mapped_column(String(96), nullable=False)
    device_name:   Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    ip_address:    Mapped[str]           = mapped_column(String(64), nullable=False)
    created_at:    Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_at:  Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class EmailLoginCode(Base):
    """Mã OTP đăng nhập/đăng ký user portal gửi qua email."""
    __tablename__ = "email_login_codes"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True)
    email:       Mapped[str]           = mapped_column(String(128), nullable=False)
    code_hash:   Mapped[str]           = mapped_column(String(128), nullable=False)
    purpose:     Mapped[str]           = mapped_column(String(32), default="user_login")
    ip_address:  Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attempts:    Mapped[int]           = mapped_column(Integer, default=0)
    created_at:  Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at:  Mapped[datetime]      = mapped_column(DateTime, nullable=False)
    used_at:     Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class BotSession(Base):
    """Log mỗi lần bot kết nối/ping (dùng để monitor)"""
    __tablename__ = "bot_sessions"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:     Mapped[int]           = mapped_column(ForeignKey("users.id"), nullable=False)
    license_key: Mapped[str]           = mapped_column(String(64), nullable=False)
    ip_address:  Mapped[str]           = mapped_column(String(64), nullable=False)
    action:      Mapped[str]           = mapped_column(String(32), nullable=False)  # "verify", "ping", "reject"
    reason:      Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mt_account:  Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at:  Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user:        Mapped["User"]        = relationship(back_populates="sessions")


class TradeLog(Base):
    """Log lệnh giao dịch từ bot gửi lên (để hiển thị trên dashboard)"""
    __tablename__ = "trade_logs"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True)
    license_key: Mapped[str]           = mapped_column(String(64), nullable=False)
    ticket:      Mapped[str]           = mapped_column(String(32), nullable=False)   # MT4 ticket number
    symbol:      Mapped[str]           = mapped_column(String(16), nullable=False)   # EURUSD, XAUUSD...
    direction:   Mapped[str]           = mapped_column(String(4), nullable=False)    # BUY / SELL
    entry_price: Mapped[float]         = mapped_column(Float, nullable=False)
    sl_price:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp_price:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lot_size:    Mapped[float]         = mapped_column(Float, nullable=False)
    status:      Mapped[str]           = mapped_column(String(16), default="open")  # open/closed/cancelled
    close_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pips:        Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opened_at:   Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at:   Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    note:        Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class BotCommand(Base):
    """Lệnh vận hành admin gửi xuống bot thật qua polling."""
    __tablename__ = "bot_commands"

    id:                 Mapped[int]                = mapped_column(Integer, primary_key=True)
    target_license_key: Mapped[str]                = mapped_column(String(64), nullable=False)
    action:             Mapped[str]                = mapped_column(String(32), nullable=False)
    symbol:             Mapped[Optional[str]]      = mapped_column(String(16), nullable=True)
    payload:            Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
    reason:             Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
    status:             Mapped[str]                = mapped_column(String(16), default="pending")
    result:             Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
    created_at:         Mapped[datetime]           = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    delivered_at:       Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at:       Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class BotRuntimeStatus(Base):
    """Trạng thái realtime mới nhất do bot báo về theo từng license/symbol."""
    __tablename__ = "bot_runtime_statuses"

    id:                  Mapped[int]                = mapped_column(Integer, primary_key=True)
    license_key:         Mapped[str]                = mapped_column(String(64), nullable=False)
    mt_account:          Mapped[Optional[str]]      = mapped_column(String(32), nullable=True)
    symbol:              Mapped[str]                = mapped_column(String(16), nullable=False)
    timeframe:           Mapped[Optional[str]]      = mapped_column(String(8), nullable=True)
    strategy:            Mapped[Optional[str]]      = mapped_column(String(32), nullable=True)
    signal:              Mapped[str]                = mapped_column(String(12), default="HOLD")
    reason:              Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
    confidence:          Mapped[Optional[float]]    = mapped_column(Float, nullable=True)
    spread_points:       Mapped[Optional[float]]    = mapped_column(Float, nullable=True)
    open_positions:      Mapped[int]                = mapped_column(Integer, default=0)
    total_positions:     Mapped[int]                = mapped_column(Integer, default=0)
    max_positions:       Mapped[int]                = mapped_column(Integer, default=0)
    max_total_positions: Mapped[int]                = mapped_column(Integer, default=0)
    dry_run:             Mapped[bool]               = mapped_column(Boolean, default=True)
    session_allowed:     Mapped[bool]               = mapped_column(Boolean, default=True)
    run_state:           Mapped[str]                = mapped_column(String(24), default="idle")
    payload:             Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
    created_at:          Mapped[datetime]           = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at:          Mapped[datetime]           = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class AppLog(Base):
    """Log toàn cầu: Errors, warnings, events quan trọng"""
    __tablename__ = "app_logs"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True)
    level:       Mapped[str]           = mapped_column(String(16), nullable=False)      # INFO, WARNING, ERROR, CRITICAL
    module:      Mapped[str]           = mapped_column(String(64), nullable=False)      # auth, bot, ai, database...
    message:     Mapped[str]           = mapped_column(Text, nullable=False)
    context:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)             # JSON context (license_key, user_id, IP...)
    created_at:  Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class SystemHealth(Base):
    """Giám sát sức khỏe hệ thống"""
    __tablename__ = "system_health"

    id:                    Mapped[int]           = mapped_column(Integer, primary_key=True)
    check_type:            Mapped[str]           = mapped_column(String(32), nullable=False)  # "database", "api", "smtp"...
    status:                Mapped[str]           = mapped_column(String(16), nullable=False)  # "healthy", "degraded", "critical"
    last_check_at:         Mapped[datetime]      = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    details:               Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:            Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── DB helpers ──────────────────────────────────────────────────────────────

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Tạo bảng + admin mặc định nếu chưa có"""
    from passlib.context import CryptContext
    from sqlalchemy import select

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.DATABASE_URL.startswith("sqlite"):
            user_columns = await conn.exec_driver_sql("PRAGMA table_info(users)")
            column_names = {row[1] for row in user_columns.fetchall()}
            if "password_hash" not in column_names:
                await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN password_hash VARCHAR(256)")
            mt5_columns = await conn.exec_driver_sql("PRAGMA table_info(mt5_accounts)")
            mt5_column_names = {row[1] for row in mt5_columns.fetchall()}
            if "created_by" not in mt5_column_names:
                await conn.exec_driver_sql("ALTER TABLE mt5_accounts ADD COLUMN created_by VARCHAR(16) DEFAULT 'admin'")
                await conn.exec_driver_sql(
                    "UPDATE mt5_accounts SET created_by='user' "
                    "WHERE note LIKE '%User portal submit%' OR note LIKE '%user tự vận hành%'"
                )

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Admin).where(Admin.username == settings.ADMIN_USERNAME))
        if not result.scalar_one_or_none():
            admin = Admin(
                username=settings.ADMIN_USERNAME,
                password_hash=pwd_ctx.hash(settings.ADMIN_PASSWORD),
            )
            session.add(admin)
            await session.commit()
            print(f"[DB] Admin mặc định đã tạo: {settings.ADMIN_USERNAME}")
