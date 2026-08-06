"""Password hashing, JWT creation/verification and secret encryption."""
from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _create_token(subject: str, token_type: str, expires_delta: timedelta, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    return _create_token(
        str(user_id), "access", timedelta(minutes=settings.access_token_minutes), {"role": role}
    )


def create_refresh_token(user_id: int) -> str:
    settings = get_settings()
    return _create_token(str(user_id), "refresh", timedelta(days=settings.refresh_token_days))


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """Decode and validate a JWT. Raises jwt.InvalidTokenError on any problem."""
    settings = get_settings()
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def token_remaining_seconds(payload: dict[str, Any]) -> int:
    """Seconds until this decoded token expires (for revocation TTLs)."""
    exp = payload.get("exp")
    if not exp:
        return 0
    return max(0, int(exp - datetime.now(timezone.utc).timestamp()))


# ---- platform API keys (for OUR public REST API, not any AI provider) ----

API_KEY_PREFIX = "ak_"


def generate_api_key() -> tuple[str, str, str]:
    """Returns (plain_key, sha256_hash, display_prefix)."""
    plain = API_KEY_PREFIX + uuid.uuid4().hex + uuid.uuid4().hex[:8]
    return plain, hash_api_key(plain), plain[:10]


def hash_api_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def generate_webhook_secret() -> str:
    return "whsec_" + uuid.uuid4().hex


def sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 signature for webhook deliveries. The timestamp is part
    of the signed payload so consumers can reject replays."""
    import hmac

    message = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


# ---- symmetric encryption for stored secrets (e.g. GitHub token) ----

def _fernet() -> Fernet:
    key = hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
