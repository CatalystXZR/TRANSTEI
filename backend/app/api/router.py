from fastapi import APIRouter

from app.api.routes import (
    auth,
    catalogos,
    configuracion,
    dashboard,
    export,
    facturas,
    finanzas,
    gastos,
    kpis,
    liquidaciones,
    mantenimiento,
    viajes,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(catalogos.router)
api_router.include_router(viajes.router)
api_router.include_router(gastos.router)
api_router.include_router(dashboard.router)
api_router.include_router(facturas.router)
api_router.include_router(finanzas.router)
api_router.include_router(mantenimiento.router)
api_router.include_router(liquidaciones.router)
api_router.include_router(configuracion.router)
api_router.include_router(export.router)
api_router.include_router(kpis.router)
