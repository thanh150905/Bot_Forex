"""
Auth routes: Admin đăng nhập, đổi mật khẩu
"""

import asyncio
import hashlib
import hmac
import re
import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, update
from pydantic import BaseModel, EmailStr

from core.config import settings
from core.database import get_db, Admin, User, License, BotSession, PortalDeviceLock, EmailLoginCode
from core.request_utils import get_client_ip
from core.security import verify_password, hash_password, create_admin_token, create_user_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class UserLoginRequest(BaseModel):
    email: str
    license_key: str
    device_id: str | None = None
    device_name: str | None = None


class UserEmailCodeRequest(BaseModel):
    email: EmailStr


class UserEmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str
    device_id: str | None = None
    device_name: str | None = None


class UserRegisterCodeRequest(BaseModel):
    email: EmailStr
    password: str


class UserRegisterVerifyRequest(BaseModel):
    email: EmailStr
    password: str
    code: str
    device_id: str | None = None
    device_name: str | None = None


class UserPasswordLoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_id: str | None = None
    device_name: str | None = None


class UserPasswordResetRequest(BaseModel):
    email: EmailStr


class UserPasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    admin_token: str
    old_password: str
    new_password: str


def is_expired(value: datetime | None) -> bool:
    if not value:
        return False
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < now


def normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def generate_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def normalize_email_code(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


EMAIL_PURPOSES = {
    "user_register": {
        "subject": "Mã xác thực đăng ký Forex Bot",
        "title": "Xác thực email đăng ký",
        "intro": "Dùng mã bên dưới để hoàn tất đăng ký tài khoản Forex Bot.",
        "action": "Hoàn tất đăng ký",
    },
    "user_login": {
        "subject": "Mã đăng nhập Forex Bot",
        "title": "Mã đăng nhập của bạn",
        "intro": "Dùng mã bên dưới để đăng nhập vào cổng khách hàng Forex Bot.",
        "action": "Đăng nhập",
    },
    "password_reset": {
        "subject": "Mã đặt lại mật khẩu Forex Bot",
        "title": "Đặt lại mật khẩu",
        "intro": "Dùng mã bên dưới để tạo mật khẩu mới cho tài khoản Forex Bot.",
        "action": "Đặt lại mật khẩu",
    },
}


def email_code_hash(email: str, code: str, purpose: str) -> str:
    payload = f"{purpose}:{email}:{code}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "***" + local[-1:]
    return f"{masked_local}@{domain}" if domain else masked_local


def smtp_is_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)


def validate_user_password(password: str) -> str:
    value = str(password or "")
    if len(value) < 8:
        raise HTTPException(status_code=400, detail="Mật khẩu tối thiểu 8 ký tự")
    if len(value) > 128:
        raise HTTPException(status_code=400, detail="Mật khẩu tối đa 128 ký tự")
    return value


