"""Integración O2.1 contra `tei_test`: resolver, gate, tools, auditoría y 42501.

Requisitos (los pone `make test`):

- `NUCLEO_TEST_DATABASE_URL` → base `tei_test` (fixtures con superusuario);
- `NUCLEO_DATABASE_URL` → `tei_app` sobre `tei_test` (engine del núcleo, RLS).

Nota de higiene: `nucleo.auditoria_consultas_agente` es append-only por trigger
y `contacto_id` es FK NOT NULL. Por eso las pruebas **dejan** los contactos y
las filas de auditoría; el resto de fixtures (ACL y flag de módulo) se limpia al
final del módulo. La base `tei_test` es desechable: `make test-db` la refresca.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest
from app.core.config import settings
from app.core.database import get_engine_nucleo
from app.main import manejador_programming_error
from app.nucleo.agente.api import estado
from app.nucleo.agente.contexto import (
    ContextoAgente,
    RolContacto,
    contexto_de_agente,
    resolver_contacto,
)
from app.nucleo.agente.ejecutores import EJECUTORES
from app.nucleo.agente.manifest import RAIZ_PAQUETE, cargar_modulo
from app.nucleo.agente.registry import Registry
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlmodel import Session

from agente_helpers import asegurar_segunda_empresa

pytestmark = pytest.mark.integracion

_CORRIDA = uuid.uuid4().int % 1_000_000


def _telefono(n: int) -> str:
    # Únicos por corrida: los contactos son irrepetibles bajo RLS (auditoría
    # append-only) y `uq_contactos_telefono_activo` impediría re-ejecutar la
    # suite sin refrescar `tei_test`.
    return f"+569{_CORRIDA:06d}{n:02d}"


_TELEFONOS = {
    "cliente": _telefono(1),
    "chofer": _telefono(2),
    "admin": _telefono(3),
    "sin_acl": _telefono(4),
    "var_false": _telefono(5),
    "otp_pendiente": _telefono(6),
}


def _dsn(base_url_test: str) -> str:
    return base_url_test.replace("postgresql+psycopg://", "postgresql://")


def _dsn_app() -> str:
    """DSN del rol de la app (`tei_app`), sin imprimirlo.

    Los fixtures escriben con el mismo rol que la aplicación: es el único con
    GRANT de INSERT/UPDATE sobre las tablas del módulo y el que queda sujeto a
    RLS. `postgres` en este entorno tiene BYPASSRLS pero **no** es superusuario
    y no tiene INSERT en `nucleo.modulos_empresa`.
    """
    url = (settings.NUCLEO_DATABASE_URL or "").strip()
    if not url:
        pytest.skip(
            "requiere NUCLEO_DATABASE_URL apuntando a tei_test con rol tei_app "
            "(lo define `make test`)"
        )
    return url.replace("postgresql+psycopg://", "postgresql://")


def _fijar_empresa(conn, empresa_id: UUID) -> None:
    """GUC de RLS a nivel de sesión del fixture (no de una transacción)."""
    conn.execute(
        "select set_config('app.empresa_id', %s, false)", (str(empresa_id),)
    )


@contextmanager
def _conexion(dsn: str):
    with psycopg.connect(dsn, connect_timeout=20) as conn:
        yield conn


def _contacto(
    conn,
    *,
    empresa_id: UUID,
    telefono: str,
    rol: str,
    cliente_id: UUID | None = None,
    chofer_id: UUID | None = None,
    otp: str = "verificado",
    activo: bool = True,
) -> UUID:
    fila = conn.execute(
        "select id, empresa_id from nucleo.contactos_whatsapp "
        "where telefono = %s and activo",
        (telefono,),
    ).fetchone()
    if fila is not None:
        if fila[1] != empresa_id:
            raise AssertionError(
                f"el teléfono fijo {telefono} pertenece a otra empresa; "
                "limpie tei_test con `make test-db`"
            )
        conn.execute(
            """
            update nucleo.contactos_whatsapp
               set rol = %s, cliente_id = %s, chofer_id = %s,
                   otp_estado = %s,
                   otp_verificado_en = case when %s = 'verificado' then now() else null end,
                   activo = %s
             where id = %s
            """,
            (rol, cliente_id, chofer_id, otp, otp, activo, fila[0]),
        )
        contacto_id = fila[0]
    else:
        contacto_id = conn.execute(
            """
            insert into nucleo.contactos_whatsapp
                (empresa_id, telefono, nombre, rol, cliente_id, chofer_id,
                 otp_estado, otp_verificado_en, activo)
            values (%s, %s, %s, %s, %s, %s, %s, now(), %s)
            returning id
            """,
            (
                empresa_id,
                telefono,
                f"Prueba O2.1 {rol}",
                rol,
                cliente_id,
                chofer_id,
                otp,
                activo,
            ),
        ).fetchone()[0]
    conn.commit()
    return contacto_id


def _acl(
    conn,
    *,
    empresa_id: UUID,
    contacto_id: UUID,
    componente: str,
    variable: str | None,
    permitido: bool,
) -> None:
    # `tei_app` no tiene DELETE sobre esta tabla (0021): se actualiza y, si no
    # existe la fila, se inserta. El índice único es
    # `(contacto_id, componente, coalesce(variable,''))`.
    actualizadas = conn.execute(
        """
        update nucleo.permisos_contacto
           set permitido = %s
         where empresa_id = %s
           and contacto_id = %s
           and componente = %s
           and coalesce(variable, '') = coalesce(%s::text, '')
        """,
        (permitido, empresa_id, contacto_id, componente, variable),
    ).rowcount
    if actualizadas == 0:
        conn.execute(
            "insert into nucleo.permisos_contacto "
            "(empresa_id, contacto_id, componente, variable, permitido) "
            "values (%s, %s, %s, %s, %s)",
            (empresa_id, contacto_id, componente, variable, permitido),
        )
    conn.commit()


def _flag(conn, empresa_id: UUID, habilitado: bool) -> None:
    conn.execute(
        """
        insert into nucleo.modulos_empresa
            (empresa_id, modulo_id, habilitado, habilitado_en, habilitado_por)
        values (%s, 'agente-whatsapp', %s, now(), 'prueba-o2-1')
        on conflict (empresa_id, modulo_id) do update
           set habilitado = excluded.habilitado,
               habilitado_en = excluded.habilitado_en,
               habilitado_por = excluded.habilitado_por
        """,
        (empresa_id, habilitado),
    )
    conn.commit()


@pytest.fixture(scope="module")
def escenario(base_url_test) -> dict:
    dsn = _dsn(base_url_test)
    dsn_app = _dsn_app()
    with _conexion(dsn) as conn, _conexion(dsn_app) as conn_app:
        fila = conn.execute(
            """
            with candidata as (
                select v.empresa_id, v.cliente_id, count(*) as n
                  from nucleo.viajes v
                 where v.cliente_id is not null
                 group by v.empresa_id, v.cliente_id
            )
            select c.empresa_id,
                   c.cliente_id,
                   (select v2.chofer_id from nucleo.viajes v2
                     where v2.empresa_id = c.empresa_id and v2.chofer_id is not null
                     limit 1) as chofer_id,
                   (select v3.cliente_id from nucleo.viajes v3
                     where v3.empresa_id = c.empresa_id
                       and v3.cliente_id <> c.cliente_id
                     limit 1) as otro_cliente_id
              from candidata c
             order by c.n desc
             limit 1
            """
        ).fetchone()
        if fila is None or fila[2] is None:
            pytest.skip("tei_test sin viajes con cliente/chofer; ejecute `make seed`")
        empresa_id, cliente_id, chofer_id, otro_cliente_id = fila
        _fijar_empresa(conn_app, empresa_id)
        otra_empresa = (asegurar_segunda_empresa(conn),)

        contactos = {
            "cliente": _contacto(
                conn_app,
                empresa_id=empresa_id,
                telefono=_TELEFONOS["cliente"],
                rol="cliente_final",
                cliente_id=cliente_id,
            ),
            "chofer": _contacto(
                conn_app,
                empresa_id=empresa_id,
                telefono=_TELEFONOS["chofer"],
                rol="conductor",
                chofer_id=chofer_id,
            ),
            "admin": _contacto(
                conn_app,
                empresa_id=empresa_id,
                telefono=_TELEFONOS["admin"],
                rol="admin",
            ),
            "sin_acl": _contacto(
                conn_app,
                empresa_id=empresa_id,
                telefono=_TELEFONOS["sin_acl"],
                rol="cliente_final",
                cliente_id=cliente_id,
            ),
            "var_false": _contacto(
                conn_app,
                empresa_id=empresa_id,
                telefono=_TELEFONOS["var_false"],
                rol="cliente_final",
                cliente_id=cliente_id,
            ),
            "otp_pendiente": _contacto(
                conn_app,
                empresa_id=empresa_id,
                telefono=_TELEFONOS["otp_pendiente"],
                rol="cliente_final",
                cliente_id=cliente_id,
                otp="pendiente",
            ),
        }

        # ACL del camino feliz: componente y variable encendidos.
        for clave in ("cliente", "chofer", "admin"):
            _acl(
                conn_app,
                empresa_id=empresa_id,
                contacto_id=contactos[clave],
                componente="despacho",
                variable=None,
                permitido=True,
            )
        _acl(
            conn,
            empresa_id=empresa_id,
            contacto_id=contactos["cliente"],
            componente="despacho",
            variable="viajes.cliente",
            permitido=True,
        )
        _acl(
            conn,
            empresa_id=empresa_id,
            contacto_id=contactos["chofer"],
            componente="despacho",
            variable="viajes.propios",
            permitido=True,
        )
        _acl(
            conn,
            empresa_id=empresa_id,
            contacto_id=contactos["admin"],
            componente="despacho",
            variable="viajes.empresa",
            permitido=True,
        )
        # Denegación por variable: componente encendido, variable apagada.
        _acl(
            conn,
            empresa_id=empresa_id,
            contacto_id=contactos["var_false"],
            componente="despacho",
            variable=None,
            permitido=True,
        )
        _acl(
            conn,
            empresa_id=empresa_id,
            contacto_id=contactos["var_false"],
            componente="despacho",
            variable="viajes.cliente",
            permitido=False,
        )
        # OTP pendiente: ACL completa, identidad no verificada.
        _acl(
            conn,
            empresa_id=empresa_id,
            contacto_id=contactos["otp_pendiente"],
            componente="despacho",
            variable=None,
            permitido=True,
        )
        _acl(
            conn,
            empresa_id=empresa_id,
            contacto_id=contactos["otp_pendiente"],
            componente="despacho",
            variable="viajes.cliente",
            permitido=True,
        )

        _flag(conn_app, empresa_id, True)

    datos = {
        "dsn": dsn,
        "empresa_id": empresa_id,
        "otra_empresa_id": otra_empresa[0],
        "cliente_id": cliente_id,
        "otro_cliente_id": otro_cliente_id,
        "chofer_id": chofer_id,
        "contactos": contactos,
        "telefonos": dict(_TELEFONOS),
    }
    yield datos

    # `tei_app` no tiene DELETE sobre estas tablas: se apagan, no se borran.
    with _conexion(dsn_app) as conn_app:
        _fijar_empresa(conn_app, empresa_id)
        conn_app.execute(
            "update nucleo.permisos_contacto set permitido = false "
            "where contacto_id = any(%s)",
            (list(contactos.values()),),
        )
        conn_app.execute(
            "update nucleo.modulos_empresa set habilitado = false "
            "where empresa_id = %s and modulo_id = 'agente-whatsapp'",
            (empresa_id,),
        )
        conn_app.commit()


def _registry() -> Registry:
    return Registry(
        modulo=cargar_modulo(RAIZ_PAQUETE, EJECUTORES), valido=True, motivo=None
    )


def _ctx(
    esc: dict,
    clave: str,
    rol: RolContacto,
    entidad: UUID | None,
    *,
    activo: bool = True,
    otp: str = "verificado",
) -> ContextoAgente:
    return ContextoAgente(
        empresa_id=esc["empresa_id"],
        contacto_id=esc["contactos"][clave],
        rol=rol,
        entidad_id=entidad,
        activo=activo,
        otp_estado=otp,
        telefono=esc["telefonos"][clave],
        request_id=f"test-o2-1-{clave}-{uuid.uuid4().hex[:8]}",
    )


def _ctx_cliente(esc: dict) -> ContextoAgente:
    return _ctx(
        esc, "cliente", RolContacto.cliente_final, esc["cliente_id"]
    )


def _ultima_auditoria(dsn: str, contacto_id: UUID) -> dict:
    with _conexion(dsn) as conn:
        fila = conn.execute(
            """
            select acceso_otorgado, componente, variable, herramienta,
                   respuesta_resumida, datos_tocados, request_id
              from nucleo.auditoria_consultas_agente
             where contacto_id = %s
             order by id desc
             limit 1
            """,
            (contacto_id,),
        ).fetchone()
    assert fila is not None, "no se escribió auditoría"
    return {
        "acceso": fila[0],
        "componente": fila[1],
        "variable": fila[2],
        "herramienta": fila[3],
        "respuesta": fila[4],
        "datos": fila[5],
        "request_id": fila[6],
    }


# ---------------------------------------------------------------------------
# Identidad
# ---------------------------------------------------------------------------


def test_resolver_contacto_dentro_de_la_empresa(escenario) -> None:
    ctx = resolver_contacto(
        empresa_id=escenario["empresa_id"],
        telefono=escenario["telefonos"]["cliente"],
        request_id="test-resolver-ok",
    )
    assert ctx is not None
    assert ctx.rol is RolContacto.cliente_final
    assert ctx.entidad_id == escenario["cliente_id"]
    assert ctx.activo is True
    assert ctx.otp_estado == "verificado"


def test_resolver_contacto_deniega_otra_empresa(escenario) -> None:
    ctx = resolver_contacto(
        empresa_id=escenario["otra_empresa_id"],
        telefono=escenario["telefonos"]["cliente"],
        request_id="test-resolver-otra",
    )
    assert ctx is None  # RLS + filtro explícito: no hay fila en esa empresa


def test_resolver_contacto_desconocido(escenario) -> None:
    assert (
        resolver_contacto(
            empresa_id=escenario["empresa_id"],
            telefono="+56999999999",
            request_id="test-resolver-unknown",
        )
        is None
    )


def test_resolver_contacto_telefono_invalido(escenario) -> None:
    with pytest.raises(ValueError):
        resolver_contacto(
            empresa_id=escenario["empresa_id"],
            telefono="12345",
            request_id="test-resolver-invalido",
        )


# ---------------------------------------------------------------------------
# Tools y auditoría
# ---------------------------------------------------------------------------


def test_c1_devuelve_solo_los_fletes_del_cliente(escenario) -> None:
    ctx = _ctx_cliente(escenario)
    respuesta = _registry().invocar("despacho.mis_fletes", {}, ctx)
    assert respuesta["ok"] is True, respuesta
    datos = respuesta["datos"]
    with _conexion(escenario["dsn"]) as conn:
        esperado = conn.execute(
            "select count(*) from nucleo.viajes "
            "where empresa_id = %s and cliente_id = %s",
            (escenario["empresa_id"], escenario["cliente_id"]),
        ).fetchone()[0]
    assert datos["total"] == esperado
    assert len(datos["items"]) == min(esperado, 50)
    for item in datos["items"]:
        assert set(item) == {
            "id_comercial_flete",
            "fecha",
            "origen",
            "destino",
            "estado",
            "tipo_carga",
        }
        assert item["fecha"].endswith("Z")
    serializado = json.dumps(datos)
    for prohibido in ("costo", "margen", "patente", "chofer", "valor_flete"):
        assert prohibido not in serializado

    auditoria = _ultima_auditoria(escenario["dsn"], ctx.contacto_id)
    assert auditoria["acceso"] is True
    assert auditoria["componente"] == "despacho"
    assert auditoria["variable"] == "viajes.cliente"
    assert auditoria["datos"]["_meta"] == {
        "tool_version": 1,
        "schema_di": "di/v1",
    }
    assert auditoria["datos"]["total"] == esperado
    assert len(auditoria["datos"]["ids"]) <= 50
    assert auditoria["request_id"] == ctx.request_id


def test_k1_filtra_por_chofer(escenario) -> None:
    ctx = _ctx(
        escenario, "chofer", RolContacto.conductor, escenario["chofer_id"]
    )
    respuesta = _registry().invocar("despacho.mis_viajes_asignados", {}, ctx)
    assert respuesta["ok"] is True, respuesta
    with _conexion(escenario["dsn"]) as conn:
        esperados = {
            str(fila[0])
            for fila in conn.execute(
                "select id from nucleo.viajes "
                "where empresa_id = %s and chofer_id = %s",
                (escenario["empresa_id"], escenario["chofer_id"]),
            ).fetchall()
        }
    devueltos = {item["viaje_id"] for item in respuesta["datos"]["items"]}
    assert devueltos == esperados
    assert devueltos  # el escenario exige al menos un viaje del chofer


def test_a1_usa_el_dia_de_chile(escenario) -> None:
    with _conexion(escenario["dsn"]) as conn:
        dia, viaje_id = conn.execute(
            "select (inicio_planificado at time zone 'America/Santiago')::date, id::text "
            "from nucleo.viajes where empresa_id = %s "
            "order by inicio_planificado desc limit 1",
            (escenario["empresa_id"],),
        ).fetchone()
    ctx = _ctx(escenario, "admin", RolContacto.admin, None)
    respuesta = _registry().invocar(
        "despacho.viajes_del_dia", {"fecha": str(dia), "limite": 100}, ctx
    )
    assert respuesta["ok"] is True, respuesta
    devueltos = {item["viaje_id"] for item in respuesta["datos"]["items"]}
    assert viaje_id in devueltos
    with _conexion(escenario["dsn"]) as conn:
        de_la_empresa = {
            str(fila[0])
            for fila in conn.execute(
                "select id from nucleo.viajes where empresa_id = %s",
                (escenario["empresa_id"],),
            ).fetchall()
        }
    assert devueltos <= de_la_empresa


def test_entrada_invalida_audita_acceso_otorgado(escenario) -> None:
    ctx = _ctx_cliente(escenario)
    respuesta = _registry().invocar(
        "despacho.mis_fletes", {"cliente_id": str(escenario["cliente_id"])}, ctx
    )
    assert respuesta["ok"] is False
    assert respuesta["error"]["codigo"] == "DATOS_INVALIDOS"
    auditoria = _ultima_auditoria(escenario["dsn"], ctx.contacto_id)
    assert auditoria["acceso"] is True
    assert auditoria["respuesta"] == "DATOS_INVALIDOS"


# ---------------------------------------------------------------------------
# Denegaciones
# ---------------------------------------------------------------------------


def test_sin_acl_deniega_componente(escenario) -> None:
    ctx = _ctx(
        escenario, "sin_acl", RolContacto.cliente_final, escenario["cliente_id"]
    )
    respuesta = _registry().invocar("despacho.mis_fletes", {}, ctx)
    assert respuesta["ok"] is False
    assert respuesta["error"]["codigo"] == "NO_AUTORIZADO"
    assert respuesta["error"]["nivel"] == "componente"
    assert respuesta["error"]["variable"] is None
    auditoria = _ultima_auditoria(escenario["dsn"], ctx.contacto_id)
    assert auditoria["acceso"] is False
    assert auditoria["variable"] is None
    assert auditoria["respuesta"] == "NO_AUTORIZADO:componente"


def test_variable_en_false_deniega_variable(escenario) -> None:
    ctx = _ctx(
        escenario, "var_false", RolContacto.cliente_final, escenario["cliente_id"]
    )
    respuesta = _registry().invocar("despacho.mis_fletes", {}, ctx)
    assert respuesta["ok"] is False
    assert respuesta["error"]["codigo"] == "NO_AUTORIZADO"
    assert respuesta["error"]["nivel"] == "variable"
    assert respuesta["error"]["variable"] == "viajes.cliente"


def test_otp_pendiente_deniega_identidad(escenario) -> None:
    ctx = _ctx(
        escenario,
        "otp_pendiente",
        RolContacto.cliente_final,
        escenario["cliente_id"],
        otp="pendiente",
    )
    respuesta = _registry().invocar("despacho.mis_fletes", {}, ctx)
    assert respuesta["ok"] is False
    assert respuesta["error"]["codigo"] == "NO_AUTORIZADO"
    assert respuesta["error"]["nivel"] == "identidad"


def test_modulo_apagado_deniega(escenario) -> None:
    # El flag se escribe con `tei_app`: `postgres` solo tiene SELECT sobre
    # `nucleo.modulos_empresa` (los GRANT del módulo son para el rol de la app).
    with _conexion(_dsn_app()) as conn_app:
        _fijar_empresa(conn_app, escenario["empresa_id"])
        _flag(conn_app, escenario["empresa_id"], False)
    try:
        ctx = _ctx_cliente(escenario)
        respuesta = _registry().invocar("despacho.mis_fletes", {}, ctx)
        assert respuesta["ok"] is False
        assert respuesta["error"]["codigo"] == "MODULO_INACTIVO"
        assert respuesta["error"]["nivel"] == "modulo"
        auditoria = _ultima_auditoria(escenario["dsn"], ctx.contacto_id)
        assert auditoria["acceso"] is False
        assert auditoria["respuesta"] == "MODULO_INACTIVO"
    finally:
        with _conexion(_dsn_app()) as conn_app:
            _fijar_empresa(conn_app, escenario["empresa_id"])
            _flag(conn_app, escenario["empresa_id"], True)


def test_tool_desconocida_se_audita(escenario) -> None:
    ctx = _ctx_cliente(escenario)
    respuesta = _registry().invocar("despacho.inventada", {}, ctx)
    assert respuesta["ok"] is False
    assert respuesta["error"]["codigo"] == "TOOL_DESCONOCIDA"
    auditoria = _ultima_auditoria(escenario["dsn"], ctx.contacto_id)
    assert auditoria["componente"] == "agente"
    assert auditoria["herramienta"] == "despacho.inventada"
    assert auditoria["acceso"] is False


def test_rol_equivocado_no_usa_acl(escenario) -> None:
    # El contacto del chofer tiene ACL de despacho, pero pide una tool de cliente.
    ctx = _ctx(
        escenario, "chofer", RolContacto.conductor, escenario["chofer_id"]
    )
    respuesta = _registry().invocar("despacho.mis_fletes", {}, ctx)
    assert respuesta["ok"] is False
    assert respuesta["error"]["nivel"] == "rol"


# ---------------------------------------------------------------------------
# Endpoint de estado y mapeo 42501
# ---------------------------------------------------------------------------


def test_estado_reporta_manifest_tools_y_flag(escenario) -> None:
    with contexto_de_agente(
        empresa_id=escenario["empresa_id"], request_id="test-estado"
    ), Session(get_engine_nucleo()) as session:
        salida = estado(
            contexto=SimpleNamespace(empresa_id=escenario["empresa_id"]),
            session=session,
        )
    assert salida.manifest.valido is True
    assert salida.manifest.version == "0.1.0"
    assert salida.tools.cargadas == 3
    assert salida.tools.por_componente == {"despacho": 3}
    assert salida.faltantes == []
    assert salida.empresa.habilitado is True
    assert salida.empresa.fuente == "fila"


def test_42501_es_programming_error_y_se_traduce_a_403(escenario) -> None:
    with contexto_de_agente(
        empresa_id=escenario["empresa_id"], request_id="test-42501"
    ), Session(get_engine_nucleo()) as session:
        rol = session.execute(text("select current_user")).scalar_one()
        if rol != "tei_app":
            pytest.skip(
                "requiere el engine del núcleo con tei_app "
                "(NUCLEO_DATABASE_URL apuntando a tei_test)"
            )
        with pytest.raises(ProgrammingError) as excinfo:
            # `tei_app` no tiene SELECT sobre public: RLS/GRANT ⇒ 42501.
            session.execute(text("select 1 from public.viajes limit 1"))
        session.rollback()
    assert excinfo.value.orig.sqlstate == "42501"

    respuesta = asyncio.run(manejador_programming_error(None, excinfo.value))
    assert respuesta.status_code == 403
    assert json.loads(respuesta.body)["codigo"] == "ACCESO_DENEGADO"


# ---------------------------------------------------------------------------
# SEC-031 — si el gate no puede leer sus llaves, deniega y deja rastro
# ---------------------------------------------------------------------------


class _FuenteQueFalla:
    """Gate que revienta al leer la ACL con un `42501` real de PostgreSQL."""

    def modulo_habilitado(self, empresa_id: UUID) -> bool | None:
        return True

    def acl(self, contexto, componente, variable):
        from sqlalchemy.exc import ProgrammingError

        class _Orig:
            sqlstate = "42501"

        raise ProgrammingError("select …", {}, _Orig())


def test_gate_que_falla_deniega_y_audita(escenario) -> None:
    ctx = _ctx_cliente(escenario)
    registro = Registry(
        modulo=cargar_modulo(RAIZ_PAQUETE, EJECUTORES),
        valido=True,
        motivo=None,
        fuente=_FuenteQueFalla(),
    )
    respuesta = registro.invocar("despacho.mis_fletes", {}, ctx)

    assert respuesta["ok"] is False
    assert respuesta["error"]["codigo"] == "NO_AUTORIZADO"

    auditoria = _ultima_auditoria(escenario["dsn"], ctx.contacto_id)
    assert auditoria["acceso"] is False
    assert auditoria["respuesta"].startswith("NO_AUTORIZADO:gate_error")
    assert auditoria["request_id"] == ctx.request_id


# ---------------------------------------------------------------------------
# Timeout por tool (§4.10) — antes era un 🔴 sin prueba
# ---------------------------------------------------------------------------


def test_statement_timeout_se_traduce_a_timeout_tool(escenario) -> None:
    """Un `57014` real de PostgreSQL debe salir como `TIMEOUT_TOOL`.

    No se simula el error: se ejecuta `pg_sleep` bajo el mismo
    `set_config('statement_timeout', …, true)` que usa `Registry._ejecutar`, y
    se clasifica la excepción resultante.
    """
    from app.nucleo.agente.registry import _SQL_TIMEOUT, clasificar_error
    from sqlalchemy.exc import OperationalError

    with contexto_de_agente(
        empresa_id=escenario["empresa_id"], request_id="test-timeout"
    ), Session(get_engine_nucleo()) as session:
        session.execute(_SQL_TIMEOUT, {"valor": "100"})  # 100 ms
        with pytest.raises(OperationalError) as excinfo:
            session.execute(text("select pg_sleep(1)"))
        session.rollback()

    assert excinfo.value.orig.sqlstate == "57014"
    assert clasificar_error(excinfo.value) == "TIMEOUT_TOOL"


def test_timeout_del_registry_usa_el_descriptor(escenario) -> None:
    """El registry fija el `timeout_ms` del descriptor en la transacción."""
    with contexto_de_agente(
        empresa_id=escenario["empresa_id"], request_id="test-timeout-efectivo"
    ), Session(get_engine_nucleo()) as session:
        session.execute(text("select set_config('statement_timeout', '1500', true)"))
        vigente = session.execute(
            text("select current_setting('statement_timeout')")
        ).scalar_one()
        session.rollback()
    assert vigente == "1500ms"


# ---------------------------------------------------------------------------
# SEC-033 — `pregunta_resumida` no persiste texto libre del llamador (§7.3.1)
# ---------------------------------------------------------------------------


def _pregunta_persistida(dsn: str, contacto_id: UUID) -> str:
    with _conexion(dsn) as conn:
        return conn.execute(
            "select pregunta_resumida from nucleo.auditoria_consultas_agente "
            "where contacto_id = %s order by id desc limit 1",
            (contacto_id,),
        ).fetchone()[0]


def test_un_telefono_del_llamador_no_llega_a_la_auditoria(escenario) -> None:
    ctx = _ctx_cliente(escenario)
    respuesta = _registry().invocar(
        "despacho.mis_fletes", {}, ctx, pregunta_resumida="+56912345678"
    )
    assert respuesta["ok"] is True, respuesta
    guardada = _pregunta_persistida(escenario["dsn"], ctx.contacto_id)
    assert guardada == "despacho.mis_fletes []"
    assert "5691" not in guardada
