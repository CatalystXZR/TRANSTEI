"""Integración O2.2 contra `tei_test`: buzón de solicitudes (contrato §6.1–§6.7).

Usa el servicio directamente con un `ContextoEmpresa` armado a mano: lo que se
prueba es la garantía del servidor (empresa, transición, concurrencia), no el
middleware de JWT, que ya está cubierto por otras suites.

Los fixtures escriben con `tei_app` (rol con GRANT y sujeto a RLS), igual que
la aplicación. Las solicitudes y hojas de ruta de prueba quedan en `tei_test`;
`make test-db` refresca.
"""

from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest
from app.core.config import settings
from app.core.contexto import (
    contexto_de_request,
    fijar_auth_id,
    fijar_empresa,
    fijar_request_id,
)
from app.core.database import get_engine_nucleo
from app.nucleo.agente import solicitudes as servicio
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    Autoaprobacion,
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    SolicitudYaDecidida,
    TipoSinEjecutor,
)
from app.nucleo.models import RolEmpresa
from sqlmodel import Session

pytestmark = pytest.mark.integracion


def _dsn(base_url_test: str) -> str:
    return base_url_test.replace("postgresql+psycopg://", "postgresql://")


def _dsn_app() -> str:
    url = (settings.NUCLEO_DATABASE_URL or "").strip()
    if not url:
        pytest.skip("requiere NUCLEO_DATABASE_URL con rol tei_app (lo define `make test`)")
    return url.replace("postgresql+psycopg://", "postgresql://")


@contextmanager
def _conexion(dsn: str):
    with psycopg.connect(dsn, connect_timeout=20) as conn:
        yield conn


def _fijar(conn, empresa_id: UUID) -> None:
    conn.execute("select set_config('app.empresa_id', %s, false)", (str(empresa_id),))


@contextmanager
def _sesion(ctx: ContextoEmpresa):
    """Sesión con los GUC de RLS que fija `get_contexto_empresa` en producción."""
    with contexto_de_request(request_id=ctx.request_id):
        fijar_auth_id(ctx.auth_id)
        fijar_request_id(ctx.request_id)
        fijar_empresa(ctx.empresa_id)
        with Session(get_engine_nucleo()) as session:
            yield session


def _contexto(empresa_id: UUID, auth_id: UUID, rol: RolEmpresa = RolEmpresa.admin) -> ContextoEmpresa:
    return ContextoEmpresa(
        auth_id=str(auth_id),
        empresa=SimpleNamespace(id=empresa_id),  # type: ignore[arg-type]
        rol=rol,
        request_id=f"test-o2-2-{uuid.uuid4().hex[:8]}",
    )


def _crear_solicitud(
    conn,
    *,
    empresa_id: UUID,
    tipo: str,
    payload: dict,
    contacto_id: UUID | None = None,
    usuario_empresa_id: UUID | None = None,
    viaje_id: UUID | None = None,
    estado: str = "pendiente",
) -> UUID:
    return conn.execute(
        """
        insert into nucleo.solicitudes
            (empresa_id, tipo, solicitante_contacto_id, solicitante_usuario_empresa_id,
             viaje_id, payload, estado)
        values (%s, cast(%s as nucleo.tipo_solicitud), %s, %s, %s,
                cast(%s as jsonb), cast(%s as nucleo.estado_solicitud))
        returning id
        """,
        (
            empresa_id,
            tipo,
            contacto_id,
            usuario_empresa_id,
            viaje_id,
            json.dumps(payload),
            estado,
        ),
    ).fetchone()[0]


def _crear_hoja_ruta(
    conn, *, empresa_id: UUID, contacto_id: UUID, solicitud_id: UUID, payload: dict
) -> UUID:
    return conn.execute(
        """
        insert into nucleo.hoja_ruta
            (empresa_id, contacto_id, solicitud_id, payload, estado)
        values (%s, %s, %s, cast(%s as jsonb), 'solicitud_creada')
        returning id
        """,
        (empresa_id, contacto_id, solicitud_id, json.dumps(payload)),
    ).fetchone()[0]


