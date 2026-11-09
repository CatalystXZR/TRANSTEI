"""Adversariales de transiciones y anulación de viaje (Ola 4, 2026-11-09).

Objetivo: atacar las garantías de `app/nucleo/servicio_transiciones.py` que el
camino feliz de `test_nucleo_transiciones.py` no cubre:

- `facturado/cobrado` nunca se alcanzan por la transición de oficina;
- `anulado` no se alcanza por `/transicion` ni siquiera enviando motivo: exige
  el endpoint `/anular` (permiso `comercial:aprobar`);
- el motivo de anulación exige 5 caracteres **útiles** (no solo espacios);
- un viaje de otra empresa es 404 y no libera reservas;
- un rol sin `comercial:aprobar` no libera reservas;
- concurrencia real: dos conexiones esperan el mismo `SELECT ... FOR UPDATE`.
  En transición y en doble anulación gana exactamente una; la otra recibe 409.

Los casos HTTP usan el `TestClient` real con la sesión de la prueba (todo se
revierte). Los de concurrencia usan datos confirmados y dos engines distintos:
sin dos conexiones simultáneas no hay prueba de concurrencia.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import ola4_helpers as h
import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app.nucleo.errores import EstadoViajeInvalido
from app.nucleo.models import EstadoViaje, ReservaRecurso, Viaje
from app.nucleo.schemas import (
    SolicitudAnulacionViaje,
    SolicitudTransicionViaje,
)
from app.nucleo.servicio_transiciones import ServicioTransiciones

pytestmark = pytest.mark.integracion

API = "/api/v1"


# ---------------------------------------------------------------------------
# A. Transición de oficina: estados que solo controla facturación
# ---------------------------------------------------------------------------
def test_transicion_a_cobrado_rechazada(client):
    """`cerrado → cobrado` no se alcanza por la mesa de despacho."""
    with h.sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = h.empresa(session, etiqueta)
        cli = h.cliente(session, empresa, etiqueta)
        recursos = h.recursos_documentados(session, empresa, cli, etiqueta)
        viaje = h.viaje(
            session, empresa, cli, EstadoViaje.cerrado, recursos=recursos
        )
        # La matriz no tiene `cerrado → cobrado`; además el servicio filtra
        # `cobrado` antes de consultarla. El contexto debe decir que la vía es
        # facturación, no "transición no permitida".
        with h.http_con_sesion(session, h.contexto(empresa)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/transicion",
                json={"estado_destino": "cobrado"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 409, resp.text
        cuerpo = resp.json()
        assert cuerpo["codigo"] == "ESTADO_VIAJE_INVALIDO"
        assert cuerpo["contexto"]["via"] == "facturacion", cuerpo
        session.expire_all()
        assert session.get(Viaje, viaje.id).estado == EstadoViaje.cerrado


def test_transicion_a_anulado_con_motivo_es_409_y_no_anula(client):
    """Enviar motivo no convierte `/transicion` en una vía de anulación.

    La matriz `nucleo.transiciones_viaje` sí tiene `confirmado → anulado` con
    `requiere_motivo=true`. Sin el rechazo explícito del servicio, despacho
    (que tiene `operacion:escribir`) podría anular saltándose
    `comercial:aprobar` y la liberación trazable de reservas.
    """
    with h.sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = h.empresa(session, etiqueta)
        cli = h.cliente(session, empresa, etiqueta)
        viaje = h.viaje(session, empresa, cli, EstadoViaje.confirmado)

        with h.http_con_sesion(session, h.contexto(empresa)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/transicion",
                json={
                    "estado_destino": "anulado",
                    "motivo": "Motivo válido de cinco o más caracteres",
                },
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 409, resp.text
        cuerpo = resp.json()
        assert cuerpo["codigo"] == "ESTADO_VIAJE_INVALIDO"
        assert cuerpo["contexto"]["via"] == "anulacion", cuerpo

        session.expire_all()
        assert session.get(Viaje, viaje.id).estado == EstadoViaje.confirmado
        assert h.eventos(session, viaje.id, "anulado") == []


# ---------------------------------------------------------------------------
# B. Motivo: longitud y caracteres útiles
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "motivo",
    ["abc", "abcd", "     ", "    x"],
    ids=["3-char", "4-char", "solo-espacios", "1-char-util"],
)
def test_anular_motivo_corto_es_422(client, motivo):
    """`min_length=5` + strip: un motivo inútil no anula ni libera reservas."""
    with h.sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = h.empresa(session, etiqueta)
        cli = h.cliente(session, empresa, etiqueta)
        recursos = h.recursos_documentados(session, empresa, cli, etiqueta)
        viaje = h.viaje(
            session, empresa, cli, EstadoViaje.asignado, recursos=recursos
        )
        reservas_activas = session.exec(
            select(ReservaRecurso).where(
                ReservaRecurso.viaje_id == viaje.id,
                ReservaRecurso.activa == True,
            )
        ).all()
        assert len(reservas_activas) == 3

        with h.http_con_sesion(session, h.contexto(empresa)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/anular",
                json={"motivo": motivo},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 422, resp.text
        session.expire_all()
        assert session.get(Viaje, viaje.id).estado == EstadoViaje.asignado
        for reserva in session.exec(
            select(ReservaRecurso).where(ReservaRecurso.viaje_id == viaje.id)
        ).all():
            assert reserva.activa is True, "un 422 no debe liberar reservas"


# ---------------------------------------------------------------------------
# C. Aislamiento y permisos: el efecto no ocurre si el control falla
# ---------------------------------------------------------------------------
def test_anular_viaje_de_otra_empresa_es_404_y_no_libera(client):
    with h.sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa_a = h.empresa(session, f"A{etiqueta}")
        empresa_b = h.empresa(session, f"B{etiqueta}")
        cli_b = h.cliente(session, empresa_b, etiqueta)
        recursos_b = h.recursos_documentados(session, empresa_b, cli_b, etiqueta)
        viaje_b = h.viaje(
            session, empresa_b, cli_b, EstadoViaje.asignado, recursos=recursos_b
        )

        with h.http_con_sesion(session, h.contexto(empresa_a)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje_b.id}/anular",
                json={"motivo": "Intento cruzado de anulación"},
                headers={"X-Empresa-ID": str(empresa_a.id)},
            )

        assert resp.status_code == 404, resp.text
        assert resp.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert viaje_b.numero_viaje not in resp.text

        session.expire_all()
        assert session.get(Viaje, viaje_b.id).estado == EstadoViaje.asignado
        for reserva in session.exec(
            select(ReservaRecurso).where(ReservaRecurso.viaje_id == viaje_b.id)
        ).all():
            assert reserva.activa is True


def test_anular_por_despacho_es_403_y_no_libera_reservas(client):
    with h.sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = h.empresa(session, etiqueta)
        cli = h.cliente(session, empresa, etiqueta)
        recursos = h.recursos_documentados(session, empresa, cli, etiqueta)
        viaje = h.viaje(
            session, empresa, cli, EstadoViaje.asignado, recursos=recursos
        )

        from app.nucleo.deps import RolEmpresa

        with h.http_con_sesion(
            session, h.contexto(empresa, RolEmpresa.despacho)
        ):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/anular",
                json={"motivo": "Despacho intenta anular"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 403, resp.text
        assert resp.json()["codigo"] == "ACCESO_DENEGADO"
        session.expire_all()
        assert session.get(Viaje, viaje.id).estado == EstadoViaje.asignado
        for reserva in session.exec(
            select(ReservaRecurso).where(ReservaRecurso.viaje_id == viaje.id)
        ).all():
            assert reserva.activa is True


# ---------------------------------------------------------------------------
# D. Concurrencia real con dos conexiones
# ---------------------------------------------------------------------------
_APP_NAME = "ola4-transiciones-concurrente"


def _esperar_dos_bloqueados(timeout: float = 10.0) -> None:
    """Espera a que DOS sesiones de la prueba estén esperando un lock."""
    limite = time.monotonic() + timeout
    with psycopg.connect(h.dsn_test(), connect_timeout=5) as observer:
        observer.autocommit = True
        while time.monotonic() < limite:
            bloqueados = observer.execute(
                "select count(*) from pg_stat_activity"
                " where application_name = %s"
                "   and wait_event_type = 'Lock'"
                "   and state = 'active'",
                (_APP_NAME,),
            ).fetchone()[0]
            if bloqueados >= 2:
                return
            time.sleep(0.05)
    raise AssertionError(
        "las dos conexiones no quedaron esperando el lock del viaje; "
        "la prueba no demuestra concurrencia"
    )


def _sesion_concurrente():
    engine = create_engine(h.url_test(), future=True)
    session = Session(engine)
    session.execute(
        text("select set_config('application_name', :n, false)"),
        {"n": _APP_NAME},
    )
    return engine, session


def _ejecutar_en_hilo(fn):
    resultados: list[object] = []
    errores: list[BaseException] = []
    cerrojo = threading.Lock()

    def correr() -> None:
        try:
            valor = fn()
            with cerrojo:
                resultados.append(valor)
        except BaseException as exc:  # noqa: BLE001 - se reporta tal cual
            with cerrojo:
                errores.append(exc)

    return correr, resultados, errores


def test_transicion_concurrente_solo_una_gana():
    """Dos conexiones esperan el FOR UPDATE; una transiciona y la otra 409."""
    from ola4_helpers import sesion_confirmada

    with sesion_confirmada() as setup:
        etiqueta = uuid4().hex[:6]
        empresa = h.empresa(setup, etiqueta)
        cli = h.cliente(setup, empresa, etiqueta)
        recursos = h.recursos_documentados(setup, empresa, cli, etiqueta)
        viaje = h.viaje(
            setup, empresa, cli, EstadoViaje.confirmado, recursos=recursos
        )
        empresa_id, viaje_id = empresa.id, viaje.id

    # El holder toma el lock antes de que arranquen los dos hilos: así ambos
    # quedan simultáneamente esperando el mismo renglón (no es secuencial).
    holder = psycopg.connect(h.dsn_test(), connect_timeout=5)
    holder.execute(
        "select id from nucleo.viajes where id = %s for update", (viaje_id,)
    )

    ctx = h.contexto(
        SimpleNamespace(id=empresa_id, razon_social="Ola4")  # type: ignore[arg-type]
    )

    def transicionar():
        engine, session = _sesion_concurrente()
        try:
            salida = ServicioTransiciones(session, ctx).transicionar(
                viaje_id,
                SolicitudTransicionViaje(estado_destino=EstadoViaje.asignado),
            )
            return ("ok", salida.estado.value)
        finally:
            session.close()
            engine.dispose()

    correr, resultados, errores = _ejecutar_en_hilo(transicionar)
    hilo_a = threading.Thread(target=correr)
    hilo_b = threading.Thread(target=correr)
    hilo_a.start()
    hilo_b.start()
    try:
        _esperar_dos_bloqueados()
    finally:
        holder.rollback()
        holder.close()
    hilo_a.join(timeout=20)
    hilo_b.join(timeout=20)

    assert not hilo_a.is_alive() and not hilo_b.is_alive()
    assert resultados == [("ok", "asignado")], resultados
    assert len(errores) == 1, errores
    assert isinstance(errores[0], EstadoViajeInvalido), errores

    with Session(create_engine(h.url_test(), future=True)) as session:
        estado = session.get(Viaje, viaje_id).estado
        eventos = h.eventos(session, viaje_id, "transicion_oficina")
    assert estado == EstadoViaje.asignado
    assert len(eventos) == 1, "una sola transición aplicada"


def test_doble_anulacion_concurrente_una_gana_y_libera_una_vez():
    """Dos conexiones anulan a la vez: una gana, la otra 409; reservas una vez."""
    from ola4_helpers import sesion_confirmada

    motivo = "Anulación concurrente Ola 4"
    with sesion_confirmada() as setup:
        etiqueta = uuid4().hex[:6]
        empresa = h.empresa(setup, etiqueta)
        cli = h.cliente(setup, empresa, etiqueta)
        recursos = h.recursos_documentados(setup, empresa, cli, etiqueta)
        viaje = h.viaje(
            setup, empresa, cli, EstadoViaje.asignado, recursos=recursos
        )
        empresa_id, viaje_id = empresa.id, viaje.id
        reservas = setup.exec(
            select(ReservaRecurso).where(ReservaRecurso.viaje_id == viaje_id)
        ).all()
        assert len(reservas) == 3

    holder = psycopg.connect(h.dsn_test(), connect_timeout=5)
    holder.execute(
        "select id from nucleo.viajes where id = %s for update", (viaje_id,)
    )

    ctx = h.contexto(
        SimpleNamespace(id=empresa_id, razon_social="Ola4")  # type: ignore[arg-type]
    )

    def anular():
        engine, session = _sesion_concurrente()
        try:
            salida = ServicioTransiciones(session, ctx).anular(
                viaje_id, SolicitudAnulacionViaje(motivo=motivo)
            )
            return ("ok", salida.estado.value, salida.reservas_liberadas)
        finally:
            session.close()
            engine.dispose()

    correr, resultados, errores = _ejecutar_en_hilo(anular)
    hilo_a = threading.Thread(target=correr)
    hilo_b = threading.Thread(target=correr)
    hilo_a.start()
    hilo_b.start()
    try:
        _esperar_dos_bloqueados()
    finally:
        holder.rollback()
        holder.close()
    hilo_a.join(timeout=20)
    hilo_b.join(timeout=20)

    assert not hilo_a.is_alive() and not hilo_b.is_alive()
    assert resultados == [("ok", "anulado", 3)], resultados
    assert len(errores) == 1, errores
    assert isinstance(errores[0], EstadoViajeInvalido), errores

    with Session(create_engine(h.url_test(), future=True)) as session:
        anulado = session.get(Viaje, viaje_id)
        reservas = session.exec(
            select(ReservaRecurso).where(ReservaRecurso.viaje_id == viaje_id)
        ).all()
        eventos = h.eventos(session, viaje_id, "anulado")
    assert anulado.estado == EstadoViaje.anulado
    assert anulado.motivo_anulacion == motivo
    assert len(eventos) == 1, "una sola anulación aplicada"
    assert len(reservas) == 3
    for reserva in reservas:
        assert reserva.activa is False
        assert reserva.cancelado_motivo == motivo
