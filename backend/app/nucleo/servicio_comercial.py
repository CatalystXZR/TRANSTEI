"""Servicio comercial del núcleo: tarifas, OC, líneas y centros de costo.

Reglas:
- Toda lectura/escritura se filtra por `empresa_id` del contexto.
- Los maestros comerciales no se borran: tarifas y centros se desactivan;
  las OC se anulan y las líneas se desactivan.
- El consumo de la OC lo mantiene PostgreSQL (`fn_oc_recalcular`). El servicio
  lo lee y explica; nunca confía en un saldo enviado por el frontend.
- El sobregiro es una decisión de gerencia: solicitarlo puede despacho,
  aprobarlo/rechazarlo solo admin o gerente.
- Toda escritura queda en `nucleo.auditoria`; el historial se expone aquí.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import func, or_, text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    AccesoDenegado,
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    traducir_integrity_error,
)
from app.nucleo.models import (
    Auditoria,
    CentroCosto,
    Cliente,
    EstadoOC,
    EstadoViaje,
    OrdenCompra,
    OrdenCompraLinea,
    RolEmpresa,
    Tarifa,
    Viaje,
)
from app.nucleo.schemas import (
    AprobacionSobregiro,
    CentroCostoCreate,
    CentroCostoOut,
    CentroCostoUpdate,
    ConsumoViajeOut,
    HistorialCambioOut,
    OrdenCompraCreate,
    OrdenCompraLineaCreate,
    OrdenCompraLineaOut,
    OrdenCompraLineaUpdate,
    OrdenCompraOut,
    OrdenCompraResumenOut,
    OrdenCompraUpdate,
    RechazoSobregiro,
    SolicitudSobregiro,
    TarifaCreate,
    TarifaOut,
    TarifaUpdate,
)
from app.nucleo.tiempo import ahora_utc, zona

CENTAVO = Decimal("0.01")
MILISIMA = Decimal("0.001")

ESTADOS_OC_CONSUMEN = [
    estado
    for estado in EstadoViaje
    if estado not in (EstadoViaje.borrador, EstadoViaje.cotizado, EstadoViaje.anulado)
]

ESTADOS_VIAJE_ACTIVOS = [
    EstadoViaje.confirmado,
    EstadoViaje.asignado,
    EstadoViaje.en_carga,
    EstadoViaje.cargado,
    EstadoViaje.en_ruta,
    EstadoViaje.en_descarga,
    EstadoViaje.descargado,
    EstadoViaje.pod_pendiente,
    EstadoViaje.cerrado,
]

ROLES_APRUEBAN_SOBREGIRO = {RolEmpresa.admin, RolEmpresa.gerente}


def _dinero(valor: Decimal | int | str | None) -> Decimal:
    return Decimal(valor or 0).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class ServicioComercial:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa
        self.tz = zona(self.empresa.zona_horaria)
        self.hoy = ahora_utc().astimezone(self.tz).date()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fijar_contexto_bd(self) -> None:
        self.session.execute(
            text("select set_config('nucleo.auth_id', :auth_id, true)"),
            {"auth_id": self.contexto.auth_id},
        )
        if self.contexto.request_id:
            self.session.execute(
                text("select set_config('nucleo.request_id', :request_id, true)"),
                {"request_id": self.contexto.request_id},
            )

    def _get(self, modelo, registro_id: UUID):
        obj = self.session.get(modelo, registro_id)
        if obj is None or obj.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Registro no encontrado en la empresa.")
        return obj

    def _cliente(self, cliente_id: UUID, *, exigir_activo: bool = True) -> Cliente:
        cliente = self.session.get(Cliente, cliente_id)
        if cliente is None or cliente.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Cliente no encontrado en la empresa.")
        if exigir_activo and not cliente.activo:
            raise DatosInvalidos("El cliente está inactivo.")
        return cliente

    def _centro(self, centro_id: UUID | None) -> CentroCosto | None:
        if centro_id is None:
            return None
        centro = self.session.get(CentroCosto, centro_id)
        if centro is None or centro.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Centro de costo no encontrado en la empresa.")
        if not centro.activo:
            raise DatosInvalidos("El centro de costo está inactivo.")
        return centro

    def _tarifa(self, tarifa_id: UUID | None) -> Tarifa | None:
        if tarifa_id is None:
            return None
        tarifa = self.session.get(Tarifa, tarifa_id)
        if tarifa is None or tarifa.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Tarifa no encontrada en la empresa.")
        return tarifa

    def _linea(self, oc: OrdenCompra, linea_id: UUID) -> OrdenCompraLinea:
        linea = self.session.get(OrdenCompraLinea, linea_id)
        if (
            linea is None
            or linea.empresa_id != self.empresa.id
            or linea.orden_compra_id != oc.id
        ):
            raise RecursoNoEncontrado("Línea de OC no encontrada.")
        return linea

    @staticmethod
    def _alerta(consumido: Decimal, total: Decimal) -> tuple[Decimal, str]:
        if total <= 0:
            return Decimal("0"), "normal"
        pct = (consumido / total * 100).quantize(Decimal("0.01"))
        if consumido > total:
            return pct, "sobregiro"
        if pct >= 100:
            return pct, "100"
        if pct >= 90:
            return pct, "90"
        if pct >= 80:
            return pct, "80"
        return pct, "normal"

    def _consumo_por_viajes(self, oc_id: UUID) -> tuple[Decimal, list[Viaje]]:
        viajes = self.session.exec(
            select(Viaje)
            .where(
                Viaje.empresa_id == self.empresa.id,
                Viaje.orden_compra_id == oc_id,
                Viaje.estado.not_in(
                    [EstadoViaje.borrador, EstadoViaje.cotizado, EstadoViaje.anulado]
                ),
            )
            .order_by(Viaje.inicio_planificado)
        ).all()
        total = sum((v.monto_total_neto or Decimal("0") for v in viajes), Decimal("0"))
        return _dinero(total), list(viajes)

    def _viaje_activo_con_tarifa(self, tarifa_id: UUID) -> Viaje | None:
        return self.session.exec(
            select(Viaje)
            .where(
                Viaje.empresa_id == self.empresa.id,
                Viaje.tarifa_id == tarifa_id,
                Viaje.estado.in_(ESTADOS_VIAJE_ACTIVOS),
            )
            .limit(1)
        ).first()

    # ------------------------------------------------------------------
    # Centros de costo
    # ------------------------------------------------------------------
    def listar_centros_costo(self, *, activo: bool | None = None) -> list[CentroCostoOut]:
        filtros = [CentroCosto.empresa_id == self.empresa.id]
        if activo is not None:
            filtros.append(CentroCosto.activo == activo)
        centros = self.session.exec(
            select(CentroCosto).where(*filtros).order_by(CentroCosto.codigo)
        ).all()
        return [
            CentroCostoOut(
                id=c.id,
                codigo=c.codigo,
                nombre=c.nombre,
                descripcion=c.descripcion,
                activo=c.activo,
                version=c.version,
            )
            for c in centros
        ]

    def crear_centro_costo(self, data: CentroCostoCreate) -> CentroCostoOut:
        self._fijar_contexto_bd()
        centro = CentroCosto(
            empresa_id=self.empresa.id,
            codigo=data.codigo.strip().upper(),
            nombre=data.nombre.strip(),
            descripcion=data.descripcion,
            activo=data.activo,
        )
        try:
            self.session.add(centro)
            self.session.commit()
            self.session.refresh(centro)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return CentroCostoOut(
            id=centro.id,
            codigo=centro.codigo,
            nombre=centro.nombre,
            descripcion=centro.descripcion,
            activo=centro.activo,
            version=centro.version,
        )

    def actualizar_centro_costo(
        self, centro_id: UUID, data: CentroCostoUpdate
    ) -> CentroCostoOut:
        centro = self._get(CentroCosto, centro_id)
        version = data.version if data.version is not None else centro.version
        if version != centro.version:
            raise ConflictoConcurrencia(
                "El centro de costo fue modificado por otro usuario. Recargue e intente nuevamente."
            )
        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                update(CentroCosto)
                .where(
                    CentroCosto.id == centro.id,
                    CentroCosto.empresa_id == self.empresa.id,
                    CentroCosto.version == version,
                )
                .values(
                    codigo=data.codigo.strip().upper(),
                    nombre=data.nombre.strip(),
                    descripcion=data.descripcion,
                    activo=data.activo,
                )
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "El centro de costo fue modificado por otro usuario."
                )
            self.session.commit()
            self.session.refresh(centro)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return CentroCostoOut(
            id=centro.id,
            codigo=centro.codigo,
            nombre=centro.nombre,
            descripcion=centro.descripcion,
            activo=centro.activo,
            version=centro.version,
        )

    def desactivar_centro_costo(self, centro_id: UUID) -> CentroCostoOut:
        centro = self._get(CentroCosto, centro_id)
        self._fijar_contexto_bd()
        self.session.execute(
            update(CentroCosto)
            .where(
                CentroCosto.id == centro.id,
                CentroCosto.empresa_id == self.empresa.id,
                CentroCosto.version == centro.version,
            )
            .values(activo=False)
        )
        self.session.commit()
        self.session.refresh(centro)
        return CentroCostoOut(
            id=centro.id,
            codigo=centro.codigo,
            nombre=centro.nombre,
            descripcion=centro.descripcion,
            activo=centro.activo,
            version=centro.version,
        )

    # ------------------------------------------------------------------
    # Tarifas
    # ------------------------------------------------------------------
    def _validar_tarifa(self, data: TarifaCreate) -> None:
        self._cliente(data.cliente_id)
        if data.vigencia_hasta is not None and data.vigencia_hasta < data.vigencia_desde:
            raise DatosInvalidos("La vigencia de la tarifa no es válida.")
        if data.moneda != self.empresa.moneda:
            raise DatosInvalidos(
                f"La tarifa debe estar en la moneda de la empresa ({self.empresa.moneda})."
            )

    def listar_tarifas(
        self,
        *,
        cliente_id: UUID | None = None,
        activo: bool | None = None,
        q: str | None = None,
        solo_vigentes: bool = False,
    ) -> list[TarifaOut]:
        filtros = [Tarifa.empresa_id == self.empresa.id]
        if cliente_id is not None:
            filtros.append(Tarifa.cliente_id == cliente_id)
        if activo is not None:
            filtros.append(Tarifa.activo == activo)
        if solo_vigentes:
            filtros.append(Tarifa.vigencia_desde <= self.hoy)
            filtros.append(
                or_(Tarifa.vigencia_hasta.is_(None), Tarifa.vigencia_hasta >= self.hoy)
            )
        if q and q.strip():
            patron = f"%{q.strip()}%"
            filtros.append(
                or_(
                    Tarifa.codigo.ilike(patron),
                    Tarifa.nombre.ilike(patron),
                    Tarifa.origen.ilike(patron),
                    Tarifa.destino.ilike(patron),
                )
            )
        tarifas = self.session.exec(
            select(Tarifa).where(*filtros).order_by(Tarifa.codigo)
        ).all()
        clientes = self._mapa_cliente([t.cliente_id for t in tarifas])
        conteos = self._conteo_viajes_por_tarifa([t.id for t in tarifas])
        return [
            self._tarifa_out(t, clientes.get(t.cliente_id), conteos.get(t.id, 0))
            for t in tarifas
        ]

    def _mapa_cliente(self, ids: Iterable[UUID]) -> dict[UUID, Cliente]:
        limpios = {i for i in ids if i is not None}
        if not limpios:
            return {}
        return {
            c.id: c
            for c in self.session.exec(
                select(Cliente).where(
                    Cliente.empresa_id == self.empresa.id, Cliente.id.in_(limpios)
                )
            ).all()
        }

    def _conteo_viajes_por_tarifa(self, ids: Iterable[UUID]) -> dict[UUID, int]:
        limpios = {i for i in ids if i is not None}
        if not limpios:
            return {}
        filas = self.session.exec(
            select(Viaje.tarifa_id, func.count(Viaje.id))
            .where(
                Viaje.empresa_id == self.empresa.id,
                Viaje.tarifa_id.in_(limpios),
                Viaje.estado.in_(ESTADOS_VIAJE_ACTIVOS),
            )
            .group_by(Viaje.tarifa_id)
        ).all()
        return {tarifa_id: int(total) for tarifa_id, total in filas if tarifa_id}

    def _tarifa_out(
        self, tarifa: Tarifa, cliente: Cliente | None, viajes_activos: int
    ) -> TarifaOut:
        vencida = bool(tarifa.vigencia_hasta and tarifa.vigencia_hasta < self.hoy)
        return TarifaOut(
            id=tarifa.id,
            cliente_id=tarifa.cliente_id,
            cliente_nombre=cliente.razon_social if cliente else "-",
            codigo=tarifa.codigo,
            nombre=tarifa.nombre,
            descripcion=tarifa.descripcion,
            modalidad=tarifa.modalidad,
            origen=tarifa.origen,
            destino=tarifa.destino,
            tipo_rampla=tarifa.tipo_rampla,
            tipo_carga=tarifa.tipo_carga,
            vigencia_desde=tarifa.vigencia_desde,
            vigencia_hasta=tarifa.vigencia_hasta,
            moneda=tarifa.moneda,
            precio_unitario=tarifa.precio_unitario,
            minimo_cobro=tarifa.minimo_cobro,
            incluye_peajes=tarifa.incluye_peajes,
            incluye_combustible=tarifa.incluye_combustible,
            precio_diesel_base=tarifa.precio_diesel_base,
            rendimiento_km_l=tarifa.rendimiento_km_l,
            participacion_combustible=tarifa.participacion_combustible,
            recargos=tarifa.recargos or {},
            condiciones=tarifa.condiciones or {},
            activo=tarifa.activo,
            vencida=vencida,
            viajes_activos=viajes_activos,
            version=tarifa.version,
            created_at=tarifa.created_at,
            updated_at=tarifa.updated_at,
        )

    def obtener_tarifa(self, tarifa_id: UUID) -> TarifaOut:
        tarifa = self._get(Tarifa, tarifa_id)
        cliente = self.session.get(Cliente, tarifa.cliente_id)
        conteos = self._conteo_viajes_por_tarifa([tarifa.id])
        return self._tarifa_out(tarifa, cliente, conteos.get(tarifa.id, 0))

    def crear_tarifa(self, data: TarifaCreate) -> TarifaOut:
        self._validar_tarifa(data)
        self._fijar_contexto_bd()
        tarifa = Tarifa(
            empresa_id=self.empresa.id,
            **data.model_dump(),
        )
        try:
            self.session.add(tarifa)
            self.session.commit()
            self.session.refresh(tarifa)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_tarifa(tarifa.id)

    def actualizar_tarifa(self, tarifa_id: UUID, data: TarifaUpdate) -> TarifaOut:
        tarifa = self._get(Tarifa, tarifa_id)
        version = data.version if data.version is not None else tarifa.version
        if version != tarifa.version:
            raise ConflictoConcurrencia(
                "La tarifa fue modificada por otro usuario. Recargue e intente nuevamente."
            )
        self._validar_tarifa(data)
        self._fijar_contexto_bd()
        valores = data.model_dump(exclude={"version"})
        try:
            resultado = self.session.execute(
                update(Tarifa)
                .where(
                    Tarifa.id == tarifa.id,
                    Tarifa.empresa_id == self.empresa.id,
                    Tarifa.version == version,
                )
                .values(**valores)
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "La tarifa fue modificada por otro usuario."
                )
            self.session.commit()
            self.session.refresh(tarifa)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_tarifa(tarifa.id)

    def desactivar_tarifa(self, tarifa_id: UUID) -> TarifaOut:
        tarifa = self._get(Tarifa, tarifa_id)
        viaje = self._viaje_activo_con_tarifa(tarifa.id)
        if viaje is not None:
            raise DatosInvalidos(
                f"La tarifa {tarifa.codigo} está siendo usada por el viaje "
                f"{viaje.numero_viaje or ''}; no se puede desactivar."
            )
        self._fijar_contexto_bd()
        self.session.execute(
            update(Tarifa)
            .where(
                Tarifa.id == tarifa.id,
                Tarifa.empresa_id == self.empresa.id,
                Tarifa.version == tarifa.version,
            )
            .values(activo=False)
        )
        self.session.commit()
        self.session.refresh(tarifa)
        return self.obtener_tarifa(tarifa.id)

    # ------------------------------------------------------------------
    # OC: lectura y presentación
    # ------------------------------------------------------------------
    def _mapa_centros(self, ids: Iterable[UUID | None]) -> dict[UUID, CentroCosto]:
        limpios = {i for i in ids if i is not None}
        if not limpios:
            return {}
        return {
            c.id: c
            for c in self.session.exec(
                select(CentroCosto).where(
                    CentroCosto.empresa_id == self.empresa.id,
                    CentroCosto.id.in_(limpios),
                )
            ).all()
        }

    @staticmethod
    def _linea_out(linea: OrdenCompraLinea) -> OrdenCompraLineaOut:
        return OrdenCompraLineaOut(
            id=linea.id,
            numero_linea=linea.numero_linea,
            descripcion=linea.descripcion,
            origen=linea.origen,
            destino=linea.destino,
            tarifa_id=linea.tarifa_id,
            centro_costo_id=linea.centro_costo_id,
            cantidad_estimada=linea.cantidad_estimada,
            unidad=linea.unidad,
            precio_unitario=linea.precio_unitario,
            monto_linea=linea.monto_linea,
            activa=linea.activa,
            version=linea.version,
        )

    def _oc_resumen(
        self,
        oc: OrdenCompra,
        cliente: Cliente | None,
        centro: CentroCosto | None,
        *,
        lineas_count: int,
        viajes_count: int,
    ) -> OrdenCompraResumenOut:
        total = _dinero(oc.monto_autorizado + oc.sobregiro_autorizado)
        consumido = _dinero(oc.monto_consumido)
        saldo = _dinero(total - consumido)
        pct, alerta = self._alerta(consumido, total)
        return OrdenCompraResumenOut(
            id=oc.id,
            cliente_id=oc.cliente_id,
            cliente_nombre=cliente.razon_social if cliente else "-",
            numero_oc=oc.numero_oc,
            referencia_interna=oc.referencia_interna,
            fecha_emision=oc.fecha_emision,
            vigencia_desde=oc.vigencia_desde,
            vigencia_hasta=oc.vigencia_hasta,
            monto_autorizado=oc.monto_autorizado,
            sobregiro_autorizado=oc.sobregiro_autorizado,
            monto_consumido=consumido,
            saldo_disponible=saldo,
            porcentaje_consumo=pct,
            alerta=alerta,
            moneda=oc.moneda,
            centro_costo_id=oc.centro_costo_id,
            centro_costo_nombre=centro.nombre if centro else oc.centro_costo,
            estado=oc.estado,
            vencida=oc.vigencia_hasta < self.hoy and oc.estado != EstadoOC.anulada,
            sobregiro_estado=oc.sobregiro_estado,
            sobregiro_solicitado=oc.sobregiro_solicitado,
            lineas_count=lineas_count,
            viajes_count=viajes_count,
            version=oc.version,
        )

    def listar_ocs(
        self,
        *,
        cliente_id: UUID | None = None,
        estado: EstadoOC | None = None,
        solo_con_saldo: bool = False,
        solo_alertas: bool = False,
        q: str | None = None,
    ) -> list[OrdenCompraResumenOut]:
        filtros = [OrdenCompra.empresa_id == self.empresa.id]
        if cliente_id is not None:
            filtros.append(OrdenCompra.cliente_id == cliente_id)
        if estado is not None:
            filtros.append(OrdenCompra.estado == estado)
        if q and q.strip():
            patron = f"%{q.strip()}%"
            filtros.append(
                or_(
                    OrdenCompra.numero_oc.ilike(patron),
                    OrdenCompra.referencia_interna.ilike(patron),
                )
            )
        ocs = self.session.exec(
            select(OrdenCompra)
            .where(*filtros)
            .order_by(OrdenCompra.vigencia_hasta, OrdenCompra.numero_oc)
        ).all()
        if not ocs:
            return []
        ids = [o.id for o in ocs]
        clientes = self._mapa_cliente([o.cliente_id for o in ocs])
        centros = self._mapa_centros([o.centro_costo_id for o in ocs])
        lineas = dict(
            self.session.exec(
                select(OrdenCompraLinea.orden_compra_id, func.count(OrdenCompraLinea.id))
                .where(
                    OrdenCompraLinea.empresa_id == self.empresa.id,
                    OrdenCompraLinea.orden_compra_id.in_(ids),
                    OrdenCompraLinea.activa == True,  # noqa: E712
                )
                .group_by(OrdenCompraLinea.orden_compra_id)
            ).all()
        )
        viajes = dict(
            self.session.exec(
                select(Viaje.orden_compra_id, func.count(Viaje.id))
                .where(
                    Viaje.empresa_id == self.empresa.id,
                    Viaje.orden_compra_id.in_(ids),
                    Viaje.estado.not_in(
                        [EstadoViaje.borrador, EstadoViaje.cotizado, EstadoViaje.anulado]
                    ),
                )
                .group_by(Viaje.orden_compra_id)
            ).all()
        )
        salida = [
            self._oc_resumen(
                oc,
                clientes.get(oc.cliente_id),
                centros.get(oc.centro_costo_id) if oc.centro_costo_id else None,
                lineas_count=int(lineas.get(oc.id, 0)),
                viajes_count=int(viajes.get(oc.id, 0)),
            )
            for oc in ocs
        ]
        if solo_con_saldo:
            salida = [o for o in salida if o.saldo_disponible > 0]
        if solo_alertas:
            salida = [o for o in salida if o.alerta in {"80", "90", "100", "sobregiro"}]
        return salida

    def obtener_oc(self, oc_id: UUID) -> OrdenCompraOut:
        oc = self._get(OrdenCompra, oc_id)
        cliente = self.session.get(Cliente, oc.cliente_id)
        centro = (
            self.session.get(CentroCosto, oc.centro_costo_id)
            if oc.centro_costo_id
            else None
        )
        lineas = self.session.exec(
            select(OrdenCompraLinea)
            .where(
                OrdenCompraLinea.empresa_id == self.empresa.id,
                OrdenCompraLinea.orden_compra_id == oc.id,
            )
            .order_by(OrdenCompraLinea.numero_linea)
        ).all()
        consumido, viajes = self._consumo_por_viajes(oc.id)
        total = _dinero(oc.monto_autorizado + oc.sobregiro_autorizado)
        pct, alerta = self._alerta(consumido, total)
        base = self._oc_resumen(
            oc,
            cliente,
            centro,
            lineas_count=sum(1 for linea in lineas if linea.activa),
            viajes_count=len(viajes),
        )
        return OrdenCompraOut(
            **base.model_dump(),
            proyecto=oc.proyecto,
            faena=oc.faena,
            condiciones_pago_dias=oc.condiciones_pago_dias,
            observaciones=oc.observaciones,
            sobregiro_motivo=oc.sobregiro_motivo,
            sobregiro_solicitado_por=oc.sobregiro_solicitado_por,
            sobregiro_solicitado_en=oc.sobregiro_solicitado_en,
            sobregiro_aprobado_por=oc.sobregiro_aprobado_por,
            sobregiro_aprobado_en=oc.sobregiro_aprobado_en,
            sobregiro_resolucion=oc.sobregiro_resolucion,
            lineas=[self._linea_out(linea) for linea in lineas],
            viajes=[
                ConsumoViajeOut(
                    id=viaje.id,
                    numero_viaje=viaje.numero_viaje or "",
                    estado=viaje.estado,
                    inicio_planificado=viaje.inicio_planificado,
                    monto=_dinero(viaje.monto_total_neto),
                    porcentaje_oc=(
                        (_dinero(viaje.monto_total_neto) / total * 100).quantize(
                            Decimal("0.01")
                        )
                        if total > 0
                        else Decimal("0")
                    ),
                )
                for viaje in viajes
            ],
            created_at=oc.created_at,
            updated_at=oc.updated_at,
        )

    # ------------------------------------------------------------------
    # OC: escritura
    # ------------------------------------------------------------------
    def _validar_linea(
        self, linea: OrdenCompraLineaCreate, cliente_id: UUID
    ) -> tuple[Decimal, CentroCosto | None]:
        if linea.cantidad_estimada <= 0:
            raise DatosInvalidos("La cantidad de la línea debe ser mayor que cero.")
        if linea.precio_unitario < 0:
            raise DatosInvalidos("El precio unitario no puede ser negativo.")
        if linea.tarifa_id is not None:
            tarifa = self._tarifa(linea.tarifa_id)
            if tarifa is not None and tarifa.cliente_id != cliente_id:
                raise DatosInvalidos(
                    f"La tarifa {tarifa.codigo} pertenece a otro cliente."
                )
        centro = self._centro(linea.centro_costo_id)
        monto = _dinero(linea.cantidad_estimada * linea.precio_unitario)
        return monto, centro

    def _validar_total_lineas(
        self,
        lineas: Iterable[OrdenCompraLineaCreate],
        cliente_id: UUID,
        monto_autorizado: Decimal,
    ) -> None:
        total = Decimal("0")
        for linea in lineas:
            monto, _ = self._validar_linea(linea, cliente_id)
            total += monto
        if total > monto_autorizado:
            raise DatosInvalidos(
                f"La suma de las líneas (${total:,.2f}) supera el monto autorizado "
                f"(${monto_autorizado:,.2f})."
            )

    def crear_oc(self, data: OrdenCompraCreate) -> OrdenCompraOut:
        self._cliente(data.cliente_id)
        centro = self._centro(data.centro_costo_id)
        if data.vigencia_hasta < data.vigencia_desde:
            raise DatosInvalidos("La vigencia de la OC no es válida.")
        if data.fecha_emision > data.vigencia_hasta:
            raise DatosInvalidos("La fecha de emisión no puede superar el fin de vigencia.")
        if data.moneda != self.empresa.moneda:
            raise DatosInvalidos(
                f"La OC debe estar en la moneda de la empresa ({self.empresa.moneda})."
            )
        if data.sobregiro_autorizado > 0 and self.contexto.rol not in ROLES_APRUEBAN_SOBREGIRO:
            raise AccesoDenegado(
                "Solo gerencia o administración puede crear una OC con sobregiro autorizado."
            )
        self._validar_total_lineas(data.lineas, data.cliente_id, data.monto_autorizado)

        self._fijar_contexto_bd()
        oc = OrdenCompra(
            empresa_id=self.empresa.id,
            cliente_id=data.cliente_id,
            numero_oc=data.numero_oc.strip(),
            referencia_interna=data.referencia_interna,
            fecha_emision=data.fecha_emision,
            vigencia_desde=data.vigencia_desde,
            vigencia_hasta=data.vigencia_hasta,
            monto_autorizado=data.monto_autorizado,
            sobregiro_autorizado=data.sobregiro_autorizado,
            moneda=data.moneda,
            centro_costo_id=centro.id if centro else None,
            centro_costo=centro.nombre if centro else None,
            proyecto=data.proyecto,
            faena=data.faena,
            condiciones_pago_dias=data.condiciones_pago_dias,
            observaciones=data.observaciones,
            estado=EstadoOC.abierta,
        )
        try:
            self.session.add(oc)
            self.session.flush()
            for indice, linea in enumerate(data.lineas, start=1):
                monto, centro_linea = self._validar_linea(linea, data.cliente_id)
                self.session.add(
                    OrdenCompraLinea(
                        empresa_id=self.empresa.id,
                        orden_compra_id=oc.id,
                        numero_linea=indice,
                        descripcion=linea.descripcion,
                        origen=linea.origen,
                        destino=linea.destino,
                        tarifa_id=linea.tarifa_id,
                        centro_costo_id=centro_linea.id if centro_linea else None,
                        cantidad_estimada=linea.cantidad_estimada,
                        unidad=linea.unidad,
                        precio_unitario=linea.precio_unitario,
                        monto_linea=monto,
                        activa=True,
                    )
                )
            self.session.commit()
            self.session.refresh(oc)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_oc(oc.id)

    def actualizar_oc(self, oc_id: UUID, data: OrdenCompraUpdate) -> OrdenCompraOut:
        oc = self._get(OrdenCompra, oc_id)
        if oc.estado == EstadoOC.anulada:
            raise ReglaNegocioViolada("Una OC anulada no se puede editar.")
        version = data.version if data.version is not None else oc.version
        if version != oc.version:
            raise ConflictoConcurrencia(
                "La OC fue modificada por otro usuario. Recargue e intente nuevamente."
            )

        valores: dict[str, Any] = {}
        for campo in (
            "referencia_interna",
            "fecha_emision",
            "vigencia_desde",
            "vigencia_hasta",
            "monto_autorizado",
            "moneda",
            "proyecto",
            "faena",
            "condiciones_pago_dias",
            "observaciones",
        ):
            valor = getattr(data, campo)
            if valor is not None:
                valores[campo] = valor
        if "moneda" in valores and valores["moneda"] != self.empresa.moneda:
            raise DatosInvalidos(
                f"La OC debe estar en la moneda de la empresa ({self.empresa.moneda})."
            )
        if data.centro_costo_id is not None:
            centro = self._centro(data.centro_costo_id)
            valores["centro_costo_id"] = centro.id if centro else None
            valores["centro_costo"] = centro.nombre if centro else None

        nuevo_inicio = valores.get("vigencia_desde", oc.vigencia_desde)
        nuevo_fin = valores.get("vigencia_hasta", oc.vigencia_hasta)
        nueva_emision = valores.get("fecha_emision", oc.fecha_emision)
        if nuevo_fin < nuevo_inicio:
            raise DatosInvalidos("La vigencia de la OC no es válida.")
        if nueva_emision > nuevo_fin:
            raise DatosInvalidos("La fecha de emisión no puede superar el fin de vigencia.")
        nuevo_monto = Decimal(valores.get("monto_autorizado", oc.monto_autorizado))
        if nuevo_monto + oc.sobregiro_autorizado < oc.monto_consumido:
            raise DatosInvalidos(
                "El monto autorizado no puede quedar bajo el consumo actual de la OC."
            )
        lineas_activas = self.session.exec(
            select(OrdenCompraLinea).where(
                OrdenCompraLinea.orden_compra_id == oc.id,
                OrdenCompraLinea.empresa_id == self.empresa.id,
                OrdenCompraLinea.activa == True,  # noqa: E712
            )
        ).all()
        total_lineas = sum((linea.monto_linea for linea in lineas_activas), Decimal("0"))
        if total_lineas > nuevo_monto:
            raise DatosInvalidos(
                "El monto autorizado no puede quedar bajo la suma de las líneas activas."
            )

        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                update(OrdenCompra)
                .where(
                    OrdenCompra.id == oc.id,
                    OrdenCompra.empresa_id == self.empresa.id,
                    OrdenCompra.version == version,
                )
                .values(**valores)
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia("La OC fue modificada por otro usuario.")
            self.session.commit()
            self.session.refresh(oc)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_oc(oc.id)

    def anular_oc(self, oc_id: UUID) -> OrdenCompraOut:
        oc = self._get(OrdenCompra, oc_id)
        if oc.estado == EstadoOC.anulada:
            return self.obtener_oc(oc.id)
        viaje = self.session.exec(
            select(Viaje)
            .where(
                Viaje.empresa_id == self.empresa.id,
                Viaje.orden_compra_id == oc.id,
                Viaje.estado.in_(ESTADOS_VIAJE_ACTIVOS),
            )
            .limit(1)
        ).first()
        if viaje is not None:
            raise DatosInvalidos(
                f"La OC {oc.numero_oc} tiene el viaje {viaje.numero_viaje or ''} activo; "
                "no se puede anular."
            )
        self._fijar_contexto_bd()
        self.session.execute(
            update(OrdenCompra)
            .where(
                OrdenCompra.id == oc.id,
                OrdenCompra.empresa_id == self.empresa.id,
                OrdenCompra.version == oc.version,
            )
            .values(estado=EstadoOC.anulada)
        )
        self.session.commit()
        self.session.refresh(oc)
        return self.obtener_oc(oc.id)

    # ------------------------------------------------------------------
    # Líneas de OC
    # ------------------------------------------------------------------
    def _suma_lineas_activas(self, oc_id: UUID) -> Decimal:
        total = self.session.exec(
            select(func.coalesce(func.sum(OrdenCompraLinea.monto_linea), 0)).where(
                OrdenCompraLinea.empresa_id == self.empresa.id,
                OrdenCompraLinea.orden_compra_id == oc_id,
                OrdenCompraLinea.activa == True,  # noqa: E712
            )
        ).one()
        return _dinero(Decimal(str(total)))

    def crear_linea_oc(
        self, oc_id: UUID, data: OrdenCompraLineaCreate
    ) -> OrdenCompraOut:
        oc = self._get(OrdenCompra, oc_id)
        if oc.estado == EstadoOC.anulada:
            raise ReglaNegocioViolada("Una OC anulada no admite líneas.")
        monto, centro = self._validar_linea(data, oc.cliente_id)
        if self._suma_lineas_activas(oc.id) + monto > oc.monto_autorizado:
            raise DatosInvalidos(
                "La nueva línea supera el monto autorizado de la OC. "
                "Solicite sobregiro o aumente el monto."
            )
        siguiente = (
            self.session.exec(
                select(func.coalesce(func.max(OrdenCompraLinea.numero_linea), 0)).where(
                    OrdenCompraLinea.orden_compra_id == oc.id
                )
            ).one()
            or 0
        )
        self._fijar_contexto_bd()
        try:
            self.session.add(
                OrdenCompraLinea(
                    empresa_id=self.empresa.id,
                    orden_compra_id=oc.id,
                    numero_linea=int(siguiente) + 1,
                    descripcion=data.descripcion,
                    origen=data.origen,
                    destino=data.destino,
                    tarifa_id=data.tarifa_id,
                    centro_costo_id=centro.id if centro else None,
                    cantidad_estimada=data.cantidad_estimada,
                    unidad=data.unidad,
                    precio_unitario=data.precio_unitario,
                    monto_linea=monto,
                    activa=True,
                )
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_oc(oc.id)

    def actualizar_linea_oc(
        self, oc_id: UUID, linea_id: UUID, data: OrdenCompraLineaUpdate
    ) -> OrdenCompraOut:
        oc = self._get(OrdenCompra, oc_id)
        if oc.estado == EstadoOC.anulada:
            raise ReglaNegocioViolada("Una OC anulada no admite cambios de líneas.")
        linea = self._linea(oc, linea_id)
        monto, centro = self._validar_linea(data, oc.cliente_id)
        suma_otras = self._suma_lineas_activas(oc.id) - (
            linea.monto_linea if linea.activa else Decimal("0")
        )
        if data.activa and suma_otras + monto > oc.monto_autorizado:
            raise DatosInvalidos(
                "La línea actualizada supera el monto autorizado de la OC."
            )
        version = data.version if data.version is not None else linea.version
        if version != linea.version:
            raise ConflictoConcurrencia(
                "La línea fue modificada por otro usuario. Recargue e intente nuevamente."
            )
        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                update(OrdenCompraLinea)
                .where(
                    OrdenCompraLinea.id == linea.id,
                    OrdenCompraLinea.empresa_id == self.empresa.id,
                    OrdenCompraLinea.version == version,
                )
                .values(
                    descripcion=data.descripcion,
                    origen=data.origen,
                    destino=data.destino,
                    tarifa_id=data.tarifa_id,
                    centro_costo_id=centro.id if centro else None,
                    cantidad_estimada=data.cantidad_estimada,
                    unidad=data.unidad,
                    precio_unitario=data.precio_unitario,
                    monto_linea=monto,
                    activa=data.activa,
                )
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia("La línea fue modificada por otro usuario.")
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_oc(oc.id)

    def desactivar_linea_oc(self, oc_id: UUID, linea_id: UUID) -> OrdenCompraOut:
        oc = self._get(OrdenCompra, oc_id)
        linea = self._linea(oc, linea_id)
        if not linea.activa:
            return self.obtener_oc(oc.id)
        self._fijar_contexto_bd()
        self.session.execute(
            update(OrdenCompraLinea)
            .where(
                OrdenCompraLinea.id == linea.id,
                OrdenCompraLinea.empresa_id == self.empresa.id,
                OrdenCompraLinea.version == linea.version,
            )
            .values(activa=False)
        )
        self.session.commit()
        return self.obtener_oc(oc.id)

    # ------------------------------------------------------------------
    # Sobregiro
    # ------------------------------------------------------------------
    def _validar_aprobador(self) -> None:
        if self.contexto.rol not in ROLES_APRUEBAN_SOBREGIRO:
            raise AccesoDenegado(
                "Solo gerencia o administración puede aprobar o rechazar un sobregiro.",
                contexto={"rol": self.contexto.rol.value},
            )

    def solicitar_sobregiro(
        self, oc_id: UUID, data: SolicitudSobregiro
    ) -> OrdenCompraOut:
        oc = self._get(OrdenCompra, oc_id)
        if oc.estado == EstadoOC.anulada:
            raise ReglaNegocioViolada("Una OC anulada no admite sobregiro.")
        if oc.sobregiro_estado == "pendiente":
            raise ReglaNegocioViolada(
                "Ya existe una solicitud de sobregiro pendiente para esta OC."
            )
        self._fijar_contexto_bd()
        self.session.execute(
            update(OrdenCompra)
            .where(
                OrdenCompra.id == oc.id,
                OrdenCompra.empresa_id == self.empresa.id,
                OrdenCompra.version == oc.version,
            )
            .values(
                sobregiro_estado="pendiente",
                sobregiro_solicitado=data.monto,
                sobregiro_motivo=data.motivo.strip(),
                sobregiro_solicitado_por=self.contexto.auth_id,
                sobregiro_solicitado_en=ahora_utc(),
                sobregiro_resolucion=None,
            )
        )
        self.session.commit()
        self.session.refresh(oc)
        return self.obtener_oc(oc.id)

    def aprobar_sobregiro(
        self, oc_id: UUID, data: AprobacionSobregiro
    ) -> OrdenCompraOut:
        self._validar_aprobador()
        oc = self._get(OrdenCompra, oc_id)
        if oc.sobregiro_estado != "pendiente":
            raise ReglaNegocioViolada("No hay una solicitud de sobregiro pendiente.")
        aprobado = data.monto if data.monto is not None else oc.sobregiro_solicitado
        if aprobado > oc.sobregiro_solicitado:
            raise DatosInvalidos(
                "El monto aprobado no puede superar el monto solicitado."
            )
        nuevo_sobregiro = oc.sobregiro_autorizado + aprobado
        self._fijar_contexto_bd()
        self.session.execute(
            update(OrdenCompra)
            .where(
                OrdenCompra.id == oc.id,
                OrdenCompra.empresa_id == self.empresa.id,
                OrdenCompra.version == oc.version,
            )
            .values(
                sobregiro_autorizado=nuevo_sobregiro,
                sobregiro_estado="aprobado",
                sobregiro_aprobado_por=self.contexto.auth_id,
                sobregiro_aprobado_en=ahora_utc(),
                sobregiro_resolucion=(
                    data.observacion.strip()
                    if data.observacion
                    else f"Sobregiro aprobado por ${aprobado:,.2f}"
                ),
            )
        )
        self.session.commit()
        self.session.refresh(oc)
        return self.obtener_oc(oc.id)

    def rechazar_sobregiro(
        self, oc_id: UUID, data: RechazoSobregiro
    ) -> OrdenCompraOut:
        self._validar_aprobador()
        oc = self._get(OrdenCompra, oc_id)
        if oc.sobregiro_estado != "pendiente":
            raise ReglaNegocioViolada("No hay una solicitud de sobregiro pendiente.")
        self._fijar_contexto_bd()
        self.session.execute(
            update(OrdenCompra)
            .where(
                OrdenCompra.id == oc.id,
                OrdenCompra.empresa_id == self.empresa.id,
                OrdenCompra.version == oc.version,
            )
            .values(
                sobregiro_estado="rechazado",
                sobregiro_aprobado_por=self.contexto.auth_id,
                sobregiro_aprobado_en=ahora_utc(),
                sobregiro_resolucion=data.motivo.strip(),
            )
        )
        self.session.commit()
        self.session.refresh(oc)
        return self.obtener_oc(oc.id)

    # ------------------------------------------------------------------
    # Historial (auditoría)
    # ------------------------------------------------------------------
    def _historial(
        self,
        tablas: list[str],
        registro_ids: list[UUID],
        *,
        limite: int = 100,
    ) -> list[HistorialCambioOut]:
        if not registro_ids:
            return []
        filas = self.session.exec(
            select(Auditoria)
            .where(
                Auditoria.empresa_id == self.empresa.id,
                Auditoria.tabla.in_(tablas),
                Auditoria.registro_id.in_(registro_ids),
            )
            .order_by(Auditoria.ocurrido_en.desc())
            .limit(limite)
        ).all()
        return [
            HistorialCambioOut(
                id=fila.id,
                tabla=fila.tabla,
                registro_id=fila.registro_id,
                operacion=fila.operacion,
                ocurrido_en=fila.ocurrido_en,
                auth_id=fila.auth_id,
                datos_antes=fila.datos_antes,
                datos_despues=fila.datos_despues,
            )
            for fila in filas
        ]

    def historial_tarifa(self, tarifa_id: UUID) -> list[HistorialCambioOut]:
        tarifa = self._get(Tarifa, tarifa_id)
        return self._historial(["nucleo.tarifas"], [tarifa.id])

    def historial_oc(self, oc_id: UUID) -> list[HistorialCambioOut]:
        oc = self._get(OrdenCompra, oc_id)
        lineas = self.session.exec(
            select(OrdenCompraLinea.id).where(
                OrdenCompraLinea.empresa_id == self.empresa.id,
                OrdenCompraLinea.orden_compra_id == oc.id,
            )
        ).all()
        return self._historial(
            ["nucleo.ordenes_compra", "nucleo.ordenes_compra_lineas"],
            [oc.id, *lineas],
        )
