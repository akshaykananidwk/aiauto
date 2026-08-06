from fastapi import APIRouter

from app.api.v1 import admin, auth, dashboard, files, prompts, updates, users, ws

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(prompts.router)
api_router.include_router(files.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(admin.router)
api_router.include_router(updates.router)
api_router.include_router(ws.router)
