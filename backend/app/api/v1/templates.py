"""Prompt library: personal + shared templates with categories, tags,
search, and favorites."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.template import PromptTemplate, TemplateFavorite
from app.models.user import User, UserRole
from app.schemas.template import TemplateCreate, TemplateOut, TemplateUpdate

router = APIRouter(prefix="/templates", tags=["templates"])


def _visible_filter(user: User):
    if user.role == UserRole.admin:
        return None  # admins see everything
    return or_(PromptTemplate.owner_id == user.id, PromptTemplate.is_shared.is_(True))


async def _favorites_of(db: AsyncSession, user_id: int) -> set[int]:
    res = await db.execute(
        select(TemplateFavorite.template_id).where(TemplateFavorite.user_id == user_id)
    )
    return set(res.scalars().all())


def _to_out(tpl: PromptTemplate, favorites: set[int], owner_name: str = "") -> TemplateOut:
    out = TemplateOut.model_validate(tpl)
    out.is_favorite = tpl.id in favorites
    out.owner_name = owner_name
    return out


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    search: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=64),
    tag: str | None = Query(default=None, max_length=64),
    favorites_only: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateOut]:
    stmt = select(PromptTemplate, User.username).join(User, PromptTemplate.owner_id == User.id)
    visible = _visible_filter(user)
    if visible is not None:
        stmt = stmt.where(visible)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(PromptTemplate.title.ilike(like), PromptTemplate.body.ilike(like)))
    if category:
        stmt = stmt.where(PromptTemplate.category == category)
    stmt = stmt.order_by(PromptTemplate.usage_count.desc(), PromptTemplate.updated_at.desc())
    rows = (await db.execute(stmt.limit(500))).all()
    favorites = await _favorites_of(db, user.id)
    out = [_to_out(tpl, favorites, owner) for tpl, owner in rows]
    if tag:
        out = [t for t in out if t.tags and tag in t.tags]
    if favorites_only:
        out = [t for t in out if t.is_favorite]
    return out


@router.get("/categories", response_model=list[str])
async def list_categories(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[str]:
    stmt = select(PromptTemplate.category).distinct()
    visible = _visible_filter(user)
    if visible is not None:
        stmt = stmt.where(visible)
    return sorted(c for c in (await db.execute(stmt)).scalars().all() if c)


async def _get_visible_template(
    template_id: int, user: User, db: AsyncSession, *, for_edit: bool = False
) -> PromptTemplate:
    tpl = await db.get(PromptTemplate, template_id)
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    is_owner_or_admin = user.role == UserRole.admin or tpl.owner_id == user.id
    if for_edit and not is_owner_or_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can modify this template")
    if not for_edit and not (is_owner_or_admin or tpl.is_shared):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return tpl


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    tpl = PromptTemplate(
        owner_id=user.id, title=body.title, body=body.body, category=body.category,
        tags=body.tags, is_shared=body.is_shared,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return _to_out(tpl, set(), user.username)


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: int,
    body: TemplateUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    tpl = await _get_visible_template(template_id, user, db, for_edit=True)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(tpl, key, value)
    await db.commit()
    await db.refresh(tpl)
    return _to_out(tpl, await _favorites_of(db, user.id))


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tpl = await _get_visible_template(template_id, user, db, for_edit=True)
    await db.delete(tpl)
    await db.commit()
    return {"ok": True}


@router.post("/{template_id}/favorite")
async def toggle_favorite(
    template_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_visible_template(template_id, user, db)
    fav = await db.get(TemplateFavorite, {"user_id": user.id, "template_id": template_id})
    if fav is None:
        db.add(TemplateFavorite(user_id=user.id, template_id=template_id))
        favored = True
    else:
        await db.delete(fav)
        favored = False
    await db.commit()
    return {"favorite": favored}


@router.post("/{template_id}/use", response_model=TemplateOut)
async def mark_used(
    template_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    tpl = await _get_visible_template(template_id, user, db)
    tpl.usage_count += 1
    await db.commit()
    await db.refresh(tpl)
    return _to_out(tpl, await _favorites_of(db, user.id))
