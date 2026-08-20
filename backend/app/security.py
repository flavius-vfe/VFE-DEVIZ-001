from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

def hash_password(password: str) -> str:
    return _hasher.hash(password)

def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False

def new_session_token() -> str:
    return secrets.token_urlsafe(48)

def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def session_expiry(days: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)
