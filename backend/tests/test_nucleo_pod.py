"""Pruebas P0-06: POD, evidencia y bloqueo de facturación."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    DatosInvalidos,
    ReglaNegocioViolada,
)
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
from app.nucleo.schemas import PODUpdate
from app.nucleo.servicio_pod import ServicioPOD

PNG_FALSO = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de POD")
    return url


def _crear_viaje(session: Session, empresa: Empresa, sufijo: str, estado: EstadoViaje):
    vence = date.today() + timedelta(days=365)
    token = uuid4().hex[:8]
    digitos = str(uuid4().int)[:10]
    cliente = Cliente(
        empresa_id=empresa.id,
        razon_social=f"Cliente POD {sufijo}",
        rut=digitos,
    )
    tracto = Tracto(
        empresa_id=empresa.id,
        patente=f"O{token[:6].upper()}",
        peso_bruto_kg=Decimal("39000"),
        tara_kg=Decimal("9000"),
        capacidad_carga_kg=Decimal("30000"),
    )
    rampla = Rampla(
        empresa_id=empresa.id,
        patente=f"D{token[:6].upper()}",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal("30000"),
    )
    chofer = Chofer(
        empresa_id=empresa.id,
        rut=str(int(digitos) + 1),
        nombre=f"Chofer POD {sufijo}",
        numero_licencia=f"LIP-{token}",
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
        codigo=f"TP-{token}",
        nombre="Ruta POD",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        precio_unitario=Decimal("100000"),
    )
    oc = OrdenCompra(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_oc=f"OCP-{token}",
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        monto_autorizado=Decimal("1000000"),
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
        estado=estado,
        inicio_planificado=inicio,
        fin_planificado=inicio + timedelta(hours=5),
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


def test_pod_completo_y_gate_facturacion_en_postgresql():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.pod limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0009: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"POD-{sufijo}",
                razon_social=f"Empresa POD {sufijo}",
                rut=f"POD-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            viaje = _crear_viaje(session, empresa, sufijo, EstadoViaje.pod_pendiente)
            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.conductor
            )
            servicio = ServicioPOD(session, contexto)

            assert servicio.obtener(viaje.id) is None

            with pytest.raises(DatosInvalidos):
                servicio.crear(
                    viaje.id,
                    receptor_nombre="Receptor",
                    receptor_rut="11.111.111-1",
                    receptor_cargo="Jefe de bodega",
                    fecha_hora=None,
                    lat=Decimal("-33.45"),
                    lon=Decimal("-70.66"),
                    danios=None,
                    observaciones=None,
                    firma_nombre="firma.txt",
                    firma_contenido=b"no es imagen",
                    firma_content_type="text/plain",
                    fotos=[],
                )

            pod = servicio.crear(
                viaje.id,
                receptor_nombre="María Receptor",
                receptor_rut="11.111.111-1",
                receptor_cargo="Jefa de bodega",
                fecha_hora=None,
                lat=Decimal("-33.450000"),
                lon=Decimal("-70.660000"),
                danios="Sin daños visibles",
                observaciones="Entrega conforme",
                firma_nombre="firma.png",
                firma_contenido=PNG_FALSO,
                firma_content_type="image/png",
                fotos=[("evidencia.png", PNG_FALSO, "image/png")],
            )
            assert pod.receptor_nombre == "María Receptor"
            assert len(pod.fotos) == 1
            assert pod.firma_url_firmada
            assert pod.facturacion_habilitada is True

            with pytest.raises(ReglaNegocioViolada):
                servicio.crear(
                    viaje.id,
                    receptor_nombre="Otro",
                    receptor_rut=None,
                    receptor_cargo=None,
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

            with pytest.raises(ConflictoConcurrencia):
                servicio.actualizar(
                    viaje.id,
                    PODUpdate(
                        receptor_nombre="Cambio",
                        version=pod.version + 4,
                    ),
                )

            actualizado = servicio.actualizar(
                viaje.id,
                PODUpdate(
                    receptor_nombre="María Receptor Actualizada",
                    receptor_rut="11.111.111-1",
                    receptor_cargo="Jefa de bodega",
                    danios="Sin daños",
                    observaciones="Actualizado",
                    version=pod.version,
                ),
                fotos=[("evidencia2.png", PNG_FALSO, "image/png")],
            )
            assert actualizado.receptor_nombre.endswith("Actualizada")
            assert len(actualizado.fotos) == 2

            # Gate de facturación sin POD: un viaje cerrado no puede facturarse.
            viaje_sin_pod = _crear_viaje(
                session, empresa, f"{sufijo}X", EstadoViaje.cerrado
            )
            with pytest.raises(IntegrityError, match="sin POD"):
                session.execute(
                    text(
                        "update nucleo.viajes set estado = 'facturado' where id = :id"
                    ),
                    {"id": viaje_sin_pod.id},
                )
            session.rollback()
    finally:
        engine.dispose()
