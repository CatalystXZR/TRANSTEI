"""Pruebas P0-11: alertas y tablero del dueño."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text, update
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
    BloqueoCreate,
    FacturaCreate,
    GastoCreate,
    IncidenteCreate,
    SolicitudSobregiro,
)
from app.nucleo.servicio_alertas import ServicioAlertas
from app.nucleo.servicio_bloqueos import ServicioBloqueos
from app.nucleo.servicio_comercial import ServicioComercial
from app.nucleo.servicio_expediente import ServicioExpediente
from app.nucleo.servicio_facturacion import ServicioFacturacion
from app.nucleo.servicio_gastos import ServicioGastos


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de alertas")
    return url


def _base(session: Session, sufijo: str):
    token = uuid4().hex[:8]
    digitos = str(uuid4().int)[:10]
    vence = date.today() + timedelta(days=365)
    empresa = Empresa(
        codigo=f"ALT-{sufijo}",
        razon_social=f"Empresa Alertas {sufijo}",
        rut=f"ALT-{sufijo}",
    )
    session.add(empresa)
    session.commit()
    session.refresh(empresa)
    cliente = Cliente(
        empresa_id=empresa.id,
        razon_social=f"Cliente Alertas {sufijo}",
        rut=digitos,
        dias_pago=30,
    )
    tracto = Tracto(
        empresa_id=empresa.id,
        patente=f"A{token[:6].upper()}",
        peso_bruto_kg=Decimal("39000"),
        tara_kg=Decimal("9000"),
        capacidad_carga_kg=Decimal("30000"),
    )
    rampla = Rampla(
        empresa_id=empresa.id,
        patente=f"V{token[:6].upper()}",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal("30000"),
    )
    chofer = Chofer(
        empresa_id=empresa.id,
        rut=str(int(digitos) + 1),
        nombre="Chofer Alertas",
        apellido_paterno=sufijo,
        numero_licencia=f"LA-{token}",
        # R-02 / 0016: la base rechaza (23514) todo viaje con chofer que no
        # sea clase A5; el fixture debe cumplir la regla vigente.
        licencia_clase="A5",
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
        codigo=f"TA-{token}",
        nombre="Ruta alertas",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        precio_unitario=Decimal("100000"),
    )
    oc = OrdenCompra(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_oc=f"OCA-{token}",
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        monto_autorizado=Decimal("5000000"),
    )
    session.add_all(docs + [tarifa, oc])
    session.commit()
    return empresa, cliente, tracto, rampla, chofer, tarifa, oc


def _viaje(
    session: Session,
    empresa,
    cliente,
    tracto,
    rampla,
    chofer,
    tarifa,
    oc,
    *,
    estado: EstadoViaje,
    inicio: datetime,
) -> Viaje:
    viaje = Viaje(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        orden_compra_id=oc.id,
        tarifa_id=tarifa.id,
        tracto_id=tracto.id,
        rampla_id=rampla.id,
        chofer_id=chofer.id,
        estado=estado,
        inicio_planificado=inicio,
        fin_planificado=inicio + timedelta(hours=4),
        buffer_minutos=30,
        peso_bruto_kg=Decimal("20000"),
        origen_nombre="Santiago",
        destino_nombre="Talca",
        valor_flete_neto=Decimal("100000"),
        distancia_km=Decimal("250"),
    )
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return viaje


def test_tablero_genera_alertas_de_todas_las_fuentes():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.facturas_nucleo limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Faltan migraciones 0011-0013: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa, cliente, tracto, rampla, chofer, tarifa, oc = _base(session, sufijo)
            despacho = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.despacho
            )
            gerente = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.gerente
            )
            contador = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.contador
            )

            ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            # A: descargado sin POD, incidente alto, score rojo.
            viaje_a = _viaje(
                session, empresa, cliente, tracto, rampla, chofer, tarifa, oc,
                estado=EstadoViaje.descargado, inicio=ahora - timedelta(days=5),
            )
            viaje_a.freight_score_estimado = Decimal("50")
            session.add(viaje_a)
            session.commit()

            # B: cerrado sin factura.
            _viaje(
                session, empresa, cliente, tracto, rampla, chofer, tarifa, oc,
                estado=EstadoViaje.cerrado, inicio=ahora - timedelta(days=4),
            )

            # C: cerrado con POD y factura vencida.
            viaje_c = _viaje(
                session, empresa, cliente, tracto, rampla, chofer, tarifa, oc,
                estado=EstadoViaje.cerrado, inicio=ahora - timedelta(days=3),
            )
            session.execute(
                text(
                    """
                    insert into nucleo.pod
                      (empresa_id, viaje_id, receptor_nombre, fecha_hora, firma_url,
                       fotos, created_by)
                    values (:empresa_id, :viaje_id, 'Receptor Alertas', now(),
                            'demo/firma.png', '[]'::jsonb, 'test')
                    """
                ),
                {"empresa_id": empresa.id, "viaje_id": viaje_c.id},
            )
            session.commit()

            # Documento por vencer mañana.
            session.add(
                Documento(
                    empresa_id=empresa.id,
                    recurso_tipo=TipoRecurso.tracto,
                    tracto_id=tracto.id,
                    tipo=TipoDocumento.otro,
                    vence_en=date.today() + timedelta(days=1),
                )
            )
            session.commit()

            # Mantención en 2 días.
            ServicioBloqueos(session, despacho).crear_bloqueo(
                BloqueoCreate(
                    recurso_tipo=TipoRecurso.tracto,
                    recurso_id=tracto.id,
                    inicio=ahora + timedelta(days=2),
                    fin=ahora + timedelta(days=2, hours=4),
                    tipo_reserva="mantenimiento",
                    motivo="Mantención preventiva alertas",
                )
            )

            # Incidente alto en A.
            ServicioExpediente(session, despacho).crear_incidente(
                viaje_a.id,
                IncidenteCreate(
                    tipo="averia",
                    severidad="alta",
                    descripcion="Falla de luces traseras",
                ),
            )

            # Sobregiro pendiente en OC.
            ServicioComercial(session, despacho).solicitar_sobregiro(
                oc.id,
                SolicitudSobregiro(monto=Decimal("100000"), motivo="Carga extra"),
            )

            # Gasto aprobado para caja negativa.
            gasto = ServicioGastos(session, despacho).crear_gasto(
                viaje_a.id,
                GastoCreate(
                    tipo="combustible",
                    fecha=date.today(),
                    monto_total=Decimal("119000"),
                    iva=Decimal("19000"),
                    litros=Decimal("100"),
                    precio_litro=Decimal("1000"),
                ),
            )
            ServicioGastos(session, gerente).aprobar_gasto(gasto.id, AprobarGasto())

            # Factura vencida de C.
            factura = ServicioFacturacion(session, contador).crear_factura(
                FacturaCreate(
                    cliente_id=cliente.id,
                    viaje_ids=[viaje_c.id],
                    fecha_emision=date.today() - timedelta(days=40),
                    fecha_vencimiento=date.today() - timedelta(days=10),
                )
            )
            assert factura.estado == "vencida"

            tablero = ServicioAlertas(session, gerente).tablero()
            categorias = {a.categoria for a in tablero.alertas}
            assert "documentos" in categorias
            assert "mantencion" in categorias
            assert "pod" in categorias
            assert "facturacion" in categorias
            assert "oc" in categorias
            assert "cxc" in categorias
            assert "margen" in categorias
            assert "incidente" in categorias
            assert "caja" in categorias

            assert tablero.kpis.documentos_por_vencer >= 1
            assert tablero.kpis.mantenciones_proximas >= 1
            assert tablero.kpis.viajes_sin_pod >= 1
            assert tablero.kpis.viajes_sin_facturar >= 1
            assert tablero.kpis.oc_con_alerta >= 1
            assert tablero.kpis.cxc_vencido > 0
            assert tablero.kpis.caja_operativa < 0
            assert tablero.salud["critica"] + tablero.salud["alta"] > 0
            assert tablero.briefing
            assert len(tablero.acciones) == 4
            assert tablero.aging.total_vencido > 0
    finally:
        engine.dispose()
