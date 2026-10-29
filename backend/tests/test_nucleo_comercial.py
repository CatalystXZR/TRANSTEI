"""Pruebas P0-03: tarifas, OC, líneas, consumo y sobregiro.

Unitarias: contratos Pydantic.
Integración: PostgreSQL local con migración 0005 aplicada.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.errores import (
    AccesoDenegado,
    ConflictoConcurrencia,
    DatosInvalidos,
    RegistroDuplicado,
)
from app.nucleo.models import Empresa, EstadoViaje, Viaje
from app.nucleo.schemas import (
    AprobacionSobregiro,
    CentroCostoCreate,
    ClienteCreateNucleo,
    OrdenCompraCreate,
    OrdenCompraLineaCreate,
    OrdenCompraLineaUpdate,
    OrdenCompraUpdate,
    SolicitudSobregiro,
    TarifaCreate,
    TarifaUpdate,
)
from app.nucleo.servicio_comercial import ServicioComercial
from app.nucleo.servicio_maestros import ServicioMaestros


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración comercial")
    return url


def test_schemas_comerciales_rechazan_datos_invalidos():
    with pytest.raises(ValidationError):
        TarifaCreate(
            cliente_id=uuid4(),
            codigo="T-1",
            nombre="Tarifa inválida",
            modalidad="viaje",
            vigencia_desde=date(2026, 2, 1),
            vigencia_hasta=date(2026, 1, 1),
            precio_unitario=Decimal("1000"),
        )
    with pytest.raises(ValidationError):
        OrdenCompraCreate(
            cliente_id=uuid4(),
            numero_oc="OC-X",
            vigencia_hasta=date(2026, 12, 31),
            monto_autorizado=Decimal("100000"),
            lineas=[
                OrdenCompraLineaCreate(
                    descripcion="Ruta",
                    cantidad_estimada=Decimal("2"),
                    precio_unitario=Decimal("80000"),
                )
            ],
        )
    with pytest.raises(ValidationError):
        SolicitudSobregiro(monto=Decimal("0"), motivo="Sobregiro urgente")


def test_flujo_comercial_completo_en_postgresql():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.centros_costo limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0005: {exc}")

        sufijo = uuid4().hex[:8]
        hoy = date.today()
        inicio = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=10)
        fin = inicio + timedelta(hours=4)

        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"COM-{sufijo}",
                razon_social=f"Empresa Comercial {sufijo}",
                rut=f"COM-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            contexto_despacho = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.despacho
            )
            contexto_gerente = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.gerente
            )
            maestros = ServicioMaestros(session, contexto_gerente)
            comercial = ServicioComercial(session, contexto_despacho)
            comercial_gerente = ServicioComercial(session, contexto_gerente)

            cliente = maestros.crear_cliente(
                ClienteCreateNucleo(
                    razon_social=f"Cliente {sufijo}", rut=f"CLI-{sufijo}"
                )
            )
            centro = comercial.crear_centro_costo(
                CentroCostoCreate(codigo=f"CC-{sufijo}", nombre="Operaciones norte")
            )
            assert centro.codigo == f"CC-{sufijo}".upper()
            with pytest.raises(RegistroDuplicado):
                comercial.crear_centro_costo(
                    CentroCostoCreate(codigo=f"CC-{sufijo}", nombre="Duplicado")
                )

            tarifa = comercial.crear_tarifa(
                TarifaCreate(
                    cliente_id=cliente.id,
                    codigo=f"TAR-{sufijo}",
                    nombre="Santiago - Concepción",
                    modalidad="viaje",
                    origen="Santiago",
                    destino="Concepción",
                    vigencia_desde=hoy,
                    vigencia_hasta=hoy + timedelta(days=365),
                    precio_unitario=Decimal("1000000"),
                    minimo_cobro=Decimal("100000"),
                )
            )
            assert tarifa.viajes_activos == 0
            with pytest.raises(ConflictoConcurrencia):
                comercial.actualizar_tarifa(
                    tarifa.id,
                    TarifaUpdate(
                        cliente_id=cliente.id,
                        codigo=f"TAR-{sufijo}",
                        nombre="Editada",
                        modalidad="viaje",
                        vigencia_desde=hoy,
                        precio_unitario=Decimal("1100000"),
                        version=tarifa.version + 5,
                    ),
                )

            oc = comercial.crear_oc(
                OrdenCompraCreate(
                    cliente_id=cliente.id,
                    numero_oc=f"OC-{sufijo}",
                    vigencia_desde=hoy,
                    vigencia_hasta=hoy + timedelta(days=180),
                    monto_autorizado=Decimal("1000000"),
                    centro_costo_id=centro.id,
                    lineas=[
                        OrdenCompraLineaCreate(
                            descripcion="Flete Santiago - Concepción",
                            cantidad_estimada=Decimal("1"),
                            precio_unitario=Decimal("800000"),
                            tarifa_id=tarifa.id,
                            centro_costo_id=centro.id,
                        )
                    ],
                )
            )
            assert oc.monto_consumido == Decimal("0")
            assert oc.alerta == "normal"
            assert len(oc.lineas) == 1
            assert oc.lineas[0].monto_linea == Decimal("800000.00")

            with pytest.raises(RegistroDuplicado):
                comercial.crear_oc(
                    OrdenCompraCreate(
                        cliente_id=cliente.id,
                        numero_oc=f"OC-{sufijo}",
                        vigencia_hasta=hoy + timedelta(days=30),
                        monto_autorizado=Decimal("500000"),
                    )
                )

            # Una línea que excede lo autorizado se rechaza.
            with pytest.raises(DatosInvalidos):
                comercial.crear_linea_oc(
                    oc.id,
                    OrdenCompraLineaCreate(
                        descripcion="Excedida",
                        cantidad_estimada=Decimal("1"),
                        precio_unitario=Decimal("500000"),
                    ),
                )

            # Consumo: viaje confirmado = 80 % de la OC.
            viaje = Viaje(
                empresa_id=empresa.id,
                cliente_id=cliente.id,
                orden_compra_id=oc.id,
                tarifa_id=tarifa.id,
                estado=EstadoViaje.confirmado,
                inicio_planificado=inicio,
                fin_planificado=fin,
                buffer_minutos=60,
                peso_bruto_kg=Decimal("20000"),
                origen_nombre="Santiago",
                destino_nombre="Concepción",
                valor_flete_neto=Decimal("800000"),
            )
            session.add(viaje)
            session.commit()
            resumen = comercial.obtener_oc(oc.id)
            assert resumen.monto_consumido == Decimal("800000.00")

            assert resumen.porcentaje_consumo == Decimal("80.00")
            assert resumen.alerta == "80"
            assert resumen.saldo_disponible == Decimal("200000.00")
            assert resumen.viajes[0].monto == Decimal("800000.00")

            # Desactivar la tarifa en uso por un viaje activo debe fallar.
            with pytest.raises(DatosInvalidos):
                comercial.desactivar_tarifa(tarifa.id)

            # Actualizar la OC a un monto inferior al consumo debe fallar.
            with pytest.raises(DatosInvalidos):
                comercial.actualizar_oc(
                    oc.id,
                    OrdenCompraUpdate(
                        monto_autorizado=Decimal("500000"), version=resumen.version
                    ),
                )

            # Despacho solicita sobregiro; despacho no puede aprobarlo.
            solicitud = comercial.solicitar_sobregiro(
                uc := oc.id,
                SolicitudSobregiro(
                    monto=Decimal("400000"), motivo="Carga adicional del cliente"
                ),
            )
            assert solicitud.sobregiro_estado == "pendiente"
            with pytest.raises(AccesoDenegado):
                comercial.aprobar_sobregiro(
                    uc, AprobacionSobregiro(monto=Decimal("400000"))
                )

            aprobada = comercial_gerente.aprobar_sobregiro(
                uc, AprobacionSobregiro(monto=Decimal("300000"), observacion="Aprobado")
            )
            assert aprobada.sobregiro_autorizado == Decimal("300000.00")
            assert aprobada.sobregiro_estado == "aprobado"
            assert aprobada.saldo_disponible == Decimal("500000.00")

            # La línea se desactiva, no se borra.
            linea = aprobada.lineas[0]
            actualizada = comercial.actualizar_linea_oc(
                oc.id,
                linea.id,
                OrdenCompraLineaUpdate(
                    descripcion=linea.descripcion,
                    cantidad_estimada=linea.cantidad_estimada,
                    precio_unitario=linea.precio_unitario,
                    tarifa_id=linea.tarifa_id,
                    centro_costo_id=linea.centro_costo_id,
                    activa=False,
                    version=linea.version,
                ),
            )
            assert actualizada.lineas[0].activa is False

            historial = comercial.historial_oc(oc.id)
            assert any(h.tabla == "nucleo.ordenes_compra" for h in historial)
            assert any(h.operacion == "INSERT" for h in historial)

            # Anular una OC con un viaje activo debe fallar.
            with pytest.raises(DatosInvalidos):
                comercial.anular_oc(oc.id)
    finally:
        engine.dispose()
