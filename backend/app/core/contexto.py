"""Contexto de request para la base de datos (RLS multiempresa + auditoría).

Por qué existe
--------------
La migración 0020 (`supabase/migrations/0020_rls_multiempresa.sql`) impone el
aislamiento por empresa con políticas RLS que leen el GUC `app.empresa_id`
(`nucleo.ctx_empresa()`). Ese GUC debe existir en **cada transacción** de un
request: los servicios hacen `commit()` intermedios (p. ej. tras crear el
viaje y antes de insertar sus reservas), y `set_config(..., true)` muere en el
COMMIT. Fijarlo una sola vez al inicio del request no alcanza.

Mecanismo
---------
1. `ContextoRequestMiddleware` (`app/main.py`) abre un `ContextoRequest` por
   request con `contexto_de_request()` y lo cierra al terminar (el `reset` del
   `ContextVar` garantiza que un request no herede el contexto del anterior).
2. `get_contexto_empresa` (`app/nucleo/deps.py`) rellena `auth_id`, `empresa_id`
   y `request_id` **después de resolver la membresía en el servidor** (nunca
   desde el body).
3. Un listener `begin` de SQLAlchemy en el engine (`app/core/database.py`) reaplica los
   GUCs al inicio de **cada** transacción de esa sesión: sobreviven a los
   `commit()` intermedios sin que los 31 servicios tengan que cambiar.

Fail-closed
-----------
Los GUCs se fijan siempre, incluso sin contexto: `app.empresa_id = ''` hace que
`nucleo.ctx_empresa()` devuelva NULL y toda política RLS filtre 0 filas. No se
depende de "no fijar nada": un valor viejo a nivel de sesión (`is_local=false`)
también queda neutralizado al inicio de la transacción siguiente. El trigger de
auditoría trata `''` como ausente (`coalesce(nullif(current_setting(...), ''), …)`),
así que no cambia el comportamiento actual.

`ContextoRequest` es mutable a propósito: las dependencias síncronas de FastAPI
corren en un hilo del pool (`run_in_threadpool`), que **copia** el
`ContextVar` pero comparte la instancia. Mutar el objeto es lo que hace visible
lo que resuelve `get_contexto_empresa` para el resto del request y para el
listener `begin` (que corre en el hilo que ejecuta la consulta).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlmodel import Session

GUC_EMPRESA = "app.empresa_id"
GUC_AUTH_ID = "nucleo.auth_id"
GUC_REQUEST_ID = "nucleo.request_id"

# `X-Request-ID` es correlación, no autoridad: se acota a un charset inocuo y a
# 128 caracteres para que no se convierta en un canal de basura hacia
# `nucleo.auditoria.request_id`.
_RE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

# Una sola ida y vuelta por transacción: los tres GUCs son independientes.
_SENTENCIA_CONTEXTO = text(
    "select set_config('app.empresa_id', :empresa_id, true),"
    " set_config('nucleo.auth_id', :auth_id, true),"
    " set_config('nucleo.request_id', :request_id, true)"
)


@dataclass
class ContextoRequest:
    """Datos de contexto que viajan con el request hasta PostgreSQL."""

    empresa_id: UUID | None = None
    auth_id: str | None = None
    request_id: str | None = None


_contexto: ContextVar[ContextoRequest | None] = ContextVar(
    "tei_contexto_request", default=None
)


def contexto_actual() -> ContextoRequest | None:
    """Contexto del request en curso, o `None` fuera de un request."""
    return _contexto.get()


def limpiar_request_id(valor: str | None) -> str | None:
    """Devuelve el `X-Request-ID` si es inocuo; si no, `None`."""
    if not valor:
        return None
    valor = valor.strip()
    return valor if _RE_REQUEST_ID.match(valor) else None


@contextmanager
def contexto_de_request(*, request_id: str | None = None) -> Iterator[ContextoRequest]:
    """Abre un contexto limpio para el request y lo descarta al terminar."""
    token: Token = _contexto.set(
        ContextoRequest(request_id=limpiar_request_id(request_id))
    )
    try:
        yield _contexto.get()  # type: ignore[misc]
    finally:
        _contexto.reset(token)


def _asegurar_contexto() -> ContextoRequest:
    """Contexto mutable del request.

    Fuera de un request (tests, scripts) crea uno local. Ese valor no se
    propaga a otros hilos, por eso el middleware es obligatorio en la app.
    """
    contexto = _contexto.get()
    if contexto is None:
        contexto = ContextoRequest()
        _contexto.set(contexto)
    return contexto


def fijar_auth_id(auth_id: str | None) -> None:
    _asegurar_contexto().auth_id = auth_id or None


def fijar_empresa(empresa_id: UUID | None) -> None:
    _asegurar_contexto().empresa_id = empresa_id


def fijar_request_id(request_id: str | None) -> None:
    _asegurar_contexto().request_id = limpiar_request_id(request_id)


def valores_contexto() -> dict[str, str]:
    """Valores de los GUCs. La ausencia se representa con `''` (fail-closed)."""
    contexto = _contexto.get() or ContextoRequest()
    return {
        "empresa_id": str(contexto.empresa_id) if contexto.empresa_id else "",
        "auth_id": contexto.auth_id or "",
        "request_id": contexto.request_id or "",
    }


def aplicar_contexto(connection: Connection) -> None:
    """Fija los GUCs en la transacción en curso de `connection`."""
    connection.execute(_SENTENCIA_CONTEXTO, valores_contexto())


def aplicar_contexto_sesion(session: Session) -> None:
    """Fija los GUCs en la transacción en curso de `session`.

    Necesario cuando el contexto cambia **después** de que la transacción ya
    empezó (el listener `begin` solo actúa al abrir una transacción).
    """
    session.execute(_SENTENCIA_CONTEXTO, valores_contexto())
