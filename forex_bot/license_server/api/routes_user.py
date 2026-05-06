"""
User portal routes: khách hàng xem trạng thái bot, MT5 account và lịch sử lệnh
theo đúng license của họ. Không cấp quyền admin.
"""

from datetime import datetime, timezone
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import BotCommand, BotRuntimeStatus, BotSession, License, MT5Account, PortalDeviceLock, TradeLog, User, get_db
from core.security import encrypt_secret, hash_password, require_user_portal, verify_password


router = APIRouter()


class UserMT5CommandRequest(BaseModel):
    action: str
    reason: Optional[str] = None


class CreateUserMT5AccountRequest(BaseModel):
    label: Optional[str] = None
    broker: Optional[str] = None
    mt_login: str
    mt_password: str
    mt_server: str
    symbol_mode: str = "XAU"
    symbols: Optional[str] = None
    timeframe: str = "M1"
    lot_size: float = 0.01
    max_positions: int = 10
    max_total_positions: int = 10
    dry_run: bool = True
    note: Optional[str] = None


class UpdateUserMT5AccountRequest(BaseModel):
    label: Optional[str] = None
    broker: Optional[str] = None
    mt_login: Optional[str] = None
    mt_password: Optional[str] = None
    mt_server: Optional[str] = None
    symbol_mode: Optional[str] = None
    symbols: Optional[str] = None
    timeframe: Optional[str] = None
    lot_size: Optional[float] = None
    max_positions: Optional[int] = None
    max_total_positions: Optional[int] = None
    dry_run: Optional[bool] = None
    note: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    note: Optional[str] = None


class ChangeUserPasswordRequest(BaseModel):
    old_password: str
    new_password: str


USER_MT5_SYMBOL_PRESETS = {
    "XAU": ("XAUUSDm", 350),
    "ETH": ("ETHUSDm", 5000),
    "BTC": ("BTCUSDm", 20000),
    "CRYPTO": ("ETHUSDm,BTCUSDm", 20000),
    "ALL": ("XAUUSDm,ETHUSDm,BTCUSDm", 20000),
}
USER_MT5_TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1"}
USER_MT5_ACCOUNT_ACTIONS = {"start", "stop", "restart"}
RUNNABLE_ACCOUNT_STATUSES = {"waiting_client", "pending_start", "pending_restart", "running"}


async def user_required(authorization: str = Header(...)) -> dict:
    token = authorization.replace("Bearer ", "")
    return require_user_portal(token)


def is_expired(value: datetime | None) -> bool:
    if not value:
        return False
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < now


def seconds_since(value: datetime | None) -> Optional[int]:
    if not value:
        return None
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int((now - value).total_seconds())


