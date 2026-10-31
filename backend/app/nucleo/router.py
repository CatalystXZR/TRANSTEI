"""Agregador de routers de la Ola B (retiro legacy: mantenimiento, nómina,
IVA, configuración y export).

Se monta bajo el router `/nucleo` ya existente (`app/nucleo/api.py`), de modo que
las rutas finales son `/api/v1/nucleo/...` sin duplicar el prefijo. Ningún router
de este módulo declara el tenant: todas las dependencias pasan por
`get_contexto_empresa` + `requiere_permiso`.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.nucleo.api_export import router as export_router
from app.nucleo.api_iva import router as iva_config_router
from app.nucleo.api_mantenimiento import router as mantenimiento_router
from app.nucleo.api_nomina import router as nomina_router

router = APIRouter()
router.include_router(mantenimiento_router)
router.include_router(nomina_router)
router.include_router(iva_config_router)
router.include_router(export_router)
