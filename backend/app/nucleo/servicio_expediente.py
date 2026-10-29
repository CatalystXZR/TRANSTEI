"""Expediente del viaje (P0-05).

Lee y escribe el detalle operativo del viaje: paradas, checklist, eventos,
incidentes, documentos y auditoría. El cierre exige checklist obligatorio
completo y ningún incidente alto/crítico abierto.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable
from uuid import UUID

import segno
from sqlalchemy import func, or_, text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    traducir_integrity_error,
)
from app.nucleo.models import (
    Auditoria,
    Chofer,
    Cliente,
    EstadoViaje,
    FacturaViaje,
    OrdenCompra,
    Rampla,
    Tarifa,
    Tracto,
    Viaje,
    ViajeChecklist,
    ViajeDocumento,
    ViajeEvento,
    ViajeIncidente,
    ViajeParada,
)
from app.nucleo.schemas import (
    ChecklistItemCreate,
    ChecklistItemOut,
    ChecklistItemUpdate,
    CerrarViaje,
    EventoCreate,
    EventoOut,
    HistorialCambioOut,
    IncidenteCreate,
    IncidenteOut,
    IncidenteUpdate,
    ListaExpedienteOut,
    ParadaCreate,
    ParadaOut,
    ParadaUpdate,
    ResumenExpedienteOut,
    ViajeDocumentoOut,
    ViajeExpedienteOut,
    ViajeExpedienteResumenOut,
)
from app.nucleo.storage import (
    eliminar_archivo,
    ruta_archivo,
    subir_archivo,
    url_firmada,
    validar_archivo,
)
from app.nucleo.servicio_pod import ServicioPOD
from app.nucleo.servicio_facturacion import ServicioFacturacion
from app.nucleo.servicio_gastos import ServicioGastos
from app.nucleo.tiempo import ahora_utc

ESTADOS_EDITABLES = {
    EstadoViaje.borrador,
    EstadoViaje.cotizado,
    EstadoViaje.confirmado,
    EstadoViaje.asignado,
    EstadoViaje.en_carga,
    EstadoViaje.cargado,
    EstadoViaje.en_ruta,
    EstadoViaje.en_descarga,
    EstadoViaje.descargado,
    EstadoViaje.pod_pendiente,
}
ESTADOS_CIERRE = {EstadoViaje.descargado, EstadoViaje.pod_pendiente}
ESTADOS_INCIDENTE_ABIERTO = {"abierto", "en_revision"}
SEVERIDADES_BLOQUEANTES = {"alta", "critica"}

TIPOS_PARADA = {"origen", "carga", "descarga", "intermedia", "devolucion"}
ESTADOS_PARADA = {"pendiente", "en_curso", "completada", "omitida"}


class ServicioExpediente:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa

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

    def _get_viaje(self, viaje_id: UUID, *, lock: bool = False) -> Viaje:
        stmt = select(Viaje).where(
            Viaje.id == viaje_id, Viaje.empresa_id == self.empresa.id
        )
        if lock:
            stmt = stmt.with_for_update()
        viaje = self.session.exec(stmt).first()
        if viaje is None:
            raise RecursoNoEncontrado(
                "Viaje no encontrado en la empresa.",
                contexto={"viaje_id": str(viaje_id)},
            )
        return viaje

    def _etiqueta_chofer(self, chofer: Chofer | None) -> str | None:
        if chofer is None:
            return None
        partes = [chofer.nombre, chofer.apellido_paterno, chofer.apellido_materno]
        return " ".join(p for p in partes if p).strip()

    def _qr_data_uri(self, viaje: Viaje) -> str:
        contenido = (
            f"{settings.FRONTEND_URL.rstrip('/')}/expediente/{viaje.id}"
            f"?viaje={viaje.numero_viaje}"
        )
        qr = segno.make(contenido, error="m")
        buffer = io.BytesIO()
        qr.save(buffer, kind="png", scale=6, border=2)
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    def _historial(
        self, tablas: list[str], ids: Iterable[UUID], *, limite: int = 120
    ) -> list[HistorialCambioOut]:
        limpios = [i for i in ids if i is not None]
        if not limpios:
            return []
        filas = self.session.exec(
            select(Auditoria)
            .where(
                Auditoria.empresa_id == self.empresa.id,
                Auditoria.tabla.in_(tablas),
                Auditoria.registro_id.in_(limpios),
            )
            .order_by(Auditoria.ocurrido_en.desc())
            .limit(limite)
        ).all()
        return [
            HistorialCambioOut(
                id=f.id,
                tabla=f.tabla,
                registro_id=f.registro_id,
                operacion=f.operacion,
                ocurrido_en=f.ocurrido_en,
                auth_id=f.auth_id,
                datos_antes=f.datos_antes,
                datos_despues=f.datos_despues,
            )
            for f in filas
        ]

    @staticmethod
    def _parada_out(parada: ViajeParada) -> ParadaOut:
        return ParadaOut(
            id=parada.id,
            orden=parada.orden,
            tipo=parada.tipo,
            nombre=parada.nombre,
            direccion=parada.direccion,
            comuna=parada.comuna,
            ciudad=parada.ciudad,
            contacto_nombre=parada.contacto_nombre,
            contacto_telefono=parada.contacto_telefono,
            ventana_desde=parada.ventana_desde,
            ventana_hasta=parada.ventana_hasta,
            estado=parada.estado,
            notas=parada.notas,
            activo=parada.activo,
            version=parada.version,
        )

    @staticmethod
    def _checklist_out(item: ViajeChecklist) -> ChecklistItemOut:
        return ChecklistItemOut(
            id=item.id,
            orden=item.orden,
            categoria=item.categoria,
            item=item.item,
            requerido=item.requerido,
            completado=item.completado,
            completado_por=item.completado_por,
            completado_en=item.completado_en,
            evidencia_url=item.evidencia_url,
            notas=item.notas,
            version=item.version,
        )

    @staticmethod
    def _evento_out(evento: ViajeEvento) -> EventoOut:
        return EventoOut(
            id=evento.id,
            tipo=evento.tipo,
            descripcion=evento.descripcion,
            ocurrido_en=evento.ocurrido_en,
            payload=evento.payload or {},
            auth_id=evento.auth_id,
        )

    @staticmethod
    def _incidente_out(incidente: ViajeIncidente) -> IncidenteOut:
        return IncidenteOut(
            id=incidente.id,
            tipo=incidente.tipo,
            severidad=incidente.severidad,
            descripcion=incidente.descripcion,
            estado=incidente.estado,
            ocurrido_en=incidente.ocurrido_en,
            reportado_por=incidente.reportado_por,
            resolucion=incidente.resolucion,
            resuelto_por=incidente.resuelto_por,
            resuelto_en=incidente.resuelto_en,
            version=incidente.version,
        )

    def _documento_out(self, doc: ViajeDocumento) -> ViajeDocumentoOut:
        signed: str | None = None
        try:
            signed = url_firmada(doc.archivo_url)
        except Exception:
            signed = None
        return ViajeDocumentoOut(
            id=doc.id,
            tipo=doc.tipo,
            nombre=doc.nombre,
            archivo_url=doc.archivo_url,
            hash_sha256=doc.hash_sha256,
            content_type=doc.content_type,
            tamano_bytes=doc.tamano_bytes,
            observaciones=doc.observaciones,
            activo=doc.activo,
            created_at=doc.created_at,
            url_firmada=signed,
        )

    # ------------------------------------------------------------------
    # Resumen y cierre
    # ------------------------------------------------------------------
    def _resumen(self, viaje: Viaje) -> ResumenExpedienteOut:
        checklist = self.session.exec(
            select(ViajeChecklist).where(
                ViajeChecklist.empresa_id == self.empresa.id,
                ViajeChecklist.viaje_id == viaje.id,
            )
        ).all()
        paradas = self.session.exec(
            select(ViajeParada).where(
                ViajeParada.empresa_id == self.empresa.id,
                ViajeParada.viaje_id == viaje.id,
                ViajeParada.activo == True,  # noqa: E712
            )
        ).all()
        incidentes = self.session.exec(
            select(ViajeIncidente).where(
                ViajeIncidente.empresa_id == self.empresa.id,
                ViajeIncidente.viaje_id == viaje.id,
            )
        ).all()
        documentos = self.session.exec(
            select(ViajeDocumento).where(
                ViajeDocumento.empresa_id == self.empresa.id,
                ViajeDocumento.viaje_id == viaje.id,
                ViajeDocumento.activo == True,  # noqa: E712
            )
        ).all()

        total = len(checklist)
        completados = sum(1 for item in checklist if item.completado)
        requeridos_pendientes = sum(
            1 for item in checklist if item.requerido and not item.completado
        )
        incidentes_abiertos = sum(
            1 for i in incidentes if i.estado in ESTADOS_INCIDENTE_ABIERTO
        )
        incidentes_bloqueantes = sum(
            1
            for i in incidentes
            if i.estado in ESTADOS_INCIDENTE_ABIERTO
            and i.severidad in SEVERIDADES_BLOQUEANTES
        )
        motivos: list[str] = []
        if viaje.estado not in ESTADOS_CIERRE:
            motivos.append(
                "El viaje debe estar descargado o con POD pendiente para cerrarse."
            )
        if requeridos_pendientes:
            motivos.append(
                f"Faltan {requeridos_pendientes} ítem(s) obligatorios del checklist."
            )
        if incidentes_bloqueantes:
            motivos.append(
                f"Hay {incidentes_bloqueantes} incidente(s) alto/crítico abiertos."
            )
        return ResumenExpedienteOut(
            checklist_total=total,
            checklist_completados=completados,
            checklist_requeridos_pendientes=requeridos_pendientes,
            paradas_total=len(paradas),
            paradas_completadas=sum(
                1 for p in paradas if p.estado in {"completada", "omitida"}
            ),
            incidentes_abiertos=incidentes_abiertos,
            documentos_count=len(documentos),
            progreso_pct=(
                (Decimal(completados) / Decimal(total) * 100).quantize(
                    Decimal("0.01")
                )
                if total
                else Decimal("0")
            ),
            puede_cerrar=not motivos,
            motivos_cierre=motivos,
        )

    def _agregar_evento(
        self,
        viaje: Viaje,
        tipo: str,
        descripcion: str,
        *,
        payload: dict[str, Any] | None = None,
        ocurrido_en: datetime | None = None,
    ) -> None:
        self.session.add(
            ViajeEvento(
                empresa_id=self.empresa.id,
                viaje_id=viaje.id,
                tipo=tipo,
                descripcion=descripcion,
                ocurrido_en=ocurrido_en or ahora_utc(),
                payload=payload or {},
                auth_id=self.contexto.auth_id,
            )
        )

    # ------------------------------------------------------------------
    # Listado y detalle
    # ------------------------------------------------------------------
    def listar_viajes(
        self,
        *,
        estado: EstadoViaje | None = None,
        cliente_id: UUID | None = None,
        q: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ListaExpedienteOut:
        filtros = [Viaje.empresa_id == self.empresa.id]
        if estado is not None:
            filtros.append(Viaje.estado == estado)
        if cliente_id is not None:
            filtros.append(Viaje.cliente_id == cliente_id)
        if q and q.strip():
            patron = f"%{q.strip()}%"
            filtros.append(
                or_(
                    Viaje.numero_viaje.ilike(patron),
                    Viaje.origen_nombre.ilike(patron),
                    Viaje.destino_nombre.ilike(patron),
                    Viaje.oc_numero_snapshot.ilike(patron),
                )
            )
        if desde is not None:
            filtros.append(Viaje.inicio_planificado >= desde)
        if hasta is not None:
            filtros.append(Viaje.inicio_planificado <= hasta)

        total = int(self.session.exec(select(func.count(Viaje.id)).where(*filtros)).one())
        viajes = self.session.exec(
            select(Viaje)
            .where(*filtros)
            .order_by(Viaje.inicio_planificado.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        if not viajes:
            return ListaExpedienteOut(
                items=[], total=total, limit=limit, offset=offset, hay_mas=False
            )
        ids = [v.id for v in viajes]
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
        tarifas = {
            t.id: t
            for t in self.session.exec(
                select(Tarifa).where(
                    Tarifa.empresa_id == self.empresa.id,
                    Tarifa.id.in_({v.tarifa_id for v in viajes if v.tarifa_id}),
                )
            ).all()
        }
        tractos = {
            t.id: t
            for t in self.session.exec(
                select(Tracto).where(
                    Tracto.empresa_id == self.empresa.id,
                    Tracto.id.in_({v.tracto_id for v in viajes if v.tracto_id}),
                )
            ).all()
        }
        ramplas = {
            r.id: r
            for r in self.session.exec(
                select(Rampla).where(
                    Rampla.empresa_id == self.empresa.id,
                    Rampla.id.in_({v.rampla_id for v in viajes if v.rampla_id}),
                )
            ).all()
        }
        choferes = {
            c.id: c
            for c in self.session.exec(
                select(Chofer).where(
                    Chofer.empresa_id == self.empresa.id,
                    Chofer.id.in_({v.chofer_id for v in viajes if v.chofer_id}),
                )
            ).all()
        }

        checklist_total = dict(
            self.session.exec(
                select(ViajeChecklist.viaje_id, func.count(ViajeChecklist.id))
                .where(
                    ViajeChecklist.empresa_id == self.empresa.id,
                    ViajeChecklist.viaje_id.in_(ids),
                )
                .group_by(ViajeChecklist.viaje_id)
            ).all()
        )
        checklist_ok = dict(
            self.session.exec(
                select(ViajeChecklist.viaje_id, func.count(ViajeChecklist.id))
                .where(
                    ViajeChecklist.empresa_id == self.empresa.id,
                    ViajeChecklist.viaje_id.in_(ids),
                    ViajeChecklist.completado == True,  # noqa: E712
                )
                .group_by(ViajeChecklist.viaje_id)
            ).all()
        )
        checklist_pend = dict(
            self.session.exec(
                select(ViajeChecklist.viaje_id, func.count(ViajeChecklist.id))
                .where(
                    ViajeChecklist.empresa_id == self.empresa.id,
                    ViajeChecklist.viaje_id.in_(ids),
                    ViajeChecklist.requerido == True,  # noqa: E712
                    ViajeChecklist.completado == False,  # noqa: E712
                )
                .group_by(ViajeChecklist.viaje_id)
            ).all()
        )
        incidentes_abiertos = dict(
            self.session.exec(
                select(ViajeIncidente.viaje_id, func.count(ViajeIncidente.id))
                .where(
                    ViajeIncidente.empresa_id == self.empresa.id,
                    ViajeIncidente.viaje_id.in_(ids),
                    ViajeIncidente.estado.in_(ESTADOS_INCIDENTE_ABIERTO),
                )
                .group_by(ViajeIncidente.viaje_id)
            ).all()
        )
        incidentes_bloqueantes = dict(
            self.session.exec(
                select(ViajeIncidente.viaje_id, func.count(ViajeIncidente.id))
                .where(
                    ViajeIncidente.empresa_id == self.empresa.id,
                    ViajeIncidente.viaje_id.in_(ids),
                    ViajeIncidente.estado.in_(ESTADOS_INCIDENTE_ABIERTO),
                    ViajeIncidente.severidad.in_(SEVERIDADES_BLOQUEANTES),
                )
                .group_by(ViajeIncidente.viaje_id)
            ).all()
        )
        docs = dict(
            self.session.exec(
                select(ViajeDocumento.viaje_id, func.count(ViajeDocumento.id))
                .where(
                    ViajeDocumento.empresa_id == self.empresa.id,
                    ViajeDocumento.viaje_id.in_(ids),
                    ViajeDocumento.activo == True,  # noqa: E712
                )
                .group_by(ViajeDocumento.viaje_id)
            ).all()
        )

        items: list[ViajeExpedienteResumenOut] = []
        for viaje in viajes:
            total_chk = int(checklist_total.get(viaje.id, 0))
            ok_chk = int(checklist_ok.get(viaje.id, 0))
            pend = int(checklist_pend.get(viaje.id, 0))
            inc = int(incidentes_abiertos.get(viaje.id, 0))
            inc_bloqueantes = int(incidentes_bloqueantes.get(viaje.id, 0))
            flete = viaje.monto_total_neto
            if flete is None:
                flete = (viaje.valor_flete_neto or Decimal("0")) + (
                    viaje.monto_recargos or Decimal("0")
                )
            cliente = clientes.get(viaje.cliente_id)
            oc = ocs.get(viaje.orden_compra_id) if viaje.orden_compra_id else None
            tarifa = tarifas.get(viaje.tarifa_id) if viaje.tarifa_id else None
            tracto = tractos.get(viaje.tracto_id) if viaje.tracto_id else None
            rampla = ramplas.get(viaje.rampla_id) if viaje.rampla_id else None
            chofer = choferes.get(viaje.chofer_id) if viaje.chofer_id else None
            items.append(
                ViajeExpedienteResumenOut(
                    id=viaje.id,
                    numero_viaje=viaje.numero_viaje or "",
                    estado=viaje.estado,
                    cliente_id=viaje.cliente_id,
                    cliente_nombre=cliente.razon_social if cliente else "-",
                    origen=viaje.origen_nombre,
                    destino=viaje.destino_nombre,
                    inicio_planificado=viaje.inicio_planificado,
                    fin_planificado=viaje.fin_planificado,
                    peso_bruto_kg=viaje.peso_bruto_kg,
                    flete_total=flete,
                    oc_numero=oc.numero_oc if oc else None,
                    tarifa_codigo=tarifa.codigo if tarifa else None,
                    tracto_patente=tracto.patente if tracto else None,
                    rampla_patente=rampla.patente if rampla else None,
                    chofer_nombre=self._etiqueta_chofer(chofer),
                    checklist_pct=(
                        (Decimal(ok_chk) / Decimal(total_chk) * 100).quantize(
                            Decimal("0.01")
                        )
                        if total_chk
                        else Decimal("0")
                    ),
                    checklist_pendientes=pend,
                    incidentes_abiertos=inc,
                    documentos_count=int(docs.get(viaje.id, 0)),
                    puede_cerrar=(
                        viaje.estado in ESTADOS_CIERRE
                        and pend == 0
                        and inc_bloqueantes == 0
                    ),
                )
            )
        return ListaExpedienteOut(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            hay_mas=offset + len(items) < total,
        )

    def obtener(self, viaje_id: UUID) -> ViajeExpedienteOut:
        viaje = self._get_viaje(viaje_id)
        cliente = self.session.get(Cliente, viaje.cliente_id)
        oc = (
            self.session.get(OrdenCompra, viaje.orden_compra_id)
            if viaje.orden_compra_id
            else None
        )
        tarifa = self.session.get(Tarifa, viaje.tarifa_id) if viaje.tarifa_id else None
        tracto = self.session.get(Tracto, viaje.tracto_id) if viaje.tracto_id else None
        rampla = self.session.get(Rampla, viaje.rampla_id) if viaje.rampla_id else None
        chofer = self.session.get(Chofer, viaje.chofer_id) if viaje.chofer_id else None

        paradas = self.session.exec(
            select(ViajeParada)
            .where(
                ViajeParada.empresa_id == self.empresa.id,
                ViajeParada.viaje_id == viaje.id,
                ViajeParada.activo == True,  # noqa: E712
            )
            .order_by(ViajeParada.orden)
        ).all()
        checklist = self.session.exec(
            select(ViajeChecklist)
            .where(
                ViajeChecklist.empresa_id == self.empresa.id,
                ViajeChecklist.viaje_id == viaje.id,
            )
            .order_by(ViajeChecklist.orden)
        ).all()
        eventos = self.session.exec(
            select(ViajeEvento)
            .where(
                ViajeEvento.empresa_id == self.empresa.id,
                ViajeEvento.viaje_id == viaje.id,
            )
            .order_by(ViajeEvento.ocurrido_en.desc())
            .limit(100)
        ).all()
        incidentes = self.session.exec(
            select(ViajeIncidente)
            .where(
                ViajeIncidente.empresa_id == self.empresa.id,
                ViajeIncidente.viaje_id == viaje.id,
            )
            .order_by(ViajeIncidente.ocurrido_en.desc())
        ).all()
        documentos = self.session.exec(
            select(ViajeDocumento)
            .where(
                ViajeDocumento.empresa_id == self.empresa.id,
                ViajeDocumento.viaje_id == viaje.id,
                ViajeDocumento.activo == True,  # noqa: E712
            )
            .order_by(ViajeDocumento.created_at.desc())
        ).all()
        historial = self._historial(
            [
                "nucleo.viajes",
                "nucleo.viaje_paradas",
                "nucleo.viaje_checklist",
                "nucleo.viaje_incidentes",
                "nucleo.viaje_documentos",
            ],
            [
                viaje.id,
                *(p.id for p in paradas),
                *(c.id for c in checklist),
                *(i.id for i in incidentes),
                *(d.id for d in documentos),
            ],
        )
        pod = ServicioPOD(self.session, self.contexto).obtener(viaje.id)
        servicio_gastos = ServicioGastos(self.session, self.contexto)
        gastos = servicio_gastos.listar_gastos(viaje.id)
        costos = servicio_gastos.costos(viaje.id)
        link_factura = self.session.exec(
            select(FacturaViaje).where(
                FacturaViaje.empresa_id == self.empresa.id,
                FacturaViaje.viaje_id == viaje.id,
            )
        ).first()
        factura = (
            ServicioFacturacion(self.session, self.contexto).obtener_factura(
                link_factura.factura_id
            )
            if link_factura is not None
            else None
        )
        flete = viaje.monto_total_neto
        if flete is None:
            flete = (viaje.valor_flete_neto or Decimal("0")) + (
                viaje.monto_recargos or Decimal("0")
            )
        return ViajeExpedienteOut(
            id=viaje.id,
            numero_viaje=viaje.numero_viaje or "",
            estado=viaje.estado,
            cliente_id=viaje.cliente_id,
            cliente_nombre=cliente.razon_social if cliente else "-",
            cliente_rut=cliente.rut if cliente else None,
            orden_compra_id=viaje.orden_compra_id,
            oc_numero=oc.numero_oc if oc else viaje.oc_numero_snapshot,
            tarifa_id=viaje.tarifa_id,
            tarifa_codigo=tarifa.codigo if tarifa else None,
            tracto_id=viaje.tracto_id,
            tracto_patente=tracto.patente if tracto else None,
            rampla_id=viaje.rampla_id,
            rampla_patente=rampla.patente if rampla else None,
            chofer_id=viaje.chofer_id,
            chofer_nombre=self._etiqueta_chofer(chofer),
            inicio_planificado=viaje.inicio_planificado,
            fin_planificado=viaje.fin_planificado,
            fin_estimado=viaje.fin_estimado,
            inicio_real=viaje.inicio_real,
            fin_real=viaje.fin_real,
            buffer_minutos=viaje.buffer_minutos,
            origen_nombre=viaje.origen_nombre,
            origen_direccion=viaje.origen_direccion,
            origen_comuna=viaje.origen_comuna,
            origen_ciudad=viaje.origen_ciudad,
            origen_region=viaje.origen_region,
            destino_nombre=viaje.destino_nombre,
            destino_direccion=viaje.destino_direccion,
            destino_comuna=viaje.destino_comuna,
            destino_ciudad=viaje.destino_ciudad,
            destino_region=viaje.destino_region,
            distancia_km=viaje.distancia_km,
            tiempo_estimado_h=viaje.tiempo_estimado_h,
            tipo_carga=viaje.tipo_carga,
            descripcion_carga=viaje.descripcion_carga,
            peso_bruto_kg=viaje.peso_bruto_kg,
            peso_neto_kg=viaje.peso_neto_kg,
            volumen_m3=viaje.volumen_m3,
            bultos=viaje.bultos,
            valor_declarado=viaje.valor_declarado,
            moneda_valor=viaje.moneda_valor,
            carga_peligrosa=viaje.carga_peligrosa,
            numero_un=viaje.numero_un,
            clase_peligro=viaje.clase_peligro,
            refrigerada=viaje.refrigerada,
            temperatura_min_c=viaje.temperatura_min_c,
            temperatura_max_c=viaje.temperatura_max_c,
            sobredimensionada=viaje.sobredimensionada,
            instrucciones_especiales=viaje.instrucciones_especiales,
            valor_flete_neto=viaje.valor_flete_neto,
            monto_recargos=viaje.monto_recargos,
            monto_total_neto=flete,
            moneda=viaje.moneda,
            condiciones_pago_dias=viaje.condiciones_pago_dias,
            observaciones=viaje.observaciones,
            motivo_anulacion=viaje.motivo_anulacion,
            created_at=viaje.created_at,
            updated_at=viaje.updated_at,
            version=viaje.version,
            paradas=[self._parada_out(p) for p in paradas],
            checklist=[self._checklist_out(c) for c in checklist],
            eventos=[self._evento_out(e) for e in eventos],
            incidentes=[self._incidente_out(i) for i in incidentes],
            documentos=[self._documento_out(d) for d in documentos],
            historial=historial,
            gastos=[g.model_dump(mode="json") for g in gastos],
            factura=factura.model_dump(mode="json") if factura else None,
            pod=pod.model_dump(mode="json") if pod is not None else None,
            costos=costos.model_dump(mode="json"),
            resumen=self._resumen(viaje),
            qr_url=self._qr_data_uri(viaje),
        )

    def qr_svg(self, viaje_id: UUID) -> str:
        viaje = self._get_viaje(viaje_id)
        contenido = (
            f"{settings.FRONTEND_URL.rstrip('/')}/expediente/{viaje.id}"
            f"?viaje={viaje.numero_viaje}"
        )
        return segno.make(contenido, error="m").svg_inline()

    # ------------------------------------------------------------------
    # Paradas
    # ------------------------------------------------------------------
    def _validar_editable(self, viaje: Viaje) -> None:
        if viaje.estado not in ESTADOS_EDITABLES:
            raise ReglaNegocioViolada(
                f"El viaje {viaje.numero_viaje} está en estado {viaje.estado.value} "
                "y ya no admite cambios de expediente."
            )

    def crear_parada(self, viaje_id: UUID, data: ParadaCreate) -> ParadaOut:
        viaje = self._get_viaje(viaje_id)
        self._validar_editable(viaje)
        if data.tipo not in TIPOS_PARADA:
            raise DatosInvalidos("Tipo de parada no válido.")
        if data.estado not in ESTADOS_PARADA:
            raise DatosInvalidos("Estado de parada no válido.")
        orden = data.orden
        if orden is None:
            orden = int(
                self.session.exec(
                    select(func.coalesce(func.max(ViajeParada.orden), 0)).where(
                        ViajeParada.viaje_id == viaje.id
                    )
                ).one()
                or 0
            ) + 1
        existe = self.session.exec(
            select(ViajeParada).where(
                ViajeParada.viaje_id == viaje.id, ViajeParada.orden == orden
            )
        ).first()
        if existe is not None:
            raise DatosInvalidos(f"Ya existe una parada con orden {orden}.")
        self._fijar_contexto_bd()
        parada = ViajeParada(
            empresa_id=self.empresa.id,
            viaje_id=viaje.id,
            orden=orden,
            tipo=data.tipo,
            nombre=data.nombre.strip(),
            direccion=data.direccion,
            comuna=data.comuna,
            ciudad=data.ciudad,
            contacto_nombre=data.contacto_nombre,
            contacto_telefono=data.contacto_telefono,
            ventana_desde=data.ventana_desde,
            ventana_hasta=data.ventana_hasta,
            estado=data.estado,
            notas=data.notas,
            activo=True,
        )
        try:
            self.session.add(parada)
            self._agregar_evento(
                viaje,
                "parada_creada",
                f"Parada {orden} creada: {data.nombre.strip()}",
                payload={"parada_id": str(parada.id), "tipo": data.tipo},
            )
            self.session.commit()
            self.session.refresh(parada)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self._parada_out(parada)

    def actualizar_parada(
        self, viaje_id: UUID, parada_id: UUID, data: ParadaUpdate
    ) -> ParadaOut:
        viaje = self._get_viaje(viaje_id)
        self._validar_editable(viaje)
        parada = self.session.get(ViajeParada, parada_id)
        if (
            parada is None
            or parada.empresa_id != self.empresa.id
            or parada.viaje_id != viaje.id
        ):
            raise RecursoNoEncontrado("Parada no encontrada en el viaje.")
        version = data.version if data.version is not None else parada.version
        if version != parada.version:
            raise ConflictoConcurrencia(
                "La parada fue modificada por otro usuario. Recargue e intente nuevamente."
            )
        if data.tipo not in TIPOS_PARADA or data.estado not in ESTADOS_PARADA:
            raise DatosInvalidos("Tipo o estado de parada no válido.")
        if data.orden is not None and data.orden != parada.orden:
            existe = self.session.exec(
                select(ViajeParada).where(
                    ViajeParada.viaje_id == viaje.id,
                    ViajeParada.orden == data.orden,
                    ViajeParada.id != parada.id,
                )
            ).first()
            if existe is not None:
                raise DatosInvalidos(f"Ya existe una parada con orden {data.orden}.")
        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                update(ViajeParada)
                .where(
                    ViajeParada.id == parada.id,
                    ViajeParada.empresa_id == self.empresa.id,
                    ViajeParada.version == version,
                )
                .values(
                    orden=data.orden or parada.orden,
                    tipo=data.tipo,
                    nombre=data.nombre.strip(),
                    direccion=data.direccion,
                    comuna=data.comuna,
                    ciudad=data.ciudad,
                    contacto_nombre=data.contacto_nombre,
                    contacto_telefono=data.contacto_telefono,
                    ventana_desde=data.ventana_desde,
                    ventana_hasta=data.ventana_hasta,
                    estado=data.estado,
                    notas=data.notas,
                    activo=data.activo,
                )
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia("La parada fue modificada por otro usuario.")
            self.session.commit()
            self.session.refresh(parada)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self._parada_out(parada)

    def desactivar_parada(self, viaje_id: UUID, parada_id: UUID) -> ParadaOut:
        viaje = self._get_viaje(viaje_id)
        self._validar_editable(viaje)
        parada = self.session.get(ViajeParada, parada_id)
        if (
            parada is None
            or parada.empresa_id != self.empresa.id
            or parada.viaje_id != viaje.id
        ):
            raise RecursoNoEncontrado("Parada no encontrada en el viaje.")
        self._fijar_contexto_bd()
        parada.activo = False
        self.session.add(parada)
        self.session.commit()
        self.session.refresh(parada)
        return self._parada_out(parada)

    # ------------------------------------------------------------------
    # Checklist
    # ------------------------------------------------------------------
    def listar_checklist(self, viaje_id: UUID) -> list[ChecklistItemOut]:
        viaje = self._get_viaje(viaje_id)
        items = self.session.exec(
            select(ViajeChecklist)
            .where(
                ViajeChecklist.empresa_id == self.empresa.id,
                ViajeChecklist.viaje_id == viaje.id,
            )
            .order_by(ViajeChecklist.orden)
        ).all()
        return [self._checklist_out(item) for item in items]

    def crear_item_checklist(
        self, viaje_id: UUID, data: ChecklistItemCreate
    ) -> ChecklistItemOut:
        viaje = self._get_viaje(viaje_id)
        self._validar_editable(viaje)
        orden = data.orden
        if orden is None:
            orden = int(
                self.session.exec(
                    select(func.coalesce(func.max(ViajeChecklist.orden), 0)).where(
                        ViajeChecklist.viaje_id == viaje.id
                    )
                ).one()
                or 0
            ) + 1
        self._fijar_contexto_bd()
        item = ViajeChecklist(
            empresa_id=self.empresa.id,
            viaje_id=viaje.id,
            orden=orden,
            categoria=data.categoria,
            item=data.item.strip(),
            requerido=data.requerido,
            completado=False,
        )
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return self._checklist_out(item)

    def actualizar_item_checklist(
        self, viaje_id: UUID, item_id: UUID, data: ChecklistItemUpdate
    ) -> ChecklistItemOut:
        viaje = self._get_viaje(viaje_id)
        self._validar_editable(viaje)
        item = self.session.get(ViajeChecklist, item_id)
        if (
            item is None
            or item.empresa_id != self.empresa.id
            or item.viaje_id != viaje.id
        ):
            raise RecursoNoEncontrado("Ítem de checklist no encontrado.")
        version = data.version if data.version is not None else item.version
        if version != item.version:
            raise ConflictoConcurrencia(
                "El ítem fue modificado por otro usuario. Recargue e intente nuevamente."
            )
        valores: dict[str, Any] = {
            "completado": data.completado,
            "notas": data.notas,
            "evidencia_url": data.evidencia_url,
        }
        if data.completado:
            if not item.completado:
                valores["completado_por"] = self.contexto.auth_id
                valores["completado_en"] = ahora_utc()
        else:
            valores["completado_por"] = None
            valores["completado_en"] = None
        self._fijar_contexto_bd()
        resultado = self.session.execute(
            update(ViajeChecklist)
            .where(
                ViajeChecklist.id == item.id,
                ViajeChecklist.empresa_id == self.empresa.id,
                ViajeChecklist.version == version,
            )
            .values(**valores)
        )
        if resultado.rowcount != 1:
            self.session.rollback()
            raise ConflictoConcurrencia("El ítem fue modificado por otro usuario.")
        self.session.commit()
        self.session.refresh(item)
        return self._checklist_out(item)

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    def listar_eventos(self, viaje_id: UUID) -> list[EventoOut]:
        viaje = self._get_viaje(viaje_id)
        eventos = self.session.exec(
            select(ViajeEvento)
            .where(
                ViajeEvento.empresa_id == self.empresa.id,
                ViajeEvento.viaje_id == viaje.id,
            )
            .order_by(ViajeEvento.ocurrido_en.desc())
            .limit(200)
        ).all()
        return [self._evento_out(e) for e in eventos]

    def crear_evento(self, viaje_id: UUID, data: EventoCreate) -> EventoOut:
        viaje = self._get_viaje(viaje_id)
        self._fijar_contexto_bd()
        evento = ViajeEvento(
            empresa_id=self.empresa.id,
            viaje_id=viaje.id,
            tipo=data.tipo,
            descripcion=data.descripcion.strip(),
            ocurrido_en=data.ocurrido_en or ahora_utc(),
            payload=data.payload,
            auth_id=self.contexto.auth_id,
        )
        self.session.add(evento)
        self.session.commit()
        self.session.refresh(evento)
        return self._evento_out(evento)

    # ------------------------------------------------------------------
    # Incidentes
    # ------------------------------------------------------------------
    def listar_incidentes(self, viaje_id: UUID) -> list[IncidenteOut]:
        viaje = self._get_viaje(viaje_id)
        incidentes = self.session.exec(
            select(ViajeIncidente)
            .where(
                ViajeIncidente.empresa_id == self.empresa.id,
                ViajeIncidente.viaje_id == viaje.id,
            )
            .order_by(ViajeIncidente.ocurrido_en.desc())
        ).all()
        return [self._incidente_out(i) for i in incidentes]

    def crear_incidente(
        self, viaje_id: UUID, data: IncidenteCreate
    ) -> IncidenteOut:
        viaje = self._get_viaje(viaje_id)
        self._fijar_contexto_bd()
        incidente = ViajeIncidente(
            empresa_id=self.empresa.id,
            viaje_id=viaje.id,
            tipo=data.tipo.strip(),
            severidad=data.severidad,
            descripcion=data.descripcion.strip(),
            estado="abierto",
            ocurrido_en=data.ocurrido_en or ahora_utc(),
            reportado_por=self.contexto.auth_id,
        )
        self.session.add(incidente)
        self._agregar_evento(
            viaje,
            "incidente_reportado",
            f"Incidente {data.severidad}: {data.descripcion.strip()}",
            payload={"incidente_id": str(incidente.id), "tipo": data.tipo},
        )
        self.session.commit()
        self.session.refresh(incidente)
        return self._incidente_out(incidente)

    def actualizar_incidente(
        self, viaje_id: UUID, incidente_id: UUID, data: IncidenteUpdate
    ) -> IncidenteOut:
        viaje = self._get_viaje(viaje_id)
        incidente = self.session.get(ViajeIncidente, incidente_id)
        if (
            incidente is None
            or incidente.empresa_id != self.empresa.id
            or incidente.viaje_id != viaje.id
        ):
            raise RecursoNoEncontrado("Incidente no encontrado en el viaje.")
        version = data.version if data.version is not None else incidente.version
        if version != incidente.version:
            raise ConflictoConcurrencia(
                "El incidente fue modificado por otro usuario. Recargue e intente nuevamente."
            )
        nuevo_estado = data.estado or incidente.estado
        nueva_resolucion = (
            data.resolucion if data.resolucion is not None else incidente.resolucion
        )
        if nuevo_estado in {"resuelto", "cerrado"} and not (nueva_resolucion or "").strip():
            raise DatosInvalidos("Debe registrar la resolución antes de cerrar el incidente.")
        valores: dict[str, Any] = {
            "estado": nuevo_estado,
            "severidad": data.severidad or incidente.severidad,
            "resolucion": nueva_resolucion,
        }
        if nuevo_estado in {"resuelto", "cerrado"} and incidente.estado not in {
            "resuelto",
            "cerrado",
        }:
            valores["resuelto_por"] = self.contexto.auth_id
            valores["resuelto_en"] = ahora_utc()
        if nuevo_estado in ESTADOS_INCIDENTE_ABIERTO:
            valores["resuelto_por"] = None
            valores["resuelto_en"] = None
        self._fijar_contexto_bd()
        resultado = self.session.execute(
            update(ViajeIncidente)
            .where(
                ViajeIncidente.id == incidente.id,
                ViajeIncidente.empresa_id == self.empresa.id,
                ViajeIncidente.version == version,
            )
            .values(**valores)
        )
        if resultado.rowcount != 1:
            self.session.rollback()
            raise ConflictoConcurrencia("El incidente fue modificado por otro usuario.")
        self._agregar_evento(
            viaje,
            "incidente_actualizado",
            f"Incidente {nuevo_estado}: {incidente.descripcion[:120]}",
            payload={"incidente_id": str(incidente.id), "estado": nuevo_estado},
        )
        self.session.commit()
        self.session.refresh(incidente)
        return self._incidente_out(incidente)

    # ------------------------------------------------------------------
    # Documentos
    # ------------------------------------------------------------------
    def listar_documentos(self, viaje_id: UUID) -> list[ViajeDocumentoOut]:
        viaje = self._get_viaje(viaje_id)
        docs = self.session.exec(
            select(ViajeDocumento)
            .where(
                ViajeDocumento.empresa_id == self.empresa.id,
                ViajeDocumento.viaje_id == viaje.id,
                ViajeDocumento.activo == True,  # noqa: E712
            )
            .order_by(ViajeDocumento.created_at.desc())
        ).all()
        return [self._documento_out(d) for d in docs]

    def subir_documento(
        self,
        viaje_id: UUID,
        *,
        tipo: str,
        nombre_archivo: str,
        contenido: bytes,
        content_type: str | None,
        observaciones: str | None,
    ) -> ViajeDocumentoOut:
        import hashlib

        viaje = self._get_viaje(viaje_id)
        self._validar_editable(viaje)
        ext = validar_archivo(nombre_archivo, contenido)
        path = ruta_archivo(
            "nucleo",
            str(self.empresa.id),
            "viajes",
            str(viaje.id),
            "documentos",
            extension=ext,
        )
        subir_archivo(path, contenido, content_type)
        self._fijar_contexto_bd()
        doc = ViajeDocumento(
            empresa_id=self.empresa.id,
            viaje_id=viaje.id,
            tipo=tipo,
            nombre=nombre_archivo,
            archivo_url=path,
            hash_sha256=hashlib.sha256(contenido).hexdigest(),
            content_type=content_type,
            tamano_bytes=len(contenido),
            observaciones=observaciones,
            activo=True,
        )
        try:
            self.session.add(doc)
            self._agregar_evento(
                viaje,
                "documento_subido",
                f"Documento adjuntado: {nombre_archivo}",
                payload={"documento_id": str(doc.id), "tipo": tipo},
            )
            self.session.commit()
            self.session.refresh(doc)
        except IntegrityError as exc:
            self.session.rollback()
            eliminar_archivo(path)
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            eliminar_archivo(path)
            raise
        return self._documento_out(doc)

    def desactivar_documento(
        self, viaje_id: UUID, documento_id: UUID
    ) -> ViajeDocumentoOut:
        viaje = self._get_viaje(viaje_id)
        self._validar_editable(viaje)
        doc = self.session.get(ViajeDocumento, documento_id)
        if (
            doc is None
            or doc.empresa_id != self.empresa.id
            or doc.viaje_id != viaje.id
        ):
            raise RecursoNoEncontrado("Documento no encontrado en el viaje.")
        doc.activo = False
        self.session.add(doc)
        self.session.commit()
        self.session.refresh(doc)
        return self._documento_out(doc)

    # ------------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------------
    def cerrar_viaje(self, viaje_id: UUID, data: CerrarViaje) -> ViajeExpedienteOut:
        viaje = self._get_viaje(viaje_id, lock=True)
        if ahora_utc() < viaje.inicio_planificado:
            raise DatosInvalidos(
                "No se puede cerrar un viaje que aún no ha iniciado."
            )
        resumen = self._resumen(viaje)
        if not resumen.puede_cerrar:
            raise DatosInvalidos(
                "No se puede cerrar el viaje: " + " ".join(resumen.motivos_cierre),
                errores=[
                    {"codigo": "CIERRE_BLOQUEADO", "mensaje": motivo}
                    for motivo in resumen.motivos_cierre
                ],
            )
        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                update(Viaje)
                .where(
                    Viaje.id == viaje.id,
                    Viaje.empresa_id == self.empresa.id,
                    Viaje.version == viaje.version,
                )
                .values(
                    estado=EstadoViaje.cerrado,
                    fin_real=viaje.fin_real or ahora_utc(),
                    observaciones=(
                        f"{viaje.observaciones}\n{data.observaciones.strip()}"
                        if viaje.observaciones and data.observaciones
                        else (data.observaciones or viaje.observaciones)
                    ),
                )
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "El viaje fue modificado por otro usuario. Recargue e intente nuevamente."
                )
            self._agregar_evento(
                viaje,
                "cerrado",
                "Viaje cerrado con checklist completo",
                payload={"resumen": resumen.model_dump(mode="json")},
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.obtener(viaje.id)

    def reabrir_viaje(self, viaje_id: UUID, motivo: str) -> ViajeExpedienteOut:
        """Reapertura excepcional: la máquina de estados no permite volver de cerrado.

        Se deja fuera del alcance del piloto para no romper la trazabilidad. El
        endpoint existe solo para devolver un error explicable.
        """
        self._get_viaje(viaje_id)
        raise ReglaNegocioViolada(
            "Un viaje cerrado no se reabre; registre un ajuste o un viaje nuevo. "
            f"Motivo recibido: {motivo[:120]}"
        )
