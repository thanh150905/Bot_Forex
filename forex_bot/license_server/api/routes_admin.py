"""
Admin routes: Quản lý user, license, IP whitelist
Tất cả endpoint yêu cầu admin token
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from pydantic import BaseModel, EmailStr
from typing import Any, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid
import json

from core.database import get_db, Admin, User, License, MT5Account, BotSession, TradeLog, BotCommand, PortalDeviceLock, BotRuntimeStatus
from core.security import encrypt_secret, require_admin
from core.config import settings
from ai_engine.indicators import Candle
from ai_engine.scalping import classify_scalping
from ai_engine.trend import classify_trend

router = APIRouter()


# ─── Dependency ───────────────────────────────────────────────────────────────

async def admin_required(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    return require_admin(token)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    username:   str
    email:      str
    note:       Optional[str] = None
    expires_at: Optional[datetime] = None  # None = không hết hạn


class UpdateUserRequest(BaseModel):
    is_active:  Optional[bool] = None
    note:       Optional[str] = None
    expires_at: Optional[datetime] = None


class CreateLicenseRequest(BaseModel):
    user_id:    int
    allowed_ip: Optional[str] = None        # None = chưa lock, tự lock khi bot verify lần đầu
    mt_account: Optional[str] = None
    expires_at: Optional[datetime] = None


class UpdateLicenseIPRequest(BaseModel):
    license_key: str
    new_ip:      Optional[str] = None       # None = xóa lock IP (reset)
    is_active:   Optional[bool] = None
    mt_account:  Optional[str] = None
    expires_at:  Optional[datetime] = None


class CandlePayload(BaseModel):
    open:   float
    high:   float
    low:    float
    close:  float
    volume: Optional[float] = None
    time:   Optional[str] = None


class AdminTrendRequest(BaseModel):
    symbol:    str
    timeframe: str = "M15"
    strategy:  str = "trend"
    candles:   list[CandlePayload]


class PaperTradeRequest(BaseModel):
    symbol:      str
    direction:   str
    entry_price: float
    sl_price:    Optional[float] = None
    tp_price:    Optional[float] = None
    lot_size:    float = 0.01
    note:        Optional[str] = None


class CreateBotCommandRequest(BaseModel):
    target_license_key: Optional[str] = None  # None/blank = gửi tới tất cả license active
    action:             str
    symbol:             Optional[str] = None
    payload:            Optional[dict[str, Any]] = None
    reason:             Optional[str] = None


class CreateMT5AccountRequest(BaseModel):
    user_id:             int
    license_key:         Optional[str] = None
    label:               Optional[str] = None
    broker:              Optional[str] = None
    mt_login:            str
    mt_password:         str
    mt_server:           str
    symbol_mode:         str = "XAU"
    symbols:             Optional[str] = None
    timeframe:           str = "M1"
    lot_size:            float = 0.01
    max_positions:       int = 10
    max_total_positions: int = 10
    max_spread_points:   int = 350
    dry_run:             bool = True
    is_active:           bool = False
    note:                Optional[str] = None


class UpdateMT5AccountRequest(BaseModel):
    user_id:             Optional[int] = None
    license_key:         Optional[str] = None
    label:               Optional[str] = None
    broker:              Optional[str] = None
    mt_login:            Optional[str] = None
    mt_password:         Optional[str] = None
    mt_server:           Optional[str] = None
    symbol_mode:         Optional[str] = None
    symbols:             Optional[str] = None
    timeframe:           Optional[str] = None
    lot_size:            Optional[float] = None
    max_positions:       Optional[int] = None
    max_total_positions: Optional[int] = None
    max_spread_points:   Optional[int] = None
    dry_run:             Optional[bool] = None
    is_active:           Optional[bool] = None
    run_status:          Optional[str] = None
    last_error:          Optional[str] = None
    note:                Optional[str] = None


class MT5AccountCommandRequest(BaseModel):
    action: str
    reason: Optional[str] = None


COMMAND_ACTIONS = {"pause", "resume", "close_all", "close_symbol", "set_config"}
MT5_SYMBOL_PRESETS = {
    "XAU": ("XAUUSDm", 350),
    "ETH": ("ETHUSDm", 5000),
    "BTC": ("BTCUSDm", 20000),
    "CRYPTO": ("ETHUSDm,BTCUSDm", 20000),
    "ALL": ("XAUUSDm,ETHUSDm,BTCUSDm", 20000),
}
LOCAL_RUNNER_ALLOWED_IPS = {"127.0.0.1", "::1", "localhost"}
MT5_ACCOUNT_STATUSES = {
    "stopped",
    "waiting_client",
    "running",
    "paused",
    "pending_start",
    "pending_stop",
    "pending_restart",
    "error",
}
MT5_ACCOUNT_ACTIONS = {"start", "stop", "restart", "mark_running", "mark_error"}


def normalize_blank(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_mt5_symbols(symbol_mode: str, symbols: Optional[str], max_spread_points: Optional[int] = None) -> tuple[str, str, int]:
    mode = (symbol_mode or "XAU").strip().upper()
    custom_symbols = ",".join(part.strip() for part in (symbols or "").split(",") if part.strip())
    if mode == "CUSTOM":
        if not custom_symbols:
            raise HTTPException(status_code=400, detail="CUSTOM cần nhập danh sách symbols")
        return mode, custom_symbols, int(max_spread_points or 350)
    if mode not in MT5_SYMBOL_PRESETS:
        raise HTTPException(status_code=400, detail="symbol_mode phải là XAU, ETH, BTC, CRYPTO, ALL hoặc CUSTOM")
    preset_symbols, preset_spread = MT5_SYMBOL_PRESETS[mode]
    if custom_symbols and custom_symbols.upper() != preset_symbols.upper():
        return mode, custom_symbols, int(max_spread_points or preset_spread)
    return mode, preset_symbols, int(max_spread_points or preset_spread)


def is_remote_client_license(license_: Optional[License]) -> bool:
    allowed_ip = (license_.allowed_ip or "").strip() if license_ else ""
    return bool(allowed_ip and allowed_ip not in LOCAL_RUNNER_ALLOWED_IPS)


def is_license_online(license_: Optional[License], now: datetime) -> bool:
    if not license_ or not license_.is_active or not license_.last_verified:
        return False
    last_seen = license_.last_verified
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return (now - last_seen).total_seconds() <= settings.BOT_PING_TIMEOUT_SECONDS


def mt5_account_source(account: MT5Account) -> str:
    source = (account.created_by or "").strip().lower()
    if source in {"admin", "user"}:
        return source
    note = (account.note or "").lower()
    if "user portal submit" in note or "user tự vận hành" in note:
        return "user"
    return "admin"


def require_admin_mt5_account(account: MT5Account) -> None:
    if mt5_account_source(account) != "admin":
        raise HTTPException(
            status_code=403,
            detail="Tài khoản MT5 này do user tự thêm. Admin chỉ được xem thống kê hoặc xóa.",
        )


def mt5_account_to_dict(account: MT5Account, user: Optional[User] = None, license_: Optional[License] = None) -> dict[str, Any]:
    source = mt5_account_source(account)
    return {
        "id": account.id,
        "user_id": account.user_id,
        "username": user.username if user else None,
        "created_by": source,
        "source_label": "User tự thêm" if source == "user" else "Admin thêm",
        "can_admin_operate": source == "admin",
        "license_key": account.license_key,
        "license_active": license_.is_active if license_ else None,
        "license_allowed_ip": license_.allowed_ip if license_ else None,
        "run_mode": "client" if is_remote_client_license(license_) else "hosted",
        "label": account.label,
        "broker": account.broker,
        "mt_login": account.mt_login,
        "mt_server": account.mt_server,
        "has_password": bool(account.mt_password_encrypted),
        "symbol_mode": account.symbol_mode,
        "symbols": account.symbols,
        "timeframe": account.timeframe,
        "lot_size": account.lot_size,
        "max_positions": account.max_positions,
        "max_total_positions": account.max_total_positions,
        "max_spread_points": account.max_spread_points,
        "dry_run": account.dry_run,
        "is_active": account.is_active,
        "run_status": account.run_status,
        "last_error": account.last_error,
        "note": account.note,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
        "last_started_at": account.last_started_at,
        "last_stopped_at": account.last_stopped_at,
    }


def trade_log_to_dict(trade: TradeLog) -> dict[str, Any]:
    return {
        "id": trade.id,
        "license_key": trade.license_key,
        "ticket": trade.ticket,
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_price": trade.entry_price,
        "sl_price": trade.sl_price,
        "tp_price": trade.tp_price,
        "lot_size": trade.lot_size,
        "status": trade.status,
        "close_price": trade.close_price,
        "profit": trade.profit,
        "pips": trade.pips,
        "opened_at": trade.opened_at,
        "closed_at": trade.closed_at,
        "note": trade.note,
    }


def group_trade_rows(trades: list[TradeLog], key_name: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for trade in trades:
        key = str(getattr(trade, key_name) or "-")
        row = groups.setdefault(
            key,
            {
                key_name: key,
                "total": 0,
                "open": 0,
                "closed": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0.0,
                "lot": 0.0,
                "pips": 0.0,
            },
        )
        row["total"] += 1
        row["lot"] += float(trade.lot_size or 0.0)
        if trade.status == "open":
            row["open"] += 1
        if trade.status == "closed":
            row["closed"] += 1
            profit = float(trade.profit or 0.0)
            row["profit"] += profit
            row["pips"] += float(trade.pips or 0.0)
            if profit > 0:
                row["wins"] += 1
            elif profit < 0:
                row["losses"] += 1

    rows = []
    for row in groups.values():
        row["profit"] = round(float(row["profit"]), 2)
        row["lot"] = round(float(row["lot"]), 4)
        row["pips"] = round(float(row["pips"]), 1)
        row["win_rate"] = round((row["wins"] / row["closed"] * 100.0), 2) if row["closed"] else 0.0
        rows.append(row)
    return sorted(rows, key=lambda item: float(item["profit"]), reverse=True)


def normalize_dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def trade_reference_time(trade: TradeLog) -> datetime:
    return normalize_dt(trade.closed_at) or normalize_dt(trade.opened_at) or datetime.now(timezone.utc)


def build_trade_summary(trades: list[TradeLog], scope_label: str = "Tất cả") -> dict[str, Any]:
    closed = [trade for trade in trades if trade.status == "closed"]
    open_rows = [trade for trade in trades if trade.status == "open"]
    wins = [trade for trade in closed if float(trade.profit or 0.0) > 0]
    losses = [trade for trade in closed if float(trade.profit or 0.0) < 0]
    breakeven = len(closed) - len(wins) - len(losses)

    gross_profit = sum(float(trade.profit or 0.0) for trade in wins)
    gross_loss = abs(sum(float(trade.profit or 0.0) for trade in losses))
    closed_profit = sum(float(trade.profit or 0.0) for trade in closed)
    closed_pips = sum(float(trade.pips or 0.0) for trade in closed)
    win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss else None
    best_trade = max(closed, key=lambda item: float(item.profit or 0.0), default=None)
    worst_trade = min(closed, key=lambda item: float(item.profit or 0.0), default=None)
    latest_trade_at = max((trade_reference_time(trade) for trade in trades), default=None)

    return {
        "scope_label": scope_label,
        "total": len(trades),
        "open": len(open_rows),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": breakeven,
        "win_rate": round(win_rate, 2),
        "closed_profit": round(closed_profit, 2),
        "closed_pips": round(closed_pips, 1),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "avg_closed_profit": round(closed_profit / len(closed), 2) if closed else 0.0,
        "avg_closed_pips": round(closed_pips / len(closed), 1) if closed else 0.0,
        "total_lot": round(sum(float(trade.lot_size or 0.0) for trade in trades), 4),
        "open_lot": round(sum(float(trade.lot_size or 0.0) for trade in open_rows), 4),
        "latest_trade_at": latest_trade_at,
        "best_trade": trade_log_to_dict(best_trade) if best_trade else None,
        "worst_trade": trade_log_to_dict(worst_trade) if worst_trade else None,
        "symbols": group_trade_rows(trades, "symbol"),
        "directions": group_trade_rows(trades, "direction"),
        "status": {
            "open": len(open_rows),
            "closed": len(closed),
            "cancelled": len([trade for trade in trades if trade.status == "cancelled"]),
        },
    }


def command_to_dict(command: BotCommand) -> dict[str, Any]:
    payload: Any = None
    if command.payload:
        try:
            payload = json.loads(command.payload)
        except json.JSONDecodeError:
            payload = command.payload
    return {
        "id": command.id,
        "target_license_key": command.target_license_key,
        "action": command.action,
        "symbol": command.symbol,
        "payload": payload,
        "reason": command.reason,
        "status": command.status,
        "result": command.result,
        "created_at": command.created_at,
        "delivered_at": command.delivered_at,
        "completed_at": command.completed_at,
    }


def runtime_status_to_dict(status: BotRuntimeStatus, user: Optional[User] = None) -> dict[str, Any]:
    payload: Any = {}
    if status.payload:
        try:
            payload = json.loads(status.payload)
        except json.JSONDecodeError:
            payload = status.payload
    return {
        "id": status.id,
        "license_key": status.license_key,
        "license_short": status.license_key[:8] + "...",
        "username": user.username if user else None,
        "mt_account": status.mt_account,
        "symbol": status.symbol,
        "timeframe": status.timeframe,
        "strategy": status.strategy,
        "signal": status.signal,
        "reason": status.reason,
        "confidence": status.confidence,
        "spread_points": status.spread_points,
        "open_positions": status.open_positions,
        "total_positions": status.total_positions,
        "max_positions": status.max_positions,
        "max_total_positions": status.max_total_positions,
        "dry_run": status.dry_run,
        "session_allowed": status.session_allowed,
        "run_state": status.run_state,
        "payload": payload,
        "created_at": status.created_at,
        "updated_at": status.updated_at,
    }


# ─── User Management ──────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Danh sách tất cả user"""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    rows = []
    for u in users:
        license_count = (await db.execute(
            select(func.count(License.id)).where(License.user_id == u.id)
        )).scalar_one()
        active_license_count = (await db.execute(
            select(func.count(License.id)).where(License.user_id == u.id, License.is_active == True)
        )).scalar_one()
        mt5_account_count = (await db.execute(
            select(func.count(MT5Account.id)).where(MT5Account.user_id == u.id)
        )).scalar_one()
        last_session = (await db.execute(
            select(BotSession.created_at)
            .where(BotSession.user_id == u.id)
            .order_by(BotSession.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        source = "self_register" if (u.note or "").lower().find("tự đăng ký") >= 0 or bool(u.password_hash) else "admin"
        rows.append(
            {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_active": u.is_active,
            "has_password": bool(u.password_hash),
            "source": source,
            "license_count": license_count,
            "active_license_count": active_license_count,
            "mt5_account_count": mt5_account_count,
            "last_session_at": last_session,
            "note": u.note,
            "created_at": u.created_at,
            "expires_at": u.expires_at,
            }
        )
    return rows


@router.post("/users")
async def create_user(body: CreateUserRequest, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Tạo user mới"""
    # Kiểm tra trùng username/email
    existing = await db.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username hoặc email đã tồn tại")

    user = User(
        username=body.username,
        email=body.email,
        note=body.note,
        expires_at=body.expires_at,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"message": "Tạo user thành công", "user_id": user.id, "username": user.username}


@router.patch("/users/{user_id}")
async def update_user(user_id: int, body: UpdateUserRequest, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Cập nhật user (kích hoạt/vô hiệu hóa, ghi chú, hạn dùng)"""
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    if not values:
        raise HTTPException(status_code=400, detail="Không có thay đổi nào")
    await db.execute(update(User).where(User.id == user_id).values(**values))
    await db.commit()
    return {"message": "Cập nhật thành công"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Xóa user (cascade xóa license + session)"""
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return {"message": "Đã xóa user"}


# ─── License Management ───────────────────────────────────────────────────────

@router.get("/licenses")
async def list_licenses(admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Danh sách tất cả license"""
    result = await db.execute(
        select(License, User)
        .join(User, License.user_id == User.id)
        .order_by(License.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": l.id,
            "license_key": l.license_key,
            "user_id": l.user_id,
            "username": u.username,
            "allowed_ip": l.allowed_ip,
            "is_active": l.is_active,
            "mt_account": l.mt_account,
            "created_at": l.created_at,
            "expires_at": l.expires_at,
            "last_verified": l.last_verified,
            "verify_count": l.verify_count,
        }
        for l, u in rows
    ]


@router.post("/licenses")
async def create_license(body: CreateLicenseRequest, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Tạo license key mới cho user"""
    user = await db.get(User, body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User không tồn tại")

    key = str(uuid.uuid4()).replace("-", "").upper()
    license_ = License(
        license_key=key,
        user_id=body.user_id,
        allowed_ip=body.allowed_ip,
        mt_account=body.mt_account,
        expires_at=body.expires_at,
    )
    db.add(license_)
    await db.commit()
    await db.refresh(license_)

    return {
        "message": "Tạo license thành công",
        "license_key": key,
        "user": user.username,
        "allowed_ip": body.allowed_ip or "Chưa lock (tự lock khi bot kết nối lần đầu)",
    }


@router.patch("/licenses/update-ip")
async def update_license_ip(body: UpdateLicenseIPRequest, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Cập nhật/reset IP cho license (khi user đổi máy)"""
    result = await db.execute(select(License).where(License.license_key == body.license_key))
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="License không tồn tại")

    values = {}
    if body.new_ip is not None:
        values["allowed_ip"] = body.new_ip if body.new_ip != "" else None
    if body.is_active is not None:
        values["is_active"] = body.is_active
    if body.mt_account is not None:
        values["mt_account"] = body.mt_account if body.mt_account != "" else None
    if body.expires_at is not None:
        values["expires_at"] = body.expires_at

    if values:
        await db.execute(update(License).where(License.license_key == body.license_key).values(**values))
        if body.new_ip == "":
            await db.execute(delete(PortalDeviceLock).where(PortalDeviceLock.license_key == body.license_key))
        await db.commit()

    return {"message": "Cập nhật license thành công", "license_key": body.license_key, **values}


@router.delete("/licenses/{license_key}")
async def revoke_license(license_key: str, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Thu hồi license (deactivate, không xóa để giữ log)"""
    await db.execute(update(License).where(License.license_key == license_key).values(is_active=False))
    await db.commit()
    return {"message": f"License {license_key} đã bị thu hồi"}


# ─── MT5 Account Management ──────────────────────────────────────────────────

@router.get("/mt5-accounts")
async def list_mt5_accounts(admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Danh sách tài khoản MT5 do admin quản lý trên VPS."""
    result = await db.execute(
        select(MT5Account, User, License)
        .join(User, MT5Account.user_id == User.id)
        .outerjoin(License, MT5Account.license_key == License.license_key)
        .order_by(MT5Account.created_at.desc())
    )
    return [mt5_account_to_dict(account, user, license_) for account, user, license_ in result.all()]


@router.post("/mt5-accounts")
async def create_mt5_account(body: CreateMT5AccountRequest,
                             admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Thêm tài khoản MT5 để runner nội bộ có thể chạy bot thay khách."""
    user = await db.get(User, body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User không tồn tại")

    license_: Optional[License] = None
    license_key = normalize_blank(body.license_key)
    if license_key:
        result = await db.execute(select(License).where(License.license_key == license_key))
        license_ = result.scalar_one_or_none()
        if not license_:
            raise HTTPException(status_code=404, detail="License không tồn tại")
        if license_.user_id != body.user_id:
            raise HTTPException(status_code=400, detail="License không thuộc user đã chọn")

    mode, symbols, max_spread = normalize_mt5_symbols(body.symbol_mode, body.symbols, body.max_spread_points)
    if body.lot_size <= 0:
        raise HTTPException(status_code=400, detail="lot_size phải lớn hơn 0")
    if body.max_positions <= 0 or body.max_total_positions <= 0:
        raise HTTPException(status_code=400, detail="Giới hạn vị thế phải lớn hơn 0")
    if not body.mt_password.strip():
        raise HTTPException(status_code=400, detail="Mật khẩu MT5 không được trống")

    account = MT5Account(
        user_id=body.user_id,
        license_key=license_key,
        label=normalize_blank(body.label),
        broker=normalize_blank(body.broker),
        mt_login=body.mt_login.strip(),
        mt_server=body.mt_server.strip(),
        mt_password_encrypted=encrypt_secret(body.mt_password),
        symbol_mode=mode,
        symbols=symbols,
        timeframe=body.timeframe.strip().upper() or "M1",
        lot_size=body.lot_size,
        max_positions=body.max_positions,
        max_total_positions=body.max_total_positions,
        max_spread_points=max_spread,
        dry_run=body.dry_run,
        is_active=body.is_active,
        run_status="waiting_client" if body.is_active and is_remote_client_license(license_) else ("pending_start" if body.is_active else "stopped"),
        created_by="admin",
        note=normalize_blank(body.note),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return {
        "message": "Đã thêm tài khoản MT5",
        "account": mt5_account_to_dict(account, user, license_),
    }


@router.patch("/mt5-accounts/{account_id}")
async def update_mt5_account(account_id: int, body: UpdateMT5AccountRequest,
                             admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Cập nhật cấu hình tài khoản MT5. Không trả lại mật khẩu."""
    account = await db.get(MT5Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Tài khoản MT5 không tồn tại")
    require_admin_mt5_account(account)

    data = body.model_dump(exclude_unset=True)
    if "user_id" in data:
        user = await db.get(User, data["user_id"])
        if not user:
            raise HTTPException(status_code=404, detail="User không tồn tại")
    else:
        user = await db.get(User, account.user_id)

    license_key = data.get("license_key", account.license_key)
    if "license_key" in data:
        license_key = normalize_blank(license_key)
        data["license_key"] = license_key
    if license_key:
        result = await db.execute(select(License).where(License.license_key == license_key))
        license_ = result.scalar_one_or_none()
        if not license_:
            raise HTTPException(status_code=404, detail="License không tồn tại")
        target_user_id = data.get("user_id", account.user_id)
        if license_.user_id != target_user_id:
            raise HTTPException(status_code=400, detail="License không thuộc user đã chọn")

    if "symbol_mode" in data or "symbols" in data or "max_spread_points" in data:
        mode, symbols, max_spread = normalize_mt5_symbols(
            data.get("symbol_mode", account.symbol_mode),
            data.get("symbols", account.symbols),
            data.get("max_spread_points", account.max_spread_points),
        )
        data["symbol_mode"] = mode
        data["symbols"] = symbols
        data["max_spread_points"] = max_spread

    if "mt_password" in data:
        password = data.pop("mt_password")
        if password:
            data["mt_password_encrypted"] = encrypt_secret(password)

    for field in ["label", "broker", "note"]:
        if field in data:
            data[field] = normalize_blank(data[field])
    for field in ["mt_login", "mt_server", "timeframe", "run_status"]:
        if field in data and data[field] is not None:
            data[field] = str(data[field]).strip()
    if "timeframe" in data and data["timeframe"]:
        data["timeframe"] = data["timeframe"].upper()
    if "run_status" in data and data["run_status"] not in MT5_ACCOUNT_STATUSES:
        raise HTTPException(status_code=400, detail=f"run_status phải thuộc: {', '.join(sorted(MT5_ACCOUNT_STATUSES))}")
    if "lot_size" in data and data["lot_size"] <= 0:
        raise HTTPException(status_code=400, detail="lot_size phải lớn hơn 0")
    if "max_positions" in data and data["max_positions"] <= 0:
        raise HTTPException(status_code=400, detail="max_positions phải lớn hơn 0")
    if "max_total_positions" in data and data["max_total_positions"] <= 0:
        raise HTTPException(status_code=400, detail="max_total_positions phải lớn hơn 0")

    data["updated_at"] = datetime.now(timezone.utc)
    if not data:
        raise HTTPException(status_code=400, detail="Không có thay đổi nào")

    await db.execute(update(MT5Account).where(MT5Account.id == account_id).values(**data))
    await db.commit()
    updated = await db.get(MT5Account, account_id)
    return {"message": "Đã cập nhật tài khoản MT5", "account": mt5_account_to_dict(updated, user, None)}


@router.post("/mt5-accounts/{account_id}/command")
async def command_mt5_account(account_id: int, body: MT5AccountCommandRequest,
                              admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Đặt trạng thái để runner VPS xử lý start/stop/restart tài khoản MT5."""
    account = await db.get(MT5Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Tài khoản MT5 không tồn tại")
    require_admin_mt5_account(account)
    action = body.action.strip().lower()
    if action not in MT5_ACCOUNT_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action phải thuộc: {', '.join(sorted(MT5_ACCOUNT_ACTIONS))}")

    license_: Optional[License] = None
    if account.license_key:
        result = await db.execute(select(License).where(License.license_key == account.license_key))
        license_ = result.scalar_one_or_none()
    remote_client = is_remote_client_license(license_)

    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {"updated_at": now}
    command_action = None
    response_message: Optional[str] = None
    bot_online = is_license_online(license_, now)
    if action == "start":
        if remote_client:
            values.update(
                {
                    "is_active": True,
                    "run_status": "running" if bot_online else "waiting_client",
                    "last_error": None,
                    "last_started_at": now,
                }
            )
            if bot_online:
                command_action = "resume"
                response_message = "Bot khách đang online, đã gửi lệnh Start"
            else:
                response_message = "Đã bật quyền chạy, đang chờ máy khách mở bot"
        else:
            values.update({"is_active": True, "run_status": "pending_start", "last_error": None})
            command_action = "resume"
    elif action == "stop":
        values.update({"is_active": False, "run_status": "pending_stop" if remote_client and bot_online else ("paused" if remote_client else "pending_stop"), "last_stopped_at": now})
        if not remote_client or bot_online:
            command_action = "pause"
        response_message = "Đã gửi lệnh Stop" if command_action else "Đã tạm dừng, bot khách hiện chưa online"
    elif action == "restart":
        if remote_client:
            values.update(
                {
                    "is_active": True,
                    "run_status": "running" if bot_online else "waiting_client",
                    "last_error": None,
                    "last_started_at": now,
                }
            )
            if bot_online:
                command_action = "resume"
                response_message = "Bot khách đang online, đã gửi lệnh Resume"
            else:
                response_message = "Không thể restart từ xa khi bot khách chưa chạy; đang chờ máy khách mở bot"
        else:
            values.update({"is_active": True, "run_status": "pending_restart", "last_error": None})
            command_action = "resume"
    elif action == "mark_running":
        values.update({"is_active": True, "run_status": "running", "last_started_at": now, "last_error": None})
    elif action == "mark_error":
        values.update({"run_status": "error", "last_error": body.reason or "Runner báo lỗi"})

    if command_action and account.license_key:
        await db.execute(
            update(BotCommand)
            .where(
                BotCommand.target_license_key == account.license_key,
                BotCommand.action == command_action,
                BotCommand.status == "pending",
            )
            .values(status="cancelled", result="Superseded by newer MT5 account command", completed_at=now)
        )
        db.add(
            BotCommand(
                target_license_key=account.license_key,
                action=command_action,
                payload=json.dumps({"source": "mt5_account", "account_id": account.id}, ensure_ascii=False),
                reason=body.reason or f"MT5 account {action}",
                status="pending",
            )
        )

    await db.execute(update(MT5Account).where(MT5Account.id == account_id).values(**values))
    await db.commit()
    mode_text = "máy khách" if remote_client else "runner VPS"
    return {"message": response_message or f"Đã đặt trạng thái {action} cho tài khoản MT5 ({mode_text})", "id": account_id}


@router.get("/mt5-accounts/{account_id}/trade-stats")
async def mt5_account_trade_stats(account_id: int, limit: int = 300, days: int = 0,
                                  admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Thống kê lệnh và win rate cho một tài khoản MT5 theo license đang gắn."""
    account = await db.get(MT5Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Tài khoản MT5 không tồn tại")

    user = await db.get(User, account.user_id)
    license_: Optional[License] = None
    if account.license_key:
        result = await db.execute(select(License).where(License.license_key == account.license_key))
        license_ = result.scalar_one_or_none()

    if not account.license_key:
        return {
            "account": mt5_account_to_dict(account, user, None),
            "summary": build_trade_summary([]),
            "trades": [],
            "message": "Tài khoản này chưa gắn license nên chưa có log lệnh để thống kê",
        }

    trades_result = await db.execute(
        select(TradeLog)
        .where(TradeLog.license_key == account.license_key)
        .order_by(TradeLog.opened_at.desc())
    )
    all_trades = trades_result.scalars().all()
    safe_days = max(0, min(int(days or 0), 3650))
    cutoff = datetime.now(timezone.utc) - timedelta(days=safe_days) if safe_days else None
    scoped_trades = [
        trade for trade in all_trades
        if cutoff is None or trade_reference_time(trade) >= cutoff
    ]
    scope_label = "Tất cả" if not safe_days else ("Hôm nay" if safe_days == 1 else f"{safe_days} ngày")
    safe_limit = max(1, min(int(limit or 300), 1000))

    return {
        "account": mt5_account_to_dict(account, user, license_),
        "summary": build_trade_summary(scoped_trades, scope_label),
        "history_total": len(all_trades),
        "scope_days": safe_days,
        "trades": [trade_log_to_dict(trade) for trade in scoped_trades[:safe_limit]],
        "message": None,
    }


@router.delete("/mt5-accounts/{account_id}")
async def delete_mt5_account(account_id: int, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Xóa tài khoản MT5 khỏi danh sách quản lý."""
    account = await db.get(MT5Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Tài khoản MT5 không tồn tại")
    await db.execute(delete(MT5Account).where(MT5Account.id == account_id))
    await db.commit()
    return {"message": "Đã xóa tài khoản MT5"}


# ─── Dashboard & Logs ─────────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Tổng quan hệ thống"""
    now = datetime.now(timezone.utc)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_users = (
        await db.execute(select(func.count(User.id)).where(User.is_active == True))
    ).scalar_one()
    total_licenses = (await db.execute(select(func.count(License.id)))).scalar_one()
    active_lic = (
        await db.execute(select(func.count(License.id)).where(License.is_active == True))
    ).scalar_one()
    total_mt5_accounts = (await db.execute(select(func.count(MT5Account.id)))).scalar_one()
    active_mt5_accounts = (
        await db.execute(select(func.count(MT5Account.id)).where(MT5Account.is_active == True))
    ).scalar_one()
    total_trades = (await db.execute(select(func.count(TradeLog.id)))).scalar_one()
    open_trades = (
        await db.execute(select(func.count(TradeLog.id)).where(TradeLog.status == "open"))
    ).scalar_one()
    closed_trades = (
        await db.execute(select(func.count(TradeLog.id)).where(TradeLog.status == "closed"))
    ).scalar_one()
    total_profit = (
        await db.execute(select(func.coalesce(func.sum(TradeLog.profit), 0.0)).where(TradeLog.status == "closed"))
    ).scalar_one()
    today_profit = (
        await db.execute(
            select(func.coalesce(func.sum(TradeLog.profit), 0.0)).where(
                TradeLog.status == "closed",
                TradeLog.closed_at >= today_start,
            )
        )
    ).scalar_one()
    online_seconds = settings.BOT_PING_TIMEOUT_SECONDS
    online_bots = 0
    bot_rows = (await db.execute(select(License, User).join(User, License.user_id == User.id))).all()
    for lic, user in bot_rows:
        if not lic.is_active or not user.is_active or not lic.last_verified:
            continue
        last_seen = lic.last_verified
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        if (now - last_seen).total_seconds() <= online_seconds:
            online_bots += 1

    return {
        "users":    {"total": total_users, "active": active_users},
        "licenses": {"total": total_licenses, "active": active_lic},
        "mt5_accounts": {"total": total_mt5_accounts, "active": active_mt5_accounts},
        "bots":     {"online": online_bots, "total": total_licenses},
        "trades":   {
            "total": total_trades,
            "open": open_trades,
            "closed": closed_trades,
            "profit": round(float(total_profit or 0.0), 2),
            "today_profit": round(float(today_profit or 0.0), 2),
        },
    }


@router.get("/bots")
async def list_bots(admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Danh sách bot theo license, kèm trạng thái online/offline dựa trên last ping."""
    result = await db.execute(
        select(License, User)
        .join(User, License.user_id == User.id)
        .order_by(License.last_verified.desc().nullslast(), License.created_at.desc())
    )
    rows = result.all()
    now = datetime.now(timezone.utc)

    bots = []
    for lic, user in rows:
        last_seen = lic.last_verified
        seconds_since_seen = None
        if last_seen:
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            seconds_since_seen = int((now - last_seen).total_seconds())

        is_online = (
            lic.is_active
            and user.is_active
            and seconds_since_seen is not None
            and seconds_since_seen <= settings.BOT_PING_TIMEOUT_SECONDS
        )

        if not lic.is_active:
            status_text = "revoked"
        elif not user.is_active:
            status_text = "user_disabled"
        elif last_seen is None:
            status_text = "never_connected"
        elif is_online:
            status_text = "online"
        else:
            status_text = "offline"

        bots.append(
            {
                "license_key": lic.license_key,
                "user_id": user.id,
                "username": user.username,
                "allowed_ip": lic.allowed_ip,
                "mt_account": lic.mt_account,
                "is_active": lic.is_active,
                "status": status_text,
                "online": is_online,
                "last_seen": lic.last_verified,
                "seconds_since_seen": seconds_since_seen,
                "verify_count": lic.verify_count,
                "created_at": lic.created_at,
                "expires_at": lic.expires_at,
            }
        )

    return bots


@router.get("/commands")
async def list_bot_commands(status: Optional[str] = None, license_key: Optional[str] = None,
                            limit: int = 100,
                            admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Command/audit log: lệnh admin đã gửi xuống bot."""
    q = select(BotCommand).order_by(BotCommand.created_at.desc()).limit(limit)
    if status:
        q = q.where(BotCommand.status == status.lower())
    if license_key:
        q = q.where(BotCommand.target_license_key == license_key)
    result = await db.execute(q)
    return [command_to_dict(command) for command in result.scalars().all()]


@router.post("/commands")
async def create_bot_command(body: CreateBotCommandRequest,
                             admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Tạo lệnh vận hành cho một bot hoặc toàn bộ license active."""
    raise HTTPException(status_code=403, detail="Lệnh vận hành bot do user thực hiện từ cổng khách hàng")
    action = body.action.strip().lower()
    if action not in COMMAND_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action phải thuộc: {', '.join(sorted(COMMAND_ACTIONS))}")

    symbol = body.symbol.strip().upper() if body.symbol else None
    if action == "close_symbol" and not symbol:
        raise HTTPException(status_code=400, detail="close_symbol cần symbol")
    if action == "set_config" and not body.payload:
        raise HTTPException(status_code=400, detail="set_config cần payload JSON")

    target = body.target_license_key.strip().upper() if body.target_license_key else None
    if target:
        exists = await db.execute(select(License.license_key).where(License.license_key == target))
        if not exists.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="License target không tồn tại")
        targets = [target]
    else:
        rows = await db.execute(
            select(License.license_key).join(User, License.user_id == User.id).where(
                License.is_active == True,
                User.is_active == True,
            )
        )
        targets = [row[0] for row in rows.all()]
        if not targets:
            raise HTTPException(status_code=400, detail="Không có license active để gửi lệnh")

    commands = []
    payload_text = json.dumps(body.payload or {}, ensure_ascii=False)
    for license_key in targets:
        command = BotCommand(
            target_license_key=license_key,
            action=action,
            symbol=symbol,
            payload=payload_text,
            reason=body.reason,
            status="pending",
        )
        db.add(command)
        commands.append(command)

    await db.commit()
    for command in commands:
        await db.refresh(command)

    return {
        "message": f"Đã tạo {len(commands)} command",
        "created": len(commands),
        "commands": [command_to_dict(command) for command in commands],
    }


@router.patch("/commands/{command_id}/cancel")
async def cancel_bot_command(command_id: int, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Hủy command chưa được bot xử lý."""
    raise HTTPException(status_code=403, detail="Admin chỉ xem lịch sử command, không hủy lệnh vận hành của user")
    result = await db.execute(select(BotCommand).where(BotCommand.id == command_id))
    command = result.scalar_one_or_none()
    if not command:
        raise HTTPException(status_code=404, detail="Command không tồn tại")
    if command.status not in {"pending", "delivered"}:
        raise HTTPException(status_code=400, detail=f"Không thể hủy command trạng thái {command.status}")
    await db.execute(
        update(BotCommand).where(BotCommand.id == command_id).values(
            status="cancelled",
            completed_at=datetime.now(timezone.utc),
            result="Cancelled by admin",
        )
    )
    await db.commit()
    return {"message": "Command đã được hủy", "id": command_id}


@router.get("/readiness")
async def readiness(admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Checklist vận hành trước khi deploy/chạy live."""
    now = datetime.now(timezone.utc)
    total_admins = (await db.execute(select(func.count(Admin.id)))).scalar_one()
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar_one()
    active_licenses = (await db.execute(select(func.count(License.id)).where(License.is_active == True))).scalar_one()
    active_mt5_accounts = (await db.execute(select(func.count(MT5Account.id)).where(MT5Account.is_active == True))).scalar_one()
    pending_commands = (await db.execute(select(func.count(BotCommand.id)).where(BotCommand.status == "pending"))).scalar_one()
    open_trades = (await db.execute(select(func.count(TradeLog.id)).where(TradeLog.status == "open"))).scalar_one()
    since_24h = datetime.now().replace(tzinfo=None) - timedelta(hours=24)
    rejects_24h = (
        await db.execute(
            select(func.count(BotSession.id)).where(
                BotSession.action == "reject",
                BotSession.created_at >= since_24h,
            )
        )
    ).scalar_one()

    db_size = None
    if settings.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
        raw_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "", 1)
        db_path = Path(raw_path)
        if db_path.exists():
            db_size = db_path.stat().st_size

    checks = [
        {
            "name": "SECRET_KEY",
            "status": "bad" if settings.SECRET_KEY.startswith("CHANGE_THIS") else "ok",
            "detail": "Đang dùng SECRET_KEY mặc định" if settings.SECRET_KEY.startswith("CHANGE_THIS") else "Đã cấu hình",
        },
        {
            "name": "Admin password",
            "status": "warn" if settings.ADMIN_PASSWORD == "Admin@2024!Strong" else "ok",
            "detail": "Nên đổi password mặc định trước khi public server"
            if settings.ADMIN_PASSWORD == "Admin@2024!Strong"
            else "Đã cấu hình password riêng",
        },
        {
            "name": "Telegram alert",
            "status": "ok" if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ADMIN_CHAT_ID else "warn",
            "detail": "Đã bật Telegram" if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ADMIN_CHAT_ID else "Chưa cấu hình Telegram alert",
        },
        {
            "name": "MT5 credential key",
            "status": "bad" if settings.MT5_CREDENTIAL_KEY.startswith("CHANGE_THIS") else "ok",
            "detail": "Cần đặt MT5_CREDENTIAL_KEY riêng trước khi lưu tài khoản thật"
            if settings.MT5_CREDENTIAL_KEY.startswith("CHANGE_THIS")
            else "Đã có key mã hóa mật khẩu MT5",
        },
        {
            "name": "MT5 hosted accounts",
            "status": "ok" if active_mt5_accounts > 0 else "warn",
            "detail": f"{active_mt5_accounts} tài khoản MT5 đang bật",
        },
        {
            "name": "Active licenses",
            "status": "ok" if active_licenses > 0 else "warn",
            "detail": f"{active_licenses} active license",
        },
        {
            "name": "Pending commands",
            "status": "warn" if pending_commands > 0 else "ok",
            "detail": f"{pending_commands} command đang chờ bot nhận",
        },
    ]

    return {
        "timestamp": now.isoformat(),
        "checks": checks,
        "server": {
            "port": settings.PORT,
            "bot_ping_timeout_seconds": settings.BOT_PING_TIMEOUT_SECONDS,
            "database_url": settings.DATABASE_URL,
            "database_size_bytes": db_size,
        },
        "counts": {
            "admins": total_admins,
            "active_users": active_users,
            "active_licenses": active_licenses,
            "active_mt5_accounts": active_mt5_accounts,
            "open_trades": open_trades,
            "rejects_24h": rejects_24h,
            "pending_commands": pending_commands,
        },
    }


@router.get("/bot-statuses")
async def bot_statuses(limit: int = 100, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Lý do bot vào/chưa vào lệnh mới nhất theo từng license/symbol."""
    rows = (
        await db.execute(
            select(BotRuntimeStatus, User)
            .outerjoin(License, BotRuntimeStatus.license_key == License.license_key)
            .outerjoin(User, License.user_id == User.id)
            .order_by(BotRuntimeStatus.updated_at.desc())
            .limit(min(max(limit, 1), 500))
        )
    ).all()
    return [runtime_status_to_dict(status, user) for status, user in rows]


@router.get("/ops-summary")
async def ops_summary(admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Live operations snapshot for the admin dashboard."""
    now = datetime.now(timezone.utc)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    bot_rows = (
        await db.execute(
            select(License, User)
            .join(User, License.user_id == User.id)
            .order_by(License.last_verified.desc().nullslast())
        )
    ).all()

    bots = []
    online_count = 0
    for lic, user in bot_rows:
        last_seen = lic.last_verified
        seconds_since_seen = None
        if last_seen:
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            seconds_since_seen = int((now - last_seen).total_seconds())

        online = (
            lic.is_active
            and user.is_active
            and seconds_since_seen is not None
            and seconds_since_seen <= settings.BOT_PING_TIMEOUT_SECONDS
        )
        online_count += 1 if online else 0
        bots.append(
            {
                "license_key": lic.license_key,
                "username": user.username,
                "online": online,
                "last_seen": lic.last_verified,
                "seconds_since_seen": seconds_since_seen,
                "mt_account": lic.mt_account,
            }
        )

    open_rows = (
        await db.execute(
            select(TradeLog)
            .where(TradeLog.status == "open")
            .order_by(TradeLog.opened_at.desc())
            .limit(200)
        )
    ).scalars().all()
    recent_closed = (
        await db.execute(
            select(TradeLog)
            .where(TradeLog.status == "closed")
            .order_by(TradeLog.closed_at.desc().nullslast(), TradeLog.opened_at.desc())
            .limit(20)
        )
    ).scalars().all()
    today_profit = (
        await db.execute(
            select(func.coalesce(func.sum(TradeLog.profit), 0.0)).where(
                TradeLog.status == "closed",
                TradeLog.closed_at >= today_start,
            )
        )
    ).scalar_one()
    today_closed = (
        await db.execute(
            select(func.count(TradeLog.id)).where(
                TradeLog.status == "closed",
                TradeLog.closed_at >= today_start,
            )
        )
    ).scalar_one()
    rejected_today = (
        await db.execute(
            select(func.count(BotSession.id)).where(
                BotSession.action == "reject",
                BotSession.created_at >= today_start,
            )
        )
    ).scalar_one()

    by_symbol: dict[str, dict[str, object]] = {}
    stale_open = 0
    for trade in open_rows:
        opened_at = trade.opened_at
        if opened_at.tzinfo is None:
            opened_at_utc = opened_at.replace(tzinfo=timezone.utc)
        else:
            opened_at_utc = opened_at
        age_seconds = int((now - opened_at_utc).total_seconds())
        if age_seconds >= 1800:
            stale_open += 1

        symbol_row = by_symbol.setdefault(
            trade.symbol,
            {"symbol": trade.symbol, "open": 0, "buy": 0, "sell": 0, "lot": 0.0},
        )
        symbol_row["open"] = int(symbol_row["open"]) + 1
        symbol_row["buy"] = int(symbol_row["buy"]) + (1 if trade.direction == "BUY" else 0)
        symbol_row["sell"] = int(symbol_row["sell"]) + (1 if trade.direction == "SELL" else 0)
        symbol_row["lot"] = round(float(symbol_row["lot"]) + float(trade.lot_size or 0), 4)

    runtime_rows = (
        await db.execute(
            select(BotRuntimeStatus, User)
            .outerjoin(License, BotRuntimeStatus.license_key == License.license_key)
            .outerjoin(User, License.user_id == User.id)
            .order_by(BotRuntimeStatus.updated_at.desc())
            .limit(30)
        )
    ).all()

    return {
        "timestamp": now.isoformat(),
        "bots": {
            "online": online_count,
            "total": len(bots),
            "items": bots[:20],
        },
        "risk": {
            "open_trades": len(open_rows),
            "stale_open_trades": stale_open,
            "today_closed_trades": today_closed,
            "today_closed_profit": round(float(today_profit or 0.0), 2),
            "rejects_today": rejected_today,
        },
        "symbols": list(by_symbol.values()),
        "runtime_statuses": [runtime_status_to_dict(status, user) for status, user in runtime_rows],
        "open_trades": [
            {
                "id": trade.id,
                "ticket": trade.ticket,
                "license_key": trade.license_key,
                "symbol": trade.symbol,
                "direction": trade.direction,
                "entry_price": trade.entry_price,
                "lot_size": trade.lot_size,
                "opened_at": trade.opened_at,
                "note": trade.note,
            }
            for trade in open_rows[:50]
        ],
        "recent_closed": [
            {
                "id": trade.id,
                "ticket": trade.ticket,
                "symbol": trade.symbol,
                "direction": trade.direction,
                "profit": trade.profit,
                "pips": trade.pips,
                "closed_at": trade.closed_at,
            }
            for trade in recent_closed
        ],
    }


@router.post("/ai/trend")
async def admin_analyze_trend(body: AdminTrendRequest, admin=Depends(admin_required)):
    """Admin dashboard gọi AI Engine trực tiếp để test signal trên web."""
    strategy = body.strategy.lower()
    min_candles = 40 if strategy == "scalping" else 60
    if len(body.candles) < min_candles:
        raise HTTPException(status_code=400, detail=f"Cần tối thiểu {min_candles} nến OHLC")

    candles = [
        Candle(
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            volume=item.volume,
            time=item.time,
        )
        for item in body.candles
    ]
    result = classify_scalping(candles) if strategy == "scalping" else classify_trend(candles)
    return {
        "status": "ok",
        "symbol": body.symbol.upper(),
        "timeframe": body.timeframe.upper(),
        "strategy": strategy,
        "trend": result.trend,
        "signal": result.signal,
        "confidence": result.confidence,
        "reason": result.reason,
        "entry_price": result.entry_price,
        "sl_price": result.sl_price,
        "tp_price": result.tp_price,
        "indicators": result.indicators,
    }


@router.post("/web-bot/paper-trade")
async def create_paper_trade(body: PaperTradeRequest, admin=Depends(admin_required),
                             db: AsyncSession = Depends(get_db)):
    """Ghi một lệnh paper từ dashboard để test flow trade log trước khi nối MT5."""
    direction = body.direction.upper()
    if direction not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="direction phải là BUY hoặc SELL")

    ticket = f"WEB-{uuid.uuid4().hex[:12].upper()}"
    trade = TradeLog(
        license_key="WEB_PAPER",
        ticket=ticket,
        symbol=body.symbol.upper(),
        direction=direction,
        entry_price=body.entry_price,
        sl_price=body.sl_price,
        tp_price=body.tp_price,
        lot_size=body.lot_size,
        status="open",
        note=body.note or "Created by Web AI Bot paper mode",
    )
    db.add(trade)
    await db.commit()
    return {"status": "ok", "message": "Paper trade đã được ghi nhận", "ticket": ticket}


@router.get("/sessions")
async def list_sessions(limit: int = 50, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Log kết nối gần nhất của bot"""
    result = await db.execute(
        select(BotSession).order_by(BotSession.created_at.desc()).limit(limit)
    )
    sessions = result.scalars().all()
    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "license_key": s.license_key[:8] + "...",
            "ip_address": s.ip_address,
            "action": s.action,
            "reason": s.reason,
            "mt_account": s.mt_account,
            "created_at": s.created_at,
        }
        for s in sessions
    ]


@router.get("/trades")
async def list_trades(license_key: Optional[str] = None, symbol: Optional[str] = None,
                      status: Optional[str] = None, direction: Optional[str] = None,
                      limit: int = 100,
                      admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Danh sách lệnh giao dịch"""
    q = select(TradeLog).order_by(TradeLog.opened_at.desc())
    if license_key:
        q = q.where(TradeLog.license_key == license_key)
    if symbol:
        q = q.where(TradeLog.symbol == symbol.upper())
    if status:
        q = q.where(TradeLog.status == status.lower())
    if direction:
        q = q.where(TradeLog.direction == direction.upper())
    q = q.limit(limit)
    result = await db.execute(q)
    trades = result.scalars().all()
    return [
        {
            "id": t.id,
            "license_key": t.license_key,
            "ticket": t.ticket,
            "symbol": t.symbol,
            "direction": t.direction,
            "entry_price": t.entry_price,
            "sl_price": t.sl_price,
            "tp_price": t.tp_price,
            "lot_size": t.lot_size,
            "status": t.status,
            "close_price": t.close_price,
            "profit": t.profit,
            "pips": t.pips,
            "opened_at": t.opened_at,
            "closed_at": t.closed_at,
            "note": t.note,
        }
        for t in trades
    ]


@router.get("/notifications")
async def list_notifications(limit: int = 20, admin=Depends(admin_required), db: AsyncSession = Depends(get_db)):
    """Recent trade/session events for dashboard toast notifications."""
    trade_rows = (
        await db.execute(select(TradeLog).order_by(TradeLog.opened_at.desc()).limit(limit))
    ).scalars().all()
    session_rows = (
        await db.execute(select(BotSession).order_by(BotSession.created_at.desc()).limit(limit))
    ).scalars().all()
    runtime_rows = (
        await db.execute(select(BotRuntimeStatus).order_by(BotRuntimeStatus.updated_at.desc()).limit(limit))
    ).scalars().all()

    events = []
    for trade in trade_rows:
        event_time = trade.closed_at if trade.status == "closed" and trade.closed_at else trade.opened_at
        if trade.status == "closed":
            title = f"Closed {trade.symbol} {trade.direction}"
            message = f"Ticket {trade.ticket} | P/L {trade.profit or 0:+.2f} | {trade.pips or 0:+.1f} pips"
        else:
            title = f"Opened {trade.symbol} {trade.direction}"
            message = f"Ticket {trade.ticket} | Lot {trade.lot_size} | Entry {trade.entry_price}"
        events.append(
            {
                "id": f"trade-{trade.id}-{trade.status}-{event_time.isoformat()}",
                "type": "trade",
                "severity": "ok" if (trade.profit or 0) >= 0 else "warn",
                "title": title,
                "message": message,
                "created_at": event_time,
            }
        )

    for session in session_rows:
        if session.action not in {"reject", "verify", "user_login", "device_lock"}:
            continue
        severity = "bad" if session.action == "reject" else ("warn" if session.action == "device_lock" else "ok")
        events.append(
            {
                "id": f"session-{session.id}-{session.action}",
                "type": "session",
                "severity": severity,
                "title": f"Bot {session.action}",
                "message": f"{session.license_key[:8]}... | {session.ip_address} | {session.reason or '-'}",
                "created_at": session.created_at,
            }
        )

    for status in runtime_rows:
        severity = "ok" if status.run_state in {"opened", "ready"} else ("bad" if status.run_state == "error" else "warn")
        events.append(
            {
                "id": f"runtime-{status.id}-{status.updated_at.isoformat()}",
                "type": "runtime",
                "severity": severity,
                "title": f"{status.symbol} {status.signal}",
                "message": status.reason or f"Spread {status.spread_points or 0:.1f} | positions {status.open_positions}/{status.max_positions}",
                "created_at": status.updated_at,
            }
        )

    recent_users = (
        await db.execute(select(User).order_by(User.created_at.desc()).limit(limit))
    ).scalars().all()
    for user in recent_users:
        source = "tự đăng ký" if (user.note or "").lower().find("tự đăng ký") >= 0 or bool(user.password_hash) else "admin tạo"
        events.append(
            {
                "id": f"user-{user.id}-{user.created_at.isoformat()}",
                "type": "user",
                "severity": "ok",
                "title": f"User mới: {user.username}",
                "message": f"{user.email} | {source}",
                "created_at": user.created_at,
            }
        )

    events.sort(key=lambda item: item["created_at"], reverse=True)
    return events[:limit]
