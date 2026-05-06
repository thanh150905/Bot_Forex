"""
JWT + Password hashing utilities
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import base64
import hashlib
import hmac
import os
import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status

from core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _credential_key(salt: bytes) -> bytes:
    source = settings.MT5_CREDENTIAL_KEY or settings.SECRET_KEY
    return hashlib.pbkdf2_hmac("sha256", source.encode("utf-8"), salt, 120_000, dklen=32)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _credential_stream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        counter_bytes = counter.to_bytes(4, "big")
        blocks.append(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def encrypt_secret(plain: str) -> str:
    """Mã hóa secret nội bộ không cần thêm dependency ngoài.

    Dùng để tránh lưu mật khẩu MT5 dạng plaintext trong DB. Khi deploy thật,
    nên đặt MT5_CREDENTIAL_KEY riêng và bảo vệ file .env/VPS.
    """
    salt = os.urandom(16)
    nonce = os.urandom(16)
    key = _credential_key(salt)
    payload = plain.encode("utf-8")
    stream = _credential_stream(key, nonce, len(payload))
    cipher = bytes(a ^ b for a, b in zip(payload, stream))
    tag = hmac.new(key, salt + nonce + cipher, hashlib.sha256).digest()
    return f"v1:{_b64(salt)}:{_b64(nonce)}:{_b64(cipher)}:{_b64(tag)}"


def decrypt_secret(encrypted: str) -> str:
    try:
        version, salt_text, nonce_text, cipher_text, tag_text = encrypted.split(":", 4)
        if version != "v1":
            raise ValueError("Unsupported secret version")
        salt = _unb64(salt_text)
        nonce = _unb64(nonce_text)
        cipher = _unb64(cipher_text)
        tag = _unb64(tag_text)
        key = _credential_key(salt)
        expected = hmac.new(key, salt + nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("Secret integrity check failed")
        stream = _credential_stream(key, nonce, len(cipher))
        payload = bytes(a ^ b for a, b in zip(cipher, stream))
        return payload.decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Không giải mã được secret MT5") from exc


def create_token(data: dict, expire_hours: int) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=expire_hours)
    payload["iat"] = datetime.now(timezone.utc)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_admin_token(admin_id: int, username: str) -> str:
    return create_token(
        {"sub": str(admin_id), "username": username, "role": "admin"},
        settings.ADMIN_TOKEN_EXPIRE_HOURS,
    )


def create_user_token(user_id: int, username: str, license_key: str, device_id: str | None = None) -> str:
    return create_token(
        {
            "sub": str(user_id),
            "username": username,
            "license_key": license_key,
            "device_id": device_id,
            "role": "user",
        },
        settings.ADMIN_TOKEN_EXPIRE_HOURS,
    )


def create_bot_token(license_key: str, user_id: int) -> str:
    """Token ngắn hạn cho bot ping xác thực"""
    return create_token(
        {"sub": license_key, "user_id": user_id, "role": "bot"},
        settings.ACCESS_TOKEN_EXPIRE_HOURS,
    )


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token đã hết hạn")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")


def require_admin(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ admin mới có quyền này")
    return payload


def require_user_portal(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("role") != "user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token user không hợp lệ")
    return payload


def require_bot(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("role") != "bot":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token không hợp lệ cho bot")
    return payload
