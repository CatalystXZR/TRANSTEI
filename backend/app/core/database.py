"""Motores de base de datos de la aplicación (ADR-0005).

Dos motores, dos DSN, dos roles:

- **legacy** (`get_engine`, `get_session`): `settings.DATABASE_URL` con el rol
  actual (hoy `postgres`, `BYPASSRLS`) y atiende `public`. No cambia de
  comportamiento respecto de la versión anterior del backend.
- **núcleo** (`get_engine_nucleo`, `get_session_nucleo`): `settings.
  NUCLEO_DATABASE_URL` con el rol `tei_app` (`NOBYPASSRLS`) y atiende solo
  `nucleo`. Es el único motor cuyas consultas quedan filtradas por las
  políticas RLS de `supabase/migrations/0020_rls_multiempresa.sql`.

La frontera es el **esquema**, no el endpoint. La única excepción declarada es
el conteo de viajes legacy abiertos en `app/nucleo/servicio_cutover.py`, que
abre su propia sesión sobre el motor legacy (lectura de plataforma, no de
tenant); cualquier otra lectura de `public` desde el núcleo es un defecto y lo
vigila `backend/tests/test_f1_ola5_dos_engines.py`.

Contexto por transacción
------------------------
El listener `begin` (Ola 4) reaplica `app.empresa_id`, `nucleo.auth_id` y
`nucleo.request_id` al inicio de cada transacción de cada motor. En el engine
legacy es inocuo (el rol bypasea RLS y no hay políticas en `public`); en el del
núcleo es lo que hace fail-closed el aislamiento.

Fallback (desviación declarada del ADR-0005 §3.2.2)
---------------------------------------------------
El ADR pide que, sin `NUCLEO_DATABASE_URL`, `/nucleo/*` responda 503 (sin
fallback). La Ola 5 se ejecuta con la base de la app todavía en un solo rol y
con el objetivo explícito de no romper el arranque local; por eso aquí el
fallback **existe y se grita**: se usa `DATABASE_URL` (un solo motor) y se
registra `RLS inerte: configure NUCLEO_DATABASE_URL` (WARNING, marcador estable)
en cada creación del engine. La guarda de rol (`verificar_rol_nucleo`) sí es
fail-closed cuando la variable **está** configurada y apunta a un rol con
`BYPASSRLS`: ese caso es un error de despliegue, no un modo de operación.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, status
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.core.contexto import aplicar_contexto

logger = logging.getLogger(__name__)

MARCADOR_RLS_INERTE = "RLS inerte: configure NUCLEO_DATABASE_URL"
MARCADOR_RLS_INACTIVO = "nucleo_rls_inactivo"

_engine: Engine | None = None
_engine_nucleo: Engine | None = None
# Rol efectivo ya verificado del engine del núcleo (None = sin verificar).
_rol_nucleo: str | None = None
# True si el engine del núcleo salió del fallback a DATABASE_URL.
_nucleo_es_fallback: bool = False


def _fijar_contexto_transaccion(connection):
    """Reaplica los GUCs del request al inicio de **cada** transacción.

    Los servicios del núcleo hacen `commit()` intermedios; `set_config(..., true)`
    muere en el COMMIT, así que `app.empresa_id`, `nucleo.auth_id` y
    `nucleo.request_id` se fijan de nuevo al abrir la transacción siguiente.
    Sin contexto de request se fijan en `''`: RLS fail-closed
    (ver `app/core/contexto.py`).

    Se engancha en `begin` de la conexión (evento de SQLAlchemy, no DDL) para
    cubrir tanto las sesiones del request como cualquier conexión cruda del
    engine de la aplicación.
    """

    aplicar_contexto(connection)


def registrar_contexto_transaccion(engine: Engine) -> Engine:
    event.listen(engine, "begin", _fijar_contexto_transaccion)
    return engine


def _crear_engine(url: str) -> Engine:
    return registrar_contexto_transaccion(
        create_engine(url, pool_pre_ping=True, echo=settings.DEBUG)
    )


# ---------------------------------------------------------------------------
# Motor legacy (`public`, rol actual de la aplicación)
# ---------------------------------------------------------------------------
def get_engine() -> Engine:
    global _engine
    if _engine is None:
        if not settings.DATABASE_URL:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Base de datos no configurada. Copie backend/.env.example "
                    "a backend/.env y complete los datos del proyecto Supabase."
                ),
            )
        _engine = _crear_engine(settings.DATABASE_URL)
    return _engine


def get_session():
    with Session(get_engine()) as session:
        yield session


# ---------------------------------------------------------------------------
# Motor del núcleo (`nucleo`, rol `tei_app` sin BYPASSRLS)
# ---------------------------------------------------------------------------
def url_nucleo() -> tuple[str, bool]:
    """URL del engine del núcleo y si proviene del fallback.

    Devuelve `(url, es_fallback)`. Sin `NUCLEO_DATABASE_URL` se usa
    `DATABASE_URL` (un solo motor) y se registra el marcador estable
    `RLS inerte: configure NUCLEO_DATABASE_URL`.
    """
    url = (settings.NUCLEO_DATABASE_URL or "").strip()
    if url:
        return url, False
    logger.warning(
        "%s (DSN del rol tei_app, ADR-0005). El núcleo usará DATABASE_URL: "
        "un solo motor y SIN aislamiento por RLS. El legacy no se ve afectado.",
        MARCADOR_RLS_INERTE,
    )
    return settings.DATABASE_URL, True


def _estado_rol(engine: Engine) -> tuple[str, bool]:
    """`(current_user, rolbypassrls)` del rol efectivo del engine."""
    with engine.connect() as connection:
        fila = connection.execute(
            text(
                "select current_user as rol,"
                " coalesce((select r.rolbypassrls from pg_roles r"
                "            where r.rolname = current_user), false) as bypass"
            )
        ).one()
    return str(fila.rol), bool(fila.bypass)


def verificar_rol_nucleo(engine: Engine, *, fallback: bool) -> str:
    """Guarda de arranque del engine del núcleo (ADR-0005 §3.2.3).

    - rol sin `BYPASSRLS` ⇒ RLS vigente, se registra el rol y se sigue;
    - rol con `BYPASSRLS` **y** DSN explícito ⇒ ERROR `nucleo_rls_inactivo` y
      503: no se sirve tráfico del núcleo creyendo que hay aislamiento;
    - rol con `BYPASSRLS` en modo fallback ⇒ WARNING (el fallback ya se avisó al
      crear el engine): es el comportamiento declarado de esta ola.
    """
    rol, bypass = _estado_rol(engine)
    if not bypass:
        logger.info("Núcleo conectado como %s (rolbypassrls=false): RLS activo.", rol)
        return rol
    if fallback:
        logger.warning(
            "%s: el núcleo conectado como %s con rolbypassrls=true. "
            "El aislamiento por RLS NO está vigente (modo fallback).",
            MARCADOR_RLS_INERTE,
            rol,
        )
        return rol
    logger.error(
        "%s: NUCLEO_DATABASE_URL conecta como %s con rolbypassrls=true. "
        "Se rechaza el tráfico del núcleo (503): configure el DSN del rol "
        "tei_app o revierta el release.",
        MARCADOR_RLS_INACTIVO,
        rol,
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "El módulo núcleo no está disponible: la conexión configurada "
            "bypasea RLS. Contacte a operación."
        ),
    )


def get_engine_nucleo() -> Engine:
    """Engine del schema `nucleo` (rol de aplicación, sin BYPASSRLS)."""
    global _engine_nucleo, _nucleo_es_fallback
    if _engine_nucleo is None:
        url, es_fallback = url_nucleo()
        if not url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Base de datos del núcleo no configurada: defina "
                    "NUCLEO_DATABASE_URL (DSN del rol tei_app)."
                ),
            )
        # La guarda de rol se ejecuta una sola vez por proceso (lazy), en la
        # primera sesión, para no pagar una conexión en cada request.
        _nucleo_es_fallback = es_fallback
        _engine_nucleo = _crear_engine(url)
    return _engine_nucleo


def _asegurar_rol_nucleo(engine: Engine) -> None:
    global _rol_nucleo
    if _rol_nucleo is not None:
        return
    _rol_nucleo = verificar_rol_nucleo(engine, fallback=_nucleo_es_fallback)


def get_session_nucleo():
    """Sesión del núcleo: engine `tei_app` + contexto por transacción."""
    engine = get_engine_nucleo()
    _asegurar_rol_nucleo(engine)
    with Session(engine) as session:
        yield session


@contextmanager
def sesion_nucleo() -> Iterator[Session]:
    """Sesión del núcleo **fuera** del ciclo de request (agente, jobs).

    Aplica la misma guarda que `get_session_nucleo`: con un DSN explícito que
    conecte con `BYPASSRLS`, lanza 503 en vez de operar con RLS inerte. Un
    consumidor que abriera `Session(get_engine_nucleo())` por su cuenta se
    saltaría esa guarda y confiaría el aislamiento solo a sus filtros.
    """
    engine = get_engine_nucleo()
    _asegurar_rol_nucleo(engine)
    with Session(engine) as session:
        yield session
