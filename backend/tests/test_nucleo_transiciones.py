"""Transiciones de estado de viaje desde la oficina y anulación (P0 — backend).

Qué cubre
---------
1. Transición válida (`confirmado → asignado`) con evento `transicion_oficina`.
2. Transición ausente en `nucleo.transiciones_viaje` → 409 con la lista de
   destinos permitidos leída de la tabla (no de un `dict` de Python).
3. Transición con `requiere_motivo` sin motivo → 422.
4. `estado_destino='facturado'` rechazado aunque la matriz lo permita (ese paso
   lo controla facturación con POD + OC).
5. Conflicto de versión (la fila cambió entre el SELECT ... FOR UPDATE y el
   UPDATE) → 409, sin commit.
6. Aislamiento: viaje de otra empresa → 404 (no 200 ni fuga).
7. Anulación: estado `anulado`, `motivo_anulacion`, reservas `activa=false` con
   motivo/actor y evento `anulado`.
8. Anular dos veces → 409 (la matriz no tiene salida desde `anulado`).
9. Anular un viaje `cerrado` → 409 (no existe `cerrado → anulado`).

Cómo se ejecuta
---------------
Todo corre dentro de una transacción que SIEMPRE se revierte (patrón de
`test_nucleo_integracion.py:55-140`): el núcleo es inmutable por triggers
(`trg_reservas_no_delete`, auditoría append-only), así que los `commit()` del
servicio liberan solo un SAVEPOINT y no queda basura en `tei_test`.

Los casos HTTP usan el `TestClient` real y sustituyen dos dependencias:
`get_contexto_empresa` (para no necesitar un JWT de Supabase) y
`get_session_nucleo` (para que el request use la conexión de la prueba, la
misma que se revierte). El resto del camino —router, schemas, permisos por rol,
manejador de errores de dominio y servicio— es el de producción. El rol de
PostgreSQL de esta conexión es el de `NUCLEO_TEST_DATABASE_URL` (sin BYPASSRLS
en `make test`); el aislamiento por RLS con `tei_app` se verifica en
`test_f1_ola5_dos_engines.py`, y aquí se verifica el filtro de servidor
(`empresa_id` resuelto en el backend, nunca desde el body).
"""

from __future__ import annotations

import contextlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine, select

from app.core.database import get_session_nucleo
from app.main import app
from app.nucleo.deps import ContextoEmpresa, RolEmpresa, get_contexto_empresa
from app.nucleo.errores import ConflictoConcurrencia
from app.nucleo.models import (
    Chofer,
    Cliente,
    Documento,
    Empresa,
    EstadoViaje,
    ModalidadTarifa,
    Rampla,
    ReservaRecurso,
    Tarifa,
    TipoDocumento,
    TipoRampla,
    TipoRecurso,
    Tracto,
    TransicionViaje,
    Viaje,
    ViajeEvento,
)
from app.nucleo.schemas import SolicitudTransicionViaje
from app.nucleo.servicio_transiciones import ServicioTransiciones
from contexto_helpers import contexto_de_prueba
from rut_helpers import rut_empresa

pytestmark = pytest.mark.integracion

API = "/api/v1"


# ---------------------------------------------------------------------------
# Infraestructura de prueba
# ---------------------------------------------------------------------------
def _url() -> str:
    # La URL validada vive en conftest (`_base_url_test`): RA-13 impide tocar
    # la base de la aplicación.
    from conftest import _base_url_test

    return _base_url_test()


