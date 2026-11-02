"""Cutover legacy: estado y congelamiento de escrituras (P0-13).

El middleware de `app.main` consulta `legacy_congelado()` para bloquear
POST/PUT/PATCH/DELETE en los routers legacy. El schema `nucleo` sigue operando.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import text
from sqlmodel import Session

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import ErrorPersistencia
from app.nucleo.schemas import CutoverEstadoOut

logger = logging.getLogger(__name__)

_CACHE_TTL = 5.0
_cache: tuple[float, bool] | None = None


def legacy_congelado() -> bool:
    """Consulta cacheada del flag para el middleware.

    Fail-closed (RA-04): si la lectura falla o la fila de control no existe,
    se asume CONGELADO. No se puede habilitar la escritura legacy sin haber
    leído el estado real del cutover; un error silencioso no debe reabrir
    escrituras que tal vez fueron congeladas deliberadamente.
    """
    global _cache
    ahora = time.monotonic()
    if _cache is not None and ahora - _cache[0] < _CACHE_TTL:
        return _cache[1]
    from app.core.database import get_engine

    try:
        with Session(get_engine()) as session:
            valor = session.execute(
                text(
                    "select legacy_escritura_congelada from nucleo.cutover_control "
                    "where id = true"
                )
            ).scalar_one_or_none()
    except Exception:
        logger.exception(
            "Cutover: no se pudo leer el flag de congelamiento; "
            "se asume CONGELADO (fail-closed)."
        )
        congelado = True
    else:
        if valor is None:
            logger.warning(
                "Cutover: no existe fila de control en nucleo.cutover_control; "
                "se asume CONGELADO (fail-closed)."
            )
            congelado = True
        else:
            congelado = bool(valor)
    _cache = (ahora, congelado)
    return congelado


def invalidar_cache() -> None:
    global _cache
    _cache = None


class ServicioCutover:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa

    def estado(self) -> CutoverEstadoOut:
        fila = self.session.execute(
            text(
                "select legacy_escritura_congelada, congelada_en, congelada_por, "
                "motivo, updated_at from nucleo.cutover_control where id = true"
            )
        ).mappings().first()
        legacy_abiertos = 0
        # 0028 retiró el esquema legacy `public`: ya no existen viajes legacy que
        # contar. El estado del cutover se conserva como registro histórico.
        legacy_abiertos = 0
        nucleo_viajes = int(
            self.session.execute(
                text("select count(*) from nucleo.viajes where empresa_id = :empresa_id"),
                {"empresa_id": self.empresa.id},
            ).scalar_one()
        )
        if fila is None:
            return CutoverEstadoOut(
                legacy_escritura_congelada=False,
                legacy_viajes_abiertos=legacy_abiertos,
                nucleo_viajes=nucleo_viajes,
                mensaje="No existe registro de cutover; se asume legacy abierto.",
            )
        return CutoverEstadoOut(
            legacy_escritura_congelada=bool(fila["legacy_escritura_congelada"]),
            congelada_en=fila["congelada_en"],
            congelada_por=fila["congelada_por"],
            motivo=fila["motivo"],
            updated_at=fila["updated_at"],
            legacy_viajes_abiertos=legacy_abiertos,
            nucleo_viajes=nucleo_viajes,
            mensaje=(
                "Escritura legacy CONGELADA: nucleo es la única fuente de verdad."
                if fila["legacy_escritura_congelada"]
                else "Escritura legacy ABIERTA: aún se puede escribir en el sistema anterior."
            ),
        )

    def congelar(self, motivo: str) -> CutoverEstadoOut:
        resultado = self.session.execute(
            text(
                """
                update nucleo.cutover_control
                   set legacy_escritura_congelada = true,
                       congelada_en = now(),
                       congelada_por = :auth_id,
                       motivo = :motivo,
                       updated_at = now()
                 where id = true
                """
            ),
            {"auth_id": self.contexto.auth_id, "motivo": motivo.strip()},
        )
        # SEC-016: sin la fila única de control, el update afecta 0 filas y el
        # commit "triunfaría" dejando el estado contradictorio (estado() dice
        # abierto, el middleware fail-closed bloquea). Se falla explícitamente.
        if resultado.rowcount != 1:
            self.session.rollback()
            raise ErrorPersistencia(
                "No se pudo congelar el legacy: falta la fila única de control "
                "(nucleo.cutover_control). Aplique la migración 0014."
            )
        self.session.commit()
        invalidar_cache()
        return self.estado()

    def descongelar(self, motivo: str) -> CutoverEstadoOut:
        resultado = self.session.execute(
            text(
                """
                update nucleo.cutover_control
                   set legacy_escritura_congelada = false,
                       congelada_en = null,
                       congelada_por = :auth_id,
                       motivo = :motivo,
                       updated_at = now()
                 where id = true
                """
            ),
            {"auth_id": self.contexto.auth_id, "motivo": motivo.strip()},
        )
        if resultado.rowcount != 1:
            self.session.rollback()
            raise ErrorPersistencia(
                "No se pudo descongelar el legacy: falta la fila única de control "
                "(nucleo.cutover_control). Aplique la migración 0014."
            )
        self.session.commit()
        invalidar_cache()
        return self.estado()
