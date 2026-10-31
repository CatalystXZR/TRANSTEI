"""Pruebas P0-10: facturación, pagos parciales, notas y aging."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine, select

from app.core.config import settings
from app.core.database import registrar_contexto_transaccion
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.errores import DatosInvalidos, ReglaNegocioViolada
from app.nucleo.models import (
    Chofer,
    Cliente,
    Documento,
    Empresa,
    EstadoViaje,
    FacturaNucleo,
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
    PromesaPagoCreate,
)
from app.nucleo.servicio_configuracion import ServicioConfiguracion
from app.nucleo.servicio_expediente import ServicioExpediente
from app.nucleo.servicio_facturacion import ServicioFacturacion, tasa_desde_porcentaje
from app.nucleo.servicio_pod import ServicioPOD
from contexto_helpers import contexto_de_prueba
from rut_helpers import rut_empresa

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


def _url_app() -> str:
    """DSN del rol de aplicación (`tei_app`), al que 0026 le da DML de configuración."""
    return (
        os.environ.get("NUCLEO_DATABASE_URL")
        or settings.NUCLEO_DATABASE_URL
        or _url()
    )


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


def _configurar_iva(empresa: Empresa, valor: int = 19) -> None:
    """Configura `iva_porcentaje` vigente para la empresa de prueba.

    Desde el fix de RET-04 la emisión exige `iva_porcentaje` configurado: no
    hay 19 % implícito. La migración 0026 sembró solo las empresas existentes
    al aplicarse; las que crea cada test son posteriores.

    La tabla 0026 solo da DML al rol de aplicación (`tei_app`); el rol
    privilegiado de las fixtures no tiene GRANT. Se escribe con el rol real y
    su contexto de empresa (RLS), igual que en `test_nucleo_ola_b_modulos.py`.
    """
    if (
        _url_app() == _url()
    ):  # pragma: no cover - entorno sin roles de 0020
        pytest.skip(
            "NUCLEO_DATABASE_URL no apunta a tei_app; no se puede configurar el "
            "IVA (0026 no da DML al rol privilegiado)"
        )
    contexto = contexto_de_prueba(
        ContextoEmpresa(
            auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.admin
        )
    )
    app_engine = registrar_contexto_transaccion(create_engine(_url_app(), future=True))
    try:
        with Session(app_engine) as app:
            ServicioConfiguracion(app, contexto).actualizar("iva_porcentaje", valor)
    finally:
        app_engine.dispose()


def _cerrar_viaje_con_pod(
    session: Session, contexto: ContextoEmpresa, viaje: Viaje
) -> None:
    """Deja un viaje cerrado y facturable: POD + checklist completo + cierre."""
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
                rut=rut_empresa(),
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)
            _configurar_iva(empresa, 19)

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


def test_crear_promesa_rechazo_db_traducido_409():
    """F-03: el commit de `crear_promesa` traduce IntegrityError → ErrorNucleo.

    La tabla de promesas no tiene unicidad natural (solo el check `monto > 0`
    como defensa de la base); se fuerza un 23514 saltando la validación Pydantic
    con `model_construct` para ejercer la traducción y verificar el rollback.
    """
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.promesas_pago_nucleo limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0013: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"PRO-{sufijo}",
                razon_social=f"Empresa Promesa {sufijo}",
                rut=rut_empresa(),
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)
            cliente = Cliente(
                empresa_id=empresa.id,
                razon_social=f"Cliente Promesa {sufijo}",
                rut=f"PRO-CLI-{sufijo}",
                dias_pago=30,
            )
            session.add(cliente)
            session.commit()
            session.refresh(cliente)
            factura = FacturaNucleo(
                empresa_id=empresa.id,
                numero_factura=f"FAC-{sufijo}",
                cliente_id=cliente.id,
                fecha_vencimiento=date.today() + timedelta(days=30),
                neto=Decimal("100000"),
                iva=Decimal("19000"),
                estado="emitida",
            )
            session.add(factura)
            session.commit()
            session.refresh(factura)

            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.contador
            )
            servicio = ServicioFacturacion(session, contexto)

            promesa = servicio.crear_promesa(
                factura.id,
                PromesaPagoCreate(
                    fecha_prometida=date.today() + timedelta(days=10),
                    monto=Decimal("50000"),
                    notas="Primera promesa",
                ),
            )
            assert len(promesa.promesas) == 1

            invalida = PromesaPagoCreate.model_construct(
                fecha_prometida=date.today() + timedelta(days=12),
                monto=Decimal("-1"),
                notas=None,
            )
            with pytest.raises(ReglaNegocioViolada) as info:
                servicio.crear_promesa(factura.id, invalida)
            assert info.value.status_code == 409
            assert info.value.codigo == "REGLA_NEGOCIO_VIOLADA"

            # El rollback dejó la sesión usable: una promesa válida posterior entra.
            otra = servicio.crear_promesa(
                factura.id,
                PromesaPagoCreate(
                    fecha_prometida=date.today() + timedelta(days=15),
                    monto=Decimal("10000"),
                ),
            )
            assert len(otra.promesas) == 2
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# RET-04 / F2: la tasa de IVA es de la empresa, no del request
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("porcentaje", "fraccion"),
    [
        (19, "0.1900"),
        (21, "0.2100"),
        (Decimal("19.5"), "0.1950"),
        (0, "0.0000"),
    ],
)
def test_tasa_desde_porcentaje_convierte_la_configuracion(porcentaje, fraccion):
    """Regla pura: `iva_porcentaje` (% en la config) → fracción del multiplicador."""
    assert tasa_desde_porcentaje(porcentaje) == Decimal(fraccion)


@pytest.mark.parametrize("valor", [-1, 101, "no-numero", None])
def test_tasa_desde_porcentaje_rechaza_valores_invalidos(valor):
    with pytest.raises(ReglaNegocioViolada) as info:
        tasa_desde_porcentaje(valor)
    assert info.value.status_code == 409
    assert info.value.codigo == "REGLA_NEGOCIO_VIOLADA"


def test_factura_usa_la_config_e_ignora_tasa_iva_del_request():
    """RET-04: una `tasa_iva` en el request no puede fijar el impuesto.

    La config vigente es 21 % — distinta del default histórico 19 % y de la
    fracción 0,10 enviada —, así que una factura con `tasa_iva` y otra sin el
    campo deben dar el **mismo** IVA: 21 % del neto.
    """
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.facturas_nucleo limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0013: {exc}")
            if (
                conn.execute(
                    text("select to_regclass('nucleo.configuracion_empresa')")
                ).scalar()
                is None
            ):  # pragma: no cover
                pytest.skip("Falta aplicar la migración 0026: no hay configuración")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"IVA-{sufijo}",
                razon_social=f"Empresa IVA {sufijo}",
                rut=rut_empresa(),
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.contador
            )
            _configurar_iva(empresa, 21)

            # La lectura de la config también funciona con el rol real de la
            # app (`tei_app`, RLS activo): es el camino de producción.
            app_engine = registrar_contexto_transaccion(
                create_engine(_url_app(), future=True)
            )
            try:
                with Session(app_engine) as app:
                    contexto_de_prueba(contexto)
                    assert ServicioFacturacion(
                        app, contexto
                    )._tasa_iva_vigente() == Decimal("0.2100")
            finally:
                app_engine.dispose()

            facturacion = ServicioFacturacion(session, contexto)

            viaje_a = _crear_viaje(session, empresa, f"{sufijo}a")
            _cerrar_viaje_con_pod(session, contexto, viaje_a)
            con_request = facturacion.crear_factura(
                FacturaCreate(
                    cliente_id=viaje_a.cliente_id,
                    viaje_ids=[viaje_a.id],
                    fecha_vencimiento=date.today() + timedelta(days=30),
                    tasa_iva=Decimal("10"),  # absurdo como fracción; se ignora
                )
            )

            viaje_b = _crear_viaje(session, empresa, f"{sufijo}b")
            _cerrar_viaje_con_pod(session, contexto, viaje_b)
            sin_request = facturacion.crear_factura(
                FacturaCreate(
                    cliente_id=viaje_b.cliente_id,
                    viaje_ids=[viaje_b.id],
                    fecha_vencimiento=date.today() + timedelta(days=30),
                )
            )

            assert con_request.neto == Decimal("100000.00")
            assert con_request.iva == Decimal("21000.00")  # 21 % de la config
            assert con_request.total == Decimal("121000.00")
            assert sin_request.iva == con_request.iva
            assert sin_request.total == con_request.total

            # El schema ya no propone una tasa por defecto (no hay 19 implícito).
            assert (
                FacturaCreate(
                    cliente_id=viaje_a.cliente_id,
                    viaje_ids=[viaje_a.id],
                    fecha_vencimiento=date.today(),
                ).model_dump()["tasa_iva"]
                is None
            )
    finally:
        engine.dispose()


def test_factura_sin_iva_configurado_falla_409_sin_efectos():
    """Fail-closed: sin `iva_porcentaje` vigente no se emite factura.

    No se inventa un 19 %: el error es de dominio (409) y ocurre antes de
    cualquier escritura, así que no queda factura ni cambia el estado del viaje.
    """
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.facturas_nucleo limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0013: {exc}")
            if (
                conn.execute(
                    text("select to_regclass('nucleo.configuracion_empresa')")
                ).scalar()
                is None
            ):  # pragma: no cover
                pytest.skip("Falta aplicar la migración 0026: no hay configuración")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"SINIVA-{sufijo}",
                razon_social=f"Empresa Sin IVA {sufijo}",
                rut=rut_empresa(),
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.contador
            )
            viaje = _crear_viaje(session, empresa, sufijo)
            _cerrar_viaje_con_pod(session, contexto, viaje)
            facturacion = ServicioFacturacion(session, contexto)

            with pytest.raises(ReglaNegocioViolada) as info:
                facturacion.crear_factura(
                    FacturaCreate(
                        cliente_id=viaje.cliente_id,
                        viaje_ids=[viaje.id],
                        fecha_vencimiento=date.today() + timedelta(days=30),
                        tasa_iva=Decimal("0.10"),  # tampoco sirve de sustituto
                    )
                )
            assert info.value.status_code == 409
            assert info.value.codigo == "REGLA_NEGOCIO_VIOLADA"
            assert info.value.contexto.get("clave") == "iva_porcentaje"
            assert "iva_porcentaje" in info.value.mensaje

            assert (
                session.exec(
                    select(FacturaNucleo).where(FacturaNucleo.empresa_id == empresa.id)
                ).all()
                == []
            )
            session.refresh(viaje)
            assert viaje.estado == EstadoViaje.cerrado
    finally:
        engine.dispose()