@pytest.fixture(scope="module")
def escenario(base_url_test) -> dict:
    dsn = _dsn(base_url_test)
    dsn_app = _dsn_app()
    with _conexion(dsn) as conn:
        fila = conn.execute(
            """
            select v.empresa_id, v.cliente_id, v.id
              from nucleo.viajes v
             where v.cliente_id is not null
             limit 1
            """
        ).fetchone()
        if fila is None:
            pytest.skip("tei_test sin viajes; ejecute `make seed`")
        empresa_id, cliente_id, viaje_id = fila
        otra = conn.execute(
            "select id from nucleo.empresas where id <> %s limit 1", (empresa_id,)
        ).fetchone()
        if otra is None:
            pytest.skip("tei_test necesita dos empresas")
        miembro = conn.execute(
            "select id, auth_id from nucleo.usuarios_empresa where empresa_id=%s limit 1",
            (empresa_id,),
        ).fetchone()
        if miembro is None:
            pytest.skip("tei_test sin membresías para la empresa del escenario")
        otro_miembro = conn.execute(
            "select id, auth_id from nucleo.usuarios_empresa "
            "where empresa_id=%s and id <> %s limit 1",
            (empresa_id, miembro[0]),
        ).fetchone()
        if otro_miembro is None:
            pytest.skip("se necesitan dos membresías para probar autoaprobación")

    with _conexion(dsn_app) as conn_app:
        _fijar(conn_app, empresa_id)
        contacto_id = conn_app.execute(
            """
            insert into nucleo.contactos_whatsapp
                (empresa_id, telefono, nombre, rol, cliente_id, otp_estado, otp_verificado_en)
            values (%s, %s, 'Prueba O2.2', 'cliente_final', %s, 'verificado', now())
            returning id
            """,
            (empresa_id, f"+5691{uuid.uuid4().int % 10**7:07d}", cliente_id),
        ).fetchone()[0]
        conn_app.commit()

    return {
        "dsn": dsn,
        "dsn_app": dsn_app,
        "empresa_id": empresa_id,
        "otra_empresa_id": otra[0],
        "cliente_id": cliente_id,
        "viaje_id": viaje_id,
        "contacto_id": contacto_id,
        "miembro_id": miembro[0],
        "miembro_auth": miembro[1],
        "otro_miembro_id": otro_miembro[0],
        "otro_miembro_auth": otro_miembro[1],
    }


def _nueva(esc: dict, **kwargs) -> UUID:
    with _conexion(esc["dsn_app"]) as conn:
        _fijar(conn, esc["empresa_id"])
        sid = _crear_solicitud(
            conn,
            empresa_id=esc["empresa_id"],
            contacto_id=kwargs.pop("contacto_id", esc["contacto_id"]),
            **kwargs,
        )
        conn.commit()
        return sid


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


def test_listar_solo_devuelve_la_empresa(escenario) -> None:
    sid = _nueva(escenario, tipo="otra", payload={"a": 1, "b": 2})
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        salida = servicio.listar(session, ctx, estado="todas", limit=100)
    ids = {i["id"] for i in salida["items"]}
    assert str(sid) in ids
    assert salida["total"] >= len(salida["items"])
    for item in salida["items"]:
        assert set(item) == {
            "id", "tipo", "estado", "solicitante", "viaje_id",
            "id_comercial_flete", "resumen", "creada_en", "decidida_en",
            "tiene_modificaciones", "version",
        }


def test_listar_por_defecto_solo_pendientes(escenario) -> None:
    sid = _nueva(escenario, tipo="otra", payload={})
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _conexion(escenario["dsn_app"]) as conn:
        _fijar(conn, escenario["empresa_id"])
        conn.execute(
            "update nucleo.solicitudes set estado='rechazada', motivo_rechazo='x', "
            "decidido_en=now(), aprobado_por='test' where id=%s",
            (sid,),
        )
        conn.commit()
    with _sesion(ctx) as session:
        salida = servicio.listar(session, ctx)
    assert all(i["estado"] == "pendiente" for i in salida["items"])
    assert str(sid) not in {i["id"] for i in salida["items"]}


