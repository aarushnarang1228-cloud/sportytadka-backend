from fastapi import APIRouter

from app.api.v1.matches import router as matches_router
from app.api.v1.teams import router as teams_router
from app.api.v1.players import router as players_router
from app.api.v1.content import router as content_router
from app.api.v1.series import router as series_router
from app.api.v1.seo import router as seo_router
from app.api.v1.search import router as search_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(matches_router)
api_router.include_router(teams_router)
api_router.include_router(players_router)
api_router.include_router(content_router)
api_router.include_router(series_router)
api_router.include_router(seo_router)
api_router.include_router(search_router)
