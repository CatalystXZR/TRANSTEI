"""Panel de capacidades del chat in-app (`/nucleo/agente/configuracion`).

Permiso único: `agente:configurar`, deny-by-default y solo heredado por `admin`.
El gerente humano está excluido de `PERMISOS_AGENTE` (AB-02), así que no puede
autoconfigurarse ni ampliar las capacidades del agente LLM.

La fuente de verdad del catálogo es `capacidades.py`; esta API solo expone y
guarda overrides por empresa. Los límites duros (agente permitido, permiso
humano y módulo activo) se validan en `capacidades.actualizar`, no en la UI.
La empresa se resuelve en `get_contexto_empresa` (`X-Empresa-ID` + membresía):
el body no acepta `empresa_id`.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.agente.chat import capacidades
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso

router = APIRouter(
    prefix="/nucleo/agente/configuracion", tags=["agente"]
)

AgenteClave = Literal["gerente", "secretaria"]


class _Cerrado(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapacidadOut(_Cerrado):
    clave: str
    nombre: str
    descripcion: str
    grupo: str
    riesgo: Literal["bajo", "medio", "alto"]
    permiso: str
    habilitada: bool
    por_defecto: bool
    disponible: bool
    motivo_no_disponible: Literal["permiso", "modulo_inactivo"] | None
    modulo: str | None
    modulo_activo: bool | None


class AgenteConfigOut(_Cerrado):
    clave: str
    nombre: str
    capacidades: list[CapacidadOut]


class ConfiguracionOut(_Cerrado):
    agentes: list[AgenteConfigOut]


class CambioCapacidadIn(_Cerrado):
    capacidad: str = Field(min_length=3, max_length=80)
    habilitada: bool


class ActualizarIn(_Cerrado):
    agente: AgenteClave
    cambios: list[CambioCapacidadIn] = Field(min_length=1, max_length=50)


class RestablecerIn(_Cerrado):
    agente: AgenteClave


@router.get("", response_model=ConfiguracionOut)
def obtener_configuracion(
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:configurar")),
    session: Session = Depends(get_session_nucleo),
) -> ConfiguracionOut:
    """Capacidades de cada agente con su valor efectivo en esta empresa."""
    return ConfiguracionOut(
        agentes=[
            _agente_out(
                capacidades.configuracion_agente(
                    session, contexto, persona.clave
                )
            )
            for persona in _personas()
        ]
    )


@router.put("", response_model=AgenteConfigOut)
def actualizar_configuracion(
    body: ActualizarIn,
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:configurar")),
    session: Session = Depends(get_session_nucleo),
) -> AgenteConfigOut:
    """Guarda uno o más overrides y devuelve el agente actualizado.

    Si cualquier cambio viola el catálogo, el permiso humano o el módulo, no se
    escribe ninguno: la validación ocurre antes de los upserts y el endpoint
    hace `rollback()` ante cualquier excepción.
    """
    try:
        resultado = capacidades.actualizar(
            session,
            contexto,
            body.agente,
            [cambio.model_dump() for cambio in body.cambios],
        )
    except Exception:
        session.rollback()
        raise
    session.commit()
    return AgenteConfigOut(**resultado)


@router.post("/restablecer", response_model=AgenteConfigOut)
def restablecer_configuracion(
    body: RestablecerIn,
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:configurar")),
    session: Session = Depends(get_session_nucleo),
) -> AgenteConfigOut:
    """Devuelve todas las capacidades del agente a su valor por defecto."""
    try:
        resultado = capacidades.restablecer(session, contexto, body.agente)
    except Exception:
        session.rollback()
        raise
    session.commit()
    return AgenteConfigOut(**resultado)


def _personas():
    # Import local: `personas` no importa `capacidades`, pero este módulo sí
    # necesita el nombre visible del agente sin duplicar el catálogo.
    from app.nucleo.agente.chat.personas import AGENTES

    return AGENTES.values()


def _agente_out(datos: dict[str, Any]) -> AgenteConfigOut:
    """Valida la salida de `capacidades.configuracion_agente` contra el schema.

    El helper faltaba y el router nunca se había montado (SEC-069): la primera
    petición real fallaba con `NameError`. Se valida aquí para que un cambio en
    `capacidades.py` rompa el contrato de forma explícita.
    """
    return AgenteConfigOut.model_validate(datos)