def test_detalle_de_otra_empresa_es_404(escenario) -> None:
    sid = _nueva(escenario, tipo="otra", payload={})
    ctx = _contexto(escenario["otra_empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session, pytest.raises(RecursoNoEncontrado):
        servicio.obtener(session, ctx, sid)


def test_detalle_incluye_payload_y_hoja_ruta(escenario) -> None:
    sid = _nueva(escenario, tipo="hoja_de_ruta", payload={"km": 10})
    with _conexion(escenario["dsn_app"]) as conn:
        _fijar(conn, escenario["empresa_id"])
        _crear_hoja_ruta(
            conn,
            empresa_id=escenario["empresa_id"],
            contacto_id=escenario["contacto_id"],
            solicitud_id=sid,
            payload={"km": 10, "faltantes": ["litros"]},
        )
        conn.commit()
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        detalle = servicio.obtener(session, ctx, sid)
    assert detalle["payload"] == {"km": 10}
    assert detalle["hoja_ruta"]["faltantes"] == ["litros"]
    assert detalle["diff"] == []


# ---------------------------------------------------------------------------
# Decisión
# ---------------------------------------------------------------------------


def test_rechazar_deja_estado_motivo_y_hoja_ruta(escenario) -> None:
    sid = _nueva(escenario, tipo="hoja_de_ruta", payload={"km": 10})
    with _conexion(escenario["dsn_app"]) as conn:
        _fijar(conn, escenario["empresa_id"])
        _crear_hoja_ruta(
            conn, empresa_id=escenario["empresa_id"],
            contacto_id=escenario["contacto_id"], solicitud_id=sid,
            payload={"km": 10},
        )
        conn.commit()
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        detalle, resultado = servicio.decidir(
            session, ctx, sid, accion="rechazar", version=1, motivo_rechazo="falta POD"
        )
        session.commit()
    assert resultado is None
    assert detalle["estado"] == "rechazada"
    assert detalle["aprobado_por"] == f"agente:{escenario['miembro_auth']}"
    assert detalle["version"] == 2
    with _conexion(escenario["dsn"]) as conn:
        estado = conn.execute(
            "select estado::text from nucleo.hoja_ruta where solicitud_id=%s", (sid,)
        ).fetchone()[0]
    assert estado == "rechazado"


def test_modificar_deja_pendiente_con_diff(escenario) -> None:
    sid = _nueva(escenario, tipo="hoja_de_ruta", payload={"km": 10, "litros": 5})
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        detalle, resultado = servicio.decidir(
            session, ctx, sid,
            accion="modificar", version=1,
            valores_modificados={"km": 12},
        )
        session.commit()
    assert resultado is None
    assert detalle["estado"] == "pendiente"
    assert detalle["valores_modificados"] == {"km": 12}
    assert detalle["diff"] == [{"campo": "km", "propuesto": 10, "modificado": 12}]
    assert detalle["version"] == 2


def test_confirmar_hoja_de_ruta_no_reescribe_el_payload(escenario) -> None:
    sid = _nueva(escenario, tipo="hoja_de_ruta", payload={"km": 10})
    with _conexion(escenario["dsn_app"]) as conn:
        _fijar(conn, escenario["empresa_id"])
        hid = _crear_hoja_ruta(
            conn, empresa_id=escenario["empresa_id"],
            contacto_id=escenario["contacto_id"], solicitud_id=sid,
            payload={"km": 10},
        )
        conn.commit()
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        detalle, resultado = servicio.decidir(
            session, ctx, sid, accion="confirmar", version=1,
            valores_modificados={"km": 12},
        )
        session.commit()
    assert detalle["estado"] == "aprobada"
    assert resultado == {"tipo": "hoja_de_ruta", "ref": str(hid), "estado": "cargado"}
    with _conexion(escenario["dsn"]) as conn:
        payload, cargados = conn.execute(
            "select payload, valores_cargados from nucleo.hoja_ruta where id=%s", (hid,)
        ).fetchone()
    assert payload == {"km": 10}, "el payload propuesto es inmutable (ADR-0003 §14.2)"
    assert cargados == {"km": 12}


def test_confirmar_tipo_sin_ejecutor_es_501(escenario) -> None:
    sid = _nueva(escenario, tipo="agendamiento", payload={})
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        with pytest.raises(TipoSinEjecutor):
            servicio.decidir(session, ctx, sid, accion="confirmar", version=1)
        session.rollback()
    with _conexion(escenario["dsn"]) as conn:
        estado = conn.execute(
            "select estado::text from nucleo.solicitudes where id=%s", (sid,)
        ).fetchone()[0]
    assert estado == "pendiente", "un 501 no puede dejar la solicitud aprobada"


def test_version_incorrecta_es_409(escenario) -> None:
    sid = _nueva(escenario, tipo="otra", payload={})
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        with pytest.raises(ConflictoConcurrencia):
            servicio.decidir(session, ctx, sid, accion="rechazar", version=99,
                             motivo_rechazo="x")
        session.rollback()


def test_ya_decidida_es_409(escenario) -> None:
    sid = _nueva(escenario, tipo="otra", payload={})
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        servicio.decidir(session, ctx, sid, accion="rechazar", version=1,
                         motivo_rechazo="primera")
        session.commit()
    with _sesion(ctx) as session:
        with pytest.raises(SolicitudYaDecidida):
            servicio.decidir(session, ctx, sid, accion="rechazar", version=2,
                             motivo_rechazo="segunda")
        session.rollback()


def test_rechazar_sin_motivo_es_422(escenario) -> None:
    sid = _nueva(escenario, tipo="otra", payload={})
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        with pytest.raises(DatosInvalidos):
            servicio.decidir(session, ctx, sid, accion="rechazar", version=1)
        session.rollback()


def test_autoaprobacion_es_403(escenario) -> None:
    """El solicitante usuario no puede aprobar su propia solicitud (§6.4)."""
    with _conexion(escenario["dsn_app"]) as conn:
        _fijar(conn, escenario["empresa_id"])
        sid = _crear_solicitud(
            conn,
            empresa_id=escenario["empresa_id"],
            tipo="otra",
            payload={},
            usuario_empresa_id=escenario["miembro_id"],
        )
        conn.commit()
    ctx = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    with _sesion(ctx) as session:
        with pytest.raises(Autoaprobacion):
            servicio.decidir(session, ctx, sid, accion="rechazar", version=1,
                             motivo_rechazo="x")
        session.rollback()


def test_otro_aprobador_si_puede(escenario) -> None:
    with _conexion(escenario["dsn_app"]) as conn:
        _fijar(conn, escenario["empresa_id"])
        sid = _crear_solicitud(
            conn,
            empresa_id=escenario["empresa_id"],
            tipo="otra",
            payload={},
            usuario_empresa_id=escenario["miembro_id"],
        )
        conn.commit()
    ctx = _contexto(escenario["empresa_id"], escenario["otro_miembro_auth"])
    with _sesion(ctx) as session:
        detalle, _ = servicio.decidir(session, ctx, sid, accion="rechazar",
                                      version=1, motivo_rechazo="no aplica")
        session.commit()
    assert detalle["estado"] == "rechazada"


# ---------------------------------------------------------------------------
# Concurrencia real: dos conexiones
# ---------------------------------------------------------------------------


def test_dos_aprobadores_solo_uno_aplica(escenario) -> None:
    """Dos conexiones simultáneas: una decide, la otra recibe 409.

    Se prueba con `FOR UPDATE` de verdad: el segundo hilo queda esperando el
    lock del primero y, al reanudar, ve el estado terminal.
    """
    sid = _nueva(escenario, tipo="hoja_de_ruta", payload={"km": 1})
    with _conexion(escenario["dsn_app"]) as conn:
        _fijar(conn, escenario["empresa_id"])
        _crear_hoja_ruta(
            conn, empresa_id=escenario["empresa_id"],
            contacto_id=escenario["contacto_id"], solicitud_id=sid,
            payload={"km": 1},
        )
        conn.commit()

    ctx_a = _contexto(escenario["empresa_id"], escenario["miembro_auth"])
    ctx_b = _contexto(escenario["empresa_id"], escenario["otro_miembro_auth"])
    bloqueado = threading.Event()
    liberar = threading.Event()
    errores: list[BaseException] = []
    resultados: list[str] = []

    def aprobador_a() -> None:
        try:
            with _sesion(ctx_a) as session:
                servicio.decidir(session, ctx_a, sid, accion="confirmar", version=1)
                bloqueado.set()          # ya tiene el lock y el update hecho
                liberar.wait(timeout=10)  # simula pensar/validar antes de commit
                session.commit()
                resultados.append("A_ok")
        except BaseException as exc:  # noqa: BLE001
            errores.append(exc)

    def aprobador_b() -> None:
        try:
            with _sesion(ctx_b) as session:
                servicio.decidir(session, ctx_b, sid, accion="confirmar", version=1)
                session.commit()
                resultados.append("B_ok")
        except BaseException as exc:  # noqa: BLE001
            errores.append(exc)

    hilo_a = threading.Thread(target=aprobador_a)
    hilo_a.start()
    if not bloqueado.wait(timeout=10):
        hilo_a.join(timeout=5)
        liberar.set()
        pytest.fail(f"el hilo A no llegó a tomar el lock; errores={errores!r}")
    hilo_b = threading.Thread(target=aprobador_b)
    hilo_b.start()
    liberar.set()
    hilo_a.join(timeout=15)
    hilo_b.join(timeout=15)

    assert resultados == ["A_ok"], resultados
    assert len(errores) == 1, errores
    assert isinstance(errores[0], (SolicitudYaDecidida, ConflictoConcurrencia))

    with _conexion(escenario["dsn"]) as conn:
        estado, version = conn.execute(
            "select estado::text, version from nucleo.solicitudes where id=%s", (sid,)
        ).fetchone()
        cargados = conn.execute(
            "select valores_cargados from nucleo.hoja_ruta where solicitud_id=%s", (sid,)
        ).fetchone()[0]
    assert estado == "aprobada"
    assert version == 2, "una sola transición, no dos efectos"
    assert cargados == {"km": 1}