def normalize_blank(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_user_mt5_symbols(symbol_mode: str, symbols: Optional[str]) -> tuple[str, str, int]:
    mode = (symbol_mode or "XAU").strip().upper()
    custom_symbols = ",".join(part.strip() for part in (symbols or "").split(",") if part.strip())
    if mode == "CUSTOM":
        if not custom_symbols:
            raise HTTPException(status_code=400, detail="CUSTOM cần nhập danh sách symbols")
        return mode, custom_symbols, 350
    if mode not in USER_MT5_SYMBOL_PRESETS:
        raise HTTPException(status_code=400, detail="symbol_mode phải là XAU, ETH, BTC, CRYPTO, ALL hoặc CUSTOM")
    preset_symbols, preset_spread = USER_MT5_SYMBOL_PRESETS[mode]
    if custom_symbols and custom_symbols.upper() != preset_symbols.upper():
        return mode, custom_symbols, preset_spread
    return mode, preset_symbols, preset_spread


async def load_user_context(payload: dict, db: AsyncSession) -> tuple[User, License]:
    user_id = int(payload.get("sub") or 0)
    license_key = str(payload.get("license_key") or "").strip().upper()
    result = await db.execute(
        select(User, License)
        .join(License, License.user_id == User.id)
        .where(User.id == user_id, License.license_key == license_key)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=403, detail="Không tìm thấy quyền truy cập license")

    user, license_ = row
    if not user.is_active or is_expired(user.expires_at):
        raise HTTPException(status_code=403, detail="Tài khoản không còn hiệu lực")
    if not license_.is_active or is_expired(license_.expires_at):
        raise HTTPException(status_code=403, detail="License không còn hiệu lực")
    device_result = await db.execute(
        select(PortalDeviceLock).where(PortalDeviceLock.license_key == license_.license_key)
    )
    device_lock = device_result.scalar_one_or_none()
    if device_lock and payload.get("device_id") != device_lock.device_id:
        raise HTTPException(status_code=403, detail="Thiết bị không được phép truy cập license này")
    return user, license_


def account_to_user_dict(account: MT5Account) -> dict[str, Any]:
    return {
        "id": account.id,
        "label": account.label,
        "broker": account.broker,
        "mt_login": account.mt_login,
        "mt_server": account.mt_server,
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
        "created_by": account.created_by,
        "last_error": account.last_error,
        "note": account.note,
        "updated_at": account.updated_at,
        "last_started_at": account.last_started_at,
        "last_stopped_at": account.last_stopped_at,
    }


def command_to_user_dict(command: BotCommand) -> dict[str, Any]:
    payload: Any = None
    if command.payload:
        try:
            payload = json.loads(command.payload)
        except json.JSONDecodeError:
            payload = command.payload
    return {
        "id": command.id,
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


def runtime_status_to_user_dict(status: BotRuntimeStatus) -> dict[str, Any]:
    payload: Any = {}
    if status.payload:
        try:
            payload = json.loads(status.payload)
        except json.JSONDecodeError:
            payload = status.payload
    return {
        "id": status.id,
        "license_key": status.license_key,
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


def money_round(value: Any) -> float:
    return round(float(value or 0), 2)


def normalize_dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def event_time(value: Optional[datetime]) -> str:
    dt = normalize_dt(value) or datetime.now(timezone.utc)
    return dt.isoformat()


def license_is_online(license_: License, now: Optional[datetime] = None) -> bool:
    age = seconds_since(license_.last_verified)
    return bool(
        license_.is_active
        and age is not None
        and age <= settings.BOT_PING_TIMEOUT_SECONDS
    )


def account_command_message(action: str, bot_online: bool) -> str:
    if action == "start":
        return "Đã bật chạy. Bot máy khách đang online nên sẽ nhận lệnh ngay." if bot_online else "Đã bật chạy. Mở watchdog/bot trên máy khách để bắt đầu."
    if action == "stop":
        return "Đã gửi lệnh dừng cho bot máy khách." if bot_online else "Đã tạm dừng tài khoản MT5."
    if action == "restart":
        return "Đã yêu cầu watchdog máy khách restart bot." if bot_online else "Đã bật lại trạng thái chờ máy khách."
    return "Đã cập nhật trạng thái tài khoản MT5"


async def enqueue_account_command(
    db: AsyncSession,
    license_key: str,
    account_id: int,
    command_action: str,
    reason: Optional[str],
    now: datetime,
) -> None:
    await db.execute(
        update(BotCommand)
        .where(
            BotCommand.target_license_key == license_key,
            BotCommand.action == command_action,
            BotCommand.status == "pending",
        )
        .values(
            status="cancelled",
            result="Superseded by newer user account command",
            completed_at=now,
        )
    )
    db.add(
        BotCommand(
            target_license_key=license_key,
            action=command_action,
            payload=json.dumps({"source": "user_mt5_account", "account_id": account_id}, ensure_ascii=False),
            reason=reason or f"User portal {command_action}",
            status="pending",
        )
    )


@router.get("/me")
async def me(payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    user, license_ = await load_user_context(payload, db)
    age = seconds_since(license_.last_verified)
    online = (
        license_.is_active
        and age is not None
        and age <= settings.BOT_PING_TIMEOUT_SECONDS
    )
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "note": user.note,
            "created_at": user.created_at,
            "expires_at": user.expires_at,
        },
        "license": {
            "license_key": license_.license_key,
            "allowed_ip": license_.allowed_ip,
            "mt_account": license_.mt_account,
            "is_active": license_.is_active,
            "expires_at": license_.expires_at,
            "last_verified": license_.last_verified,
            "seconds_since_seen": age,
            "online": online,
        },
    }


@router.patch("/me")
async def update_me(body: UpdateProfileRequest, payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    user, _ = await load_user_context(payload, db)
    values: dict[str, Any] = {}
    if body.username is not None:
        username = body.username.strip()
        if len(username) < 3:
            raise HTTPException(status_code=400, detail="Tên hiển thị tối thiểu 3 ký tự")
        if len(username) > 64:
            raise HTTPException(status_code=400, detail="Tên hiển thị tối đa 64 ký tự")
        exists = await db.execute(select(User.id).where(User.username == username, User.id != user.id))
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Tên hiển thị đã tồn tại")
        values["username"] = username
    if body.note is not None:
        values["note"] = body.note.strip()[:500] or None
    if not values:
        raise HTTPException(status_code=400, detail="Không có thay đổi nào")
    await db.execute(update(User).where(User.id == user.id).values(**values))
    await db.commit()
    return {"message": "Đã cập nhật hồ sơ"}


@router.post("/change-password")
async def change_user_password(body: ChangeUserPasswordRequest,
                               payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    user, _ = await load_user_context(payload, db)
    if not user.password_hash or not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")
    if len(body.new_password or "") < 8:
        raise HTTPException(status_code=400, detail="Mật khẩu mới tối thiểu 8 ký tự")
    await db.execute(update(User).where(User.id == user.id).values(password_hash=hash_password(body.new_password)))
    await db.commit()
    return {"message": "Đã đổi mật khẩu"}


@router.get("/summary")
async def summary(payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    user, license_ = await load_user_context(payload, db)
    license_key = license_.license_key

    open_trades = (await db.execute(
        select(func.count(TradeLog.id)).where(TradeLog.license_key == license_key, TradeLog.status == "open")
    )).scalar_one()
    total_trades = (await db.execute(
        select(func.count(TradeLog.id)).where(TradeLog.license_key == license_key)
    )).scalar_one()
    closed_trades = (await db.execute(
        select(func.count(TradeLog.id)).where(TradeLog.license_key == license_key, TradeLog.status == "closed")
    )).scalar_one()
    closed_profit = (await db.execute(
        select(func.coalesce(func.sum(TradeLog.profit), 0.0)).where(
            TradeLog.license_key == license_key,
            TradeLog.status == "closed",
        )
    )).scalar_one()
    winning_trades = (await db.execute(
        select(func.count(TradeLog.id)).where(
            TradeLog.license_key == license_key,
            TradeLog.status == "closed",
            TradeLog.profit > 0,
        )
    )).scalar_one()
    losing_trades = (await db.execute(
        select(func.count(TradeLog.id)).where(
            TradeLog.license_key == license_key,
            TradeLog.status == "closed",
            TradeLog.profit < 0,
        )
    )).scalar_one()
    gross_profit = (await db.execute(
        select(func.coalesce(func.sum(TradeLog.profit), 0.0)).where(
            TradeLog.license_key == license_key,
            TradeLog.status == "closed",
            TradeLog.profit > 0,
        )
    )).scalar_one()
    gross_loss = (await db.execute(
        select(func.coalesce(func.sum(TradeLog.profit), 0.0)).where(
            TradeLog.license_key == license_key,
            TradeLog.status == "closed",
            TradeLog.profit < 0,
        )
    )).scalar_one()
    total_lot = (await db.execute(
        select(func.coalesce(func.sum(TradeLog.lot_size), 0.0)).where(TradeLog.license_key == license_key)
    )).scalar_one()
    open_lot = (await db.execute(
        select(func.coalesce(func.sum(TradeLog.lot_size), 0.0)).where(
            TradeLog.license_key == license_key,
            TradeLog.status == "open",
        )
    )).scalar_one()
    closed_pips = (await db.execute(
        select(func.coalesce(func.sum(TradeLog.pips), 0.0)).where(
            TradeLog.license_key == license_key,
            TradeLog.status == "closed",
        )
    )).scalar_one()
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_profit = (await db.execute(
        select(func.coalesce(func.sum(TradeLog.profit), 0.0)).where(
            TradeLog.license_key == license_key,
            TradeLog.status == "closed",
            TradeLog.closed_at >= today_start,
        )
    )).scalar_one()

    accounts = (await db.execute(
        select(MT5Account)
        .where(MT5Account.user_id == user.id, MT5Account.license_key == license_key)
        .order_by(MT5Account.updated_at.desc())
    )).scalars().all()
    account_status_counts: dict[str, int] = {}
    for account in accounts:
        key = account.run_status or "unknown"
        account_status_counts[key] = account_status_counts.get(key, 0) + 1
    pending_commands = (await db.execute(
        select(func.count(BotCommand.id)).where(
            BotCommand.target_license_key == license_key,
            BotCommand.status.in_(["pending", "delivered"]),
        )
    )).scalar_one()
    latest_trade = (await db.execute(
        select(TradeLog)
        .where(TradeLog.license_key == license_key)
        .order_by(TradeLog.opened_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    symbol_rows = (await db.execute(
        select(
            TradeLog.symbol,
            func.count(TradeLog.id),
            func.coalesce(func.sum(TradeLog.profit), 0.0),
            func.coalesce(func.sum(TradeLog.lot_size), 0.0),
        )
        .where(TradeLog.license_key == license_key)
        .group_by(TradeLog.symbol)
        .order_by(func.coalesce(func.sum(TradeLog.profit), 0.0).desc())
        .limit(8)
    )).all()
    direction_rows = (await db.execute(
        select(
            TradeLog.direction,
            func.count(TradeLog.id),
            func.coalesce(func.sum(TradeLog.profit), 0.0),
            func.coalesce(func.sum(TradeLog.lot_size), 0.0),
        )
        .where(TradeLog.license_key == license_key)
        .group_by(TradeLog.direction)
    )).all()

    seen_age = seconds_since(license_.last_verified)
    gross_loss_abs = abs(float(gross_loss or 0))
    win_rate = (float(winning_trades or 0) / float(closed_trades or 1) * 100) if closed_trades else 0.0
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "license": {
            "license_key": license_key,
            "allowed_ip": license_.allowed_ip,
            "mt_account": license_.mt_account,
            "last_verified": license_.last_verified,
            "seconds_since_seen": seen_age,
            "online": seen_age is not None and seen_age <= settings.BOT_PING_TIMEOUT_SECONDS,
        },
        "stats": {
            "open_trades": open_trades,
            "total_trades": total_trades,
            "closed_trades": closed_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "closed_profit": round(float(closed_profit or 0), 2),
            "gross_profit": money_round(gross_profit),
            "gross_loss": money_round(gross_loss),
            "profit_factor": round(float(gross_profit or 0) / gross_loss_abs, 2) if gross_loss_abs else None,
            "today_profit": round(float(today_profit or 0), 2),
            "total_lot": round(float(total_lot or 0), 4),
            "open_lot": round(float(open_lot or 0), 4),
            "closed_pips": round(float(closed_pips or 0), 1),
            "mt5_accounts": len(accounts),
            "active_mt5_accounts": len([account for account in accounts if account.is_active]),
            "account_status_counts": account_status_counts,
            "pending_commands": pending_commands,
            "latest_trade": {
                "ticket": latest_trade.ticket,
                "symbol": latest_trade.symbol,
                "direction": latest_trade.direction,
                "status": latest_trade.status,
                "profit": latest_trade.profit,
                "opened_at": latest_trade.opened_at,
            } if latest_trade else None,
            "symbols": [
                {"symbol": row[0] or "-", "total": row[1], "profit": money_round(row[2]), "lot": round(float(row[3] or 0), 4)}
                for row in symbol_rows
            ],
            "directions": [
                {"direction": row[0] or "-", "total": row[1], "profit": money_round(row[2]), "lot": round(float(row[3] or 0), 4)}
                for row in direction_rows
            ],
        },
        "accounts": [account_to_user_dict(account) for account in accounts],
    }


@router.get("/notifications")
async def notifications(limit: int = 30, payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    user, license_ = await load_user_context(payload, db)
    limit = min(max(limit, 1), 80)
    events: list[dict[str, Any]] = []

    trades_rows = (await db.execute(
        select(TradeLog)
        .where(TradeLog.license_key == license_.license_key)
        .order_by(TradeLog.opened_at.desc())
        .limit(limit)
    )).scalars().all()
    for trade in trades_rows:
        profit = float(trade.profit or 0)
        events.append({
            "id": f"trade-{trade.id}-{trade.status}",
            "type": "trade",
            "severity": "ok" if profit >= 0 else "warn",
            "title": f"{trade.status.upper()} {trade.symbol} {trade.direction}",
            "message": f"Ticket {trade.ticket} | Lot {trade.lot_size} | P/L {profit:+.2f}",
            "created_at": event_time(trade.closed_at if trade.status == "closed" and trade.closed_at else trade.opened_at),
        })

    account_rows = (await db.execute(
        select(MT5Account)
        .where(MT5Account.user_id == user.id, MT5Account.license_key == license_.license_key)
        .order_by(MT5Account.updated_at.desc())
        .limit(limit)
    )).scalars().all()
    for account in account_rows:
        severity = "bad" if account.run_status == "error" else ("ok" if account.run_status == "running" else "warn")
        events.append({
            "id": f"account-{account.id}-{account.updated_at.isoformat()}",
            "type": "account",
            "severity": severity,
            "title": f"MT5 {account.mt_login} - {account.run_status}",
            "message": account.last_error or account.note or f"{account.symbols} | {account.timeframe} | lot {account.lot_size}",
            "created_at": event_time(account.updated_at),
        })

    runtime_rows = (await db.execute(
        select(BotRuntimeStatus)
        .where(BotRuntimeStatus.license_key == license_.license_key)
        .order_by(BotRuntimeStatus.updated_at.desc())
        .limit(limit)
    )).scalars().all()
    for status in runtime_rows:
        severity = "ok" if status.run_state in {"opened", "ready"} else ("bad" if status.run_state == "error" else "warn")
        events.append({
            "id": f"runtime-{status.id}-{status.updated_at.isoformat()}",
            "type": "runtime",
            "severity": severity,
            "title": f"{status.symbol} {status.signal}",
            "message": status.reason or f"Spread {status.spread_points or 0:.1f} | positions {status.open_positions}/{status.max_positions}",
            "created_at": event_time(status.updated_at),
        })

    command_rows = (await db.execute(
        select(BotCommand)
        .where(BotCommand.target_license_key == license_.license_key)
        .order_by(BotCommand.created_at.desc())
        .limit(limit)
    )).scalars().all()
    for command in command_rows:
        events.append({
            "id": f"command-{command.id}-{command.status}",
            "type": "command",
            "severity": "bad" if command.status == "failed" else ("ok" if command.status == "done" else "warn"),
            "title": f"Command {command.action}",
            "message": command.result or command.reason or f"Trạng thái {command.status}",
            "created_at": event_time(command.completed_at or command.created_at),
        })

    session_rows = (await db.execute(
        select(BotSession)
        .where(BotSession.license_key == license_.license_key)
        .order_by(BotSession.created_at.desc())
        .limit(limit)
    )).scalars().all()
    for session in session_rows:
        events.append({
            "id": f"session-{session.id}",
            "type": "session",
            "severity": "bad" if session.action == "reject" else "ok",
            "title": f"Phiên {session.action}",
            "message": session.reason or f"IP {session.ip_address}",
            "created_at": event_time(session.created_at),
        })

    events.sort(key=lambda item: item["created_at"], reverse=True)
    return events[:limit]


@router.get("/mt5-accounts")
async def mt5_accounts(payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    user, license_ = await load_user_context(payload, db)
    result = await db.execute(
        select(MT5Account)
        .where(MT5Account.user_id == user.id, MT5Account.license_key == license_.license_key)
        .order_by(MT5Account.updated_at.desc())
    )
    return [account_to_user_dict(account) for account in result.scalars().all()]


@router.get("/bot-statuses")
async def bot_statuses(limit: int = 50, payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    """Lý do bot vào/chưa vào lệnh mới nhất cho license của user."""
    _, license_ = await load_user_context(payload, db)
    result = await db.execute(
        select(BotRuntimeStatus)
        .where(BotRuntimeStatus.license_key == license_.license_key)
        .order_by(BotRuntimeStatus.updated_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    return [runtime_status_to_user_dict(status) for status in result.scalars().all()]


@router.post("/mt5-accounts")
async def create_mt5_account(body: CreateUserMT5AccountRequest,
                             payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    user, license_ = await load_user_context(payload, db)
    mt_login = body.mt_login.strip()
    mt_server = body.mt_server.strip()
    mt_password = body.mt_password.strip()
    timeframe = body.timeframe.strip().upper() or "M1"

    if not mt_login:
        raise HTTPException(status_code=400, detail="MT5 login không được trống")
    if not mt_server:
        raise HTTPException(status_code=400, detail="MT5 server không được trống")
    if not mt_password:
        raise HTTPException(status_code=400, detail="Mật khẩu MT5 không được trống")
    if timeframe not in USER_MT5_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"timeframe phải thuộc: {', '.join(sorted(USER_MT5_TIMEFRAMES))}")
    if body.lot_size <= 0:
        raise HTTPException(status_code=400, detail="lot_size phải lớn hơn 0")
    if body.max_positions <= 0 or body.max_total_positions <= 0:
        raise HTTPException(status_code=400, detail="Giới hạn lệnh phải lớn hơn 0")
    if body.max_total_positions < body.max_positions:
        raise HTTPException(status_code=400, detail="Max tổng lệnh phải lớn hơn hoặc bằng max lệnh / symbol")

    existing = await db.execute(
        select(MT5Account).where(
            MT5Account.user_id == user.id,
            MT5Account.license_key == license_.license_key,
            MT5Account.mt_login == mt_login,
            MT5Account.mt_server == mt_server,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tài khoản MT5 này đã được gửi trước đó")

    mode, symbols, max_spread = normalize_user_mt5_symbols(body.symbol_mode, body.symbols)
    note_parts = [normalize_blank(body.note), "User portal submit: user tự vận hành"]
    account = MT5Account(
        user_id=user.id,
        license_key=license_.license_key,
        label=normalize_blank(body.label),
        broker=normalize_blank(body.broker),
        mt_login=mt_login,
        mt_server=mt_server,
        mt_password_encrypted=encrypt_secret(mt_password),
        symbol_mode=mode,
        symbols=symbols,
        timeframe=timeframe,
        lot_size=body.lot_size,
        max_positions=body.max_positions,
        max_total_positions=body.max_total_positions,
        max_spread_points=max_spread,
        dry_run=body.dry_run,
        is_active=True,
        run_status="waiting_client",
        created_by="user",
        note=" | ".join(part for part in note_parts if part),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return {
        "message": "Đã lưu tài khoản MT5 và bật trạng thái chờ máy khách. Mở watchdog/bot trên máy khách để chạy.",
        "account": account_to_user_dict(account),
    }


@router.patch("/mt5-accounts/{account_id}")
async def update_mt5_account(account_id: int, body: UpdateUserMT5AccountRequest,
                             payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    user, license_ = await load_user_context(payload, db)
    account = await db.get(MT5Account, account_id)
    if not account or account.user_id != user.id or account.license_key != license_.license_key:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản MT5")

    data = body.model_dump(exclude_unset=True)
    values: dict[str, Any] = {}

    mt_login = str(data.get("mt_login", account.mt_login) or "").strip()
    mt_server = str(data.get("mt_server", account.mt_server) or "").strip()
    if "mt_login" in data:
        if not mt_login:
            raise HTTPException(status_code=400, detail="MT5 login không được trống")
        values["mt_login"] = mt_login
    if "mt_server" in data:
        if not mt_server:
            raise HTTPException(status_code=400, detail="MT5 server không được trống")
        values["mt_server"] = mt_server
    if ("mt_login" in data or "mt_server" in data) and (mt_login != account.mt_login or mt_server != account.mt_server):
        duplicate = await db.execute(
            select(MT5Account.id).where(
                MT5Account.user_id == user.id,
                MT5Account.license_key == license_.license_key,
                MT5Account.mt_login == mt_login,
                MT5Account.mt_server == mt_server,
                MT5Account.id != account.id,
            )
        )
        if duplicate.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Tài khoản MT5 này đã tồn tại")

    if "mt_password" in data:
        password = str(data.pop("mt_password") or "").strip()
        if password:
            values["mt_password_encrypted"] = encrypt_secret(password)

    if "symbol_mode" in data or "symbols" in data:
        mode, symbols, max_spread = normalize_user_mt5_symbols(
            data.get("symbol_mode", account.symbol_mode),
            data.get("symbols", account.symbols),
        )
        values["symbol_mode"] = mode
        values["symbols"] = symbols
        values["max_spread_points"] = max_spread

    if "timeframe" in data:
        timeframe = str(data["timeframe"] or account.timeframe or "M1").strip().upper()
        if timeframe not in USER_MT5_TIMEFRAMES:
            raise HTTPException(status_code=400, detail=f"timeframe phải thuộc: {', '.join(sorted(USER_MT5_TIMEFRAMES))}")
        values["timeframe"] = timeframe
    if "lot_size" in data:
        if data["lot_size"] is None or data["lot_size"] <= 0:
            raise HTTPException(status_code=400, detail="lot_size phải lớn hơn 0")
        values["lot_size"] = data["lot_size"]
    if "max_positions" in data:
        if data["max_positions"] is None or data["max_positions"] <= 0:
            raise HTTPException(status_code=400, detail="max_positions phải lớn hơn 0")
        values["max_positions"] = data["max_positions"]
    if "max_total_positions" in data:
        if data["max_total_positions"] is None or data["max_total_positions"] <= 0:
            raise HTTPException(status_code=400, detail="max_total_positions phải lớn hơn 0")
        values["max_total_positions"] = data["max_total_positions"]

    next_max_positions = int(values.get("max_positions", account.max_positions))
    next_max_total_positions = int(values.get("max_total_positions", account.max_total_positions))
    if next_max_total_positions < next_max_positions:
        raise HTTPException(status_code=400, detail="Max tổng lệnh phải lớn hơn hoặc bằng max lệnh / symbol")

    for field in ["label", "broker", "note"]:
        if field in data:
            values[field] = normalize_blank(data[field])
    if "dry_run" in data:
        values["dry_run"] = bool(data["dry_run"])

    if not values:
        raise HTTPException(status_code=400, detail="Không có thay đổi nào")

    values["updated_at"] = datetime.now(timezone.utc)
    await db.execute(update(MT5Account).where(MT5Account.id == account_id).values(**values))
    await db.commit()
    updated = await db.get(MT5Account, account_id)
    return {
        "message": "Đã cập nhật tài khoản MT5. Nếu bot đang chạy, bấm Restart để áp dụng cấu hình mới.",
        "account": account_to_user_dict(updated),
    }


@router.post("/mt5-accounts/{account_id}/command")
async def command_mt5_account(account_id: int, body: UserMT5CommandRequest,
                              payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    user, license_ = await load_user_context(payload, db)
    account = await db.get(MT5Account, account_id)
    if not account or account.user_id != user.id or account.license_key != license_.license_key:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản MT5")

    action = body.action.strip().lower()
    if action not in USER_MT5_ACCOUNT_ACTIONS:
        raise HTTPException(status_code=400, detail="action phải là start, stop hoặc restart")

    now = datetime.now(timezone.utc)
    bot_online = license_is_online(license_, now)
    values: dict[str, Any] = {"updated_at": now}
    command_action: Optional[str] = None

    if action == "start":
        values.update({
            "is_active": True,
            "run_status": "running" if bot_online else "waiting_client",
            "last_error": None,
            "last_started_at": now,
        })
        if bot_online:
            command_action = "resume"
    elif action == "stop":
        values.update({
            "is_active": False,
            "run_status": "pending_stop" if bot_online else "paused",
            "last_stopped_at": now,
        })
        if bot_online:
            command_action = "pause"
    elif action == "restart":
        values.update({
            "is_active": True,
            "run_status": "pending_restart" if bot_online else "waiting_client",
            "last_error": None,
            "last_started_at": now,
        })

    if command_action:
        await enqueue_account_command(
            db,
            license_.license_key,
            account.id,
            command_action,
            body.reason or f"User portal {action}",
            now,
        )

    await db.execute(update(MT5Account).where(MT5Account.id == account_id).values(**values))
    await db.commit()
    updated = await db.get(MT5Account, account_id)
    return {
        "message": account_command_message(action, bot_online),
        "account": account_to_user_dict(updated),
    }


@router.get("/trades")
async def trades(status: Optional[str] = None, direction: Optional[str] = None,
                 symbol: Optional[str] = None, limit: int = 100,
                 payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    _, license_ = await load_user_context(payload, db)
    q = select(TradeLog).where(TradeLog.license_key == license_.license_key).order_by(TradeLog.opened_at.desc())
    if status:
        q = q.where(TradeLog.status == status.lower())
    if direction:
        q = q.where(TradeLog.direction == direction.upper())
    if symbol:
        q = q.where(TradeLog.symbol == symbol.upper())
    q = q.limit(min(max(limit, 1), 500))
    result = await db.execute(q)
    return [
        {
            "id": trade.id,
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
        for trade in result.scalars().all()
    ]


@router.get("/sessions")
async def sessions(limit: int = 50, payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    _, license_ = await load_user_context(payload, db)
    result = await db.execute(
        select(BotSession)
        .where(BotSession.license_key == license_.license_key)
        .order_by(BotSession.created_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    return [
        {
            "id": session.id,
            "ip_address": session.ip_address,
            "action": session.action,
            "reason": session.reason,
            "mt_account": session.mt_account,
            "created_at": session.created_at,
        }
        for session in result.scalars().all()
    ]


@router.get("/commands")
async def commands(limit: int = 50, payload=Depends(user_required), db: AsyncSession = Depends(get_db)):
    _, license_ = await load_user_context(payload, db)
    result = await db.execute(
        select(BotCommand)
        .where(BotCommand.target_license_key == license_.license_key)
        .order_by(BotCommand.created_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    return [command_to_user_dict(command) for command in result.scalars().all()]
