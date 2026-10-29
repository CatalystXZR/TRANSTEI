"""Pruebas P0-09: configuración, tarifa piso, simulador y Freight Score."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.models import (
    Chofer,
    Cliente,
    Documento,
    Empresa,
    EstadoViaje,
    ModalidadTarifa,
    OrdenCompra,
    Rampla,
    Tarifa,
    TipoDocumento,
    TipoRampla,
    TipoRecurso,
    Tracto,
    Viaje,
)
from app.nucleo.schemas import (
    AprobarGasto,
    ConfiguracionCostosUpdate,
    GastoCreate,
    SimulacionFlete,
)
from app.nucleo.servicio_gastos import ServicioGastos
from app.nucleo.servicio_rentabilidad import ServicioRentabilidad


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de rentabilidad")
    return url


def _crear_viaje(session: Session, empresa: Empresa, sufijo: str) -> Viaje:
    token = uuid4().hex[:8]
    digitos = str(uuid4().int)[:10]
    vence = date.today() + timedelta(days=365)
    cliente = Cliente(
        empresa_id=empresa.id,
        razon_social=f"Cliente Rentabilidad {sufijo}",
        rut=digitos,
        dias_pago=45,
    )
    tracto = Tracto(
        empresa_id=empresa.id,
        patente=f"R{token[:6].upper()}",
        peso_bruto_kg=Decimal("39000"),
        tara_kg=Decimal("9000"),
        capacidad_carga_kg=Decimal("30000"),
    )
    rampla = Rampla(
        empresa_id=empresa.id,
        patente=f"T{token[:6].upper()}",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal("28000"),
    )
    chofer = Chofer(
        empresa_id=empresa.id,
        rut=str(int(digitos) + 1),
        nombre="Chofer Rentabilidad",
        apellido_paterno=sufijo,
        numero_licencia=f"LR-{token}",
        # R-02 / 0016: la base rechaza (23514) todo viaje con chofer que no
        # sea clase A5; el fixture debe cumplir la regla vigente.
        licencia_clase="A5",
        porcentaje_comision=Decimal("0.05"),
    )
    session.add_all([cliente, tracto, rampla, chofer])
    session.commit()
    docs = [
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
    tarifa = Tarifa(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        codigo=f"TR-{token}",
        nombre="Ruta rentabilidad",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        precio_unitario=Decimal("1000000"),
    )
    oc = OrdenCompra(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_oc=f"OCR-{token}",
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        monto_autorizado=Decimal("5000000"),
    )
    session.add_all(docs + [tarifa, oc])
    session.commit()
    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    inicio = ahora - timedelta(hours=6)
    viaje = Viaje(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        orden_compra_id=oc.id,
        tarifa_id=tarifa.id,
        tracto_id=tracto.id,
        rampla_id=rampla.id,
        chofer_id=chofer.id,
        estado=EstadoViaje.en_ruta,
        inicio_planificado=inicio,
        fin_planificado=inicio + timedelta(hours=8),
        buffer_minutos=60,
        peso_bruto_kg=Decimal("25000"),
        origen_nombre="Santiago",
        destino_nombre="Concepción",
        distancia_km=Decimal("500"),
        valor_flete_neto=Decimal("1000000"),
        condiciones_pago_dias=45,
    )
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return viaje


def test_configuracion_simulador_y_freight_score():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.configuracion_costos limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0012: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"REN-{sufijo}",
                razon_social=f"Empresa Rentabilidad {sufijo}",
                rut=f"REN-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.gerente
            )
            servicio = ServicioRentabilidad(session, contexto)
            inicial = servicio.obtener_config()
            assert inicial.configurado is False

            config = servicio.guardar_config(
                ConfiguracionCostosUpdate(
                    costo_fijo_mensual=Decimal("30000000"),
                    viajes_estimados_mes=60,
                    margen_objetivo=Decimal("0.25"),
                    benchmark_margen_km=Decimal("1200"),
                    contribucion_minima=Decimal("100000"),
                    costo_variable_km_estandar=Decimal("900"),
                )
            )
            assert config.configurado is True
            assert config.version == 1

            # Ejemplo del catálogo: score ~92,9.
            resultado = servicio.simular(
                SimulacionFlete(
                    distancia_km=Decimal("500"),
                    peso_kg=Decimal("25000"),
                    capacidad_kg=Decimal("28000"),
                    flete_neto=Decimal("1200000"),
                    costos_variables=Decimal("450000"),
                    dias_pago=45,
                    retorno="cargado_completo",
                    riesgo_puntos=1,
                )
            )
            assert resultado.semaforo == "verde"
            assert Decimal("92.0") <= resultado.score <= Decimal("93.5")
            assert resultado.tarifa_piso_estrategica == Decimal("1266666.67")
            assert resultado.tarifa_piso_tactica == Decimal("550000.00")
            assert len(resultado.componentes) == 6
            assert any("Freight Score" in e for e in resultado.explicacion)

            # Ejemplo de flete malo: amarillo ~61,4.
            malo = servicio.simular(
                SimulacionFlete(
                    distancia_km=Decimal("500"),
                    peso_kg=Decimal("25000"),
                    capacidad_kg=Decimal("28000"),
                    flete_neto=Decimal("800000"),
                    costos_variables=Decimal("450000"),
                    dias_pago=75,
                    retorno="vacio_sin_alternativa",
                    riesgo_puntos=3,
                )
            )
            assert malo.semaforo == "amarillo"
            assert Decimal("64.5") <= malo.score <= Decimal("65.5")

            # Rentabilidad real de un viaje con gasto aprobado.
            viaje = _crear_viaje(session, empresa, sufijo)
            despacho = ServicioGastos(
                session,
                ContextoEmpresa(
                    auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.despacho
                ),
            )
            gerente = ServicioGastos(
                session,
                ContextoEmpresa(
                    auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.gerente
                ),
            )
            gasto = despacho.crear_gasto(
                viaje.id,
                GastoCreate(
                    tipo="combustible",
                    fecha=date.today(),
                    monto_total=Decimal("119000"),
                    iva=Decimal("19000"),
                    litros=Decimal("100"),
                    precio_litro=Decimal("1000"),
                ),
            )
            gerente.aprobar_gasto(gasto.id, AprobarGasto())

            rentabilidad = servicio.rentabilidad_viaje(viaje.id)
            assert rentabilidad.viaje_id == viaje.id
            assert rentabilidad.fuente_costos == "real"
            assert rentabilidad.costo_variable == Decimal("150000.00")  # 100k gasto + 50k comisión
            assert rentabilidad.ingreso_total == Decimal("1000000.00")
            assert rentabilidad.score > 0
            assert len(rentabilidad.componentes) == 6

            session.refresh(viaje)
            assert viaje.freight_score_estimado == rentabilidad.score
            assert viaje.freight_score_detalle["semaforo"] == rentabilidad.semaforo
    finally:
        engine.dispose()
