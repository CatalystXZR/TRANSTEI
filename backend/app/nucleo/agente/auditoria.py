"""Auditoría de consultas del agente (contrato §7).

`nucleo.auditoria_consultas_agente` es append-only por trigger
(`fn_consultas_agente_inmutable`, 0021:719-735). Este módulo **solo inserta**;
nunca actualiza ni borra.

Protocolo (§7.2):

- una fila por intento terminado, en una transacción separada de la tool;
- `empresa_id` y `contacto_id` salen del `ContextoAgente`, nunca del body;
- `datos_tocados` guarda IDs y metadatos, jamás el contenido (el comentario de
  la tabla lo prohíbe, 0021:714-716);
- si la inserción falla, la función devuelve `None` y **no** propaga: la
  decisión de qué hacer la toma el registry (lectura → `AUDITORIA_FALLIDA`;
  escritura → se conserva la solicitud y se registra en el log del runtime).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from app.core.contexto import aplicar_contexto_sesion
from app.core.database import sesion_nucleo
from app.nucleo.agente.contexto import ContextoAgente

logger = logging.getLogger("app.nucleo.agente.auditoria")

_MAX_TEXTO = 500
_MAX_IDS = 50

_SQL_INSERTAR = text(
    """
    insert into nucleo.auditoria_consultas_agente
        (empresa_id, contacto_id, conversacion_id, mensaje_id, componente,
         variable, herramienta, pregunta_resumida, datos_tocados,
         respuesta_resumida, acceso_otorgado, request_id)
    values
        (:empresa_id, :contacto_id, :conversacion_id, :mensaje_id, :componente,
         :variable, :herramienta, :pregunta, cast(:datos as jsonb),
         :respuesta, :acceso, :request_id)
    returning id
    """
)


def _recortar(valor: str | None) -> str | None:
    if valor is None:
        return None
    return valor[:_MAX_TEXTO]


def datos_tocados(
    *, ids: tuple[str, ...] | list[str], total: int, tool_version: int, schema_di: str
) -> dict[str, Any]:
    """`datos_tocados` de §7.3: IDs (máx. 50) + total + `_meta`."""
    recortados = [str(i) for i in list(ids)[:_MAX_IDS]]
    return {
        "ids": recortados,
        "total": int(total),
        "_meta": {"tool_version": int(tool_version), "schema_di": schema_di},
    }


def registrar_consulta(
    *,
    contexto: ContextoAgente,
    componente: str,
    variable: str | None,
    herramienta: str,
    acceso_otorgado: bool,
    respuesta: str,
    pregunta_resumida: str | None = None,
    datos: dict[str, Any] | None = None,
) -> int | None:
    """Inserta una fila de auditoría. Devuelve `id` o `None` si falló."""
    parametros = {
        "empresa_id": contexto.empresa_id,
        "contacto_id": contexto.contacto_id,
        "conversacion_id": contexto.conversacion_id,
        "mensaje_id": contexto.mensaje_id,
        "componente": componente,
        "variable": variable,
        "herramienta": herramienta,
        "pregunta": _recortar(pregunta_resumida),
        "datos": json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
        if datos is not None
        else None,
        "respuesta": _recortar(respuesta),
        "acceso": acceso_otorgado,
        "request_id": contexto.request_id,
    }
    try:
        with sesion_nucleo() as session:
            aplicar_contexto_sesion(session)
            fila = session.execute(_SQL_INSERTAR, parametros).one()
            session.commit()
            return int(fila[0])
    except Exception as exc:  # noqa: BLE001 — la auditoría nunca tumba la tool
        # Deliberado: si la auditoría propaga, una caída de la tabla de log
        # convierte una lectura en un 500 y oculta la causa. El código de error
        # se decide arriba (`AUDITORIA_FALLIDA`).
        #
        # Se registra tipo y SQLSTATE, nunca `repr(exc)`: el mensaje de
        # SQLAlchemy incluye la sentencia y sus parámetros, que aquí llevan la
        # pregunta resumida y los IDs (`SEC-037`, AGENTS.md §4).
        logger.error(
            "agente.auditoria_fallida herramienta=%s componente=%s request_id=%s "
            "tipo=%s sqlstate=%s",
            herramienta,
            componente,
            contexto.request_id,
            type(exc.orig).__name__ if getattr(exc, "orig", None) is not None else type(exc).__name__,
            getattr(getattr(exc, "orig", None), "sqlstate", None),
        )
        return None