def build_code_email_html(purpose: str, code: str) -> str:
    meta = EMAIL_PURPOSES.get(purpose, EMAIL_PURPOSES["user_login"])
    expire_minutes = settings.EMAIL_CODE_EXPIRE_MINUTES
    return f"""<!doctype html>
<html lang="vi">
  <body style="margin:0;background:#f4f6f8;font-family:Segoe UI,Arial,sans-serif;color:#17202a;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f8;padding:28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #d8e0e8;border-radius:14px;overflow:hidden;">
            <tr>
              <td style="background:#121922;padding:22px 26px;color:#ffffff;">
                <div style="font-size:13px;letter-spacing:0;text-transform:uppercase;color:#32c1a9;font-weight:700;">Forex Bot</div>
                <div style="font-size:24px;font-weight:750;margin-top:6px;">{meta["title"]}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:26px;">
                <p style="margin:0 0 18px;color:#354554;font-size:15px;line-height:1.6;">{meta["intro"]}</p>
                <div style="background:#e2f4ef;border:1px solid #b9e2d8;border-radius:12px;padding:18px;text-align:center;">
                  <div style="font-size:12px;color:#627080;font-weight:700;text-transform:uppercase;">Mã xác thực</div>
                  <div style="font-size:38px;line-height:1.2;letter-spacing:8px;font-weight:800;color:#14685b;margin-top:8px;">{code}</div>
                </div>
                <p style="margin:18px 0 0;color:#627080;font-size:13px;line-height:1.6;">Mã có hiệu lực trong {expire_minutes} phút. Vì an toàn tài khoản, không chuyển tiếp mã này cho bất kỳ ai.</p>
                <p style="margin:16px 0 0;color:#627080;font-size:13px;line-height:1.6;">Nếu bạn không yêu cầu thao tác này, vui lòng bỏ qua email.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 26px;background:#fafbfd;border-top:1px solid #d8e0e8;color:#91a2b3;font-size:12px;">
                Email tự động từ Forex Bot License Server.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def build_code_email_text(purpose: str, code: str) -> str:
    meta = EMAIL_PURPOSES.get(purpose, EMAIL_PURPOSES["user_login"])
    return "\n".join(
        [
            "Forex Bot",
            meta["title"],
            "",
            meta["intro"],
            f"Mã xác thực: {code}",
            f"Mã có hiệu lực trong {settings.EMAIL_CODE_EXPIRE_MINUTES} phút.",
            "",
            "Nếu bạn không yêu cầu thao tác này, vui lòng bỏ qua email.",
        ]
    )


def send_email_code(email: str, code: str, purpose: str) -> bool:
    """Gửi mã OTP qua SMTP. Nếu thiếu SMTP, log để dev biết nhưng không trả mã về UI."""
    if not smtp_is_configured():
        print(f"[MAIL][DEV] Email OTP cho {email}: {code}")
        return False

    meta = EMAIL_PURPOSES.get(purpose, EMAIL_PURPOSES["user_login"])
    message = EmailMessage()
    from_name = settings.SMTP_FROM_NAME.strip()
    from_email = settings.SMTP_FROM_EMAIL.strip()
    message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    message["To"] = email
    message["Subject"] = meta["subject"]
    message.set_content(build_code_email_text(purpose, code))
    message.add_alternative(build_code_email_html(purpose, code), subtype="html")

    smtp_cls = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    with smtp_cls(settings.SMTP_HOST, settings.SMTP_PORT, timeout=12) as smtp:
        if not settings.SMTP_USE_SSL and settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)
    return True


async def unique_username_for_email(email: str, db: AsyncSession) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", email.split("@", 1)[0]).strip("_").lower()
    base = (base or "user")[:42]
    candidate = base
    for _ in range(12):
        exists = await db.execute(select(User.id).where(User.username == candidate))
        if not exists.scalar_one_or_none():
            return candidate
        candidate = f"{base[:35]}_{secrets.token_hex(3)}"
    return f"user_{secrets.token_hex(8)}"


async def get_or_create_email_user(email: str, db: AsyncSession) -> tuple[User, bool]:
    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()
    if user:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị vô hiệu hóa")
        if is_expired(user.expires_at):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã hết hạn")
        return user, False

    username = await unique_username_for_email(email, db)
    user = User(
        username=username,
        email=email,
        note="User tự đăng ký qua email OTP",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user, True


async def get_or_create_portal_license(user: User, created_new_user: bool, db: AsyncSession) -> License:
    result = await db.execute(
        select(License).where(License.user_id == user.id).order_by(License.created_at.desc())
    )
    licenses = result.scalars().all()
    for license_ in licenses:
        if license_.is_active and not is_expired(license_.expires_at):
            return license_

    if licenses and not created_new_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="License của tài khoản không còn hiệu lực. Liên hệ admin để kích hoạt lại.",
        )

    license_ = License(user_id=user.id)
    db.add(license_)
    await db.flush()
    return license_


async def create_and_send_email_code(email: str, purpose: str, client_ip: str, db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    cooldown = max(settings.EMAIL_CODE_RESEND_SECONDS, 0)

    latest_result = await db.execute(
        select(EmailLoginCode)
        .where(
            EmailLoginCode.email == email,
            EmailLoginCode.purpose == purpose,
            EmailLoginCode.used_at.is_(None),
        )
        .order_by(EmailLoginCode.created_at.desc())
    )
    latest = latest_result.scalars().first()
    if latest and cooldown:
        created_at = normalize_utc(latest.created_at) or now
        elapsed = int((now - created_at).total_seconds())
        if elapsed < cooldown:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Vui lòng đợi {cooldown - elapsed}s trước khi gửi lại mã",
            )

    await db.execute(
        update(EmailLoginCode)
        .where(
            EmailLoginCode.email == email,
            EmailLoginCode.purpose == purpose,
            EmailLoginCode.used_at.is_(None),
        )
        .values(used_at=now)
    )

    code = generate_email_code()
    code_row = EmailLoginCode(
        email=email,
        code_hash=email_code_hash(email, code, purpose),
        purpose=purpose,
        ip_address=client_ip,
        expires_at=now + timedelta(minutes=max(settings.EMAIL_CODE_EXPIRE_MINUTES, 1)),
    )
    db.add(code_row)
    await db.commit()
    await db.refresh(code_row)

    try:
        mail_sent = await asyncio.to_thread(send_email_code, email, code, purpose)
    except Exception as exc:
        await db.execute(update(EmailLoginCode).where(EmailLoginCode.id == code_row.id).values(used_at=now))
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Không gửi được email xác thực: {exc}") from exc

    if not mail_sent:
        raise HTTPException(
            status_code=500,
            detail="Chưa cấu hình SMTP. Copy license_server/.env.example thành .env, điền SMTP_USERNAME/SMTP_PASSWORD rồi restart server.",
        )

    return {
        "message": f"Đã gửi mã xác thực tới {mask_email(email)}",
        "email": email,
        "mail_sent": True,
        "expires_in_seconds": settings.EMAIL_CODE_EXPIRE_MINUTES * 60,
    }


async def consume_email_code(email: str, purpose: str, code: str, db: AsyncSession) -> EmailLoginCode:
    normalized_code = normalize_email_code(code)
    now = datetime.now(timezone.utc)
    if len(normalized_code) != 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã xác thực phải gồm 6 chữ số")

    code_result = await db.execute(
        select(EmailLoginCode)
        .where(
            EmailLoginCode.email == email,
            EmailLoginCode.purpose == purpose,
            EmailLoginCode.used_at.is_(None),
        )
        .order_by(EmailLoginCode.created_at.desc())
    )
    code_row = code_result.scalars().first()
    if not code_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mã xác thực không tồn tại hoặc đã được dùng")

    expires_at = normalize_utc(code_row.expires_at) or now
    if expires_at < now:
        code_row.used_at = now
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mã xác thực đã hết hạn")

    if code_row.attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
        code_row.used_at = now
        await db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Mã này đã nhập sai quá nhiều lần")

    code_row.attempts += 1
    if not hmac.compare_digest(code_row.code_hash, email_code_hash(email, normalized_code, purpose)):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mã xác thực không đúng")

    code_row.used_at = now
    return code_row


async def issue_user_portal_login(
    user: User,
    license_: License,
    device_id: str,
    device_name: str | None,
    client_ip: str,
    db: AsyncSession,
) -> dict:
    if len(device_id) < 16:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Thiếu mã thiết bị đăng nhập")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị vô hiệu hóa")
    if not license_.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="License đã bị thu hồi")
    if is_expired(user.expires_at):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã hết hạn")
    if is_expired(license_.expires_at):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="License đã hết hạn")

    if license_.allowed_ip is None:
        await db.execute(
            update(License).where(License.license_key == license_.license_key).values(allowed_ip=client_ip)
        )
        db.add(
            BotSession(
                user_id=user.id,
                license_key=license_.license_key,
                ip_address=client_ip,
                action="user_login",
                reason="User portal IP đã được lock lần đầu",
                mt_account=license_.mt_account,
            )
        )
        await db.commit()
        license_.allowed_ip = client_ip
    elif license_.allowed_ip != client_ip:
        db.add(
            BotSession(
                user_id=user.id,
                license_key=license_.license_key,
                ip_address=client_ip,
                action="reject",
                reason=f"User portal IP không khớp: yêu cầu {client_ip}, được phép {license_.allowed_ip}",
                mt_account=license_.mt_account,
            )
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP không được phép. Liên hệ admin để reset IP.")

    device_result = await db.execute(
        select(PortalDeviceLock).where(PortalDeviceLock.license_key == license_.license_key)
    )
    device_lock = device_result.scalar_one_or_none()
    if device_lock is None:
        db.add(
            PortalDeviceLock(
                user_id=user.id,
                license_key=license_.license_key,
                device_id=device_id,
                device_name=device_name,
                ip_address=client_ip,
            )
        )
        db.add(
            BotSession(
                user_id=user.id,
                license_key=license_.license_key,
                ip_address=client_ip,
                action="device_lock",
                reason=f"User portal device đã được lock lần đầu: {device_name or device_id[:12]}",
                mt_account=license_.mt_account,
            )
        )
        await db.commit()
    elif device_lock.device_id != device_id:
        db.add(
            BotSession(
                user_id=user.id,
                license_key=license_.license_key,
                ip_address=client_ip,
                action="reject",
                reason=f"Thiết bị user portal không khớp: {device_name or device_id[:12]}",
                mt_account=license_.mt_account,
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="License này đã được khóa cho thiết bị khác. Liên hệ admin để reset thiết bị.",
        )
    else:
        await db.execute(
            update(PortalDeviceLock)
            .where(PortalDeviceLock.id == device_lock.id)
            .values(last_seen_at=datetime.now(timezone.utc), ip_address=client_ip, device_name=device_name or device_lock.device_name)
        )
        await db.commit()

    token = create_user_token(user.id, user.username, license_.license_key, device_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "message": f"Chào mừng {user.username}!",
        "user": {"id": user.id, "username": user.username, "email": user.email},
        "license_key": license_.license_key,
        "ip_locked": license_.allowed_ip,
        "device_locked": True,
    }


@router.post("/admin/login")
async def admin_login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Admin đăng nhập → nhận JWT token"""
    result = await db.execute(select(Admin).where(Admin.username == body.username))
    admin = result.scalar_one_or_none()

    if not admin or not verify_password(body.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sai username hoặc mật khẩu")

    # Cập nhật last_login
    await db.execute(
        update(Admin).where(Admin.id == admin.id).values(last_login=datetime.now(timezone.utc))
    )
    await db.commit()

    token = create_admin_token(admin.id, admin.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "message": f"Chào mừng {admin.username}!",
    }


@router.post("/user/request-email-code")
async def request_user_email_code(body: UserEmailCodeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """User tự đăng ký/đăng nhập portal bằng email OTP."""
    client_ip = get_client_ip(request)
    email = normalize_email(str(body.email))
    return await create_and_send_email_code(email, "user_login", client_ip, db)


@router.post("/user/verify-email-code")
async def verify_user_email_code(body: UserEmailVerifyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Xác thực email OTP, tự tạo user/license nếu là email mới, rồi cấp token portal."""
    client_ip = get_client_ip(request)
    email = normalize_email(str(body.email))
    device_id = (body.device_id or "").strip()
    device_name = (body.device_name or "").strip()[:160] or None
    await consume_email_code(email, "user_login", body.code, db)
    user, created_new_user = await get_or_create_email_user(email, db)
    license_ = await get_or_create_portal_license(user, created_new_user, db)
    return await issue_user_portal_login(user, license_, device_id, device_name, client_ip, db)


@router.post("/user/register/request-code")
async def request_user_register_code(body: UserRegisterCodeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """User đăng ký bằng email + mật khẩu, nhận mã xác thực qua mail."""
    client_ip = get_client_ip(request)
    email = normalize_email(str(body.email))
    validate_user_password(body.password)

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    existing = result.scalar_one_or_none()
    if existing and existing.password_hash:
        raise HTTPException(status_code=400, detail="Email đã có tài khoản. Hãy đăng nhập hoặc dùng quên mật khẩu.")
    if existing and not existing.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị vô hiệu hóa")

    return await create_and_send_email_code(email, "user_register", client_ip, db)


@router.post("/user/register/verify")
async def verify_user_register(body: UserRegisterVerifyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Xác thực mã đăng ký, lưu mật khẩu user và đăng nhập vào portal."""
    client_ip = get_client_ip(request)
    email = normalize_email(str(body.email))
    password = validate_user_password(body.password)
    device_id = (body.device_id or "").strip()
    device_name = (body.device_name or "").strip()[:160] or None

    await consume_email_code(email, "user_register", body.code, db)
    user, created_new_user = await get_or_create_email_user(email, db)
    if user.password_hash and not created_new_user:
        await db.commit()
        raise HTTPException(status_code=400, detail="Email đã có tài khoản. Hãy đăng nhập hoặc dùng quên mật khẩu.")
    user.password_hash = hash_password(password)
    if not user.note:
        user.note = "User tự đăng ký qua email"
    license_ = await get_or_create_portal_license(user, created_new_user, db)
    await db.commit()
    return await issue_user_portal_login(user, license_, device_id, device_name, client_ip, db)


@router.post("/user/password-login")
async def user_password_login(body: UserPasswordLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """User đăng nhập portal bằng email + mật khẩu."""
    client_ip = get_client_ip(request)
    email = normalize_email(str(body.email))
    device_id = (body.device_id or "").strip()
    device_name = (body.device_name or "").strip()[:160] or None

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email hoặc mật khẩu không đúng")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị vô hiệu hóa")
    if is_expired(user.expires_at):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã hết hạn")

    license_ = await get_or_create_portal_license(user, False, db)
    return await issue_user_portal_login(user, license_, device_id, device_name, client_ip, db)


@router.post("/user/password-reset/request-code")
async def request_user_password_reset(body: UserPasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Gửi mã quên mật khẩu qua email."""
    client_ip = get_client_ip(request)
    email = normalize_email(str(body.email))
    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Email chưa có tài khoản. Hãy đăng ký trước.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị vô hiệu hóa")
    return await create_and_send_email_code(email, "password_reset", client_ip, db)


@router.post("/user/password-reset/confirm")
async def confirm_user_password_reset(body: UserPasswordResetConfirmRequest, db: AsyncSession = Depends(get_db)):
    """Xác thực mã quên mật khẩu và lưu mật khẩu mới."""
    email = normalize_email(str(body.email))
    new_password = validate_user_password(body.new_password)
    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Email chưa có tài khoản")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị vô hiệu hóa")
    await consume_email_code(email, "password_reset", body.code, db)
    user.password_hash = hash_password(new_password)
    await db.commit()
    return {"message": "Đặt lại mật khẩu thành công. Bạn có thể đăng nhập bằng mật khẩu mới."}


@router.post("/user/login")
async def user_login(body: UserLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """User đăng nhập cổng khách hàng bằng email + license key."""
    client_ip = get_client_ip(request)
    email = body.email.strip().lower()
    license_key = body.license_key.strip().upper()
    device_id = (body.device_id or "").strip()
    device_name = (body.device_name or "").strip()[:160] or None
    if len(device_id) < 16:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Thiếu mã thiết bị đăng nhập")
    result = await db.execute(
        select(User, License)
        .join(License, License.user_id == User.id)
        .where(func.lower(User.email) == email, License.license_key == license_key)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email hoặc license key không đúng")

    user, license_ = row
    return await issue_user_portal_login(user, license_, device_id, device_name, client_ip, db)


@router.post("/admin/change-password")
async def change_password(body: ChangePasswordRequest, db: AsyncSession = Depends(get_db)):
    """Admin đổi mật khẩu"""
    from core.security import require_admin
    payload = require_admin(body.admin_token)

    result = await db.execute(select(Admin).where(Admin.id == int(payload["sub"])))
    admin = result.scalar_one_or_none()

    if not admin or not verify_password(body.old_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Mật khẩu cũ không đúng")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Mật khẩu mới tối thiểu 8 ký tự")

    await db.execute(
        update(Admin).where(Admin.id == admin.id).values(password_hash=hash_password(body.new_password))
    )
    await db.commit()
    return {"message": "Đổi mật khẩu thành công"}
