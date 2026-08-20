from __future__ import annotations
from datetime import datetime, timezone
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, UserSession
from .security import hash_session_token

SESSION_COOKIE = "deviz_session"

def current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    if not session_token:
        raise HTTPException(status_code=401, detail="Autentificare necesară.")
    token_hash = hash_session_token(session_token)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
    if not session:
        raise HTTPException(status_code=401, detail="Sesiune invalidă.")
    now = datetime.now(timezone.utc)
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        db.execute(delete(UserSession).where(UserSession.id == session.id))
        db.commit()
        raise HTTPException(status_code=401, detail="Sesiunea a expirat.")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Utilizator inactiv.")
    return user
