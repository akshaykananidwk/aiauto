from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.audit import audit

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    return await UserRepository(db).list()


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    repo = UserRepository(db)
    if await repo.get_by_username(body.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        department=body.department,
        role=body.role,
        hashed_password=hash_password(body.password),
    )
    repo.add(user)
    await db.flush()
    await audit(db, "user.created", f"user {user.username} created", user_id=admin.id,
                meta={"new_user": user.username, "role": user.role.value}, commit=True)
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await UserRepository(db).get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    patch = body.model_dump(exclude_none=True)
    if "password" in patch:
        user.hashed_password = hash_password(patch.pop("password"))
    for key, value in patch.items():
        setattr(user, key, value)
    if user.id == admin.id and user.is_active is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")
    await audit(db, "user.updated", f"user {user.username} updated", user_id=admin.id,
                meta={"target": user.username, "fields": list(patch.keys())}, commit=True)
    await db.refresh(user)
    return user


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await UserRepository(db).get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")
    user.is_active = False
    await audit(db, "user.deactivated", f"user {user.username} deactivated",
                user_id=admin.id, commit=True)
    return {"ok": True}
