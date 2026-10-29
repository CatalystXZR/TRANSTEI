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
from app.nucleo.api import router as nucleo_router
from app.nucleo.api_alertas import router as nucleo_alertas_router
from app.nucleo.api_bloqueos import router as nucleo_bloqueos_router
from app.nucleo.api_comercial import router as nucleo_comercial_router
from app.nucleo.api_conductor import router as nucleo_conductor_router
from app.nucleo.api_cutover import router as nucleo_cutover_router
from app.nucleo.api_expediente import router as nucleo_expediente_router
from app.nucleo.api_facturacion import router as nucleo_facturacion_router
from app.nucleo.api_gastos import router as nucleo_gastos_router
from app.nucleo.api_maestros import router as nucleo_maestros_router
from app.nucleo.api_permisos import router as nucleo_permisos_router
from app.nucleo.api_pod import router as nucleo_pod_router
from app.nucleo.api_rentabilidad import router as nucleo_rentabilidad_router

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
api_router.include_router(nucleo_router)
api_router.include_router(nucleo_maestros_router)
api_router.include_router(nucleo_comercial_router)
api_router.include_router(nucleo_bloqueos_router)
api_router.include_router(nucleo_expediente_router)
api_router.include_router(nucleo_pod_router)
api_router.include_router(nucleo_conductor_router)
api_router.include_router(nucleo_gastos_router)
api_router.include_router(nucleo_rentabilidad_router)
api_router.include_router(nucleo_facturacion_router)
api_router.include_router(nucleo_alertas_router)
api_router.include_router(nucleo_permisos_router)
api_router.include_router(nucleo_cutover_router)
