from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import bearer, get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_remaining_seconds,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RefreshRequest, TokenPair
from app.schemas.user import UserOut
from app.services.audit import audit
from app.services.auth_guard import (
    clear_failures,
    is_locked,
    record_failure,
    revoke_jti,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    if await is_locked(body.username):
        raise HTTPException(
            status.HTTP_423_LOCKED,
            "Account temporarily locked after repeated failed logins. Try again later.",
        )
    user = await UserRepository(db).get_by_username(body.username)
    # bcrypt is CPU-heavy — keep it off the event loop; compare against a
    # constant dummy hash for unknown users so timing stays uniform
    hashed = user.hashed_password if user else (
        "$2b$12$C6UzMDM.H6dfI/f/IKcEeO7ZUXsK9mfDaMTUZyCdyktIePkyHuIW6")
    valid = await asyncio.to_thread(verify_password, body.password, hashed)
    if user is None or not valid:
        await record_failure(body.username)
        await audit(db, "auth.login_failed", f"failed login for '{body.username}'",
                    level="warning", commit=True)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    await clear_failures(body.username)
    user.last_login_at = datetime.now(timezone.utc)
    await audit(db, "auth.login", f"{user.username} logged in", user_id=user.id,
                meta={"computer_name": body.computer_name}, commit=True)
    return TokenPair(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    from app.services.auth_guard import is_revoked

    try:
        payload = decode_token(body.refresh_token, "refresh")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if await is_revoked(payload.get("jti", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token has been revoked")
    user = await UserRepository(db).get(int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or not found")
    # rotation: the old refresh token can never be used again
    await revoke_jti(payload.get("jti", ""), token_remaining_seconds(payload))
    return TokenPair(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # revoke the access token that made this call
    if credentials is not None:
        try:
            payload = decode_token(credentials.credentials, "access")
            await revoke_jti(payload.get("jti", ""), token_remaining_seconds(payload))
        except pyjwt.InvalidTokenError:
            pass
    await audit(db, "auth.logout", f"{user.username} logged out", user_id=user.id, commit=True)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await asyncio.to_thread(verify_password, body.current_password,
                                   user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.hashed_password = await asyncio.to_thread(hash_password, body.new_password)
    await audit(db, "auth.password_changed", f"{user.username} changed password",
                user_id=user.id, commit=True)
    return {"ok": True}
