from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import AdminDashboard, StaffDashboard
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/admin", response_model=AdminDashboard)
async def admin_dashboard(
    _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> AdminDashboard:
    return await DashboardService(db).admin()


@router.get("/staff", response_model=StaffDashboard)
async def staff_dashboard(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> StaffDashboard:
    return await DashboardService(db).staff(user.id)


@router.get("/announcement")
async def announcement(
    _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """Company-wide announcement banner text (set by admins in Settings)."""
    from app.repositories.setting import SettingRepository

    text = await SettingRepository(db).get("app.announcement", "")
    return {"announcement": text or ""}
