"""
Email utilities - Gửi email qua SMTP
"""

import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import traceback

from core.config import settings
from core.logger import email_logger


HTML_EMAIL_TEMPLATE = """
<html>
    <body style="font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <h2 style="color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px;">{title}</h2>
            <p style="color: #555; line-height: 1.6;">{intro}</p>
            <div style="background-color: #f0f0f0; padding: 20px; border-radius: 4px; text-align: center; margin: 20px 0;">
                <p style="font-size: 12px; color: #999; margin-top: 0;">Mã xác thực của bạn:</p>
                <h1 style="letter-spacing: 5px; color: #007bff; margin: 10px 0;">{code}</h1>
                <p style="font-size: 12px; color: #999;">Hết hạn trong {expires_minutes} phút</p>
            </div>
            <p style="color: #555; line-height: 1.6;">
                Nếu bạn không yêu cầu {action}, vui lòng bỏ qua email này.
            </p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="color: #999; font-size: 12px; text-align: center;">
                © 2024-2025 Forex Bot System. All rights reserved.
            </p>
        </div>
    </body>
</html>
"""


def is_smtp_configured() -> bool:
    """Kiểm tra SMTP đã cấu hình chưa"""
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL and settings.SMTP_USERNAME)


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    retry_count: int = 3,
) -> bool:
    """
    Gửi email bất đồng bộ
    
    Args:
        to_email: Địa chỉ email đích
        subject: Tiêu đề email
        html_content: Nội dung HTML
        text_content: Nội dung plain text (fallback)
        retry_count: Số lần retry nếu thất bại
    
    Returns:
        True nếu gửi thành công, False nếu thất bại
    """
    if not is_smtp_configured():
        email_logger.warning(f"SMTP not configured! Email to {to_email} not sent.")
        return False
    
    loop = asyncio.get_event_loop()
    
    for attempt in range(1, retry_count + 1):
        try:
            await loop.run_in_executor(
                None,
                _send_email_sync,
                to_email,
                subject,
                html_content,
                text_content,
            )
            email_logger.info(f"✅ Email sent to {to_email} | Subject: {subject}")
            return True
        except Exception as e:
            email_logger.warning(
                f"⚠️ Email send attempt {attempt}/{retry_count} failed for {to_email}: {str(e)}"
            )
            if attempt < retry_count:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s, 8s...
            else:
                email_logger.error(
                    f"❌ Email send FAILED after {retry_count} attempts for {to_email}: {str(e)}"
                )
                return False
    
    return False


def _send_email_sync(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
):
    """Synchronous email send (runs in executor)"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    
    # Plain text part (fallback)
    if text_content:
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
    else:
        # Strip HTML to get basic text
        text_only = html_content.replace("<html>", "").replace("</html>", "").replace("<body>", "").replace("</body>", "").replace("<br>", "\n")
        msg.attach(MIMEText(text_only, "plain", "utf-8"))
    
    # HTML part (preferred)
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    
    # Send via SMTP
    if settings.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)


async def send_code_email(
    email: str,
    code: str,
    purpose: str,
    expires_minutes: int = 10,
) -> bool:
    """
    Gửi email với OTP code
    
    Args:
        email: Email đích
        code: 6-digit code
        purpose: "user_register" | "user_login" | "password_reset"
        expires_minutes: Thời gian hết hạn (phút)
    
    Returns:
        True nếu thành công
    """
    purposes = {
        "user_register": {
            "subject": "Forex Bot - Mã xác thực đăng ký",
            "title": "Xác thực email đăng ký",
            "intro": "Dùng mã 6 chữ số bên dưới để hoàn tất đăng ký tài khoản Forex Bot.",
            "action": "đăng ký",
        },
        "user_login": {
            "subject": "Forex Bot - Mã đăng nhập",
            "title": "Mã đăng nhập của bạn",
            "intro": "Dùng mã 6 chữ số bên dưới để đăng nhập vào cổng khách hàng Forex Bot.",
            "action": "đăng nhập",
        },
        "password_reset": {
            "subject": "Forex Bot - Mã đặt lại mật khẩu",
            "title": "Đặt lại mật khẩu",
            "intro": "Dùng mã 6 chữ số bên dưới để tạo mật khẩu mới cho tài khoản Forex Bot.",
            "action": "đặt lại mật khẩu",
        },
    }
    
    if purpose not in purposes:
        email_logger.error(f"Unknown email purpose: {purpose}")
        return False
    
    config = purposes[purpose]
    
    html = HTML_EMAIL_TEMPLATE.format(
        title=config["title"],
        intro=config["intro"],
        code=code,
        expires_minutes=expires_minutes,
        action=config["action"],
    )
    
    return await send_email(
        to_email=email,
        subject=config["subject"],
        html_content=html,
        retry_count=3,
    )


async def send_admin_alert(
    subject: str,
    message: str,
    severity: str = "info",  # "info", "warning", "critical"
) -> bool:
    """
    Gửi cảnh báo cho admin
    
    Args:
        subject: Tiêu đề alert
        message: Nội dung chi tiết
        severity: "info", "warning", "critical"
    
    Returns:
        True nếu thành công
    """
    if not settings.SMTP_FROM_EMAIL or not settings.ADMIN_USERNAME:
        email_logger.warning("Admin email not configured")
        return False
    
    severity_emoji = {
        "info": "ℹ️",
        "warning": "⚠️",
        "critical": "🚨",
    }
    
    html = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>{severity_emoji.get(severity, "")} {subject}</h2>
            <pre style="background-color: #f0f0f0; padding: 10px; border-radius: 4px;">{message}</pre>
            <hr>
            <p style="font-size: 12px; color: #999;">
                Thời gian: {asyncio.get_event_loop().time()}
            </p>
        </body>
    </html>
    """
    
    # Gửi cho admin nếu có email admin trong cấu hình
    admin_emails = [email for email in [settings.SMTP_FROM_EMAIL] if email]
    
    for admin_email in admin_emails:
        await send_email(
            to_email=admin_email,
            subject=f"[{severity.upper()}] {subject}",
            html_content=html,
            retry_count=2,
        )
    
    return True
