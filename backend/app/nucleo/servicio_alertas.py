"""Alertas operativas y tablero del dueño (P0-11).

No crea una tabla de alertas: calcula el estado actual desde las fuentes de
verdad (documentos, agenda, viajes, POD, facturas, OC, costos y pagos). Así el
tablero nunca muestra una alerta resuelta como pendiente.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.models import (
    Chofer,
    Documento,
    EstadoViaje,
    FacturaViaje,
    OrdenCompra,
    PagoNucleo,
    POD,
    Rampla,
    ReservaRecurso,
    Tracto,
    TipoReserva,
    Viaje,
    ViajeGasto,
    ViajeIncidente,
)
from app.nucleo.schemas import (
    AccionTableroOut,
    AlertaOut,
    TableroKpisOut,
    TableroOut,
)
from app.nucleo.servicio_comercial import ServicioComercial
from app.nucleo.servicio_facturacion import ServicioFacturacion
from app.nucleo.tiempo import ahora_utc, zona

SEVERIDAD_ORDEN = {"critica": 0, "alta": 1, "media": 2, "baja": 3}
ESTADOS_ACTIVOS = [
    EstadoViaje.confirmado,
    EstadoViaje.asignado,
    EstadoViaje.en_carga,
    EstadoViaje.cargado,
    EstadoViaje.en_ruta,
    EstadoViaje.en_descarga,
    EstadoViaje.descargado,
    EstadoViaje.pod_pendiente,
]


class ServicioAlertas:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa
        self.tz = zona(self.empresa.zona_horaria)
        self.ahora = ahora_utc()
        self.hoy = self.ahora.astimezone(self.tz).date()

    # ------------------------------------------------------------------
    # Helpers de etiquetas
    # ------------------------------------------------------------------
    def _etiqueta_documento(self, doc: Documento) -> str:
        if doc.tracto_id:
            tracto = self.session.get(Tracto, doc.tracto_id)
            return f"Tracto {tracto.patente}" if tracto else "Tracto"
        if doc.rampla_id:
            rampla = self.session.get(Rampla, doc.rampla_id)
            return f"Rampla {rampla.patente}" if rampla else "Rampla"
        if doc.chofer_id:
            chofer = self.session.get(Chofer, doc.chofer_id)
            if chofer:
                return " ".join(
                    p
                    for p in [chofer.nombre, chofer.apellido_paterno]
                    if p
                ).strip()
            return "Chofer"
        return "Recurso"

    @staticmethod
    def _alerta(
        *,
        categoria: str,
        severidad: str,
        titulo: str,
        detalle: str,
        accion: str,
        link: str,
        entidad_tipo: str | None = None,
        entidad_id: str | None = None,
        fecha_referencia: str | None = None,
    ) -> AlertaOut:
        return AlertaOut(
            id=f"{categoria}:{entidad_tipo or '-'}:{entidad_id or '-'}:{titulo}",
            categoria=categoria,
            severidad=severidad,
            titulo=titulo,
            detalle=detalle,
            accion=accion,
            link=link,
            entidad_tipo=entidad_tipo,
            entidad_id=entidad_id,
            fecha_referencia=fecha_referencia,
        )

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------
    def tablero(self) -> TableroOut:
        alertas: list[AlertaOut] = []
        docs_count = 0
        mant_count = 0
        sin_pod = 0
        sin_facturar = 0
        oc_alertas = 0
        margen_scores: list[Decimal] = []

        # 1. Documentos por vencer o vencidos.
        limite = self.hoy + timedelta(days=self.empresa.dias_alerta_documentos)
        documentos = self.session.exec(
            select(Documento)
            .where(
                Documento.empresa_id == self.empresa.id,
                Documento.es_vigente == True,  # noqa: E712
                Documento.vence_en <= limite,
            )
            .order_by(Documento.vence_en)
            .limit(200)
        ).all()
        for doc in documentos:
            docs_count += 1
            dias = (doc.vence_en - self.hoy).days
            if dias < 0:
                severidad = "critica"
                titulo = f"Documento vencido: {doc.tipo.value}"
                detalle = f"{self._etiqueta_documento(doc)} · venció el {doc.vence_en} ({-dias} días)."
            elif dias <= 7:
                severidad = "alta"
                titulo = f"Documento por vencer: {doc.tipo.value}"
                detalle = f"{self._etiqueta_documento(doc)} · vence en {dias} día(s) el {doc.vence_en}."
            else:
                severidad = "media"
                titulo = f"Documento próximo a vencer: {doc.tipo.value}"
                detalle = f"{self._etiqueta_documento(doc)} · vence el {doc.vence_en}."
            alertas.append(
                self._alerta(
                    categoria="documentos",
                    severidad=severidad,
                    titulo=titulo,
                    detalle=detalle,
                    accion="Renovar o cargar el documento",
                    link="/maestros",
                    entidad_tipo=doc.recurso_tipo.value,
                    entidad_id=str(doc.tracto_id or doc.rampla_id or doc.chofer_id),
                    fecha_referencia=doc.vence_en.isoformat(),
                )
            )

        # 2. Mantenciones / bloqueos próximos (7 días).
        fin_mant = self.ahora + timedelta(days=7)
        bloques = self.session.exec(
            select(ReservaRecurso)
            .where(
                ReservaRecurso.empresa_id == self.empresa.id,
                ReservaRecurso.activa == True,  # noqa: E712
                ReservaRecurso.tipo_reserva == TipoReserva.mantenimiento,
                func.lower(ReservaRecurso.ventana) <= fin_mant,
                func.upper(ReservaRecurso.ventana) >= self.ahora,
            )
            .order_by(func.lower(ReservaRecurso.ventana))
            .limit(100)
        ).all()
        for bloqueo in bloques:
            mant_count += 1
            inicio = getattr(bloqueo.ventana, "lower", None)
            horas = (
                (inicio - self.ahora).total_seconds() / 3600 if inicio else 999
            )
            severidad = "alta" if horas <= 48 else "media"
            alertas.append(
                self._alerta(
                    categoria="mantencion",
                    severidad=severidad,
                    titulo="Mantención programada",
                    detalle=f"{bloqueo.motivo or 'Mantención'} · inicia {inicio.isoformat(timespec='minutes') if inicio else '—'}.",
                    accion="Revisar agenda y asignación",
                    link="/agenda",
                    entidad_tipo=bloqueo.recurso_tipo.value,
                    entidad_id=str(bloqueo.id),
                    fecha_referencia=inicio.isoformat() if inicio else None,
                )
            )

        # 3. Viajes sin POD.
        con_pod = select(POD.viaje_id).where(POD.empresa_id == self.empresa.id)
        sin_pod_viajes = self.session.exec(
            select(Viaje)
            .where(
                Viaje.empresa_id == self.empresa.id,
                Viaje.estado.in_([EstadoViaje.descargado, EstadoViaje.pod_pendiente]),
                Viaje.id.not_in(con_pod),
            )
            .order_by(Viaje.fin_planificado)
            .limit(100)
        ).all()
        for viaje in sin_pod_viajes:
            sin_pod += 1
            alertas.append(
                self._alerta(
                    categoria="pod",
                    severidad="alta",
                    titulo=f"Viaje {viaje.numero_viaje} sin POD",
                    detalle=f"{viaje.origen_nombre} → {viaje.destino_nombre}; no se puede facturar.",
                    accion="Capturar firma y evidencia",
                    link=f"/expediente/{viaje.id}",
                    entidad_tipo="viaje",
                    entidad_id=str(viaje.id),
                    fecha_referencia=viaje.fin_planificado.isoformat(),
                )
            )

        # 4. Viajes cerrados sin facturar.
        facturados = select(FacturaViaje.viaje_id).where(
            FacturaViaje.empresa_id == self.empresa.id
        )
        cerrados = self.session.exec(
            select(Viaje)
            .where(
                Viaje.empresa_id == self.empresa.id,
                Viaje.estado == EstadoViaje.cerrado,
                Viaje.id.not_in(facturados),
            )
            .order_by(Viaje.fin_real, Viaje.fin_planificado)
            .limit(100)
        ).all()
        for viaje in cerrados:
            sin_facturar += 1
            referencia = viaje.fin_real or viaje.fin_planificado
            dias = max(0, (self.hoy - referencia.astimezone(self.tz).date()).days)
            alertas.append(
                self._alerta(
                    categoria="facturacion",
                    severidad="alta" if dias >= 3 else "media",
                    titulo=f"Viaje {viaje.numero_viaje} cerrado sin facturar",
                    detalle=f"Cerrado hace {dias} día(s); flete {viaje.monto_total_neto or viaje.valor_flete_neto}.",
                    accion="Emitir factura",
                    link="/cobranza",
                    entidad_tipo="viaje",
                    entidad_id=str(viaje.id),
                    fecha_referencia=referencia.isoformat(),
                )
            )

        # 5. OC con alerta y sobregiros pendientes.
        comercial = ServicioComercial(self.session, self.contexto)
        for oc in comercial.listar_ocs(solo_alertas=True):
            oc_alertas += 1
            severidad = (
                "critica"
                if oc.alerta in {"100", "sobregiro"} or oc.vencida
                else "alta"
                if oc.alerta == "90"
                else "media"
            )
            alertas.append(
                self._alerta(
                    categoria="oc",
                    severidad=severidad,
                    titulo=f"OC {oc.numero_oc} al {oc.alerta}%",
                    detalle=(
                        f"Consumido ${oc.monto_consumido:,.0f} de ${oc.monto_autorizado:,.0f}; "
                        f"saldo ${oc.saldo_disponible:,.0f}."
                    ),
                    accion="Revisar consumo y solicitar sobregiro",
                    link="/comercial",
                    entidad_tipo="orden_compra",
                    entidad_id=str(oc.id),
                    fecha_referencia=oc.vigencia_hasta.isoformat(),
                )
            )
        pendientes = self.session.exec(
            select(OrdenCompra).where(
                OrdenCompra.empresa_id == self.empresa.id,
                OrdenCompra.sobregiro_estado == "pendiente",
            )
        ).all()
        for oc in pendientes:
            oc_alertas += 1
            alertas.append(
                self._alerta(
                    categoria="oc",
                    severidad="alta",
                    titulo=f"Sobregiro pendiente en OC {oc.numero_oc}",
                    detalle=f"Solicitado ${oc.sobregiro_solicitado:,.0f}: {oc.sobregiro_motivo or 'sin motivo'}.",
                    accion="Aprobar o rechazar",
                    link="/comercial",
                    entidad_tipo="orden_compra",
                    entidad_id=str(oc.id),
                )
            )

        # 6. CxC y aging.
        facturacion = ServicioFacturacion(self.session, self.contexto)
        aging = facturacion.aging()
        if aging.total_vencido > 0:
            mas_90 = next(
                (b.monto for b in aging.buckets if b.etiqueta == "> 90 días"),
                Decimal("0"),
            )
            alertas.append(
                self._alerta(
                    categoria="cxc",
                    severidad="critica" if mas_90 > 0 else "alta",
                    titulo="Cartera vencida",
                    detalle=f"${aging.total_vencido:,.0f} vencido de ${aging.total_cxc:,.0f} en CxC.",
                    accion="Gestionar cobranza y promesas",
                    link="/cobranza",
                    entidad_tipo="cartera",
                    fecha_referencia=self.hoy.isoformat(),
                )
            )

        # 7. Margen / Freight Score rojo.
        viajes_margen = self.session.exec(
            select(Viaje)
            .where(
                Viaje.empresa_id == self.empresa.id,
                Viaje.estado != EstadoViaje.anulado,
                Viaje.freight_score_estimado.is_not(None),
            )
            .order_by(Viaje.inicio_planificado.desc())
            .limit(200)
        ).all()
        for viaje in viajes_margen:
            if viaje.freight_score_estimado is not None:
                margen_scores.append(viaje.freight_score_estimado)
            if viaje.freight_score_estimado is not None and viaje.freight_score_estimado < 60:
                alertas.append(
                    self._alerta(
                        categoria="margen",
                        severidad=(
                            "critica"
                            if viaje.freight_score_estimado < 40
                            else "alta"
                        ),
                        titulo=f"Freight Score rojo en {viaje.numero_viaje}",
                        detalle=(
                            f"Score {viaje.freight_score_estimado}; "
                            f"flete ${viaje.monto_total_neto or viaje.valor_flete_neto:,.0f}."
                        ),
                        accion="Revisar tarifa, costos o retorno",
                        link=f"/expediente/{viaje.id}",
                        entidad_tipo="viaje",
                        entidad_id=str(viaje.id),
                        fecha_referencia=viaje.inicio_planificado.isoformat(),
                    )
                )

        # 8. Caja operativa de los últimos 30 días.
        desde = self.hoy - timedelta(days=30)
        ingresos = self.session.exec(
            select(func.coalesce(func.sum(PagoNucleo.monto), 0)).where(
                PagoNucleo.empresa_id == self.empresa.id,
                PagoNucleo.fecha >= desde,
            )
        ).one()
        gastos = self.session.exec(
            select(func.coalesce(func.sum(ViajeGasto.monto_neto), 0)).where(
                ViajeGasto.empresa_id == self.empresa.id,
                ViajeGasto.estado == "aprobado",
                ViajeGasto.fecha >= desde,
                ViajeGasto.activo == True,  # noqa: E712
            )
        ).one()
        caja = Decimal(str(ingresos or 0)) - Decimal(str(gastos or 0))
        if caja < 0:
            alertas.append(
                self._alerta(
                    categoria="caja",
                    severidad="critica",
                    titulo="Caja operativa negativa",
                    detalle=f"Cobros ${ingresos:,.0f} − gastos ${gastos:,.0f} = ${caja:,.0f} en 30 días.",
                    accion="Acelerar cobranza o revisar gastos",
                    link="/cobranza",
                )
            )

        # 9. Incidentes abiertos de alta severidad.
        incidentes = self.session.exec(
            select(ViajeIncidente).where(
                ViajeIncidente.empresa_id == self.empresa.id,
                ViajeIncidente.estado.in_(["abierto", "en_revision"]),
                ViajeIncidente.severidad.in_(["alta", "critica"]),
            )
        ).all()
        for incidente in incidentes:
            alertas.append(
                self._alerta(
                    categoria="incidente",
                    severidad="critica" if incidente.severidad == "critica" else "alta",
                    titulo=f"Incidente {incidente.severidad} abierto",
                    detalle=incidente.descripcion[:180],
                    accion="Resolver incidente",
                    link=f"/expediente/{incidente.viaje_id}",
                    entidad_tipo="viaje",
                    entidad_id=str(incidente.viaje_id),
                )
            )

        # KPIs y salud.
        viajes_activos = int(
            self.session.exec(
                select(func.count(Viaje.id)).where(
                    Viaje.empresa_id == self.empresa.id,
                    Viaje.estado.in_(ESTADOS_ACTIVOS),
                )
            ).one()
        )
        tractos_activos = int(
            self.session.exec(
                select(func.count(Tracto.id)).where(
                    Tracto.empresa_id == self.empresa.id,
                    Tracto.activo == True,  # noqa: E712
                )
            ).one()
        )
        tractos_disponibles = int(
            self.session.exec(
                select(func.count(Tracto.id)).where(
                    Tracto.empresa_id == self.empresa.id,
                    Tracto.activo == True,  # noqa: E712
                    Tracto.estado == "disponible",
                )
            ).one()
        )
        margen_promedio = (
            (sum(margen_scores) / len(margen_scores)).quantize(Decimal("0.01"))
            if margen_scores
            else None
        )
        conteo = {
            "critica": sum(1 for a in alertas if a.severidad == "critica"),
            "alta": sum(1 for a in alertas if a.severidad == "alta"),
            "media": sum(1 for a in alertas if a.severidad == "media"),
            "baja": sum(1 for a in alertas if a.severidad == "baja"),
        }
        kpis = TableroKpisOut(
            cxc_total=aging.total_cxc,
            cxc_vencido=aging.total_vencido,
            caja_operativa=caja.quantize(Decimal("0.01")),
            viajes_activos=viajes_activos,
            tractos_activos=tractos_activos,
            tractos_disponibles=tractos_disponibles,
            oc_con_alerta=oc_alertas,
            documentos_por_vencer=docs_count,
            mantenciones_proximas=mant_count,
            viajes_sin_pod=sin_pod,
            viajes_sin_facturar=sin_facturar,
            freight_score_promedio=margen_promedio,
            alertas_criticas=conteo["critica"],
            alertas_altas=conteo["alta"],
            alertas_medias=conteo["media"],
        )
        briefing: list[str] = []
        if conteo["critica"]:
            briefing.append(
                f"Resolver primero {conteo['critica']} alerta(s) crítica(s)."
            )
        if aging.total_vencido > 0:
            briefing.append(
                f"Cobrar ${aging.total_vencido:,.0f} vencidos de CxC."
            )
        if sin_pod:
            briefing.append(f"Capturar POD en {sin_pod} viaje(s) entregado(s).")
        if sin_facturar:
            briefing.append(f"Facturar {sin_facturar} viaje(s) cerrado(s).")
        if docs_count:
            briefing.append(f"Renovar {docs_count} documento(s) por vencer.")
        if mant_count:
            briefing.append(f"Revisar {mant_count} mantención(es) próxima(s).")
        if caja < 0:
            briefing.append("Caja operativa negativa: priorizar cobranza.")
        if not briefing:
            briefing.append("Sin acciones críticas: operación al día.")

        acciones = [
            AccionTableroOut(
                titulo="Ver alertas críticas",
                descripcion="Filtre el centro de alertas por severidad crítica.",
                link="/tablero",
                prioridad="critica" if conteo["critica"] else "media",
            ),
            AccionTableroOut(
                titulo="Gestionar cobranza",
                descripcion=f"CxC vencida: ${aging.total_vencido:,.0f}.",
                link="/cobranza",
                prioridad="alta" if aging.total_vencido > 0 else "baja",
            ),
            AccionTableroOut(
                titulo="Revisar OC",
                descripcion=f"{oc_alertas} OC con alerta o sobregiro.",
                link="/comercial",
                prioridad="alta" if oc_alertas else "baja",
            ),
            AccionTableroOut(
                titulo="Abrir agenda",
                descripcion=f"{mant_count} mantención(es) en los próximos 7 días.",
                link="/agenda",
                prioridad="media" if mant_count else "baja",
            ),
        ]

        alertas.sort(
            key=lambda a: (
                SEVERIDAD_ORDEN.get(a.severidad, 9),
                a.fecha_referencia or "",
            )
        )
        return TableroOut(
            generado_en=self.ahora,
            zona_horaria=self.empresa.zona_horaria,
            kpis=kpis,
            salud=conteo,
            alertas=alertas[:300],
            briefing=briefing,
            acciones=acciones,
            aging=aging,
        )
