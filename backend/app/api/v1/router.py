from fastapi import APIRouter

from app.api.v1.endpoints.scenes import router as scenes_router
from app.api.v1.endpoints.analyses import router as analyses_router

api_router = APIRouter()

api_router.include_router(scenes_router)
api_router.include_router(analyses_router)
