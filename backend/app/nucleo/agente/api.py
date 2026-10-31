"""Endpoint de diagnóstico del módulo agente: `GET /nucleo/agente/estado`.

Contrato: `docs/arquitectura/conector-agente-whatsapp.md` §6.5.

- **Permiso:** `agente:buzon` (deny-by-default; no se hereda por rol salvo
  `admin`, ver `permisos.py` y AB-02).
- **Nunca 500 por manifiesto roto:** 200 con `manifest.valido=false` y
  `tools.cargadas=0` (§2.5).
- **No expone secretos ni contactos.** Solo versión, componentes, el flag de la
  empresa del request y las tablas que faltan.
- **No ejecuta migraciones:** `to_regclass` es una lectura de catálogo.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.agente.registry import cargar_registry
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso

router = APIRouter(prefix="/nucleo/agente", tags=["agente"])

# Tablas sin las cuales el módulo no puede operar (§2.6). `modulos_empresa` es
# la llave 1; el resto son las tablas de 0021 que usan tools/auditoría/buzón.
TABLAS_REQUERIDAS: tuple[str, ...] = (
    "nucleo.modulos_empresa",
    "nucleo.contactos_whatsapp",
    "nucleo.permisos_contacto",
    "nucleo.conversaciones",
    "nucleo.conversacion_mensajes",
    "nucleo.solicitudes",
    "nucleo.hoja_ruta",
    "nucleo.auditoria_consultas_agente",
    "nucleo.id_comercial_contador",
)


class _Cerrado(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManifestEstado(_Cerrado):
    valido: bool
    version: str | None
    schema_di: str | None
    motivo: str | None


class EmpresaEstado(_Cerrado):
    habilitado: bool
    fuente: Literal["defecto", "fila"]


class ToolsEstado(_Cerrado):
    cargadas: int
    por_componente: dict[str, int]


class EstadoAgenteOut(_Cerrado):
    modulo_id: str
    manifest: ManifestEstado
    empresa: EmpresaEstado
    tools: ToolsEstado
    migraciones_requeridas: list[str]
    faltantes: list[str]


def _tablas_faltantes(session: Session) -> list[str]:
    faltantes: list[str] = []
    for nombre in TABLAS_REQUERIDAS:
        existe = session.execute(
            text("select to_regclass(:nombre)"), {"nombre": nombre}
        ).scalar_one()
        if existe is None:
            faltantes.append(nombre)
    return faltantes


def _estado_empresa(session: Session, contexto: ContextoEmpresa, faltantes: list[str]) -> EmpresaEstado:
    if "nucleo.modulos_empresa" in faltantes:
        return EmpresaEstado(habilitado=False, fuente="defecto")
    fila = session.execute(
        text(
            "select habilitado from nucleo.modulos_empresa "
            "where empresa_id = :empresa_id and modulo_id = :modulo_id"
        ),
        {"empresa_id": contexto.empresa_id, "modulo_id": "agente-whatsapp"},
    ).first()
    if fila is None:
        return EmpresaEstado(habilitado=False, fuente="defecto")
    return EmpresaEstado(habilitado=bool(fila[0]), fuente="fila")


@router.get("/estado", response_model=EstadoAgenteOut)
def estado(
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:buzon")),
    session: Session = Depends(get_session_nucleo),
) -> EstadoAgenteOut:
    registry = cargar_registry()
    faltantes = _tablas_faltantes(session)
    manifiesto = registry.estado()
    return EstadoAgenteOut(
        modulo_id="agente-whatsapp",
        manifest=ManifestEstado(**manifiesto),
        empresa=_estado_empresa(session, contexto, faltantes),
        tools=ToolsEstado(
            cargadas=registry.tools_cargadas,
            por_componente=registry.por_componente(),
        ),
        migraciones_requeridas=list(registry.migraciones),
        faltantes=faltantes,
    )
