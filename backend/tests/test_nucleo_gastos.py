"""Pruebas P0-08: gastos, combustible y costo real."""

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
from app.nucleo.errores import AccesoDenegado, ReglaNegocioViolada
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
    GastoCreate,
    PrecioDieselCreate,
    RechazarGasto,
)
from app.nucleo.servicio_gastos import ServicioGastos


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de gastos")
    return url


def _crear_viaje(session: Session, empresa: Empresa, sufijo: str) -> Viaje:
    token = uuid4().hex[:8]
    digitos = str(uuid4().int)[:10]
    vence = date.today() + timedelta(days=365)
    cliente = Cliente(
        empresa_id=empresa.id,
        razon_social=f"Cliente Gastos {sufijo}",
        rut=digitos,
    )
    tracto = Tracto(
        empresa_id=empresa.id,
        patente=f"G{token[:6].upper()}",
        peso_bruto_kg=Decimal("39000"),
        tara_kg=Decimal("9000"),
        capacidad_carga_kg=Decimal("30000"),
    )
    rampla = Rampla(
        empresa_id=empresa.id,
        patente=f"M{token[:6].upper()}",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal("30000"),
    )
    chofer = Chofer(
        empresa_id=empresa.id,
        rut=str(int(digitos) + 1),
        nombre="Chofer Gastos",
        apellido_paterno=sufijo,
        numero_licencia=f"LG-{token}",
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
        codigo=f"TG-{token}",
        nombre="Ruta gastos",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        precio_unitario=Decimal("1000000"),
    )
    oc = OrdenCompra(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_oc=f"OCG-{token}",
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
        peso_bruto_kg=Decimal("20000"),
        origen_nombre="Santiago",
        destino_nombre="Concepción",
        distancia_km=Decimal("500"),
        valor_flete_neto=Decimal("1000000"),
    )
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return viaje


def test_gastos_combustible_costo_y_aprobacion():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.viaje_gastos limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0011: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"GAS-{sufijo}",
                razon_social=f"Empresa Gastos {sufijo}",
                rut=f"GAS-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            viaje = _crear_viaje(session, empresa, sufijo)
            auth_despacho = str(uuid4())
            auth_gerente = str(uuid4())
            despacho = ServicioGastos(
                session,
                ContextoEmpresa(
                    auth_id=auth_despacho, empresa=empresa, rol=RolEmpresa.despacho
                ),
            )
            gerente = ServicioGastos(
                session,
                ContextoEmpresa(
                    auth_id=auth_gerente, empresa=empresa, rol=RolEmpresa.gerente
                ),
            )

            precio = despacho.crear_precio(
                PrecioDieselCreate(fecha=date.today(), precio_litro=Decimal("1000"))
            )
            assert precio.precio_litro == Decimal("1000.0000")
            assert despacho.precio_vigente(date.today()).precio_litro == Decimal("1000.0000")

            combustible = despacho.crear_gasto(
                viaje.id,
                GastoCreate(
                    tipo="combustible",
                    proveedor="Copec",
                    fecha=date.today(),
                    monto_total=Decimal("119000"),
                    iva=Decimal("19000"),
                    litros=Decimal("100"),
                    precio_litro=Decimal("1000"),
                    km_odometro=Decimal("125000"),
                ),
            )
            assert combustible.estado == "pendiente"
            assert combustible.monto_neto == Decimal("100000.00")

            # Sin precio explícito usa el precio vigente.
            combustible2 = despacho.crear_gasto(
                viaje.id,
                GastoCreate(
                    tipo="combustible",
                    fecha=date.today(),
                    monto_total=Decimal("59500"),
                    iva=Decimal("9500"),
                    litros=Decimal("50"),
                ),
            )
            assert combustible2.precio_litro == Decimal("1000.0000")

            peaje = despacho.crear_gasto(
                viaje.id,
                GastoCreate(
                    tipo="peaje",
                    fecha=date.today(),
                    monto_total=Decimal("20000"),
                    tag="TAG-123",
                ),
            )

            costos = despacho.costos(viaje.id)
            assert costos.gastos_aprobados == Decimal("0.00")
            assert costos.gastos_pendientes == Decimal("198500.00")
            assert costos.comision_estimada == Decimal("50000.00")
            assert costos.costo_variable == Decimal("50000.00")
            assert costos.margen == Decimal("950000.00")

            # Despacho no puede aprobar.
            with pytest.raises(AccesoDenegado):
                despacho.aprobar_gasto(combustible.id, AprobarGasto())

            aprobado = gerente.aprobar_gasto(combustible.id, AprobarGasto())
            assert aprobado.estado == "aprobado"
            assert aprobado.aprobado_por == auth_gerente

            # Autoaprobación de un contador con el mismo auth del creador.
            contador_mismo = ServicioGastos(
                session,
                ContextoEmpresa(
                    auth_id=auth_despacho, empresa=empresa, rol=RolEmpresa.contador
                ),
            )
            with pytest.raises(AccesoDenegado):
                contador_mismo.aprobar_gasto(combustible2.id, AprobarGasto())

            gerente.aprobar_gasto(combustible2.id, AprobarGasto())
            gerente.aprobar_gasto(peaje.id, AprobarGasto())

            costos = despacho.costos(viaje.id)
            assert costos.gastos_aprobados == Decimal("170000.00")
            assert costos.gastos_pendientes == Decimal("0.00")
            assert costos.costo_variable == Decimal("220000.00")
            assert costos.rendimiento_km_l == Decimal("3.33")  # 500 / 150
            assert costos.costo_por_km == Decimal("440.00")
            assert {p.tipo for p in costos.por_tipo} == {"combustible", "peaje"}

            session.refresh(viaje)
            assert viaje.costo_variable_real == Decimal("220000.00")
            assert viaje.costo_total_real == Decimal("220000.00")

            otro = despacho.crear_gasto(
                viaje.id,
                GastoCreate(
                    tipo="estadia",
                    fecha=date.today(),
                    monto_total=Decimal("10000"),
                ),
            )
            rechazado = gerente.rechazar_gasto(
                otro.id, RechazarGasto(motivo="Sin respaldo del cliente")
            )
            assert rechazado.estado == "rechazado"
            assert rechazado.motivo_rechazo.startswith("Sin respaldo")

            costos = despacho.costos(viaje.id)
            assert costos.gastos_aprobados == Decimal("170000.00")
            assert costos.gastos_pendientes == Decimal("0.00")
    finally:
        engine.dispose()
