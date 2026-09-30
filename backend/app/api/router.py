from fastapi import APIRouter

from app.api.routes import auth, catalogos, dashboard, gastos, viajes

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(catalogos.router)
api_router.include_router(viajes.router)
api_router.include_router(gastos.router)
api_router.include_router(dashboard.router)
