"""Pruebas P0-10: facturación, pagos parciales, notas y aging."""

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
from app.nucleo.errores import DatosInvalidos, ReglaNegocioViolada
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
    CerrarViaje,
    ChecklistItemUpdate,
    FacturaCreate,
    NotaCreditoCreate,
    PagoCreate,
    PODUpdate,
)
from app.nucleo.servicio_expediente import ServicioExpediente
from app.nucleo.servicio_facturacion import ServicioFacturacion
from app.nucleo.servicio_pod import ServicioPOD

PNG_FALSO = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de facturación")
    return url


def _crear_viaje(session: Session, empresa: Empresa, sufijo: str) -> Viaje:
    token = uuid4().hex[:8]
    digitos = str(uuid4().int)[:10]
    vence = date.today() + timedelta(days=365)
    cliente = Cliente(
        empresa_id=empresa.id,
        razon_social=f"Cliente Factura {sufijo}",
        rut=digitos,
        dias_pago=30,
    )
    tracto = Tracto(
        empresa_id=empresa.id,
        patente=f"F{token[:6].upper()}",
        peso_bruto_kg=Decimal("39000"),
        tara_kg=Decimal("9000"),
        capacidad_carga_kg=Decimal("30000"),
    )
    rampla = Rampla(
        empresa_id=empresa.id,
        patente=f"U{token[:6].upper()}",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal("30000"),
    )
    chofer = Chofer(
        empresa_id=empresa.id,
        rut=str(int(digitos) + 1),
        nombre="Chofer Factura",
        apellido_paterno=sufijo,
        numero_licencia=f"LF-{token}",
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
        codigo=f"TF-{token}",
        nombre="Ruta factura",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        precio_unitario=Decimal("100000"),
    )
    oc = OrdenCompra(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_oc=f"OCF-{token}",
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        monto_autorizado=Decimal("5000000"),
    )
    session.add_all(docs + [tarifa, oc])
    session.commit()
    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    inicio = ahora - timedelta(days=1)
    viaje = Viaje(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        orden_compra_id=oc.id,
        tarifa_id=tarifa.id,
        tracto_id=tracto.id,
        rampla_id=rampla.id,
        chofer_id=chofer.id,
        estado=EstadoViaje.pod_pendiente,
        inicio_planificado=inicio,
        fin_planificado=inicio + timedelta(hours=8),
        buffer_minutos=60,
        peso_bruto_kg=Decimal("20000"),
        origen_nombre="Santiago",
        destino_nombre="Concepción",
        valor_flete_neto=Decimal("100000"),
    )
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return viaje


def test_factura_pagos_parciales_nota_y_aging():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.facturas_nucleo limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0013: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"FAC-{sufijo}",
                razon_social=f"Empresa Factura {sufijo}",
                rut=f"FAC-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.contador
            )
            viaje = _crear_viaje(session, empresa, sufijo)

            pod = ServicioPOD(session, contexto).crear(
                viaje.id,
                receptor_nombre="Receptor Factura",
                receptor_rut="11.111.111-1",
                receptor_cargo="Jefe de bodega",
                fecha_hora=None,
                lat=None,
                lon=None,
                danios=None,
                observaciones=None,
                firma_nombre="firma.png",
                firma_contenido=PNG_FALSO,
                firma_content_type="image/png",
                fotos=[],
            )
            assert pod.facturacion_habilitada is True

            expediente = ServicioExpediente(session, contexto)
            for item in expediente.listar_checklist(viaje.id):
                expediente.actualizar_item_checklist(
                    viaje.id,
                    item.id,
                    ChecklistItemUpdate(completado=True, version=item.version),
                )
            cerrado = expediente.cerrar_viaje(
                viaje.id, CerrarViaje(observaciones="Cierre para facturación")
            )
            assert cerrado.estado == EstadoViaje.cerrado

            facturacion = ServicioFacturacion(session, contexto)
            facturables = facturacion.viajes_facturables()
            assert any(v.viaje_id == viaje.id and v.tiene_pod for v in facturables)

            factura = facturacion.crear_factura(
                FacturaCreate(
                    cliente_id=viaje.cliente_id,
                    viaje_ids=[viaje.id],
                    fecha_vencimiento=date.today() + timedelta(days=30),
                )
            )
            assert factura.numero_factura.startswith("FAC-")
            assert factura.neto == Decimal("100000.00")
            assert factura.iva == Decimal("19000.00")
            assert factura.total == Decimal("119000.00")
            assert factura.saldo == Decimal("119000.00")
            assert factura.estado == "emitida"
            assert len(factura.viajes) == 1

            session.refresh(viaje)
            assert viaje.estado == EstadoViaje.facturado

            # No se puede facturar dos veces el mismo viaje.
            with pytest.raises((ReglaNegocioViolada, DatosInvalidos)):
                facturacion.crear_factura(
                    FacturaCreate(
                        cliente_id=viaje.cliente_id,
                        viaje_ids=[viaje.id],
                        fecha_vencimiento=date.today() + timedelta(days=30),
                    )
                )

            parcial = facturacion.registrar_pago(
                factura.id,
                PagoCreate(
                    monto=Decimal("50000"),
                    metodo="transferencia",
                    referencia="TRX-1",
                ),
            )
            assert parcial.estado == "parcial"
            assert parcial.saldo == Decimal("69000.00")

            with pytest.raises(DatosInvalidos):
                facturacion.registrar_pago(
                    factura.id, PagoCreate(monto=Decimal("1000000"))
                )

            con_nota = facturacion.crear_nota_credito(
                factura.id,
                NotaCreditoCreate(
                    monto=Decimal("19000"), motivo="Ajuste de recargo"
                ),
            )
            assert len(con_nota.notas) == 1
            assert con_nota.saldo == Decimal("50000.00")

            pagada = facturacion.registrar_pago(
                factura.id,
                PagoCreate(
                    monto=Decimal("50000"),
                    metodo="cheque",
                    referencia="CH-2",
                ),
            )
            assert pagada.estado == "pagada"
            assert pagada.saldo == Decimal("0.00")
            assert len(pagada.pagos) == 2

            session.refresh(viaje)
            assert viaje.estado == EstadoViaje.cobrado

            aging = facturacion.aging()
            assert aging.total_cxc == Decimal("0.00")
            assert aging.facturas_abiertas == 0
            assert len(aging.buckets) == 5
    finally:
        engine.dispose()