@contextlib.contextmanager
def sesion_aislada():
    """Sesión sobre una transacción que siempre se revierte."""
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn_probe:
            try:
                conn_probe.execute(text("select 1 from nucleo.viajes limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover - entorno
                pytest.skip(f"Falta aplicar la migración 0004: {exc}")

        conn = engine.connect()
        transaccion = conn.begin()
        try:
            with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
                yield session
        finally:
            transaccion.rollback()
            conn.close()
    finally:
        engine.dispose()


@contextlib.contextmanager
def http_con_sesion(session: Session, contexto: ContextoEmpresa):
    """`TestClient` sobre la sesión de la prueba (misma transacción revertida)."""
    app.dependency_overrides[get_session_nucleo] = lambda: session
    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(
        contexto
    )
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def _empresa(session: Session, etiqueta: str) -> Empresa:
    empresa = Empresa(
        codigo=f"TRANS-{etiqueta}",
        razon_social=f"Empresa transiciones {etiqueta}",
        rut=rut_empresa(),
        buffer_operacional_min=60,
    )
    session.add(empresa)
    session.commit()
    session.refresh(empresa)
    return empresa


def _cliente(session: Session, empresa: Empresa, etiqueta: str) -> Cliente:
    cliente = Cliente(
        empresa_id=empresa.id,
        razon_social=f"Cliente {etiqueta}",
        rut=f"CLI-{etiqueta}",
    )
    session.add(cliente)
    session.commit()
    session.refresh(cliente)
    return cliente


def _recursos_documentados(
    session: Session, empresa: Empresa, cliente: Cliente, etiqueta: str
) -> tuple[Tracto, Rampla, Chofer, Tarifa]:
    """Flota con documentos vigentes y tarifa: requisito de `estado='asignado'`.

    `fn_viaje_validar` (0004:1140-1325) exige tarifa vigente y documentos de
    tracto/rampla/chofer vigentes hasta el fin del viaje + margen.
    """
    tracto = Tracto(
        empresa_id=empresa.id,
        patente=f"T{etiqueta[:5].upper()}",
        peso_bruto_kg=Decimal("39000"),
        tara_kg=Decimal("9000"),
        capacidad_carga_kg=Decimal("30000"),
        licencias_permitidas=["A5"],
    )
    rampla = Rampla(
        empresa_id=empresa.id,
        patente=f"R{etiqueta[:5].upper()}",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal("30000"),
        volumen_m3=Decimal("80"),
    )
    chofer = Chofer(
        empresa_id=empresa.id,
        rut=f"CHO-{etiqueta}",
        nombre=f"Chofer {etiqueta}",
        numero_licencia=f"LIC-{etiqueta}",
        licencia_clase="A5",
    )
    session.add_all([tracto, rampla, chofer])
    session.commit()
    for recurso in (tracto, rampla, chofer):
        session.refresh(recurso)

    vence = date.today() + timedelta(days=400)
    session.add_all(
        [
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.revision_tecnica, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.permiso_circulacion, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.seguro_obligatorio, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.soap, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.revision_tecnica, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.permiso_circulacion, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.seguro_carga, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.chofer, chofer_id=chofer.id, tipo=TipoDocumento.licencia_conducir, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.chofer, chofer_id=chofer.id, tipo=TipoDocumento.examen_medico, vence_en=vence),
        ]
    )
    tarifa = Tarifa(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        codigo=f"TAR-{etiqueta}",
        nombre="Santiago - Concepción",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date.today(),
        vigencia_hasta=date.today() + timedelta(days=400),
        precio_unitario=Decimal("100000"),
    )
    session.add(tarifa)
    session.commit()
    session.refresh(tarifa)
    return tracto, rampla, chofer, tarifa


def _viaje(
    session: Session,
    empresa: Empresa,
    cliente: Cliente,
    estado: EstadoViaje,
    *,
    recursos: tuple[Tracto, Rampla, Chofer, Tarifa] | None = None,
    dias_desde_hoy: int = 30,
) -> Viaje:
    inicio = (
        datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        + timedelta(days=dias_desde_hoy)
    )
    viaje = Viaje(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        estado=estado,
        inicio_planificado=inicio,
        fin_planificado=inicio + timedelta(hours=4),
        buffer_minutos=60,
        peso_bruto_kg=Decimal("25000"),
        origen_nombre="Santiago",
        destino_nombre="Concepción",
        valor_flete_neto=Decimal("100000"),
        tarifa_id=recursos[3].id if recursos else None,
        tracto_id=recursos[0].id if recursos else None,
        rampla_id=recursos[1].id if recursos else None,
        chofer_id=recursos[2].id if recursos else None,
    )
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return viaje


def _contexto(empresa: Empresa, rol: RolEmpresa = RolEmpresa.admin) -> ContextoEmpresa:
    return ContextoEmpresa(auth_id=str(uuid4()), empresa=empresa, rol=rol)


def _eventos(session: Session, viaje_id: UUID, tipo: str) -> list[ViajeEvento]:
    return list(
        session.exec(
            select(ViajeEvento).where(
                ViajeEvento.viaje_id == viaje_id,
                ViajeEvento.tipo == tipo,
            )
        ).all()
    )


def _destinos_en_matriz(session: Session, origen: EstadoViaje) -> list[str]:
    return sorted(
        fila.estado_destino.value
        for fila in session.exec(
            select(TransicionViaje).where(TransicionViaje.estado_origen == origen)
        ).all()
    )


# ---------------------------------------------------------------------------
# 1. Transición válida + evento
# ---------------------------------------------------------------------------
def test_transicion_valida_confirmado_a_asignado(client):
    with sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = _empresa(session, etiqueta)
        cliente = _cliente(session, empresa, etiqueta)
        recursos = _recursos_documentados(session, empresa, cliente, etiqueta)
        viaje = _viaje(
            session, empresa, cliente, EstadoViaje.confirmado, recursos=recursos
        )
        version_inicial = viaje.version

        with http_con_sesion(session, _contexto(empresa)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/transicion",
                json={"estado_destino": "asignado"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 200, resp.text
        cuerpo = resp.json()
        assert cuerpo["estado"] == "asignado"
        assert cuerpo["estado_anterior"] == "confirmado"
        assert cuerpo["numero_viaje"] == viaje.numero_viaje
        assert cuerpo["version"] == version_inicial + 1

        session.expire_all()
        actualizado = session.get(Viaje, viaje.id)
        assert actualizado.estado == EstadoViaje.asignado

        eventos = _eventos(session, viaje.id, "transicion_oficina")
        assert len(eventos) == 1, "debe quedar exactamente un evento de la transición"
        payload = eventos[0].payload
        assert payload["estado_origen"] == "confirmado"
        assert payload["estado_destino"] == "asignado"
        assert payload["origen"] == "oficina"


# ---------------------------------------------------------------------------
# 2. Transición ausente en la matriz (la tabla es la fuente de verdad)
# ---------------------------------------------------------------------------
def test_transicion_no_permitida_por_matriz(client):
    with sesion_aislada() as session:
        empresa = _empresa(session, uuid4().hex[:6])
        cliente = _cliente(session, empresa, uuid4().hex[:6])
        viaje = _viaje(session, empresa, cliente, EstadoViaje.confirmado)
        permitidos_db = _destinos_en_matriz(session, EstadoViaje.confirmado)

        with http_con_sesion(session, _contexto(empresa)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/transicion",
                json={"estado_destino": "en_ruta"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 409, resp.text
        cuerpo = resp.json()
        assert cuerpo["codigo"] == "ESTADO_VIAJE_INVALIDO"
        # Los destinos permitidos salen de `nucleo.transiciones_viaje`.
        assert cuerpo["contexto"]["destinos_permitidos"] == permitidos_db
        assert "en_ruta" not in permitidos_db

        session.expire_all()
        assert session.get(Viaje, viaje.id).estado == EstadoViaje.confirmado


# ---------------------------------------------------------------------------
# 3. `requiere_motivo` sin motivo → 422
# ---------------------------------------------------------------------------
def test_transicion_que_requiere_motivo_sin_motivo(client):
    """La única fila con `requiere_motivo` es `* → anulado` (0004:779-808)."""
    with sesion_aislada() as session:
        empresa = _empresa(session, uuid4().hex[:6])
        cliente = _cliente(session, empresa, uuid4().hex[:6])
        viaje = _viaje(session, empresa, cliente, EstadoViaje.confirmado)

        with http_con_sesion(session, _contexto(empresa)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/transicion",
                json={"estado_destino": "anulado"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 422, resp.text
        assert resp.json()["codigo"] == "DATOS_INVALIDOS"

        session.expire_all()
        assert session.get(Viaje, viaje.id).estado == EstadoViaje.confirmado


# ---------------------------------------------------------------------------
# 4. `facturado` nunca por la transición de oficina
# ---------------------------------------------------------------------------
def test_transicion_a_facturado_rechazada(client):
    with sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = _empresa(session, etiqueta)
        cliente = _cliente(session, empresa, etiqueta)
        recursos = _recursos_documentados(session, empresa, cliente, etiqueta)
        # `cerrado` exige recursos (fn_viaje_validar) y los tenía el viaje real.
        viaje = _viaje(session, empresa, cliente, EstadoViaje.cerrado, recursos=recursos)
        # La matriz SÍ permite cerrado → facturado; el endpoint debe rechazarlo.
        assert "facturado" in _destinos_en_matriz(session, EstadoViaje.cerrado)

        with http_con_sesion(session, _contexto(empresa)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/transicion",
                json={"estado_destino": "facturado"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 409, resp.text
        cuerpo = resp.json()
        assert cuerpo["codigo"] == "ESTADO_VIAJE_INVALIDO"
        assert cuerpo["contexto"]["via"] == "facturacion"
        assert "facturación" in cuerpo["mensaje"] or "facturacion" in cuerpo["mensaje"]

        session.expire_all()
        assert session.get(Viaje, viaje.id).estado == EstadoViaje.cerrado


# ---------------------------------------------------------------------------
# 5. Conflicto de versión → 409 sin commit
# ---------------------------------------------------------------------------
class _ResultadoFalso:
    def __init__(self, *, filas: list | None = None, rowcount: int = 0) -> None:
        self._filas = filas or []
        self.rowcount = rowcount

    def first(self):
        return self._filas[0] if self._filas else None

    def all(self):
        return list(self._filas)


class _SesionConflicto:
    """Simula la carrera: la fila cambió entre el `FOR UPDATE` y el `UPDATE`.

    En producción el `SELECT ... FOR UPDATE` protege el invariante; el `WHERE
    version = :version` es la segunda barrera (por ejemplo, si un trigger o una
    migración toca la fila). Aquí se fuerza `rowcount = 0` para verificar que el
    servicio no confunda "no actualicé nada" con éxito.
    """

    def __init__(self, viaje: Viaje, transicion: TransicionViaje) -> None:
        self.viaje = viaje
        self.transicion = transicion
        self.commits = 0
        self.rollbacks = 0
        self.eventos: list[object] = []

    def exec(self, sentencia):  # noqa: A003 - imita la API de Session
        texto = str(sentencia)
        if "transiciones_viaje" in texto:
            return _ResultadoFalso(filas=[self.transicion])
        return _ResultadoFalso(filas=[self.viaje])

    def execute(self, sentencia, *args, **kwargs):
        return _ResultadoFalso(rowcount=0)

    def add(self, obj) -> None:
        self.eventos.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, obj) -> None:  # pragma: no cover - no debe alcanzarse
        raise AssertionError("no se refresca un viaje que no se actualizó")


def test_conflicto_de_version_no_reporta_exito():
    empresa = Empresa(codigo="TRANS-CONF", razon_social="Empresa", rut=rut_empresa())
    inicio = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
    viaje = Viaje(
        empresa_id=empresa.id,
        cliente_id=uuid4(),
        numero_viaje="VJ-TEST-CONF",
        estado=EstadoViaje.confirmado,
        inicio_planificado=inicio,
        fin_planificado=inicio + timedelta(hours=4),
        tracto_id=uuid4(),
        rampla_id=uuid4(),
        chofer_id=uuid4(),
        version=1,
    )
    transicion = TransicionViaje(
        estado_origen=EstadoViaje.confirmado,
        estado_destino=EstadoViaje.asignado,
        requiere_motivo=False,
    )
    sesion = _SesionConflicto(viaje, transicion)
    contexto = ContextoEmpresa(
        auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.admin
    )

    with pytest.raises(ConflictoConcurrencia) as excinfo:
        ServicioTransiciones(sesion, contexto).transicionar(  # type: ignore[arg-type]
            viaje.id, SolicitudTransicionViaje(estado_destino=EstadoViaje.asignado)
        )

    assert excinfo.value.status_code == 409
    assert sesion.commits == 0, "no se commitea un UPDATE que no afectó filas"
    assert sesion.rollbacks == 1
    assert sesion.eventos == [], "no se registra evento de una transición fallida"


# ---------------------------------------------------------------------------
# 6. Aislamiento: viaje de otra empresa → 404
# ---------------------------------------------------------------------------
def test_viaje_de_otra_empresa_no_existe_para_el_contexto(client):
    with sesion_aislada() as session:
        empresa_a = _empresa(session, uuid4().hex[:6])
        empresa_b = _empresa(session, uuid4().hex[:6])
        cliente_b = _cliente(session, empresa_b, uuid4().hex[:6])
        viaje_b = _viaje(session, empresa_b, cliente_b, EstadoViaje.confirmado)

        with http_con_sesion(session, _contexto(empresa_a)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje_b.id}/transicion",
                json={"estado_destino": "asignado"},
                headers={"X-Empresa-ID": str(empresa_a.id)},
            )

        assert resp.status_code == 404, resp.text
        assert resp.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        # El 404 repite el id solicitado (lo envió el cliente) pero no debe
        # revelar ningún dato del viaje ajeno.
        assert viaje_b.numero_viaje not in resp.text

        session.expire_all()
        assert session.get(Viaje, viaje_b.id).estado == EstadoViaje.confirmado


# ---------------------------------------------------------------------------
# 7. Anulación: estado, motivo, reservas liberadas y evento
# ---------------------------------------------------------------------------
def test_anulacion_libera_reservas_y_audita(client):
    with sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = _empresa(session, etiqueta)
        cliente = _cliente(session, empresa, etiqueta)
        recursos = _recursos_documentados(session, empresa, cliente, etiqueta)
        viaje = _viaje(
            session, empresa, cliente, EstadoViaje.asignado, recursos=recursos
        )

        reservas_antes = list(
            session.exec(
                select(ReservaRecurso).where(
                    ReservaRecurso.viaje_id == viaje.id,
                    ReservaRecurso.activa == True,  # noqa: E712
                )
            ).all()
        )
        assert len(reservas_antes) == 3, (
            "el trigger fn_viaje_reservas debe haber creado tracto/rampla/chofer"
        )

        motivo = "Cliente canceló el embarque"
        with http_con_sesion(session, _contexto(empresa)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/anular",
                json={"motivo": motivo},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 200, resp.text
        cuerpo = resp.json()
        assert cuerpo["estado"] == "anulado"
        assert cuerpo["estado_anterior"] == "asignado"
        assert cuerpo["reservas_liberadas"] == 3

        session.expire_all()
        anulado = session.get(Viaje, viaje.id)
        assert anulado.estado == EstadoViaje.anulado
        assert anulado.motivo_anulacion == motivo
        assert anulado.anulado_en is not None

        reservas = list(
            session.exec(
                select(ReservaRecurso).where(ReservaRecurso.viaje_id == viaje.id)
            ).all()
        )
        assert reservas, "las reservas no se borran: se desactivan"
        for reserva in reservas:
            assert reserva.activa is False
            assert reserva.cancelado_motivo == motivo
            assert reserva.cancelado_por is not None
            assert reserva.cancelado_en is not None

        eventos = _eventos(session, viaje.id, "anulado")
        assert len(eventos) == 1
        assert eventos[0].payload["motivo"] == motivo
        assert eventos[0].payload["estado_destino"] == "anulado"


# ---------------------------------------------------------------------------
# 8. Anular dos veces → 409 (sin tabla de idempotencia: manda la matriz)
# ---------------------------------------------------------------------------
def test_anular_dos_veces_es_conflicto(client):
    with sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = _empresa(session, etiqueta)
        cliente = _cliente(session, empresa, etiqueta)
        viaje = _viaje(session, empresa, cliente, EstadoViaje.confirmado)

        with http_con_sesion(session, _contexto(empresa)):
            primera = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/anular",
                json={"motivo": "Anulación inicial"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )
            segunda = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/anular",
                json={"motivo": "Anulación repetida"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert primera.status_code == 200, primera.text
        assert segunda.status_code == 409, segunda.text
        assert segunda.json()["codigo"] == "ESTADO_VIAJE_INVALIDO"

        session.expire_all()
        assert session.get(Viaje, viaje.id).motivo_anulacion == "Anulación inicial"
        assert len(_eventos(session, viaje.id, "anulado")) == 1


# ---------------------------------------------------------------------------
# 9. Anular un viaje cerrado → 409
# ---------------------------------------------------------------------------
def test_anular_viaje_cerrado_es_conflicto(client):
    with sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = _empresa(session, etiqueta)
        cliente = _cliente(session, empresa, etiqueta)
        recursos = _recursos_documentados(session, empresa, cliente, etiqueta)
        viaje = _viaje(session, empresa, cliente, EstadoViaje.cerrado, recursos=recursos)

        with http_con_sesion(session, _contexto(empresa)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/anular",
                json={"motivo": "Intento sobre viaje cerrado"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 409, resp.text
        cuerpo = resp.json()
        assert cuerpo["codigo"] == "ESTADO_VIAJE_INVALIDO"
        assert cuerpo["contexto"]["estado_origen"] == "cerrado"

        session.expire_all()
        assert session.get(Viaje, viaje.id).estado == EstadoViaje.cerrado


# ---------------------------------------------------------------------------
# Permisos: anular no es una acción de despacho
# ---------------------------------------------------------------------------
def test_anular_exige_permiso_comercial_aprobar(client):
    with sesion_aislada() as session:
        etiqueta = uuid4().hex[:6]
        empresa = _empresa(session, etiqueta)
        cliente = _cliente(session, empresa, etiqueta)
        viaje = _viaje(session, empresa, cliente, EstadoViaje.confirmado)

        with http_con_sesion(session, _contexto(empresa, RolEmpresa.despacho)):
            resp = client.post(
                f"{API}/nucleo/viajes/{viaje.id}/anular",
                json={"motivo": "Despacho intenta anular"},
                headers={"X-Empresa-ID": str(empresa.id)},
            )

        assert resp.status_code == 403, resp.text
        assert resp.json()["codigo"] == "ACCESO_DENEGADO"

        session.expire_all()
        assert session.get(Viaje, viaje.id).estado == EstadoViaje.confirmado
