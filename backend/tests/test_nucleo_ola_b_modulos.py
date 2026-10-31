"""Ola B del retiro legacy — pruebas de integración PostgreSQL + HTTP.

Cubre los cuatro módulos portados a `nucleo` (0024–0026):

- mantenimiento: pauta, registro, semáforo CN-08 y validaciones (costo, km,
  tracto xor rampla);
- nómina: comisión R-01/R-05, CN-03, CN-04 (HALF_UP), emisión idempotente,
  imputación de anticipos, anulación con motivo y concurrencia de emisión;
- IVA: solo débito, sin crédito ni a pagar (P-09);
- configuración: vigencia/historial, iva 0–100, PUT idempotente;
- export CSV: permisos por rol y protección de inyección de fórmulas.

Las pruebas que necesitan base se omiten si `NUCLEO_TEST_DATABASE_URL` no está
definida (misma regla que el resto de la suite, RA-13). Las que ejercen los
servicios corren con el rol real `tei_app` (RLS vigente) y las fixtures se
siembran con el rol privilegiado, igual que el seed/cutover. Las HTTP sustituyen
`get_contexto_empresa` por un contexto construido, pero **no** desactivan
`requiere_permiso`: el 403 se mide sobre la matriz real de roles.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.config import settings
from app.core.database import registrar_contexto_transaccion
from app.main import app
from app.nucleo.deps import ContextoEmpresa, RolEmpresa, get_contexto_empresa
from app.nucleo.errores import (
    DatosInvalidos,
    RegistroDuplicado,
    ReglaNegocioViolada,
)
from app.nucleo.models import (
    Chofer,
    Cliente,
    Empresa,
    EstadoViaje,
    FacturaNucleo,
    FacturaViaje,
    Rampla,
    TipoRampla,
    Tracto,
    Viaje,
)
from app.nucleo.schemas import (
    AjusteCreate,
    AnticipoCreate,
    LiquidacionCreate,
    MantenimientoCreate,
    PautaMantenimientoCreate,
)
from app.nucleo.servicio_configuracion import ServicioConfiguracion
from app.nucleo.servicio_export import _celda
from app.nucleo.servicio_iva import ServicioIva
from app.nucleo.servicio_mantenimiento import ServicioMantenimiento
from app.nucleo.servicio_nomina import ServicioNomina, rango_mes
from contexto_helpers import contexto_de_prueba
from rut_helpers import rut_empresa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, create_engine

API = "/api/v1/nucleo"
MES = "2026-05"


def _url_admin() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite la integración de Ola B")
    return url


def _url_app() -> str:
    """DSN del rol de aplicación (`tei_app`), con fallback al de test."""
    return (
        os.environ.get("NUCLEO_DATABASE_URL")
        or settings.NUCLEO_DATABASE_URL
        or _url_admin()
    )


# ---------------------------------------------------------------------------
# Unidades puras (también corren bajo `make test`; las de esquema están además
# en `test_nucleo_schemas.py`, que sí forma parte de `make unit`).
# ---------------------------------------------------------------------------
def test_rango_mes_semiabierto_y_diciembre():
    assert rango_mes("2026-05") == (date(2026, 5, 1), date(2026, 6, 1))
    assert rango_mes("2026-12") == (date(2026, 12, 1), date(2027, 1, 1))
    with pytest.raises(DatosInvalidos):
        rango_mes("2026-13")


def test_celda_csv_neutraliza_formulas():
    assert _celda("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert _celda("+56 9 1234") == "'+56 9 1234"
    assert _celda("-100,00") == "'-100,00"
    assert _celda("@cmd") == "'@cmd"
    assert _celda("normal") == "normal"
    assert _celda(None) == ""
    assert _celda(Decimal("-12.50")) == "'-12,50"


def test_permisos_ola_b_por_rol():
    from app.nucleo.permisos import permisos_de

    assert {"mantenimiento:leer", "mantenimiento:escribir"} <= permisos_de(
        RolEmpresa.taller
    )
    assert {"liquidaciones:leer", "liquidaciones:escribir", "iva:leer"} <= permisos_de(
        RolEmpresa.contador
    )
    assert "liquidaciones:leer" not in permisos_de(RolEmpresa.tesoreria)
    assert "liquidaciones:leer" not in permisos_de(RolEmpresa.taller)
    assert "mantenimiento:escribir" not in permisos_de(RolEmpresa.auditor)
    assert "configuracion:escribir" not in permisos_de(RolEmpresa.contador)


# ---------------------------------------------------------------------------
# Fixtures de integración
# ---------------------------------------------------------------------------
class Entorno:
    def __init__(self, app_engine, admin_engine, empresa, chofer, tracto, rampla, cliente) -> None:
        self.engine = app_engine
        self.admin_engine = admin_engine
        self.empresa = empresa
        self.chofer = chofer
        self.tracto = tracto
        self.rampla = rampla
        self.cliente = cliente

    def contexto(self, rol: RolEmpresa = RolEmpresa.admin, auth: str | None = None):
        contexto = ContextoEmpresa(
            auth_id=auth or str(uuid4()), empresa=self.empresa, rol=rol
        )
        # Fija app.empresa_id / nucleo.auth_id en el ContextVar del request de
        # prueba: sin esto el rol `tei_app` (sin BYPASSRLS) vería 0 filas.
        return contexto_de_prueba(contexto)


@pytest.fixture
def entorno():
    if _url_app() == _url_admin():
        pytest.skip(
            "NUCLEO_DATABASE_URL no apunta al rol tei_app; la integración con RLS "
            "se omite (el rol privilegiado no tiene GRANT en 0024–0026)"
        )
    admin_engine = create_engine(_url_admin(), future=True)
    # El listener `begin` reaplica app.empresa_id/nucleo.auth_id en cada
    # transacción del rol `tei_app` (sin BYPASSRLS).
    app_engine = registrar_contexto_transaccion(create_engine(_url_app(), future=True))
    try:
        with admin_engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.pautas_mantenimiento limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover - entorno sin 0024
                pytest.skip(f"Falta la migración 0024: {exc}")
        token = uuid4().hex[:8]
        with Session(admin_engine) as session:
            empresa = Empresa(
                codigo=f"OLAB-{token}",
                razon_social=f"Empresa Ola B {token}",
                rut=rut_empresa(),
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)
            chofer = Chofer(
                empresa_id=empresa.id,
                rut=str(uuid4().int)[:10],
                nombre="Chofer Ola B",
                apellido_paterno=token,
                licencia_clase="A5",
                numero_licencia=f"OB-{token}",
                sueldo_base=Decimal("400000"),
                porcentaje_comision=Decimal("0.10"),
            )
            tracto = Tracto(
                empresa_id=empresa.id,
                patente=f"OB{token[:5].upper()}",
                peso_bruto_kg=Decimal("39000"),
                tara_kg=Decimal("9000"),
                capacidad_carga_kg=Decimal("30000"),
                km_actual=Decimal("0"),
            )
            rampla = Rampla(
                empresa_id=empresa.id,
                patente=f"OR{token[:5].upper()}",
                tipo=TipoRampla.plana,
                capacidad_carga_kg=Decimal("30000"),
            )
            cliente = Cliente(
                empresa_id=empresa.id,
                razon_social=f"Cliente Ola B {token}",
                rut=str(uuid4().int)[:10],
            )
            session.add_all([chofer, tracto, rampla, cliente])
            session.commit()
            for objeto in (chofer, tracto, rampla, cliente):
                session.refresh(objeto)
            yield Entorno(
                app_engine, admin_engine, empresa, chofer, tracto, rampla, cliente
            )
    finally:
        app_engine.dispose()
        admin_engine.dispose()


def _viaje(session: Session, entorno: Entorno, *, flete: Decimal) -> Viaje:
    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    viaje = Viaje(
        empresa_id=entorno.empresa.id,
        numero_viaje=f"OB-{uuid4().hex[:10]}",
        cliente_id=entorno.cliente.id,
        chofer_id=entorno.chofer.id,
        estado=EstadoViaje.borrador,
        inicio_planificado=ahora,
        fin_planificado=ahora + timedelta(hours=8),
        fin_real=ahora + timedelta(hours=8),
        origen_nombre="Santiago",
        destino_nombre="Concepción",
        valor_flete_neto=flete,
    )
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return viaje


def _factura(
    session: Session,
    entorno: Entorno,
    *,
    viaje: Viaje | None,
    neto: Decimal,
    iva: Decimal,
    estado: str = "emitida",
    fecha_emision: date = date(2026, 5, 10),
    cliente_id=None,
) -> FacturaNucleo:
    factura = FacturaNucleo(
        empresa_id=entorno.empresa.id,
        numero_factura=f"F-{uuid4().hex[:10]}",
        cliente_id=cliente_id or entorno.cliente.id,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_emision + timedelta(days=30),
        neto=neto,
        iva=iva,
        estado=estado,
    )
    session.add(factura)
    session.commit()
    session.refresh(factura)
    if viaje is not None:
        session.add(
            FacturaViaje(
                empresa_id=entorno.empresa.id,
                factura_id=factura.id,
                viaje_id=viaje.id,
                monto=neto,
            )
        )
        session.commit()
    return factura


# ---------------------------------------------------------------------------
# Mantenimiento — CN-08 y validaciones
# ---------------------------------------------------------------------------
def test_mantenimiento_cn08_y_validaciones(entorno):
    contexto = entorno.contexto()
    with Session(entorno.engine) as session:
        servicio = ServicioMantenimiento(session, contexto)
        pauta = servicio.crear_pauta(
            PautaMantenimientoCreate(
                recurso_tipo="tracto",
                item=f"aceite {uuid4().hex[:6]}",
                intervalo_km=20000,
            )
        )
        assert pauta.intervalo_km == 20000

        registro = servicio.crear_mantenimiento(
            MantenimientoCreate(
                pauta_id=pauta.id,
                tracto_id=entorno.tracto.id,
                fecha=date(2026, 5, 1),
                km=Decimal("10000"),
                costo=Decimal("0"),
            )
        )
        assert registro.intervalo_km_snapshot == 20000  # snapshot

        filas = servicio.estado(recurso_id=entorno.tracto.id)
        assert len(filas) == 1
        assert filas[0].proximo_km == Decimal("30000.0")
        assert filas[0].restante_km == Decimal("20000.0")
        assert filas[0].estado == "ok"

        # Mover el odómetro reclasifica sin tocar el histórico (no se almacena).
        for km, esperado in (
            (Decimal("30000"), "pendiente"),
            (Decimal("25000"), "por_vencer"),
            (Decimal("24999"), "ok"),
        ):
            session.execute(
                text(
                    "update nucleo.tractos set km_actual = :km"
                    " where empresa_id = :empresa_id and id = :id"
                ),
                {"km": km, "empresa_id": entorno.empresa.id, "id": entorno.tracto.id},
            )
            session.commit()
            estado = servicio.estado(recurso_id=entorno.tracto.id)[0]
            assert estado.estado == esperado, (km, estado.estado)

        # Rampla: el modelo no tiene odómetro => sin_odometro.
        pauta_rampla = servicio.crear_pauta(
            PautaMantenimientoCreate(
                recurso_tipo="rampla",
                item=f"frenos {uuid4().hex[:6]}",
                intervalo_km=60000,
            )
        )
        assert servicio.estado(recurso_id=entorno.rampla.id)[0].estado == "sin_registro"
        servicio.crear_mantenimiento(
            MantenimientoCreate(
                pauta_id=pauta_rampla.id,
                rampla_id=entorno.rampla.id,
                fecha=date(2026, 5, 2),
                km=Decimal("1000"),
            )
        )
        assert servicio.estado(recurso_id=entorno.rampla.id)[0].estado == "sin_odometro"

        # Pauta de tracto + rampla => 422 de dominio.
        with pytest.raises(DatosInvalidos):
            servicio.crear_mantenimiento(
                MantenimientoCreate(
                    pauta_id=pauta.id,
                    rampla_id=entorno.rampla.id,
                    fecha=date(2026, 5, 3),
                    km=Decimal("10000"),
                )
            )
        # Km por debajo del odómetro actual => 422.
        with pytest.raises(DatosInvalidos):
            servicio.crear_mantenimiento(
                MantenimientoCreate(
                    pauta_id=pauta.id,
                    tracto_id=entorno.tracto.id,
                    fecha=date(2026, 5, 4),
                    km=Decimal("1"),
                )
            )
        # Ítem activo duplicado => 409.
        with pytest.raises(RegistroDuplicado):
            servicio.crear_pauta(
                PautaMantenimientoCreate(
                    recurso_tipo="tracto", item=pauta.item, intervalo_km=30000
                )
            )


def test_mantenimiento_historico_no_se_borra_ni_se_reescribe(entorno):
    with Session(entorno.engine) as session:
        servicio = ServicioMantenimiento(session, entorno.contexto())
        pauta = servicio.crear_pauta(
            PautaMantenimientoCreate(item=f"engrase {uuid4().hex[:6]}", intervalo_km=5000)
        )
        registro = servicio.crear_mantenimiento(
            MantenimientoCreate(
                pauta_id=pauta.id,
                tracto_id=entorno.tracto.id,
                fecha=date(2026, 5, 5),
                km=Decimal("5000"),
            )
        )
        # `tei_app` no tiene DELETE: 42501. Si se concediera, el trigger daría
        # 23514. En ambos casos el histórico no se borra.
        with pytest.raises(SQLAlchemyError):
            session.execute(
                text("delete from nucleo.mantenimientos where id = :id"),
                {"id": registro.id},
            )
        session.rollback()
        anulado = servicio.anular_mantenimiento(registro.id, "registro duplicado")
        assert anulado.estado == "anulado"
        assert ServicioMantenimiento(
            session, entorno.contexto()
        ).estado(recurso_id=entorno.tracto.id)[0].estado == "sin_registro"


# ---------------------------------------------------------------------------
# Nómina — CN-03, CN-04, emisión, anulación
# ---------------------------------------------------------------------------
def test_nomina_cn03_cn04_emision_y_anulacion(entorno):
    with Session(entorno.engine) as session:
        servicio = ServicioNomina(session, entorno.contexto())
        viaje = _viaje(session, entorno, flete=Decimal("1800000"))
        _factura(session, entorno, viaje=viaje, neto=Decimal("1800000"), iva=Decimal("342000"))

        servicio.crear_ajuste(
            AjusteCreate(
                chofer_id=entorno.chofer.id,
                mes=MES,
                tipo="bono",
                concepto="bono cumplimiento",
                monto=Decimal("50000"),
            )
        )
        servicio.crear_ajuste(
            AjusteCreate(
                chofer_id=entorno.chofer.id,
                mes=MES,
                tipo="descuento",
                concepto="descuento préstamo",
                monto=Decimal("100000"),
            )
        )
        anticipo = servicio.crear_anticipo(
            AnticipoCreate(
                chofer_id=entorno.chofer.id,
                fecha=date(2026, 5, 5),
                monto=Decimal("150000"),
                mes_imputacion=MES,
            )
        )

        liquidacion = servicio.crear_liquidacion(
            LiquidacionCreate(
                chofer_id=entorno.chofer.id,
                mes=MES,
                sueldo_base=Decimal("400000"),
            )
        )
        # CN-03: 400.000 + 180.000 + 50.000 - 100.000 - 150.000 = 380.000
        assert liquidacion.comision == Decimal("180000.00")
        assert liquidacion.total_liquido == Decimal("380000.00")
        assert liquidacion.estado == "borrador"
        assert anticipo.estado == "pendiente"

        emitida = servicio.emitir(liquidacion.id)
        assert emitida.estado == "emitida"
        assert emitida.emitida_por == servicio.contexto.auth_id
        assert emitida.total_liquido == Decimal("380000.00")

        imputado = session.execute(
            text(
                "select estado, liquidacion_id from nucleo.anticipos_chofer"
                " where empresa_id = :empresa_id and id = :id"
            ),
            {"empresa_id": entorno.empresa.id, "id": anticipo.id},
        ).mappings().one()
        assert imputado["estado"] == "descontado"
        assert imputado["liquidacion_id"] == liquidacion.id

        # Idempotencia de la emisión: mismo documento, sin reimputar.
        otra_vez = servicio.emitir(liquidacion.id)
        assert otra_vez.id == emitida.id
        assert otra_vez.emitida_en == emitida.emitida_en

        # Emitida es inmutable en montos aun por SQL directo (garantía de la base).
        with pytest.raises(IntegrityError):
            session.execute(
                text("update nucleo.liquidaciones set comision = 1 where id = :id"),
                {"id": liquidacion.id},
            )
        session.rollback()

        anulada = servicio.anular(liquidacion.id, "error de período")
        assert anulada.estado == "anulada"
        assert anulada.motivo_anulacion == "error de período"
        assert servicio.anular(liquidacion.id, "error de período").estado == "anulada"
        with pytest.raises(ReglaNegocioViolada):
            servicio.anular(liquidacion.id, "otro motivo")


def test_nomina_cn04_half_up_y_duplicado(entorno):
    with Session(entorno.engine) as session:
        ServicioNomina(session, entorno.contexto())  # fija el contexto RLS
        token = uuid4().hex[:6]
        chofer = Chofer(
            empresa_id=entorno.empresa.id,
            rut=str(uuid4().int)[:10],
            nombre="Chofer 12.5",
            apellido_paterno=token,
            licencia_clase="A5",
            numero_licencia=f"OB-{token}",
            sueldo_base=Decimal("0"),
            porcentaje_comision=Decimal("0.125"),
        )
        session.add(chofer)
        session.commit()
        session.refresh(chofer)
        viaje = _viaje(session, entorno, flete=Decimal("1000009"))
        session.execute(
            text("update nucleo.viajes set chofer_id = :chofer where id = :viaje"),
            {"chofer": chofer.id, "viaje": viaje.id},
        )
        session.commit()
        _factura(session, entorno, viaje=viaje, neto=Decimal("1000009"), iva=Decimal("190002"))

        # La base es la definición única del redondeo (CN-04).
        directo = session.execute(
            text("select nucleo.redondear_half_up(1000009 * 0.125, 2)")
        ).scalar_one()
        assert Decimal(directo) == Decimal("125001.13")

        servicio = ServicioNomina(session, entorno.contexto())
        liquidacion = servicio.crear_liquidacion(
            LiquidacionCreate(chofer_id=chofer.id, mes=MES)
        )
        assert liquidacion.comision == Decimal("125001.13")  # HALF_UP, no 125001.12

        with pytest.raises(RegistroDuplicado):
            servicio.crear_liquidacion(LiquidacionCreate(chofer_id=chofer.id, mes=MES))


def test_nomina_concurrencia_emision_imputa_una_sola_vez(entorno):
    with Session(entorno.engine) as session:
        servicio = ServicioNomina(session, entorno.contexto())
        viaje = _viaje(session, entorno, flete=Decimal("1000000"))
        _factura(session, entorno, viaje=viaje, neto=Decimal("1000000"), iva=Decimal("190000"))
        anticipo = servicio.crear_anticipo(
            AnticipoCreate(
                chofer_id=entorno.chofer.id,
                monto=Decimal("70000"),
                mes_imputacion=MES,
            )
        )
        liquidacion = servicio.crear_liquidacion(
            LiquidacionCreate(chofer_id=entorno.chofer.id, mes=MES)
        )

    def emitir():
        motor = registrar_contexto_transaccion(create_engine(_url_app(), future=True))
        try:
            with Session(motor) as session:
                return ServicioNomina(
                    session, entorno.contexto()
                ).emitir(liquidacion.id).estado
        finally:
            motor.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: emitir(), range(2)))
    assert resultados == ["emitida", "emitida"]

    with Session(entorno.engine) as session:
        entorno.contexto()
        filas = session.execute(
            text(
                "select count(*) from nucleo.anticipos_chofer"
                " where empresa_id = :empresa_id and chofer_id = :chofer_id"
                " and mes_imputacion = :mes and estado = 'descontado'"
                " and liquidacion_id = :liquidacion_id"
            ),
            {
                "empresa_id": entorno.empresa.id,
                "chofer_id": entorno.chofer.id,
                "mes": MES,
                "liquidacion_id": liquidacion.id,
            },
        ).scalar_one()
        assert filas == 1
        estado = session.execute(
            text("select estado from nucleo.liquidaciones where id = :id"),
            {"id": liquidacion.id},
        ).scalar_one()
        assert estado == "emitida"
        assert anticipo.id is not None


# ---------------------------------------------------------------------------
# IVA — solo débito (CN-07)
# ---------------------------------------------------------------------------
def test_iva_solo_debito_ignora_anuladas(entorno):
    contexto = entorno.contexto()
    with Session(entorno.engine) as session:
        _factura(
            session, entorno, viaje=None, neto=Decimal("500000"),
            iva=Decimal("95000"), fecha_emision=date(2026, 5, 10),
        )
        _factura(
            session, entorno, viaje=None, neto=Decimal("300000"),
            iva=Decimal("0"), fecha_emision=date(2026, 5, 11),
        )
        _factura(
            session, entorno, viaje=None, neto=Decimal("76000"),
            iva=Decimal("14440"), estado="anulada",
            fecha_emision=date(2026, 5, 12),
        )
        _factura(
            session, entorno, viaje=None, neto=Decimal("100000"),
            iva=Decimal("19000"), fecha_emision=date(2026, 6, 1),
        )
        servicio = ServicioIva(session, contexto)
        resumen = servicio.resumen(date(2026, 5, 1), date(2026, 5, 31))
        assert resumen.iva_debito == Decimal("95000.00")
        assert resumen.base_neta == Decimal("800000.00")
        assert resumen.facturas == 2
        assert resumen.tasa_iva is None  # empresa nueva sin configuración
        assert "crédito" in resumen.advertencia.lower()
        with pytest.raises(DatosInvalidos):
            servicio.resumen(date(2026, 5, 31), date(2026, 5, 1))


# ---------------------------------------------------------------------------
# Configuración — vigencia, historial e idempotencia
# ---------------------------------------------------------------------------
def test_configuracion_vigencia_historial_e_idempotencia(entorno):
    with Session(entorno.engine) as session:
        servicio = ServicioConfiguracion(session, entorno.contexto())
        assert servicio.listar().items == []

        primero = servicio.actualizar("iva_porcentaje", 19)
        assert primero.valor == 19
        assert servicio.actualizar("iva_porcentaje", Decimal("19.0")).version == 1

        segundo = servicio.actualizar("iva_porcentaje", 21)
        assert segundo.valor == 21
        assert segundo.vigente_desde > primero.vigente_desde

        historial = session.execute(
            text(
                "select valor, vigente_hasta is null as vigente"
                " from nucleo.configuracion_empresa"
                " where empresa_id = :empresa_id and clave = 'iva_porcentaje'"
                " order by vigente_desde"
            ),
            {"empresa_id": entorno.empresa.id},
        ).all()
        assert len(historial) == 2
        assert [fila.vigente for fila in historial] == [False, True]
        assert servicio.valor_vigente("iva_porcentaje") == 21

        for invalido in (-1, 101, "abc", True):
            with pytest.raises(DatosInvalidos):
                servicio.actualizar("iva_porcentaje", invalido)
        with pytest.raises(DatosInvalidos):
            servicio.actualizar("clave_inventada", 1)


# ---------------------------------------------------------------------------
# HTTP — 201/200/403/422 sobre la matriz real de permisos
# ---------------------------------------------------------------------------
@pytest.fixture
def cliente_http(entorno):
    from fastapi.testclient import TestClient

    return TestClient(app)


def _override(contexto):
    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(contexto)


def test_http_mantenimiento_201_200_403_422(entorno, cliente_http):
    admin = entorno.contexto(RolEmpresa.admin)
    _override(admin)
    try:
        creada = cliente_http.post(
            f"{API}/mantenimiento/pautas",
            json={
                "recurso_tipo": "tracto",
                "item": f"filtro {uuid4().hex[:6]}",
                "intervalo_km": 15000,
            },
        )
        assert creada.status_code == 201, creada.text
        assert creada.json()["recurso_tipo"] == "tracto"

        assert cliente_http.get(f"{API}/mantenimiento/pautas").status_code == 200

        malo = cliente_http.post(
            f"{API}/mantenimiento/pautas",
            json={"recurso_tipo": "tracto", "item": "x", "intervalo_km": 0},
        )
        assert malo.status_code == 422
        assert cliente_http.get(
            f"{API}/mantenimiento/pautas?recurso_tipo=chofer"
        ).status_code == 422

        registro = cliente_http.post(
            f"{API}/mantenimiento/mantenimientos",
            json={
                "pauta_id": creada.json()["id"],
                "tracto_id": str(entorno.tracto.id),
                "fecha": "2026-05-10",
                "km": "10.0",
                "costo": "12345.67",
            },
        )
        assert registro.status_code == 201, registro.text
        assert cliente_http.get(f"{API}/mantenimiento/estado").status_code == 200

        ambos = cliente_http.post(
            f"{API}/mantenimiento/mantenimientos",
            json={
                "pauta_id": creada.json()["id"],
                "tracto_id": str(entorno.tracto.id),
                "rampla_id": str(entorno.rampla.id),
                "fecha": "2026-05-10",
                "km": "10.0",
            },
        )
        assert ambos.status_code == 422
    finally:
        app.dependency_overrides.clear()

    _override(entorno.contexto(RolEmpresa.conductor))
    try:
        assert cliente_http.get(f"{API}/mantenimiento/pautas").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_http_nomina_201_200_403_422(entorno, cliente_http):
    contador = entorno.contexto(RolEmpresa.contador)
    _override(contador)
    try:
        with Session(entorno.admin_engine) as session:
            viaje = _viaje(session, entorno, flete=Decimal("1000000"))
            _factura(
                session, entorno, viaje=viaje, neto=Decimal("1000000"),
                iva=Decimal("190000"),
            )
        creada = cliente_http.post(
            f"{API}/liquidaciones",
            json={"chofer_id": str(entorno.chofer.id), "mes": MES},
        )
        assert creada.status_code == 201, creada.text
        assert cliente_http.get(f"{API}/liquidaciones?mes={MES}").status_code == 200
        assert cliente_http.post(
            f"{API}/anticipos",
            json={
                "chofer_id": str(entorno.chofer.id),
                "monto": "10000",
                "mes_imputacion": MES,
            },
        ).status_code == 201
        assert cliente_http.get(f"{API}/ajustes?mes={MES}").status_code == 200

        malo = cliente_http.post(
            f"{API}/liquidaciones",
            json={"chofer_id": str(entorno.chofer.id), "mes": "2026-13"},
        )
        assert malo.status_code == 422
    finally:
        app.dependency_overrides.clear()

    _override(entorno.contexto(RolEmpresa.taller))
    try:
        assert cliente_http.get(f"{API}/liquidaciones").status_code == 403
        assert cliente_http.get(f"{API}/export/liquidaciones").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_http_iva_configuracion_y_export(entorno, cliente_http):
    admin = entorno.contexto(RolEmpresa.admin)
    _override(admin)
    try:
        assert cliente_http.get(
            f"{API}/iva/resumen?desde=2026-05-01&hasta=2026-05-31"
        ).status_code == 200
        assert cliente_http.get(
            f"{API}/iva/resumen?desde=2026-05-31&hasta=2026-05-01"
        ).status_code == 422
        assert cliente_http.get(f"{API}/configuracion").status_code == 200
        actualizado = cliente_http.put(
            f"{API}/configuracion/iva_porcentaje", json={"valor": 19}
        )
        assert actualizado.status_code == 200, actualizado.text
        assert actualizado.json()["valor"] == 19
        assert cliente_http.put(
            f"{API}/configuracion/iva_porcentaje", json={"valor": 101}
        ).status_code == 422

        export = cliente_http.get(f"{API}/export/facturas")
        assert export.status_code == 200
        assert export.headers["content-type"].startswith("text/csv")
        assert export.content.startswith(b"\xef\xbb\xbf")  # BOM
        assert cliente_http.get(f"{API}/export/viajes").status_code == 200
    finally:
        app.dependency_overrides.clear()

    _override(entorno.contexto(RolEmpresa.contador))
    try:
        assert cliente_http.get(f"{API}/configuracion").status_code == 200
        assert cliente_http.put(
            f"{API}/configuracion/iva_porcentaje", json={"valor": 19}
        ).status_code == 403
        assert cliente_http.get(f"{API}/export/liquidaciones").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_export_neutraliza_formula_en_celda(entorno, cliente_http):
    with Session(entorno.admin_engine) as session:
        cliente = Cliente(
            empresa_id=entorno.empresa.id,
            razon_social='=HYPERLINK("http://x")',
            rut=str(uuid4().int)[:10],
        )
        session.add(cliente)
        session.commit()
        session.refresh(cliente)
        _factura(
            session, entorno, viaje=None, neto=Decimal("1000"),
            iva=Decimal("190"), cliente_id=cliente.id,
        )
    _override(entorno.contexto(RolEmpresa.admin))
    try:
        respuesta = cliente_http.get(f"{API}/export/facturas")
        assert respuesta.status_code == 200
        texto_csv = respuesta.content.decode("utf-8-sig")
        assert "'=HYPERLINK" in texto_csv
    finally:
        app.dependency_overrides.clear()
