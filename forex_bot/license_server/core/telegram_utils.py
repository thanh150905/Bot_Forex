"""
Telegram notification utilities
"""

import asyncio
import aiohttp
from typing import Optional
from datetime import datetime, timezone

from core.config import settings
from core.logger import telegram_logger


class TelegramNotifier:
    """Send notifications to admin via Telegram"""
    
    BASE_URL = "https://api.telegram.org/bot"
    
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"{self.BASE_URL}{token}"
        self.is_configured = bool(token and chat_id)
    
    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Gửi tin nhắn text
        
        Args:
            message: Nội dung (HTML format)
            parse_mode: "HTML" | "Markdown"
        
        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            telegram_logger.warning("Telegram not configured")
            return False
        
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        
        return await self._send_request(payload, "sendMessage")
    
    async def send_photo(
        self,
        photo_url: str,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
    ) -> bool:
        """Gửi ảnh"""
        if not self.is_configured:
            return False
        
        payload = {
            "chat_id": self.chat_id,
            "photo": photo_url,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        
        if caption:
            payload["caption"] = caption
        
        return await self._send_request(payload, "sendPhoto")
    
    async def send_document(
        self,
        document_url: str,
        caption: Optional[str] = None,
    ) -> bool:
        """Gửi document"""
        if not self.is_configured:
            return False
        
        payload = {
            "chat_id": self.chat_id,
            "document": document_url,
        }
        
        if caption:
            payload["caption"] = caption
        
        return await self._send_request(payload, "sendDocument")
    
    async def _send_request(self, payload: dict, method: str) -> bool:
        """Send HTTP request to Telegram API"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.api_url}/{method}",
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        return True
                    else:
                        telegram_logger.warning(f"Telegram API error {resp.status}: {await resp.text()}")
                        return False
        except asyncio.TimeoutError:
            telegram_logger.warning("Telegram request timeout")
            return False
        except Exception as e:
            telegram_logger.error(f"Telegram send failed: {e}")
            return False


# Global telegram instance
_telegram: Optional[TelegramNotifier] = None


def get_telegram() -> Optional[TelegramNotifier]:
    """Get global telegram instance"""
    global _telegram
    if _telegram is None and settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ADMIN_CHAT_ID:
        _telegram = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_ADMIN_CHAT_ID)
    return _telegram


# Helper functions for common notifications

async def notify_license_verification(username: str, license_key: str, status: str, ip: str):
    """Notify admin khi bot verify license"""
    tg = get_telegram()
    if not tg:
        return
    
    emoji = "✅" if status == "success" else "❌"
    message = f"""
{emoji} <b>Bot License Verification</b>

<b>Status:</b> {status}
<b>User:</b> {username}
<b>License:</b> <code>{license_key}</code>
<b>IP:</b> {ip}
<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    await tg.send_message(message)


async def notify_trade_opened(
    username: str,
    symbol: str,
    direction: str,
    entry: float,
    lot: float,
    sl: float = None,
    tp: float = None,
):
    """Notify admin khi bot mở lệnh"""
    tg = get_telegram()
    if not tg:
        return
    
    direction_emoji = "📈" if direction == "BUY" else "📉"
    
    message = f"""
{direction_emoji} <b>Trade Opened</b>

<b>User:</b> {username}
<b>Symbol:</b> {symbol}
<b>Direction:</b> <b>{direction}</b>
<b>Entry:</b> {entry}
<b>Lot:</b> {lot}
<b>SL:</b> {sl or 'N/A'}
<b>TP:</b> {tp or 'N/A'}
<b>Time:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}
"""
    await tg.send_message(message)


async def notify_trade_closed(
    username: str,
    symbol: str,
    ticket: str,
    profit: float,
    pips: float = None,
):
    """Notify admin khi bot đóng lệnh"""
    tg = get_telegram()
    if not tg:
        return
    
    profit_emoji = "💰" if profit > 0 else "💸"
    
    message = f"""
{profit_emoji} <b>Trade Closed</b>

<b>User:</b> {username}
<b>Symbol:</b> {symbol}
<b>Ticket:</b> <code>{ticket}</code>
<b>Profit/Loss:</b> <b>${profit:+.2f}</b>
<b>Pips:</b> {pips or 'N/A'}
<b>Time:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}
"""
    await tg.send_message(message)


async def notify_error_alert(
    title: str,
    message: str,
    severity: str = "warning",  # "info", "warning", "critical"
    username: str = None,
):
    """Notify admin về error"""
    tg = get_telegram()
    if not tg:
        return
    
    severity_emoji = {
        "info": "ℹ️",
        "warning": "⚠️",
        "critical": "🚨",
    }
    
    tg_message = f"""
{severity_emoji.get(severity, "")} <b>{title}</b>

<b>Severity:</b> {severity.upper()}
<b>User:</b> {username or 'System'}

<code>{message}</code>

<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    await tg.send_message(tg_message)


async def notify_bot_connection(
    username: str,
    license_key: str,
    action: str,  # "connect", "disconnect", "timeout"
    details: str = None,
):
    """Notify bot connection status"""
    tg = get_telegram()
    if not tg:
        return
    
    action_emoji = {
        "connect": "🟢",
        "disconnect": "🔴",
        "timeout": "🟡",
    }
    
    message = f"""
{action_emoji.get(action, "")} <b>Bot {action.capitalize()}</b>

<b>User:</b> {username}
<b>License:</b> <code>{license_key}</code>
{f'<b>Details:</b> {details}' if details else ''}
<b>Time:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}
"""
    await tg.send_message(message)


async def notify_daily_report(username: str, report: dict):
    """Gửi daily report"""
    tg = get_telegram()
    if not tg:
        return
    
    message = f"""
📊 <b>Daily Trading Report</b>

<b>User:</b> {username}
<b>Trades:</b> {report.get('total_trades', 0)}
<b>Win Rate:</b> {report.get('win_rate', 0):.1f}%
<b>Profit/Loss:</b> <b>${report.get('total_pnl', 0):+.2f}</b>
<b>Max DD:</b> {report.get('max_dd', 0):.1f}%
<b>Equity:</b> ${report.get('equity', 0):.2f}

<b>Date:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
"""
    await tg.send_message(message)
