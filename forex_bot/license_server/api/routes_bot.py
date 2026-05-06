"""
Bot routes: Endpoint mà bot C++ gọi để xác thực license + IP
Logic:
  1. Bot gửi license_key + IP thực + MT account
  2. Server kiểm tra license, IP, hạn dùng
  3. Nếu IP chưa lock → tự động lock vào IP đó (lần đầu kết nối)
  4. Nếu IP khác → từ chối, ghi log
  5. Trả về JWT token ngắn hạn cho bot dùng để ping định kỳ
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Any, Optional
from datetime import datetime, timezone
import json
import os
import httpx

from core.database import get_db, License, User, BotSession, TradeLog, BotCommand, MT5Account, BotRuntimeStatus
from core.request_utils import get_client_ip
from core.security import create_bot_token
from core.config import settings

router = APIRouter()


def validate_bot_token(bot_token: str, license_key: str) -> None:
    from core.security import decode_token
    payload = decode_token(bot_token)
    if payload.get("sub") != license_key:
        raise HTTPException(status_code=403, detail="Token không khớp license")


# ─── Schemas ──────────────────────────────────────────────────────────────────

class VerifyRequest(BaseModel):
    license_key: str
    mt_account:  Optional[str] = None   # MT4/MT5 account number (tùy chọn kiểm tra thêm)
    hosted_runner: bool = False


class PingRequest(BaseModel):
    bot_token:   str
    license_key: str
    hosted_runner: bool = False


class TradeReportRequest(BaseModel):
    bot_token:   str
    license_key: str
    ticket:      str
    symbol:      str
    direction:   str        # "BUY" | "SELL"
    entry_price: float
    sl_price:    Optional[float] = None
    tp_price:    Optional[float] = None
    lot_size:    float
    status:      str        # "open" | "closed" | "cancelled"
    close_price: Optional[float] = None
    profit:      Optional[float] = None
    pips:        Optional[float] = None
    note:        Optional[str] = None


class PositionSnapshot(BaseModel):
    ticket:      str
    symbol:      str
    direction:   str
    entry_price: float
    sl_price:    Optional[float] = None
    tp_price:    Optional[float] = None
    lot_size:    float
    profit:      Optional[float] = None
    pips:        Optional[float] = None
    opened_at:   Optional[datetime] = None
    note:        Optional[str] = None


class PositionSyncRequest(BaseModel):
    bot_token:   str
    license_key: str
    mt_account:  Optional[str] = None
    positions:   list[PositionSnapshot] = []
    mark_missing_closed: bool = True


class BotStatusReportRequest(BaseModel):
    bot_token:           str
    license_key:         str
    mt_account:          Optional[str] = None
    symbol:              str
    timeframe:           Optional[str] = None
    strategy:            Optional[str] = None
    signal:              str = "HOLD"
    reason:              Optional[str] = None
    confidence:          Optional[float] = None
    spread_points:       Optional[float] = None
    open_positions:      int = 0
    total_positions:     int = 0
    max_positions:       int = 0
    max_total_positions: int = 0
    dry_run:             bool = True
    session_allowed:     bool = True
    run_state:           str = "idle"
    payload:             Optional[dict[str, Any]] = None


class CommandPollRequest(BaseModel):
    bot_token:   str
    license_key: str


class CommandAckRequest(BaseModel):
    bot_token:   str
    license_key: str
    status:      str
    result:      Optional[str] = None


class RunStateRequest(BaseModel):
    license_key: str
    mt_account: Optional[str] = None


def is_localhost_ip(ip_address: str) -> bool:
    return ip_address in {"127.0.0.1", "::1", "localhost"}


def is_hosted_runner_request(ip_address: str, hosted_runner: bool) -> bool:
    allow_bypass = os.getenv("ALLOW_HOSTED_RUNNER_IP_BYPASS", "").strip().lower() in {"1", "true", "yes", "on"}
    return allow_bypass and hosted_runner and is_localhost_ip(ip_address)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/verify")
async def verify_license(body: VerifyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Bot gọi endpoint này khi khởi động.
    Trả về token nếu hợp lệ, từ chối nếu sai IP / hết hạn / bị thu hồi.
    """
    client_ip = get_client_ip(request)
    hosted_runner = is_hosted_runner_request(client_ip, body.hosted_runner)

    # 1. Tìm license
    result = await db.execute(select(License).where(License.license_key == body.license_key))
    lic = result.scalar_one_or_none()

    async def log_session(action: str, reason: str = None):
        session = BotSession(
            user_id=lic.user_id if lic else 0,
            license_key=body.license_key,
            ip_address=client_ip,
            action=action,
            reason=reason,
            mt_account=body.mt_account,
        )
        db.add(session)
        await db.commit()

    if not lic:
        await log_session("reject", "License không tồn tại")
        raise HTTPException(status_code=403, detail="License không hợp lệ")

    if not lic.is_active:
        await log_session("reject", "License đã bị thu hồi")
        raise HTTPException(status_code=403, detail="License đã bị thu hồi")

    # 2. Kiểm tra hạn dùng
    if lic.expires_at and lic.expires_at < datetime.now(timezone.utc):
        await log_session("reject", f"License hết hạn: {lic.expires_at}")
        raise HTTPException(status_code=403, detail=f"License hết hạn vào {lic.expires_at.strftime('%Y-%m-%d')}")

    # 3. Kiểm tra user
    user = await db.get(User, lic.user_id)
    if not user or not user.is_active:
        await log_session("reject", "User bị vô hiệu hóa")
        raise HTTPException(status_code=403, detail="Tài khoản bị vô hiệu hóa")

    if user.expires_at and user.expires_at < datetime.now(timezone.utc):
        await log_session("reject", "User hết hạn")
        raise HTTPException(status_code=403, detail="Tài khoản hết hạn")

    account_query = select(MT5Account).where(MT5Account.license_key == body.license_key)
    if body.mt_account:
        account_query = account_query.where(MT5Account.mt_login == str(body.mt_account))
    account_result = await db.execute(account_query.order_by(MT5Account.id.desc()))
    mt5_account = account_result.scalars().first()
    start_allowed_statuses = {"waiting_client", "pending_start", "pending_restart", "running"}
    if mt5_account and (not mt5_account.is_active or mt5_account.run_status not in start_allowed_statuses):
        reason = f"Tài khoản MT5 chưa được user bật chạy: status={mt5_account.run_status}"
        await log_session("reject", reason)
        raise HTTPException(status_code=403, detail="Tài khoản MT5 chưa được bật chạy trên cổng khách hàng")

    # 4. Kiểm tra IP
    if hosted_runner:
        ip_status = f"Hosted runner nội bộ qua {client_ip}"
    elif lic.allowed_ip is None:
        # Lần đầu kết nối → tự động lock IP
        await db.execute(
            update(License).where(License.license_key == body.license_key).values(allowed_ip=client_ip)
        )
        ip_status = "IP đã được lock lần đầu"
    elif lic.allowed_ip != client_ip:
        # IP khác → từ chối ngay
        reason = f"IP không khớp: yêu cầu {client_ip}, được phép {lic.allowed_ip}"
        await log_session("reject", reason)
        # Thông báo cho admin qua Telegram
        await _notify_admin(f"⚠️ IP KHÔNG HỢP LỆ!\nLicense: {body.license_key[:8]}...\nIP cố truy cập: {client_ip}\nIP được phép: {lic.allowed_ip}")
        raise HTTPException(status_code=403, detail="IP không được phép. Liên hệ admin để cập nhật IP.")
    else:
        ip_status = "IP hợp lệ"

    # 5. Cập nhật last_verified + verify_count
    await db.execute(
        update(License).where(License.license_key == body.license_key).values(
            last_verified=datetime.now(timezone.utc),
            verify_count=License.verify_count + 1,
        )
    )
    account_runtime_update = (
        update(MT5Account)
        .where(MT5Account.license_key == body.license_key)
        .values(
            is_active=True,
            run_status="running",
            last_error=None,
            last_started_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    if body.mt_account:
        account_runtime_update = account_runtime_update.where(MT5Account.mt_login == str(body.mt_account))
    await db.execute(account_runtime_update)
    await db.commit()

    # 6. Tạo bot token
    token = create_bot_token(body.license_key, lic.user_id)
    await log_session("verify", ip_status)

    return {
        "status": "ok",
        "message": "Xác thực thành công",
        "bot_token": token,
        "token_expires_hours": settings.ACCESS_TOKEN_EXPIRE_HOURS,
        "user": user.username,
        "ip_locked": "hosted-runner" if hosted_runner else client_ip,
    }


@router.post("/ping")
async def ping(body: PingRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Bot gọi định kỳ (mỗi 5 phút) để giữ session.
    Trả về token mới nếu sắp hết hạn.
    """
    from core.security import decode_token
    client_ip = get_client_ip(request)

    payload = decode_token(body.bot_token)
    if payload.get("sub") != body.license_key:
        raise HTTPException(status_code=403, detail="Token không khớp license")

    # Xác thực lại IP nhanh
    result = await db.execute(select(License).where(License.license_key == body.license_key))
    lic = result.scalar_one_or_none()
    if not lic or not lic.is_active:
        raise HTTPException(status_code=403, detail="License không hợp lệ")
    hosted_runner = is_hosted_runner_request(client_ip, body.hosted_runner)
    if lic.allowed_ip and lic.allowed_ip != client_ip and not hosted_runner:
        raise HTTPException(status_code=403, detail="IP thay đổi, xác thực lại")

    # Cập nhật last ping
    await db.execute(
        update(License).where(License.license_key == body.license_key).values(
            last_verified=datetime.now(timezone.utc)
        )
    )
    await db.commit()

    # Cấp token mới
    new_token = create_bot_token(body.license_key, lic.user_id)
    return {"status": "ok", "bot_token": new_token}


@router.post("/run-state")
async def run_state(body: RunStateRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Watchdog máy khách hỏi server xem tài khoản có được phép chạy bot chưa."""
    client_ip = get_client_ip(request)
    result = await db.execute(select(License).where(License.license_key == body.license_key))
    lic = result.scalar_one_or_none()
    if not lic or not lic.is_active:
        raise HTTPException(status_code=403, detail="License không hợp lệ")
    if lic.allowed_ip and lic.allowed_ip != client_ip:
        raise HTTPException(status_code=403, detail="IP không được phép")

    user = await db.get(User, lic.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản bị vô hiệu hóa")
    if lic.expires_at and lic.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="License hết hạn")
    if user.expires_at and user.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="Tài khoản hết hạn")

    account_query = select(MT5Account).where(MT5Account.license_key == body.license_key)
    if body.mt_account:
        account_query = account_query.where(MT5Account.mt_login == str(body.mt_account))
    account_result = await db.execute(account_query.order_by(MT5Account.id.desc()))
    account = account_result.scalars().first()
    if not account:
        return {
            "status": "ok",
            "should_run": False,
            "run_status": "missing_account",
            "message": "Tài khoản MT5 chưa được thêm trên web",
            "poll_seconds": 5,
        }

    runnable_statuses = {"waiting_client", "pending_start", "pending_restart", "running"}
    should_run = bool(account.is_active and account.run_status in runnable_statuses)
    if account.run_status == "pending_restart" and should_run:
        message = "restart"
    else:
        message = "start" if should_run else "stop: user chưa bật chạy hoặc đã tạm dừng"
    return {
        "status": "ok",
        "account_id": account.id,
        "should_run": should_run,
        "run_status": account.run_status,
        "is_active": account.is_active,
        "message": message,
        "poll_seconds": 5,
    }


@router.post("/commands")
async def poll_commands(body: CommandPollRequest, db: AsyncSession = Depends(get_db)):
    """Bot poll các command admin đang chờ xử lý."""
    validate_bot_token(body.bot_token, body.license_key)

    result = await db.execute(
        select(BotCommand)
        .where(
            BotCommand.target_license_key == body.license_key,
            BotCommand.status == "pending",
        )
        .order_by(BotCommand.created_at.asc())
        .limit(20)
    )
    commands = result.scalars().all()
    now = datetime.now(timezone.utc)
    for command in commands:
        command.status = "delivered"
        command.delivered_at = now
    await db.commit()

    payload = []
    for command in commands:
        data = None
        if command.payload:
            try:
                data = json.loads(command.payload)
            except json.JSONDecodeError:
                data = command.payload
        payload.append(
            {
                "id": command.id,
                "action": command.action,
                "symbol": command.symbol,
                "payload": data,
                "reason": command.reason,
                "created_at": command.created_at,
            }
        )
    return {"status": "ok", "commands": payload}


@router.post("/commands/{command_id}/ack")
async def ack_command(command_id: int, body: CommandAckRequest, db: AsyncSession = Depends(get_db)):
    """Bot báo kết quả xử lý command."""
    validate_bot_token(body.bot_token, body.license_key)
    status = body.status.lower()
    if status not in {"done", "failed"}:
        raise HTTPException(status_code=400, detail="status phải là done hoặc failed")

    result = await db.execute(
        select(BotCommand).where(
            BotCommand.id == command_id,
            BotCommand.target_license_key == body.license_key,
        )
    )
    command = result.scalar_one_or_none()
    if not command:
        raise HTTPException(status_code=404, detail="Command không tồn tại")
    if command.status == "cancelled":
        return {"status": "ok", "message": "Command đã bị hủy"}

    now = datetime.now(timezone.utc)
    await db.execute(
        update(BotCommand).where(BotCommand.id == command_id).values(
            status=status,
            result=body.result,
            completed_at=now,
        )
    )
    if command.action in {"pause", "resume"}:
        target_account_id: Optional[int] = None
        if command.payload:
            try:
                payload_data = json.loads(command.payload)
                if isinstance(payload_data, dict) and payload_data.get("account_id"):
                    target_account_id = int(payload_data["account_id"])
            except (TypeError, ValueError, json.JSONDecodeError):
                target_account_id = None
        if status == "done" and command.action == "pause":
            account_values = {
                "is_active": False,
                "run_status": "paused",
                "last_error": None,
                "last_stopped_at": now,
                "updated_at": now,
            }
        elif status == "done" and command.action == "resume":
            account_values = {
                "is_active": True,
                "run_status": "running",
                "last_error": None,
                "last_started_at": now,
                "updated_at": now,
            }
        else:
            account_values = {
                "run_status": "error",
                "last_error": body.result or f"Command {command.action} failed",
                "updated_at": now,
            }
        account_update = update(MT5Account).where(MT5Account.license_key == body.license_key)
        if target_account_id:
            account_update = account_update.where(MT5Account.id == target_account_id)
        await db.execute(account_update.values(**account_values))
    await db.commit()
    return {"status": "ok", "message": "Command ack recorded"}


@router.post("/report-trade")
async def report_trade(body: TradeReportRequest, db: AsyncSession = Depends(get_db)):
    """
    Bot gửi thông tin lệnh lên server (để hiển thị trên dashboard + gửi Telegram).
    """
    from core.security import decode_token
    payload = decode_token(body.bot_token)
    if payload.get("sub") != body.license_key:
        raise HTTPException(status_code=403, detail="Token không hợp lệ")

    # Kiểm tra xem ticket đã tồn tại chưa
    result = await db.execute(
        select(TradeLog).where(
            (TradeLog.license_key == body.license_key) & (TradeLog.ticket == body.ticket)
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Cập nhật lệnh đã có (ví dụ: lệnh đóng)
        from sqlalchemy import update as sql_update
        await db.execute(
            sql_update(TradeLog).where(TradeLog.id == existing.id).values(
                status=body.status,
                close_price=body.close_price,
                profit=body.profit,
                pips=body.pips,
                closed_at=datetime.now(timezone.utc) if body.status == "closed" else None,
                note=body.note,
            )
        )
    else:
        # Tạo log mới
        trade = TradeLog(
            license_key=body.license_key,
            ticket=body.ticket,
            symbol=body.symbol,
            direction=body.direction,
            entry_price=body.entry_price,
            sl_price=body.sl_price,
            tp_price=body.tp_price,
            lot_size=body.lot_size,
            status=body.status,
            close_price=body.close_price,
            profit=body.profit,
            pips=body.pips,
            note=body.note,
        )
        db.add(trade)

    await db.commit()

    # Gửi Telegram notification
    if body.status == "open":
        msg = (
            f"📈 <b>VÀO LỆNH MỚI</b>\n"
            f"Symbol: <code>{body.symbol}</code>  |  {body.direction}\n"
            f"Entry: <code>{body.entry_price}</code>\n"
            f"SL: <code>{body.sl_price or 'N/A'}</code>  |  TP: <code>{body.tp_price or 'N/A'}</code>\n"
            f"Lot: {body.lot_size}\n"
            f"Ticket: #{body.ticket}"
        )
    elif body.status == "closed":
        emoji = "✅" if (body.profit or 0) >= 0 else "❌"
        msg = (
            f"{emoji} <b>ĐÓNG LỆNH</b>\n"
            f"Symbol: <code>{body.symbol}</code>  |  {body.direction}\n"
            f"Entry: {body.entry_price}  →  Close: {body.close_price}\n"
            f"Pips: {body.pips:+.1f}  |  Profit: {body.profit:+.2f}$\n"
            f"Ticket: #{body.ticket}"
        )
    else:
        msg = None

    if msg:
        await _notify_admin(msg)

    return {"status": "ok", "message": "Trade đã được ghi nhận"}


@router.post("/sync-positions")
async def sync_positions(body: PositionSyncRequest, db: AsyncSession = Depends(get_db)):
    """Bot gửi snapshot position MT5 thật để server dọn log open bị treo."""
    validate_bot_token(body.bot_token, body.license_key)
    now = datetime.now(timezone.utc)

    live_tickets = {str(position.ticket) for position in body.positions if str(position.ticket).strip()}
    existing_open_rows = (
        await db.execute(
            select(TradeLog).where(
                TradeLog.license_key == body.license_key,
                TradeLog.status == "open",
            )
        )
    ).scalars().all()
    existing_open_by_ticket = {trade.ticket: trade for trade in existing_open_rows}

    created_count = 0
    refreshed_count = 0
    marked_closed_count = 0

    for position in body.positions:
        ticket = str(position.ticket).strip()
        if not ticket:
            continue
        direction = position.direction.upper()
        if direction not in {"BUY", "SELL"}:
            continue

        existing = existing_open_by_ticket.get(ticket)
        if existing:
            existing.symbol = position.symbol.upper()
            existing.direction = direction
            existing.entry_price = position.entry_price
            existing.sl_price = position.sl_price
            existing.tp_price = position.tp_price
            existing.lot_size = position.lot_size
            refreshed_count += 1
            continue

        db.add(
            TradeLog(
                license_key=body.license_key,
                ticket=ticket,
                symbol=position.symbol.upper(),
                direction=direction,
                entry_price=position.entry_price,
                sl_price=position.sl_price,
                tp_price=position.tp_price,
                lot_size=position.lot_size,
                status="open",
                opened_at=position.opened_at or now,
                note=position.note or "MT5 sync: found live position not yet logged by bot",
            )
        )
        created_count += 1

    if body.mark_missing_closed:
        for trade in existing_open_rows:
            if trade.ticket in live_tickets:
                continue
            sync_note = "MT5 sync: position not found in live snapshot; marked closed externally, profit unknown"
            trade.status = "closed"
            trade.closed_at = now
            trade.note = f"{trade.note} | {sync_note}" if trade.note else sync_note
            marked_closed_count += 1

    account_update = (
        update(MT5Account)
        .where(MT5Account.license_key == body.license_key)
        .values(
            last_error=None,
            updated_at=now,
        )
    )
    if body.mt_account:
        account_update = account_update.where(MT5Account.mt_login == str(body.mt_account))
    await db.execute(account_update)
    await db.commit()

    return {
        "status": "ok",
        "live_positions": len(live_tickets),
        "created": created_count,
        "refreshed": refreshed_count,
        "marked_closed": marked_closed_count,
    }


@router.post("/status")
async def report_runtime_status(body: BotStatusReportRequest, db: AsyncSession = Depends(get_db)):
    """Bot cập nhật lý do vào/chưa vào lệnh mới nhất để web hiển thị realtime."""
    validate_bot_token(body.bot_token, body.license_key)
    now = datetime.now(timezone.utc)
    mt_account = str(body.mt_account or "").strip() or None
    symbol = body.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol không được trống")

    existing = (
        await db.execute(
            select(BotRuntimeStatus).where(
                BotRuntimeStatus.license_key == body.license_key,
                BotRuntimeStatus.symbol == symbol,
                BotRuntimeStatus.mt_account == mt_account,
            )
        )
    ).scalar_one_or_none()

    values = {
        "mt_account": mt_account,
        "symbol": symbol,
        "timeframe": (body.timeframe or "").strip().upper() or None,
        "strategy": (body.strategy or "").strip().lower() or None,
        "signal": (body.signal or "HOLD").strip().upper()[:12],
        "reason": body.reason,
        "confidence": body.confidence,
        "spread_points": body.spread_points,
        "open_positions": max(0, int(body.open_positions or 0)),
        "total_positions": max(0, int(body.total_positions or 0)),
        "max_positions": max(0, int(body.max_positions or 0)),
        "max_total_positions": max(0, int(body.max_total_positions or 0)),
        "dry_run": bool(body.dry_run),
        "session_allowed": bool(body.session_allowed),
        "run_state": (body.run_state or "idle").strip().lower()[:24],
        "payload": json.dumps(body.payload or {}, ensure_ascii=False),
        "updated_at": now,
    }

    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
    else:
        db.add(BotRuntimeStatus(license_key=body.license_key, created_at=now, **values))

    await db.commit()
    return {"status": "ok", "message": "Runtime status updated"}


# ─── Helper ───────────────────────────────────────────────────────────────────

async def _notify_admin(message: str):
    """Gửi Telegram message cho admin"""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_CHAT_ID:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": settings.TELEGRAM_ADMIN_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                },
            )
    except Exception:
        pass  # Không để lỗi Telegram ảnh hưởng main flow
