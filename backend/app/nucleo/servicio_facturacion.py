"""Facturación y cobranza del núcleo (P0-10).

Sin DTE real: el folio se genera con `nucleo.siguiente_folio`. Una factura
agrupa viajes cerrados con POD y OC. PostgreSQL recalcula estado/saldo con
pagos y notas de crédito, y pasa los viajes a `cobrado` al pagarse.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func, text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    traducir_integrity_error,
)
from app.nucleo.models import (
    Cliente,
    EstadoViaje,
    FacturaNucleo,
    FacturaViaje,
    NotaCreditoNucleo,
    OrdenCompra,
    PagoNucleo,
    POD,
    PromesaPagoNucleo,
    Viaje,
    ViajeEvento,
)
from app.nucleo.schemas import (
    AgingBucketOut,
    AgingOut,
    FacturaCreate,
    FacturaOut,
    FacturaResumenOut,
    FacturaViajeOut,
    NotaCreditoCreate,
    NotaCreditoOut,
    PagoCreate,
    PagoOut,
    PromesaPagoCreate,
    PromesaPagoOut,
    ViajeFacturableOut,
)
from app.nucleo.tiempo import ahora_utc, zona

CENTAVO = Decimal("0.01")


def _d(valor: Decimal | int | str | None) -> Decimal:
    return Decimal(valor or 0).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class ServicioFacturacion:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa
        self.tz = zona(self.empresa.zona_horaria)
        self.hoy = ahora_utc().astimezone(self.tz).date()

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

    def _get_factura(self, factura_id: UUID) -> FacturaNucleo:
        factura = self.session.get(FacturaNucleo, factura_id)
        if factura is None or factura.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Factura no encontrada en la empresa.")
        return factura

    def _pagos_factura(self, factura_id: UUID) -> list[PagoNucleo]:
        return list(
            self.session.exec(
                select(PagoNucleo)
                .where(
                    PagoNucleo.empresa_id == self.empresa.id,
                    PagoNucleo.factura_id == factura_id,
                )
                .order_by(PagoNucleo.fecha, PagoNucleo.created_at)
            ).all()
        )

    def _notas_factura(self, factura_id: UUID) -> list[NotaCreditoNucleo]:
        return list(
            self.session.exec(
                select(NotaCreditoNucleo)
                .where(
                    NotaCreditoNucleo.empresa_id == self.empresa.id,
                    NotaCreditoNucleo.factura_id == factura_id,
                )
                .order_by(NotaCreditoNucleo.fecha)
            ).all()
        )

    def _promesas_factura(self, factura_id: UUID) -> list[PromesaPagoNucleo]:
        return list(
            self.session.exec(
                select(PromesaPagoNucleo)
                .where(
                    PromesaPagoNucleo.empresa_id == self.empresa.id,
                    PromesaPagoNucleo.factura_id == factura_id,
                )
                .order_by(PromesaPagoNucleo.fecha_prometida)
            ).all()
        )

    def _viajes_factura(self, factura_id: UUID) -> list[FacturaViaje]:
        return list(
            self.session.exec(
                select(FacturaViaje).where(
                    FacturaViaje.empresa_id == self.empresa.id,
                    FacturaViaje.factura_id == factura_id,
                )
            ).all()
        )

    def _saldos(self, factura_id: UUID) -> tuple[Decimal, Decimal, Decimal]:
        pagado = self.session.exec(
            select(func.coalesce(func.sum(PagoNucleo.monto), 0)).where(
                PagoNucleo.empresa_id == self.empresa.id,
                PagoNucleo.factura_id == factura_id,
            )
        ).one()
        notas = self.session.exec(
            select(func.coalesce(func.sum(NotaCreditoNucleo.monto), 0)).where(
                NotaCreditoNucleo.empresa_id == self.empresa.id,
                NotaCreditoNucleo.factura_id == factura_id,
                NotaCreditoNucleo.estado == "aplicada",
            )
        ).one()
        return _d(pagado), _d(notas), Decimal("0")

    @staticmethod
    def _aging(dias: int) -> str:
        if dias <= 0:
            return "por_vencer"
        if dias <= 30:
            return "0_30"
        if dias <= 60:
            return "31_60"
        if dias <= 90:
            return "61_90"
        return "mas_90"

    def _resumen(
        self,
        factura: FacturaNucleo,
        cliente: Cliente | None,
        oc: OrdenCompra | None,
        pagado: Decimal,
        notas: Decimal,
        viajes_count: int,
    ) -> FacturaResumenOut:
        total = _d(factura.total)
        saldo = _d(total - pagado - notas)
        dias_atraso = max(0, (self.hoy - factura.fecha_vencimiento).days)
        if saldo <= 0:
            dias_atraso = 0
        return FacturaResumenOut(
            id=factura.id,
            numero_factura=factura.numero_factura,
            cliente_id=factura.cliente_id,
            cliente_nombre=cliente.razon_social if cliente else "-",
            orden_compra_id=factura.orden_compra_id,
            oc_numero=oc.numero_oc if oc else None,
            fecha_emision=factura.fecha_emision,
            fecha_vencimiento=factura.fecha_vencimiento,
            moneda=factura.moneda,
            neto=_d(factura.neto),
            iva=_d(factura.iva),
            total=total,
            pagado=pagado,
            notas_credito=notas,
            saldo=saldo,
            estado=factura.estado,
            dias_atraso=dias_atraso,
            aging=self._aging(dias_atraso if saldo > 0 else -1),
            viajes_count=viajes_count,
            version=factura.version,
        )

    def listar_facturas(
        self,
        *,
        cliente_id: UUID | None = None,
        estado: str | None = None,
        solo_vencidas: bool = False,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FacturaResumenOut]:
        filtros = [FacturaNucleo.empresa_id == self.empresa.id]
        if cliente_id is not None:
            filtros.append(FacturaNucleo.cliente_id == cliente_id)
        if estado is not None:
            filtros.append(FacturaNucleo.estado == estado)
        if solo_vencidas:
            filtros.append(FacturaNucleo.fecha_vencimiento < self.hoy)
            filtros.append(FacturaNucleo.estado.not_in(["pagada", "anulada"]))
        if q and q.strip():
            patron = f"%{q.strip()}%"
            filtros.append(FacturaNucleo.numero_factura.ilike(patron))
        facturas = list(
            self.session.exec(
                select(FacturaNucleo)
                .where(*filtros)
                .order_by(FacturaNucleo.fecha_vencimiento, FacturaNucleo.numero_factura)
                .offset(offset)
                .limit(limit)
            ).all()
        )
        if not facturas:
            return []
        ids = [f.id for f in facturas]
        clientes = {
            c.id: c
            for c in self.session.exec(
                select(Cliente).where(
                    Cliente.empresa_id == self.empresa.id,
                    Cliente.id.in_({f.cliente_id for f in facturas}),
                )
            ).all()
        }
        ocs = {
            o.id: o
            for o in self.session.exec(
                select(OrdenCompra).where(
                    OrdenCompra.empresa_id == self.empresa.id,
                    OrdenCompra.id.in_(
                        {f.orden_compra_id for f in facturas if f.orden_compra_id}
                    ),
                )
            ).all()
        }
        pagos = dict(
            self.session.exec(
                select(PagoNucleo.factura_id, func.coalesce(func.sum(PagoNucleo.monto), 0))
                .where(
                    PagoNucleo.empresa_id == self.empresa.id,
                    PagoNucleo.factura_id.in_(ids),
                )
                .group_by(PagoNucleo.factura_id)
            ).all()
        )
        notas = dict(
            self.session.exec(
                select(
                    NotaCreditoNucleo.factura_id,
                    func.coalesce(func.sum(NotaCreditoNucleo.monto), 0),
                )
                .where(
                    NotaCreditoNucleo.empresa_id == self.empresa.id,
                    NotaCreditoNucleo.factura_id.in_(ids),
                    NotaCreditoNucleo.estado == "aplicada",
                )
                .group_by(NotaCreditoNucleo.factura_id)
            ).all()
        )
        viajes = dict(
            self.session.exec(
                select(FacturaViaje.factura_id, func.count(FacturaViaje.id))
                .where(
                    FacturaViaje.empresa_id == self.empresa.id,
                    FacturaViaje.factura_id.in_(ids),
                )
                .group_by(FacturaViaje.factura_id)
            ).all()
        )
        return [
            self._resumen(
                f,
                clientes.get(f.cliente_id),
                ocs.get(f.orden_compra_id) if f.orden_compra_id else None,
                _d(pagos.get(f.id, 0)),
                _d(notas.get(f.id, 0)),
                int(viajes.get(f.id, 0)),
            )
            for f in facturas
        ]

    def viajes_facturables(
        self,
        *,
        cliente_id: UUID | None = None,
        orden_compra_id: UUID | None = None,
    ) -> list[ViajeFacturableOut]:
        filtros = [
            Viaje.empresa_id == self.empresa.id,
            Viaje.estado == EstadoViaje.cerrado,
        ]
        if cliente_id is not None:
            filtros.append(Viaje.cliente_id == cliente_id)
        if orden_compra_id is not None:
            filtros.append(Viaje.orden_compra_id == orden_compra_id)
        viajes = list(
            self.session.exec(
                select(Viaje)
                .where(*filtros)
                .order_by(Viaje.fin_planificado.desc())
                .limit(300)
            ).all()
        )
        if not viajes:
            return []
        clientes = {
            c.id: c
            for c in self.session.exec(
                select(Cliente).where(
                    Cliente.empresa_id == self.empresa.id,
                    Cliente.id.in_({v.cliente_id for v in viajes}),
                )
            ).all()
        }
        ocs = {
            o.id: o
            for o in self.session.exec(
                select(OrdenCompra).where(
                    OrdenCompra.empresa_id == self.empresa.id,
                    OrdenCompra.id.in_(
                        {v.orden_compra_id for v in viajes if v.orden_compra_id}
                    ),
                )
            ).all()
        }
        facturados = {
            viaje_id
            for viaje_id in self.session.exec(
                select(FacturaViaje.viaje_id).where(
                    FacturaViaje.empresa_id == self.empresa.id,
                    FacturaViaje.viaje_id.in_([v.id for v in viajes]),
                )
            ).all()
        }
        con_pod = {
            viaje_id
            for viaje_id in self.session.exec(
                select(POD.viaje_id).where(
                    POD.empresa_id == self.empresa.id,
                    POD.viaje_id.in_([v.id for v in viajes]),
                )
            ).all()
        }
        salida: list[ViajeFacturableOut] = []
        for viaje in viajes:
            if viaje.id in facturados or viaje.orden_compra_id is None:
                continue
            monto = viaje.monto_total_neto
            if monto is None:
                monto = viaje.valor_flete_neto + viaje.monto_recargos
            cliente = clientes.get(viaje.cliente_id)
            oc = ocs.get(viaje.orden_compra_id) if viaje.orden_compra_id else None
            salida.append(
                ViajeFacturableOut(
                    viaje_id=viaje.id,
                    numero_viaje=viaje.numero_viaje or "",
                    cliente_id=viaje.cliente_id,
                    cliente_nombre=cliente.razon_social if cliente else "-",
                    orden_compra_id=viaje.orden_compra_id,
                    oc_numero=oc.numero_oc if oc else None,
                    fecha_inicio=viaje.inicio_planificado,
                    monto=_d(monto),
                    tiene_pod=viaje.id in con_pod,
                )
            )
        return salida

    def obtener_factura(self, factura_id: UUID) -> FacturaOut:
        factura = self._get_factura(factura_id)
        cliente = self.session.get(Cliente, factura.cliente_id)
        oc = (
            self.session.get(OrdenCompra, factura.orden_compra_id)
            if factura.orden_compra_id
            else None
        )
        pagos = self._pagos_factura(factura.id)
        notas = self._notas_factura(factura.id)
        promesas = self._promesas_factura(factura.id)
        links = self._viajes_factura(factura.id)
        viajes: list[FacturaViajeOut] = []
        for link in links:
            viaje = self.session.get(Viaje, link.viaje_id)
            if viaje is not None:
                viajes.append(
                    FacturaViajeOut(
                        viaje_id=viaje.id,
                        numero_viaje=viaje.numero_viaje or "",
                        estado=viaje.estado,
                        monto=_d(link.monto),
                        fecha_inicio=viaje.inicio_planificado,
                    )
                )
        pagado = _d(sum((p.monto for p in pagos), Decimal("0")))
        notas_total = _d(
            sum((n.monto for n in notas if n.estado == "aplicada"), Decimal("0"))
        )
        resumen = self._resumen(
            factura, cliente, oc, pagado, notas_total, len(links)
        )
        return FacturaOut(
            **resumen.model_dump(),
            observaciones=factura.observaciones,
            viajes=viajes,
            pagos=[
                PagoOut(
                    id=p.id,
                    factura_id=p.factura_id,
                    fecha=p.fecha,
                    monto=_d(p.monto),
                    metodo=p.metodo,
                    referencia=p.referencia,
                    observaciones=p.observaciones,
                    created_at=p.created_at,
                    created_by=p.created_by,
                )
                for p in pagos
            ],
            notas=[
                NotaCreditoOut(
                    id=n.id,
                    factura_id=n.factura_id,
                    numero=n.numero,
                    fecha=n.fecha,
                    monto=_d(n.monto),
                    motivo=n.motivo,
                    estado=n.estado,
                    created_at=n.created_at,
                )
                for n in notas
            ],
            promesas=[
                PromesaPagoOut(
                    id=p.id,
                    factura_id=p.factura_id,
                    fecha_prometida=p.fecha_prometida,
                    monto=_d(p.monto),
                    estado=p.estado,
                    notas=p.notas,
                    created_at=p.created_at,
                )
                for p in promesas
            ],
            created_at=factura.created_at,
            updated_at=factura.updated_at,
        )

    def _validar_viajes_facturables(
        self, data: FacturaCreate
    ) -> tuple[list[Viaje], OrdenCompra, Cliente]:
        cliente = self.session.get(Cliente, data.cliente_id)
        if cliente is None or cliente.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Cliente no encontrado en la empresa.")
        if not cliente.activo:
            raise DatosInvalidos("El cliente está inactivo; no se puede facturar.")
        viajes: list[Viaje] = []
        for viaje_id in data.viaje_ids:
            viaje = self.session.exec(
                select(Viaje).where(
                    Viaje.id == viaje_id, Viaje.empresa_id == self.empresa.id
                )
            ).first()
            if viaje is None:
                raise RecursoNoEncontrado(
                    f"Viaje {viaje_id} no encontrado en la empresa."
                )
            if viaje.cliente_id != cliente.id:
                raise DatosInvalidos(
                    f"El viaje {viaje.numero_viaje} pertenece a otro cliente."
                )
            if viaje.estado != EstadoViaje.cerrado:
                raise ReglaNegocioViolada(
                    f"El viaje {viaje.numero_viaje} está en {viaje.estado.value}; "
                    "solo se facturan viajes cerrados."
                )
            if viaje.orden_compra_id is None:
                raise ReglaNegocioViolada(
                    f"El viaje {viaje.numero_viaje} no tiene OC; no se puede facturar."
                )
            if not self.session.exec(
                select(POD.id).where(
                    POD.empresa_id == self.empresa.id, POD.viaje_id == viaje.id
                )
            ).first():
                raise ReglaNegocioViolada(
                    f"El viaje {viaje.numero_viaje} no tiene POD; no se puede facturar."
                )
            ya = self.session.exec(
                select(FacturaViaje.id).where(
                    FacturaViaje.empresa_id == self.empresa.id,
                    FacturaViaje.viaje_id == viaje.id,
                )
            ).first()
            if ya is not None:
                raise ReglaNegocioViolada(
                    f"El viaje {viaje.numero_viaje} ya está en otra factura."
                )
            viajes.append(viaje)
        ocs = {v.orden_compra_id for v in viajes}
        if len(ocs) != 1:
            raise DatosInvalidos("Todos los viajes deben pertenecer a la misma OC.")
        oc_id = ocs.pop()
        if data.orden_compra_id is not None and data.orden_compra_id != oc_id:
            raise DatosInvalidos("La OC indicada no coincide con la de los viajes.")
        oc = self.session.get(OrdenCompra, oc_id)
        if oc is None or oc.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("OC no encontrada en la empresa.")
        if oc.cliente_id != cliente.id:
            raise DatosInvalidos("La OC pertenece a otro cliente.")
        if oc.estado == "anulada":
            raise ReglaNegocioViolada("La OC está anulada.")
        if oc.moneda != self.empresa.moneda:
            raise DatosInvalidos("La moneda de la OC no coincide con la empresa.")
        return viajes, oc, cliente

    def crear_factura(self, data: FacturaCreate) -> FacturaOut:
        viajes, oc, _cliente = self._validar_viajes_facturables(data)
        neto = _d(
            sum(
                (
                    v.monto_total_neto
                    if v.monto_total_neto is not None
                    else (v.valor_flete_neto + v.monto_recargos)
                )
                for v in viajes
            )
        )
        if neto <= 0:
            raise DatosInvalidos("El neto de la factura debe ser mayor que cero.")
        iva = _d(neto * data.tasa_iva)
        estado_inicial = "vencida" if data.fecha_vencimiento < self.hoy else "emitida"
        self._fijar_contexto_bd()
        try:
            folio = self.session.execute(
                text(
                    "select nucleo.siguiente_folio(:empresa_id, 'FAC', :periodo)"
                ),
                {
                    "empresa_id": self.empresa.id,
                    "periodo": str(data.fecha_emision.year),
                },
            ).scalar_one()
            factura = FacturaNucleo(
                empresa_id=self.empresa.id,
                numero_factura=folio,
                cliente_id=data.cliente_id,
                orden_compra_id=oc.id,
                fecha_emision=data.fecha_emision,
                fecha_vencimiento=data.fecha_vencimiento,
                moneda=self.empresa.moneda,
                neto=neto,
                iva=iva,
                estado=estado_inicial,
                observaciones=data.observaciones,
            )
            self.session.add(factura)
            self.session.flush()
            for viaje in viajes:
                monto = _d(
                    viaje.monto_total_neto
                    if viaje.monto_total_neto is not None
                    else (viaje.valor_flete_neto + viaje.monto_recargos)
                )
                self.session.add(
                    FacturaViaje(
                        empresa_id=self.empresa.id,
                        factura_id=factura.id,
                        viaje_id=viaje.id,
                        monto=monto,
                    )
                )
                resultado = self.session.execute(
                    update(Viaje)
                    .where(
                        Viaje.id == viaje.id,
                        Viaje.empresa_id == self.empresa.id,
                        Viaje.version == viaje.version,
                    )
                    .values(estado=EstadoViaje.facturado)
                )
                if resultado.rowcount != 1:
                    raise ConflictoConcurrencia(
                        f"El viaje {viaje.numero_viaje} fue modificado por otro usuario."
                    )
                self.session.add(
                    ViajeEvento(
                        empresa_id=self.empresa.id,
                        viaje_id=viaje.id,
                        tipo="facturado",
                        descripcion=f"Facturado en {folio}",
                        ocurrido_en=ahora_utc(),
                        payload={"factura_id": str(factura.id), "numero": folio},
                        auth_id=self.contexto.auth_id,
                    )
                )
            self.session.commit()
            self.session.refresh(factura)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_factura(factura.id)

    def registrar_pago(self, factura_id: UUID, data: PagoCreate) -> FacturaOut:
        factura = self._get_factura(factura_id)
        if factura.estado == "anulada":
            raise ReglaNegocioViolada("La factura está anulada.")
        pagado, notas, _ = self._saldos(factura.id)
        saldo = _d(_d(factura.total) - pagado - notas)
        if saldo <= 0:
            raise ReglaNegocioViolada("La factura ya está pagada.")
        if data.monto > saldo:
            raise DatosInvalidos(
                f"El pago ${data.monto:,.2f} supera el saldo ${saldo:,.2f}."
            )
        self._fijar_contexto_bd()
        pago = PagoNucleo(
            empresa_id=self.empresa.id,
            factura_id=factura.id,
            fecha=data.fecha,
            monto=data.monto,
            metodo=data.metodo,
            referencia=data.referencia,
            observaciones=data.observaciones,
        )
        try:
            self.session.add(pago)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_factura(factura.id)

    def crear_nota_credito(
        self, factura_id: UUID, data: NotaCreditoCreate
    ) -> FacturaOut:
        factura = self._get_factura(factura_id)
        if factura.estado == "anulada":
            raise ReglaNegocioViolada("La factura está anulada.")
        pagado, notas, _ = self._saldos(factura.id)
        saldo = _d(_d(factura.total) - pagado - notas)
        if data.monto > saldo:
            raise DatosInvalidos(
                f"La nota de crédito ${data.monto:,.2f} supera el saldo ${saldo:,.2f}."
            )
        self._fijar_contexto_bd()
        try:
            folio = self.session.execute(
                text("select nucleo.siguiente_folio(:empresa_id, 'NC', :periodo)"),
                {
                    "empresa_id": self.empresa.id,
                    "periodo": str(data.fecha.year),
                },
            ).scalar_one()
            nota = NotaCreditoNucleo(
                empresa_id=self.empresa.id,
                factura_id=factura.id,
                numero=folio,
                fecha=data.fecha,
                monto=data.monto,
                motivo=data.motivo.strip(),
                estado="aplicada",
            )
            self.session.add(nota)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_factura(factura.id)

    def crear_promesa(
        self, factura_id: UUID, data: PromesaPagoCreate
    ) -> FacturaOut:
        factura = self._get_factura(factura_id)
        if factura.estado in {"pagada", "anulada"}:
            raise ReglaNegocioViolada("La factura no admite promesas de pago.")
        self._fijar_contexto_bd()
        promesa = PromesaPagoNucleo(
            empresa_id=self.empresa.id,
            factura_id=factura.id,
            fecha_prometida=data.fecha_prometida,
            monto=data.monto,
            estado="pendiente",
            notas=data.notas,
        )
        self.session.add(promesa)
        self.session.commit()
        return self.obtener_factura(factura.id)

    def aging(self) -> AgingOut:
        facturas = self.listar_facturas(limit=1000)
        abiertas = [f for f in facturas if f.saldo > 0 and f.estado != "anulada"]
        total = _d(sum((f.saldo for f in abiertas), Decimal("0")))
        vencido = _d(sum((f.saldo for f in abiertas if f.dias_atraso > 0), Decimal("0")))
        buckets = {
            "por_vencer": {"etiqueta": "Por vencer", "facturas": 0, "monto": Decimal("0")},
            "0_30": {"etiqueta": "0–30 días", "facturas": 0, "monto": Decimal("0")},
            "31_60": {"etiqueta": "31–60 días", "facturas": 0, "monto": Decimal("0")},
            "61_90": {"etiqueta": "61–90 días", "facturas": 0, "monto": Decimal("0")},
            "mas_90": {"etiqueta": "> 90 días", "facturas": 0, "monto": Decimal("0")},
        }
        for factura in abiertas:
            bucket = buckets.get(factura.aging)
            if bucket is None:
                continue
            bucket["facturas"] += 1
            bucket["monto"] += factura.saldo
        return AgingOut(
            total_cxc=total,
            total_vencido=vencido,
            facturas_abiertas=len(abiertas),
            buckets=[
                AgingBucketOut(
                    etiqueta=b["etiqueta"],
                    facturas=b["facturas"],
                    monto=_d(b["monto"]),
                )
                for b in buckets.values()
            ],
            mensaje=(
                f"{len(abiertas)} factura(s) abiertas; ${vencido:,.0f} vencido."
                if abiertas
                else "Sin facturas abiertas."
            ),
        )
