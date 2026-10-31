"""Gate de cuatro llaves (contrato §4.3–§4.4, §4.7).

La autorización se calcula con una función **pura** (`autorizar`) sobre una
fuente de datos inyectable (`FuenteGate`). Eso permite probar la matriz
completa de denegaciones sin base y, en producción, leer las llaves en cada
invocación, sin caché (§4.8).

Orden (un cortocircuito por llave, todos auditables):

1. manifiesto válido;
2. identidad: contacto activo y OTP verificado;
3. llave 1: fila `(empresa_id, 'agente-whatsapp')` con `habilitado=true`;
4. llave 2: rol en `descriptor.roles`;
5. llave 3: ACL de componente (`variable is null`);
6. llave 4: ACL de variable.

Deny-by-default: solo `True` autoriza. `False`, `None` y ausencia son lo mismo.
El rol no sustituye la ACL y el flag de empresa no sustituye la ACL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.contexto import aplicar_contexto_sesion
from app.core.database import sesion_nucleo
from app.nucleo.agente.contexto import ContextoAgente
from app.nucleo.agente.manifest import Descriptor
from app.nucleo.errores import _sqlstate

logger = logging.getLogger("app.nucleo.agente.gate")

MODULO_ID = "agente-whatsapp"

# §4.4 — llave 1.
_SQL_MODULO = text(
    """
    select habilitado
      from nucleo.modulos_empresa
     where empresa_id = :empresa_id
       and modulo_id = :modulo_id
    """
)

# §4.4 — llave 3 (componente: variable NULL) y llave 4 (variable concreta).
_SQL_ACL_COMPONENTE = text(
    """
    select permitido
      from nucleo.permisos_contacto
     where empresa_id = :empresa_id
       and contacto_id = :contacto_id
       and componente = :componente
       and variable is null
    """
)
_SQL_ACL_VARIABLE = text(
    """
    select permitido
      from nucleo.permisos_contacto
     where empresa_id = :empresa_id
       and contacto_id = :contacto_id
       and componente = :componente
       and variable = :variable
    """
)

_aviso_tabla_ausente = False


class FuenteGate(Protocol):
    """Lecturas de las llaves 1, 3 y 4."""

    def modulo_habilitado(self, empresa_id: UUID) -> bool | None:
        """`True`/`False`; `None` si `nucleo.modulos_empresa` no existe."""

    def acl(
        self, contexto: ContextoAgente, componente: str, variable: str | None
    ) -> bool | None:
        """`True`/`False`; `None` si no hay fila o hay integridad rota."""


@dataclass(frozen=True, slots=True)
class Decision:
    permitido: bool
    codigo: str | None = None
    nivel: str | None = None  # identidad | modulo | rol | componente | variable
    componente: str = ""
    variable: str | None = None
    respuesta: str | None = None  # "NO_AUTORIZADO:rol", "MODULO_INACTIVO", …


def _denegar(
    codigo: str,
    nivel: str,
    *,
    componente: str,
    variable: str | None,
    respuesta: str,
) -> Decision:
    return Decision(
        permitido=False,
        codigo=codigo,
        nivel=nivel,
        componente=componente,
        variable=variable,
        respuesta=respuesta,
    )


def autorizar(
    *,
    descriptor: Descriptor,
    contexto: ContextoAgente,
    manifiesto_valido: bool,
    fuente: FuenteGate,
) -> Decision:
    """Aplica las seis compuertas en orden. No consulta la entrada."""
    componente = descriptor.componente
    variable = descriptor.variable

    if not manifiesto_valido:
        return _denegar(
            "MODULO_INACTIVO",
            "modulo",
            componente=componente,
            variable=variable,
            respuesta="MODULO_INACTIVO",
        )

    if not contexto.activo or contexto.otp_estado != "verificado":
        # Precondición de identidad, no quinta llave de ACL (INV-AW03 / D-12).
        return _denegar(
            "NO_AUTORIZADO",
            "identidad",
            componente=componente,
            variable=variable,
            respuesta="NO_AUTORIZADO:identidad",
        )

    if fuente.modulo_habilitado(contexto.empresa_id) is not True:
        return _denegar(
            "MODULO_INACTIVO",
            "modulo",
            componente=componente,
            variable=variable,
            respuesta="MODULO_INACTIVO",
        )

    if str(contexto.rol) not in descriptor.roles:
        return _denegar(
            "NO_AUTORIZADO",
            "rol",
            componente=componente,
            variable=variable,
            respuesta="NO_AUTORIZADO:rol",
        )

    if fuente.acl(contexto, componente, None) is not True:
        return _denegar(
            "NO_AUTORIZADO",
            "componente",
            componente=componente,
            variable=None,
            respuesta="NO_AUTORIZADO:componente",
        )

    if fuente.acl(contexto, componente, variable) is not True:
        return _denegar(
            "NO_AUTORIZADO",
            "variable",
            componente=componente,
            variable=variable,
            respuesta="NO_AUTORIZADO:variable",
        )

    return Decision(permitido=True, componente=componente, variable=variable)


class FuenteGateBD:
    """Implementación real: `tei_app` + `app.empresa_id` en cada lectura."""

    def modulo_habilitado(self, empresa_id: UUID) -> bool | None:
        global _aviso_tabla_ausente
        try:
            with sesion_nucleo() as session:
                aplicar_contexto_sesion(session)
                fila = session.execute(
                    _SQL_MODULO,
                    {"empresa_id": empresa_id, "modulo_id": MODULO_ID},
                ).first()
            if fila is None:
                return False
            return bool(fila[0])
        except ProgrammingError as exc:
            if _sqlstate(exc) == "42P01":
                if not _aviso_tabla_ausente:
                    _aviso_tabla_ausente = True
                    logger.warning(
                        "nucleo.modulos_empresa no existe: el gate queda cerrado "
                        "(fail-closed). Aplique la migración 0023."
                    )
                return None
            raise

    def acl(
        self, contexto: ContextoAgente, componente: str, variable: str | None
    ) -> bool | None:
        sql = _SQL_ACL_COMPONENTE if variable is None else _SQL_ACL_VARIABLE
        parametros = {
            "empresa_id": contexto.empresa_id,
            "contacto_id": contexto.contacto_id,
            "componente": componente,
        }
        if variable is not None:
            parametros["variable"] = variable
        with sesion_nucleo() as session:
            aplicar_contexto_sesion(session)
            filas = session.execute(sql, parametros).all()
        if len(filas) > 1:
            # `uq_permisos_contacto_valor` (0021:262-263) lo impide; si pasa,
            # la fila se escribió con BYPASSRLS y no es confiable.
            logger.error(
                "agente.acl_integridad_rota contacto=%s componente=%s variable=%s",
                contexto.contacto_id,
                componente,
                variable,
            )
            return None
        if not filas:
            return None
        return bool(filas[0][0])
