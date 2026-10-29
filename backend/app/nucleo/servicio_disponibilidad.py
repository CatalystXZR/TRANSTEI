"""Motor de disponibilidad y confirmación de asignaciones.

Diseño:
1. El servicio calcula y explica; la base garantiza.
2. Las lecturas son batch (documentos y reservas por tipo de recurso) para
   evitar N+1 en la mesa de despacho.
3. La confirmación bloquea el viaje (`FOR UPDATE`), toma locks de asesoría
   por recurso en orden determinista y deja que la restricción EXCLUDE sea el
   árbitro final ante dos despachadores concurrentes.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    ConflictoDisponibilidad,
    DatosInvalidos,
    EstadoViajeInvalido,
    RecursoNoEncontrado,
    traducir_integrity_error,
)
from app.nucleo.models import (
    Auditoria,
    Chofer,
    Cliente,
    Documento,
    Empresa,
    EstadoEmpresa,
    EstadoOC,
    EstadoRecurso,
    EstadoViaje,
    OrdenCompra,
    Rampla,
    ReservaRecurso,
    Tarifa,
    TipoDocumento,
    TipoRampla,
    TipoRecurso,
    Tracto,
    UsuarioEmpresa,
    Viaje,
)
from app.nucleo.politicas import (
    Hallazgo,
    RequisitoDocumento,
    documentos_requeridos,
    validar_carga,
    validar_oc,
    validar_tarifa,
)
from app.nucleo.schemas import (
    AsignacionConfirmada,
    ConflictoOut,
    DocumentoOut,
    EmpresaMembresiaOut,
    IncidenciaOut,
    LibreDesdeOut,
    ListaRecursosOut,
    ListaViajesOut,
    OrdenCompraOpcionOut,
    PaginacionOut,
    RecursoOut,
    ReservaOut,
    ResultadoValidacion,
    SolicitudAsignacion,
    TarifaOpcionOut,
    VentanaOut,
    ViajeCreateNucleo,
    ViajeResumenOut,
)
from app.nucleo.tarifas import ErrorTarifa, calcular_flete
from app.nucleo.tiempo import (
    Intervalo,
    a_utc,
    ahora_utc,
    calcular_libre_desde,
    zona,
)
from app.nucleo.tiempo import (
    inicio_operativo_posible as calcular_inicio_operativo,
)

MAX_RECURSOS = 500
MAX_VENTANA_DIAS = 90


def listar_empresas_usuario(session: Session, auth_id: str) -> list[EmpresaMembresiaOut]:
    """Empresas activas a las que pertenece el usuario autenticado."""
    try:
        auth_uuid = UUID(auth_id)
    except ValueError:
        return []
    membresias = session.exec(
        select(UsuarioEmpresa).where(
            UsuarioEmpresa.auth_id == auth_uuid,
            UsuarioEmpresa.activo == True,  # noqa: E712
        )
    ).all()
    if not membresias:
        return []
    empresas = {
        e.id: e
        for e in session.exec(
            select(Empresa).where(
                Empresa.id.in_([m.empresa_id for m in membresias]),
                Empresa.estado == EstadoEmpresa.activa,
            )
        ).all()
    }
    salida: list[EmpresaMembresiaOut] = []
    for membresia in membresias:
        empresa = empresas.get(membresia.empresa_id)
        if empresa is None:
            continue
        salida.append(
            EmpresaMembresiaOut(
                id=empresa.id,
                codigo=empresa.codigo,
                razon_social=empresa.razon_social,
                rut=empresa.rut,
                zona_horaria=empresa.zona_horaria,
                moneda=empresa.moneda,
                buffer_operacional_min=empresa.buffer_operacional_min,
                rol=membresia.rol,
            )
        )
    return salida


class ServicioDisponibilidad:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa
        self.tz = zona(self.empresa.zona_horaria)

    # ------------------------------------------------------------------
    # Helpers de recursos
    # ------------------------------------------------------------------
    def _modelo(self, tipo: TipoRecurso):
        return {
            TipoRecurso.tracto: Tracto,
            TipoRecurso.rampla: Rampla,
            TipoRecurso.chofer: Chofer,
        }[tipo]

    def _id_documento(self, tipo: TipoRecurso):
        return {
            TipoRecurso.tracto: Documento.tracto_id,
            TipoRecurso.rampla: Documento.rampla_id,
            TipoRecurso.chofer: Documento.chofer_id,
        }[tipo]

    def _id_reserva(self, tipo: TipoRecurso):
        return {
            TipoRecurso.tracto: ReservaRecurso.tracto_id,
            TipoRecurso.rampla: ReservaRecurso.rampla_id,
            TipoRecurso.chofer: ReservaRecurso.chofer_id,
        }[tipo]

    def _etiqueta(self, tipo: TipoRecurso, recurso: Any) -> str:
        if tipo == TipoRecurso.chofer:
            partes = [recurso.nombre, recurso.apellido_paterno, recurso.apellido_materno]
            return " ".join(p for p in partes if p).strip()
        return getattr(recurso, "patente", str(recurso.id))

    def _cargar_recurso(self, tipo: TipoRecurso, recurso_id: UUID) -> Any:
        modelo = self._modelo(tipo)
        recurso = self.session.get(modelo, recurso_id)
        if recurso is None or recurso.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado(
                f"{tipo.value.capitalize()} no encontrado en la empresa.",
                contexto={"recurso_tipo": tipo.value, "recurso_id": str(recurso_id)},
            )
        return recurso

    # ------------------------------------------------------------------
    # Documentos
    # ------------------------------------------------------------------
    def _requisitos(
        self,
        tipo: TipoRecurso,
        *,
        carga_peligrosa: bool,
        refrigerada: bool,
    ) -> list[RequisitoDocumento]:
        return documentos_requeridos(
            tipo,
            self.empresa,
            carga_peligrosa=carga_peligrosa,
            refrigerada=refrigerada,
        )

    def _cargar_documentos(
        self,
        tipo: TipoRecurso,
        ids: Sequence[UUID],
    ) -> dict[UUID, dict[TipoDocumento, Documento]]:
        if not ids:
            return {}
        columna = self._id_documento(tipo)
        stmt = (
            select(Documento)
            .where(
                Documento.empresa_id == self.empresa.id,
                Documento.recurso_tipo == tipo,
                Documento.es_vigente == True,
                columna.in_(list(ids)),
            )
            .order_by(Documento.vence_en.desc())
        )
        documentos = self.session.exec(stmt).all()
        salida: dict[UUID, dict[TipoDocumento, Documento]] = {i: {} for i in ids}
        for doc in documentos:
            recurso_id = getattr(doc, f"{tipo.value}_id")
            if recurso_id is None:
                continue
            # El primero es el de mayor vencimiento; la unicidad parcial ya
            # impide más de un documento vigente del mismo tipo.
            salida.setdefault(recurso_id, {}).setdefault(doc.tipo, doc)
        return salida

    def _evaluar_documentos(
        self,
        tipo: TipoRecurso,
        recurso_id: UUID,
        requisitos: Sequence[RequisitoDocumento],
        documentos: dict[TipoDocumento, Documento],
        fecha_limite: date,
        hoy: date,
    ) -> tuple[list[DocumentoOut], list[Hallazgo]]:
        salida: list[DocumentoOut] = []
        hallazgos: list[Hallazgo] = []
        alerta_dias = self.empresa.dias_alerta_documentos

        for req in requisitos:
            doc = documentos.get(req.tipo)
            if doc is None:
                salida.append(
                    DocumentoOut(
                        recurso_tipo=tipo,
                        recurso_id=recurso_id,
                        tipo=req.tipo.value,
                        estado="faltante",
                        requerido=True,
                        bloqueante=True,
                        motivo=req.motivo,
                    )
                )
                hallazgos.append(
                    Hallazgo(
                        "DOCUMENTO_FALTANTE",
                        f"Falta {req.motivo} ({req.tipo.value})",
                        True,
                        tipo,
                        str(recurso_id),
                    )
                )
                continue

            dias = (doc.vence_en - hoy).days
            if doc.vence_en < hoy:
                estado = "vencido"
                bloqueante = True
            elif doc.vence_en < fecha_limite:
                estado = "insuficiente"
                bloqueante = True
            elif dias <= alerta_dias:
                estado = "por_vencer"
                bloqueante = False
            else:
                estado = "vigente"
                bloqueante = False

            salida.append(
                DocumentoOut(
                    recurso_tipo=tipo,
                    recurso_id=recurso_id,
                    tipo=req.tipo.value,
                    estado=estado,
                    requerido=True,
                    bloqueante=bloqueante,
                    vence_en=doc.vence_en.isoformat(),
                    dias_restantes=dias,
                    motivo=req.motivo,
                    numero=doc.numero,
                )
            )
            if bloqueante:
                if estado == "vencido":
                    mensaje = f"{req.motivo} vencido el {doc.vence_en}"
                else:
                    mensaje = (
                        f"{req.motivo} vence el {doc.vence_en}, antes del fin del viaje "
                        f"(requerido hasta {fecha_limite})"
                    )
                hallazgos.append(
                    Hallazgo("DOCUMENTO_NO_VIGENTE", mensaje, True, tipo, str(recurso_id))
                )
        return salida, hallazgos

    def _documentos_por_recurso(
        self,
        tipo: TipoRecurso,
        recursos: Sequence[Any],
        *,
        carga_peligrosa: bool,
        refrigerada: bool,
        fecha_limite: date,
    ) -> tuple[dict[UUID, list[DocumentoOut]], dict[UUID, list[Hallazgo]]]:
        ids = [r.id for r in recursos]
        docs = self._cargar_documentos(tipo, ids)
        hoy = ahora_utc().astimezone(self.tz).date()
        salida_docs: dict[UUID, list[DocumentoOut]] = {}
        salida_hall: dict[UUID, list[Hallazgo]] = {}
        requisitos = self._requisitos(
            tipo, carga_peligrosa=carga_peligrosa, refrigerada=refrigerada
        )
        for recurso in recursos:
            evaluados, hallazgos = self._evaluar_documentos(
                tipo,
                recurso.id,
                requisitos,
                docs.get(recurso.id, {}),
                fecha_limite,
                hoy,
            )
            salida_docs[recurso.id] = evaluados
            salida_hall[recurso.id] = hallazgos
        return salida_docs, salida_hall

    # ------------------------------------------------------------------
    # Reservas
    # ------------------------------------------------------------------
    @staticmethod
    def _intervalo_de_reserva(reserva: ReservaRecurso) -> Intervalo | None:
        rango = reserva.ventana
        inicio = getattr(rango, "lower", None)
        fin = getattr(rango, "upper", None)
        if inicio is None or fin is None:
            return None
        return Intervalo(
            inicio=inicio,
            fin=fin,
            tipo=reserva.tipo_reserva.value,
            motivo=reserva.motivo,
            referencia_id=str(reserva.viaje_id) if reserva.viaje_id else str(reserva.id),
        )

    def _cargar_reservas(
        self,
        tipo: TipoRecurso,
        ids: Sequence[UUID],
        *,
        desde: datetime,
        excluir_viaje_id: UUID | None = None,
    ) -> dict[UUID, list[ReservaRecurso]]:
        if not ids:
            return {}
        columna = self._id_reserva(tipo)
        stmt = (
            select(ReservaRecurso)
            .where(
                ReservaRecurso.empresa_id == self.empresa.id,
                ReservaRecurso.recurso_tipo == tipo,
                ReservaRecurso.activa == True,
                columna.in_(list(ids)),
                func.upper(ReservaRecurso.ventana) > desde,
            )
            .order_by(func.lower(ReservaRecurso.ventana))
        )
        if excluir_viaje_id is not None:
            stmt = stmt.where(
                or_(
                    ReservaRecurso.viaje_id.is_(None),
                    ReservaRecurso.viaje_id != excluir_viaje_id,
                )
            )
        filas = self.session.exec(stmt).all()
        salida: dict[UUID, list[ReservaRecurso]] = {i: [] for i in ids}
        for reserva in filas:
            recurso_id = getattr(reserva, f"{tipo.value}_id")
            if recurso_id is None:
                continue
            salida.setdefault(recurso_id, []).append(reserva)
        return salida

    def _reservas_out(self, reservas: Iterable[ReservaRecurso]) -> list[ReservaOut]:
        salida: list[ReservaOut] = []
        for r in reservas:
            rango = r.ventana
            if getattr(rango, "lower", None) is None or getattr(rango, "upper", None) is None:
                continue
            salida.append(
                ReservaOut(
                    id=r.id,
                    tipo_reserva=r.tipo_reserva,
                    inicio=rango.lower,
                    fin=rango.upper,
                    motivo=r.motivo,
                    viaje_id=r.viaje_id,
                )
            )
        return salida

    def _conflictos(
        self,
        tipo: TipoRecurso,
        recurso_id: UUID,
        reservas: Sequence[ReservaRecurso],
        desde: datetime,
        hasta: datetime,
    ) -> list[ConflictoOut]:
        salida: list[ConflictoOut] = []
        for reserva in reservas:
            rango = reserva.ventana
            inicio = getattr(rango, "lower", None)
            fin = getattr(rango, "upper", None)
            if inicio is None or fin is None:
                continue
            if inicio < hasta and fin > desde:
                salida.append(
                    ConflictoOut(
                        recurso_tipo=tipo,
                        recurso_id=recurso_id,
                        tipo_reserva=reserva.tipo_reserva,
                        inicio=inicio,
                        fin=fin,
                        motivo=reserva.motivo,
                        viaje_id=reserva.viaje_id,
                    )
                )
        return salida

    # ------------------------------------------------------------------
    # Evaluación de un recurso
    # ------------------------------------------------------------------
    def _evaluar_recurso(
        self,
        tipo: TipoRecurso,
        recurso: Any,
        *,
        desde: datetime,
        hasta: datetime,
        fecha_limite: date,
        documentos: list[DocumentoOut],
        hallazgos_docs: list[Hallazgo],
        reservas: Sequence[ReservaRecurso],
        minutos_traslado: int = 0,
        ventana_desde: datetime | None = None,
        ventana_hasta: datetime | None = None,
        exigir_libre_ahora: bool = True,
    ) -> RecursoOut:
        intervalos = [i for r in reservas if (i := self._intervalo_de_reserva(r)) is not None]
        # `desde`/`hasta` describen la consulta de disponibilidad; la ventana
        # de conflicto puede ser distinta (por ejemplo, un viaje futuro).
        conflictos = self._conflictos(
            tipo,
            recurso.id,
            reservas,
            ventana_desde or desde,
            ventana_hasta or hasta,
        )
        estado = recurso.estado
        bloqueo_estado = estado in (EstadoRecurso.baja, EstadoRecurso.bloqueado)
        doc_ok = not any(h.bloqueante for h in hallazgos_docs)

        incidencias: list[IncidenciaOut] = []
        advertencias: list[IncidenciaOut] = []
        for h in hallazgos_docs:
            item = IncidenciaOut(
                codigo=h.codigo,
                mensaje=h.mensaje,
                bloqueante=h.bloqueante,
                recurso_tipo=h.recurso_tipo,
                recurso_id=h.recurso_id,
            )
            (incidencias if h.bloqueante else advertencias).append(item)

        if not recurso.activo:
            incidencias.append(
                IncidenciaOut(
                    codigo="RECURSO_INACTIVO",
                    mensaje=f"{self._etiqueta(tipo, recurso)} está inactivo",
                    bloqueante=True,
                    recurso_tipo=tipo,
                    recurso_id=str(recurso.id),
                )
            )
        if bloqueo_estado:
            incidencias.append(
                IncidenciaOut(
                    codigo="RECURSO_BLOQUEADO",
                    mensaje=f"{self._etiqueta(tipo, recurso)} está en estado {estado.value}",
                    bloqueante=True,
                    recurso_tipo=tipo,
                    recurso_id=str(recurso.id),
                )
            )
        if estado in (
            EstadoRecurso.en_taller,
            EstadoRecurso.en_descanso,
            EstadoRecurso.vacaciones,
        ) and not intervalos:
            advertencias.append(
                IncidenciaOut(
                    codigo="ESTADO_SIN_BLOQUEO",
                    mensaje=(
                        f"El estado es {estado.value} pero no hay un bloqueo con ventana. "
                        "Registre la mantención/descanso para que la agenda sea confiable."
                    ),
                    bloqueante=False,
                    recurso_tipo=tipo,
                    recurso_id=str(recurso.id),
                )
            )

        for c in conflictos:
            inicio_local = c.inicio.astimezone(self.tz).strftime("%d-%m-%Y %H:%M")
            fin_local = c.fin.astimezone(self.tz).strftime("%d-%m-%Y %H:%M")
            incidencias.append(
                IncidenciaOut(
                    codigo="CONFLICTO_RESERVA",
                    mensaje=(
                        f"Ocupado por {c.tipo_reserva.value} "
                        f"({inicio_local} a {fin_local})"
                        + (f": {c.motivo}" if c.motivo else "")
                    ),
                    bloqueante=True,
                    recurso_tipo=tipo,
                    recurso_id=str(recurso.id),
                )
            )

        if bloqueo_estado or not doc_ok or not recurso.activo:
            libre_desde = None
        else:
            libre_desde = calcular_libre_desde(desde, intervalos)
        inicio_posible = (
            calcular_inicio_operativo(libre_desde, minutos_traslado)
            if libre_desde is not None
            else None
        )

        disponibles = (
            recurso.activo
            and not bloqueo_estado
            and doc_ok
            and not conflictos
            and (
                not exigir_libre_ahora
                or libre_desde is None
                or libre_desde <= desde
            )
        )

        proximas = self._reservas_out(
            sorted(reservas, key=lambda r: getattr(r.ventana, "lower", desde))[:5]
        )

        return RecursoOut(
            id=recurso.id,
            tipo=tipo,
            etiqueta=self._etiqueta(tipo, recurso),
            estado=estado,
            activo=recurso.activo,
            disponible=disponibles,
            libre_desde=libre_desde,
            inicio_operativo_posible=inicio_posible,
            documentos_ok=doc_ok,
            capacidad_carga_kg=getattr(recurso, "capacidad_carga_kg", None),
            volumen_m3=getattr(recurso, "volumen_m3", None),
            tipo_rampla=getattr(getattr(recurso, "tipo", None), "value", None),
            licencia_clase=getattr(recurso, "licencia_clase", None),
            incidencias=incidencias,
            advertencias=advertencias,
            documentos=documentos,
            proximas_reservas=proximas,
        )

    # ------------------------------------------------------------------
    # Listado / libre desde
    # ------------------------------------------------------------------
    def listar_recursos(
        self,
        tipo: TipoRecurso,
        *,
        desde: datetime,
        hasta: datetime,
        capacidad_min_kg: Decimal | None = None,
        tipo_rampla: TipoRampla | None = None,
        carga_peligrosa: bool = False,
        refrigerada: bool = False,
        solo_aptos: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> ListaRecursosOut:
        desde_u = a_utc(desde, "desde")
        hasta_u = a_utc(hasta, "hasta")
        if hasta_u <= desde_u:
            raise DatosInvalidos("La ventana debe tener hasta > desde.")
        if hasta_u - desde_u > timedelta(days=MAX_VENTANA_DIAS):
            raise DatosInvalidos(f"La ventana no puede superar {MAX_VENTANA_DIAS} días.")
        if limit < 1 or limit > 200:
            raise DatosInvalidos("limit debe estar entre 1 y 200.")
        if offset < 0:
            raise DatosInvalidos("offset no puede ser negativo.")

        ahora = ahora_utc()
        desde_efectivo = max(desde_u, ahora)
        fecha_limite = (
            (hasta_u + timedelta(minutes=self.empresa.buffer_operacional_min))
            .astimezone(self.tz)
            .date()
            + timedelta(days=self.empresa.dias_margen_documentos)
        )

        modelo = self._modelo(tipo)
        stmt = select(modelo).where(
            modelo.empresa_id == self.empresa.id,
            modelo.activo == True,
        )
        if tipo in (TipoRecurso.tracto, TipoRecurso.rampla) and capacidad_min_kg is not None:
            stmt = stmt.where(modelo.capacidad_carga_kg >= capacidad_min_kg)
        if tipo == TipoRecurso.rampla and tipo_rampla is not None:
            stmt = stmt.where(modelo.tipo == tipo_rampla)
        stmt = stmt.limit(MAX_RECURSOS)
        recursos = self.session.exec(stmt).all()

        docs_por_recurso, hall_por_recurso = self._documentos_por_recurso(
            tipo,
            recursos,
            carga_peligrosa=carga_peligrosa,
            refrigerada=refrigerada,
            fecha_limite=fecha_limite,
        )
        reservas_por_recurso = self._cargar_reservas(
            tipo, [r.id for r in recursos], desde=desde_efectivo
        )

        items: list[RecursoOut] = []
        for recurso in recursos:
            evaluado = self._evaluar_recurso(
                tipo,
                recurso,
                desde=desde_efectivo,
                hasta=hasta_u,
                fecha_limite=fecha_limite,
                documentos=docs_por_recurso.get(recurso.id, []),
                hallazgos_docs=hall_por_recurso.get(recurso.id, []),
                reservas=reservas_por_recurso.get(recurso.id, []),
            )
            if solo_aptos and not evaluado.disponible:
                continue
            items.append(evaluado)

        items.sort(
            key=lambda r: (
                not r.disponible,
                r.libre_desde or datetime.max.replace(tzinfo=ahora.tzinfo),
                r.etiqueta,
            )
        )
        total = len(items)
        pagina = items[offset : offset + limit]
        return ListaRecursosOut(
            items=pagina,
            paginacion=PaginacionOut(
                total=total, limit=limit, offset=offset, hay_mas=offset + limit < total
            ),
            desde=desde_efectivo,
            hasta=hasta_u,
            zona_horaria=self.empresa.zona_horaria,
        )

    def libre_desde(
        self,
        tipo: TipoRecurso,
        recurso_id: UUID,
        *,
        desde: datetime | None = None,
        minutos_traslado: int = 0,
    ) -> LibreDesdeOut:
        recurso = self._cargar_recurso(tipo, recurso_id)
        ahora = ahora_utc()
        desde_u = a_utc(desde or ahora, "desde")
        desde_efectivo = max(desde_u, ahora)
        hoy = ahora.astimezone(self.tz).date()
        fecha_limite = hoy + timedelta(days=self.empresa.dias_margen_documentos)

        requisitos = self._requisitos(tipo, carga_peligrosa=False, refrigerada=False)
        docs = self._cargar_documentos(tipo, [recurso.id]).get(recurso.id, {})
        documentos, hallazgos = self._evaluar_documentos(
            tipo, recurso.id, requisitos, docs, fecha_limite, hoy
        )
        reservas_map = self._cargar_reservas(tipo, [recurso.id], desde=desde_efectivo)
        reservas = reservas_map.get(recurso.id, [])
        intervalos = [i for r in reservas if (i := self._intervalo_de_reserva(r)) is not None]
        doc_ok = not any(h.bloqueante for h in hallazgos)

        bloqueo_estado = recurso.estado in (EstadoRecurso.baja, EstadoRecurso.bloqueado)
        libre = None if (bloqueo_estado or not doc_ok or not recurso.activo) else calcular_libre_desde(desde_efectivo, intervalos)
        inicio_posible = (
            calcular_inicio_operativo(libre, minutos_traslado) if libre is not None else None
        )
        disponible = bool(
            recurso.activo
            and not bloqueo_estado
            and doc_ok
            and libre is not None
            and libre <= desde_efectivo
        )

        incidencias = [
            IncidenciaOut(
                codigo=h.codigo,
                mensaje=h.mensaje,
                bloqueante=h.bloqueante,
                recurso_tipo=h.recurso_tipo,
                recurso_id=h.recurso_id,
            )
            for h in hallazgos
        ]
        advertencias = [
            IncidenciaOut(
                codigo=d.tipo.upper(),
                mensaje=f"{d.motivo}: vence {d.vence_en}",
                bloqueante=False,
                recurso_tipo=tipo,
                recurso_id=str(recurso.id),
            )
            for d in documentos
            if d.estado == "por_vencer"
        ]
        if bloqueo_estado:
            incidencias.append(
                IncidenciaOut(
                    codigo="RECURSO_BLOQUEADO",
                    mensaje=f"Estado operativo {recurso.estado.value}",
                    bloqueante=True,
                    recurso_tipo=tipo,
                    recurso_id=str(recurso.id),
                )
            )

        if disponible:
            mensaje = "Disponible en la fecha consultada."
        elif libre is not None:
            mensaje = f"Queda libre desde {libre.isoformat(timespec='minutes')}."
        elif not doc_ok:
            mensaje = "No asignable: documentación faltante o vencida."
        else:
            mensaje = "No asignable por estado operativo."

        return LibreDesdeOut(
            recurso_tipo=tipo,
            recurso_id=recurso.id,
            etiqueta=self._etiqueta(tipo, recurso),
            consultado_desde=desde_efectivo,
            libre_desde=libre,
            inicio_operativo_posible=inicio_posible,
            disponible=disponible,
            documentos_ok=doc_ok,
            documentos=documentos,
            incidencias=incidencias,
            advertencias=advertencias,
            proximas_reservas=self._reservas_out(reservas[:10]),
            mensaje=mensaje,
        )

    # ------------------------------------------------------------------
    # Validación de una asignación concreta
    # ------------------------------------------------------------------
    def _cargar_viaje(self, viaje_id: UUID, *, lock: bool = False) -> Viaje:
        stmt = select(Viaje).where(
            Viaje.id == viaje_id,
            Viaje.empresa_id == self.empresa.id,
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

    def listar_tarifas_nucleo(
        self,
        *,
        cliente_id: UUID | None = None,
    ) -> list[TarifaOpcionOut]:
        filtros = [
            Tarifa.empresa_id == self.empresa.id,
            Tarifa.activo == True,  # noqa: E712
        ]
        if cliente_id is not None:
            filtros.append(Tarifa.cliente_id == cliente_id)
        tarifas = self.session.exec(
            select(Tarifa)
            .where(*filtros)
            .order_by(Tarifa.cliente_id, Tarifa.codigo)
            .limit(500)
        ).all()
        return [
            TarifaOpcionOut(
                id=t.id,
                cliente_id=t.cliente_id,
                codigo=t.codigo,
                nombre=t.nombre,
                modalidad=t.modalidad,
                origen=t.origen,
                destino=t.destino,
                moneda=t.moneda,
                precio_unitario=t.precio_unitario,
                minimo_cobro=t.minimo_cobro,
                vigencia_desde=t.vigencia_desde,
                vigencia_hasta=t.vigencia_hasta,
                activo=t.activo,
            )
            for t in tarifas
        ]

    def listar_ocs_nucleo(
        self,
        *,
        cliente_id: UUID | None = None,
    ) -> list[OrdenCompraOpcionOut]:
        filtros = [
            OrdenCompra.empresa_id == self.empresa.id,
            OrdenCompra.estado != EstadoOC.anulada,
        ]
        if cliente_id is not None:
            filtros.append(OrdenCompra.cliente_id == cliente_id)
        ocs = self.session.exec(
            select(OrdenCompra)
            .where(*filtros)
            .order_by(OrdenCompra.fecha_emision.desc())
            .limit(500)
        ).all()
        return [
            OrdenCompraOpcionOut(
                id=o.id,
                cliente_id=o.cliente_id,
                numero_oc=o.numero_oc,
                monto_autorizado=o.monto_autorizado,
                monto_consumido=o.monto_consumido,
                sobregiro_autorizado=o.sobregiro_autorizado,
                moneda=o.moneda,
                vigencia_desde=o.vigencia_desde,
                vigencia_hasta=o.vigencia_hasta,
                estado=o.estado,
            )
            for o in ocs
        ]

    def crear_viaje(self, propuesta: ViajeCreateNucleo) -> ViajeResumenOut:
        """Crea y confirma un viaje del núcleo en una sola transacción.

        La OC es requisito de facturación, no de despacho: si falta, el viaje
        se crea y la UI advierte que no se podrá facturar hasta cargarla.
        """
        try:
            inicio = a_utc(propuesta.inicio_planificado, "inicio_planificado")
            a_utc(propuesta.fin_planificado, "fin_planificado")
            fecha_inicio_local = inicio.astimezone(self.tz).date()

            cliente = self.session.get(Cliente, propuesta.cliente_id)
            if cliente is None or cliente.empresa_id != self.empresa.id:
                raise RecursoNoEncontrado("Cliente no encontrado en la empresa.")
            if not cliente.activo:
                raise DatosInvalidos("El cliente está inactivo.")

            tarifa = self.session.get(Tarifa, propuesta.tarifa_id)
            if tarifa is None or tarifa.empresa_id != self.empresa.id:
                raise RecursoNoEncontrado("Tarifa no encontrada en la empresa.")
            if not tarifa.activo:
                raise DatosInvalidos(f"La tarifa {tarifa.codigo} está inactiva.")
            if tarifa.cliente_id != cliente.id:
                raise DatosInvalidos(f"La tarifa {tarifa.codigo} pertenece a otro cliente.")
            if fecha_inicio_local < tarifa.vigencia_desde:
                raise DatosInvalidos(
                    f"La tarifa {tarifa.codigo} comienza a regir el {tarifa.vigencia_desde}."
                )
            if tarifa.vigencia_hasta is not None and fecha_inicio_local > tarifa.vigencia_hasta:
                raise DatosInvalidos(
                    f"La tarifa {tarifa.codigo} venció el {tarifa.vigencia_hasta}."
                )

            try:
                flete = calcular_flete(
                    modalidad=tarifa.modalidad,
                    precio_unitario=tarifa.precio_unitario,
                    minimo_cobro=tarifa.minimo_cobro,
                    distancia_km=propuesta.distancia_km,
                    peso_bruto_kg=propuesta.peso_bruto_kg,
                    tiempo_estimado_h=propuesta.tiempo_estimado_h,
                )
            except ErrorTarifa as exc:
                raise DatosInvalidos(str(exc)) from exc

            total = flete + propuesta.monto_recargos
            oc = None
            if propuesta.orden_compra_id is not None:
                oc = self.session.get(OrdenCompra, propuesta.orden_compra_id)
                if oc is None or oc.empresa_id != self.empresa.id:
                    raise RecursoNoEncontrado("OC no encontrada en la empresa.")
                if oc.cliente_id != cliente.id:
                    raise DatosInvalidos(f"La OC {oc.numero_oc} pertenece a otro cliente.")
                if oc.estado == EstadoOC.anulada:
                    raise DatosInvalidos(f"La OC {oc.numero_oc} está anulada.")
                if oc.estado == EstadoOC.vencida:
                    raise DatosInvalidos(f"La OC {oc.numero_oc} está vencida.")
                if fecha_inicio_local < oc.vigencia_desde or fecha_inicio_local > oc.vigencia_hasta:
                    raise DatosInvalidos(
                        f"La OC {oc.numero_oc} no está vigente para la fecha del viaje."
                    )
                disponible = (
                    oc.monto_autorizado
                    + oc.sobregiro_autorizado
                    - oc.monto_consumido
                )
                if total > disponible:
                    raise DatosInvalidos(
                        f"La OC {oc.numero_oc} no tiene saldo suficiente: "
                        f"disponible ${disponible:,.0f}, viaje ${total:,.0f}."
                    )

            buffer = (
                propuesta.buffer_minutos
                if propuesta.buffer_minutos is not None
                else self.empresa.buffer_operacional_min
            )
            viaje = Viaje(
                empresa_id=self.empresa.id,
                cliente_id=cliente.id,
                orden_compra_id=oc.id if oc is not None else None,
                tarifa_id=tarifa.id,
                estado=EstadoViaje.confirmado,
                buffer_minutos=buffer,
                valor_flete_neto=flete,
                monto_recargos=propuesta.monto_recargos,
                moneda=tarifa.moneda,
                condiciones_pago_dias=(
                    propuesta.condiciones_pago_dias
                    if propuesta.condiciones_pago_dias is not None
                    else cliente.dias_pago
                ),
                **propuesta.model_dump(
                    exclude={
                        "cliente_id",
                        "orden_compra_id",
                        "tarifa_id",
                        "buffer_minutos",
                        "monto_recargos",
                        "condiciones_pago_dias",
                    }
                ),
            )
            self.session.add(viaje)
            self.session.commit()
            self.session.refresh(viaje)
            return self._resumen_viaje(viaje)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise

    def _resumen_viaje(self, viaje: Viaje) -> ViajeResumenOut:
        cliente = self.session.get(Cliente, viaje.cliente_id)
        oc = self.session.get(OrdenCompra, viaje.orden_compra_id) if viaje.orden_compra_id else None
        tarifa = self.session.get(Tarifa, viaje.tarifa_id) if viaje.tarifa_id else None
        tracto = self.session.get(Tracto, viaje.tracto_id) if viaje.tracto_id else None
        rampla = self.session.get(Rampla, viaje.rampla_id) if viaje.rampla_id else None
        chofer = self.session.get(Chofer, viaje.chofer_id) if viaje.chofer_id else None
        flete = viaje.monto_total_neto
        if flete is None:
            flete = (viaje.valor_flete_neto or Decimal("0")) + (
                viaje.monto_recargos or Decimal("0")
            )
        return ViajeResumenOut(
            id=viaje.id,
            numero_viaje=viaje.numero_viaje or "",
            estado=viaje.estado,
            cliente_id=viaje.cliente_id,
            cliente_nombre=cliente.razon_social if cliente else "-",
            orden_compra_id=viaje.orden_compra_id,
            oc_numero=oc.numero_oc if oc else None,
            tarifa_id=viaje.tarifa_id,
            tarifa_codigo=tarifa.codigo if tarifa else None,
            origen=viaje.origen_nombre,
            destino=viaje.destino_nombre,
            inicio_planificado=viaje.inicio_planificado,
            fin_planificado=viaje.fin_planificado,
            buffer_minutos=viaje.buffer_minutos,
            peso_bruto_kg=viaje.peso_bruto_kg,
            flete_total=flete,
            tracto_id=viaje.tracto_id,
            tracto_patente=tracto.patente if tracto else None,
            rampla_id=viaje.rampla_id,
            rampla_patente=rampla.patente if rampla else None,
            chofer_id=viaje.chofer_id,
            chofer_nombre=self._etiqueta(TipoRecurso.chofer, chofer) if chofer else None,
            carga_peligrosa=viaje.carga_peligrosa,
            refrigerada=viaje.refrigerada,
        )

    def listar_viajes(
        self,
        *,
        estado: EstadoViaje | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ListaViajesOut:
        """Viajes del núcleo para la mesa de despacho.

        Por defecto devuelve los estados que el despacho necesita ver:
        confirmados (por asignar) y asignados (reasignables).
        """
        if limit < 1 or limit > 200:
            raise DatosInvalidos("limit debe estar entre 1 y 200.")
        if offset < 0:
            raise DatosInvalidos("offset no puede ser negativo.")

        desde_u = a_utc(desde, "desde") if desde is not None else None
        hasta_u = a_utc(hasta, "hasta") if hasta is not None else None
        if desde_u is not None and hasta_u is not None and hasta_u <= desde_u:
            raise DatosInvalidos("La ventana debe tener hasta > desde.")

        estados = (
            [estado]
            if estado is not None
            else [EstadoViaje.confirmado, EstadoViaje.asignado]
        )
        filtros = [
            Viaje.empresa_id == self.empresa.id,
            Viaje.estado.in_(estados),
        ]
        if desde_u is not None:
            filtros.append(Viaje.inicio_planificado >= desde_u)
        if hasta_u is not None:
            filtros.append(Viaje.inicio_planificado <= hasta_u)

        total = self.session.exec(
            select(func.count(Viaje.id)).where(*filtros)
        ).one()
        viajes = self.session.exec(
            select(Viaje)
            .where(*filtros)
            .order_by(Viaje.inicio_planificado)
            .offset(offset)
            .limit(limit)
        ).all()

        def mapa(modelo, ids):
            limpios = {i for i in ids if i is not None}
            if not limpios:
                return {}
            return {
                obj.id: obj
                for obj in self.session.exec(
                    select(modelo).where(modelo.id.in_(limpios))
                ).all()
            }

        clientes = mapa(Cliente, [v.cliente_id for v in viajes])
        ocs = mapa(OrdenCompra, [v.orden_compra_id for v in viajes])
        tarifas = mapa(Tarifa, [v.tarifa_id for v in viajes])
        tractos = mapa(Tracto, [v.tracto_id for v in viajes])
        ramplas = mapa(Rampla, [v.rampla_id for v in viajes])
        choferes = mapa(Chofer, [v.chofer_id for v in viajes])

        items: list[ViajeResumenOut] = []
        for viaje in viajes:
            cliente = clientes.get(viaje.cliente_id)
            oc = ocs.get(viaje.orden_compra_id) if viaje.orden_compra_id else None
            tarifa = tarifas.get(viaje.tarifa_id) if viaje.tarifa_id else None
            tracto = tractos.get(viaje.tracto_id) if viaje.tracto_id else None
            rampla = ramplas.get(viaje.rampla_id) if viaje.rampla_id else None
            chofer = choferes.get(viaje.chofer_id) if viaje.chofer_id else None
            flete = viaje.monto_total_neto
            if flete is None:
                flete = (viaje.valor_flete_neto or Decimal("0")) + (
                    viaje.monto_recargos or Decimal("0")
                )
            items.append(
                ViajeResumenOut(
                    id=viaje.id,
                    numero_viaje=viaje.numero_viaje or "",
                    estado=viaje.estado,
                    cliente_id=viaje.cliente_id,
                    cliente_nombre=cliente.razon_social if cliente else "-",
                    orden_compra_id=viaje.orden_compra_id,
                    oc_numero=oc.numero_oc if oc else None,
                    tarifa_id=viaje.tarifa_id,
                    tarifa_codigo=tarifa.codigo if tarifa else None,
                    origen=viaje.origen_nombre,
                    destino=viaje.destino_nombre,
                    inicio_planificado=viaje.inicio_planificado,
                    fin_planificado=viaje.fin_planificado,
                    buffer_minutos=viaje.buffer_minutos,
                    peso_bruto_kg=viaje.peso_bruto_kg,
                    flete_total=flete,
                    tracto_id=viaje.tracto_id,
                    tracto_patente=tracto.patente if tracto else None,
                    rampla_id=viaje.rampla_id,
                    rampla_patente=rampla.patente if rampla else None,
                    chofer_id=viaje.chofer_id,
                    chofer_nombre=self._etiqueta(TipoRecurso.chofer, chofer)
                    if chofer
                    else None,
                    carga_peligrosa=viaje.carga_peligrosa,
                    refrigerada=viaje.refrigerada,
                )
            )

        return ListaViajesOut(
            items=items,
            total=int(total),
            limit=limit,
            offset=offset,
            hay_mas=offset + len(items) < int(total),
        )

    def _consumo_neto_oc(self, viaje: Viaje, oc: OrdenCompra) -> Decimal:
        """Consumo de la OC excluyendo el monto actual del viaje si ya está contado."""
        monto_actual = (viaje.valor_flete_neto or Decimal("0")) + (
            viaje.monto_recargos or Decimal("0")
        )
        if viaje.estado in (EstadoViaje.borrador, EstadoViaje.cotizado, EstadoViaje.anulado):
            return oc.monto_consumido or Decimal("0")
        return max(Decimal("0"), (oc.monto_consumido or Decimal("0")) - monto_actual)

    def validar_asignacion(
        self,
        viaje_id: UUID,
        propuesta: SolicitudAsignacion,
    ) -> ResultadoValidacion:
        viaje = self._cargar_viaje(viaje_id)
        if viaje.estado not in (EstadoViaje.confirmado, EstadoViaje.asignado):
            raise EstadoViajeInvalido(
                f"El viaje {viaje.numero_viaje} está en estado {viaje.estado.value}; "
                "solo se asigna desde 'confirmado' o se reasigna desde 'asignado'.",
                contexto={"estado": viaje.estado.value},
            )

        inicio = a_utc(propuesta.inicio_planificado, "inicio_planificado")
        fin_base = a_utc(
            propuesta.fin_estimado or propuesta.fin_planificado,
            "fin_estimado/fin_planificado",
        )
        buffer = (
            propuesta.buffer_minutos
            if propuesta.buffer_minutos is not None
            else (
                viaje.buffer_minutos
                if viaje.buffer_minutos is not None
                else self.empresa.buffer_operacional_min
            )
        )
        fin_reserva = fin_base + timedelta(minutes=buffer)
        fecha_limite = (
            fin_reserva.astimezone(self.tz).date()
            + timedelta(days=self.empresa.dias_margen_documentos)
        )
        ahora = ahora_utc()
        # "Libre desde" se mide desde ahora, no desde la fecha propuesta.
        # Así el despachador ve la disponibilidad real del recurso y el
        # traslado en vacío se puede comparar contra la hora de inicio.
        desde_disponibilidad = ahora

        tracto = self._cargar_recurso(TipoRecurso.tracto, propuesta.tracto_id)
        rampla = self._cargar_recurso(TipoRecurso.rampla, propuesta.rampla_id)
        chofer = self._cargar_recurso(TipoRecurso.chofer, propuesta.chofer_id)

        recursos: list[RecursoOut] = []
        documentos_todos: list[DocumentoOut] = []
        conflictos_todos: list[ConflictoOut] = []
        incidencias: list[IncidenciaOut] = []
        advertencias: list[IncidenciaOut] = []
        libres: list[datetime] = []

        for tipo, recurso in (
            (TipoRecurso.tracto, tracto),
            (TipoRecurso.rampla, rampla),
            (TipoRecurso.chofer, chofer),
        ):
            requisitos = self._requisitos(
                tipo,
                carga_peligrosa=viaje.carga_peligrosa,
                refrigerada=viaje.refrigerada,
            )
            docs_map = self._cargar_documentos(tipo, [recurso.id]).get(recurso.id, {})
            docs_out, hall_docs = self._evaluar_documentos(
                tipo,
                recurso.id,
                requisitos,
                docs_map,
                fecha_limite,
                ahora.astimezone(self.tz).date(),
            )
            reservas = self._cargar_reservas(
                tipo, [recurso.id], desde=desde_disponibilidad, excluir_viaje_id=viaje.id
            ).get(recurso.id, [])
            evaluado = self._evaluar_recurso(
                tipo,
                recurso,
                desde=desde_disponibilidad,
                hasta=fin_reserva,
                fecha_limite=fecha_limite,
                documentos=docs_out,
                hallazgos_docs=hall_docs,
                reservas=reservas,
                minutos_traslado=propuesta.minutos_traslado,
                ventana_desde=inicio,
                ventana_hasta=fin_reserva,
                exigir_libre_ahora=False,
            )
            recursos.append(evaluado)
            documentos_todos.extend(docs_out)
            conflictos_todos.extend(
                self._conflictos(tipo, recurso.id, reservas, inicio, fin_reserva)
            )
            incidencias.extend(evaluado.incidencias)
            advertencias.extend(evaluado.advertencias)
            if evaluado.libre_desde is not None:
                libres.append(evaluado.libre_desde)

        for recurso_evaluado in recursos:
            if (
                recurso_evaluado.inicio_operativo_posible is not None
                and inicio < recurso_evaluado.inicio_operativo_posible
            ):
                incidencias.append(
                    IncidenciaOut(
                        codigo="TRASLADO_INSUFICIENTE",
                        mensaje=(
                            f"{recurso_evaluado.etiqueta}: el recurso queda operativo "
                            f"desde {recurso_evaluado.inicio_operativo_posible.isoformat(timespec='minutes')}, "
                            f"después del inicio propuesto "
                            f"{inicio.isoformat(timespec='minutes')}. Ajuste la hora o el traslado."
                        ),
                        bloqueante=True,
                        recurso_tipo=recurso_evaluado.tipo,
                        recurso_id=str(recurso_evaluado.id),
                    )
                )

        hallazgos_carga = validar_carga(viaje, tracto, rampla, chofer)
        for h in hallazgos_carga:
            item = IncidenciaOut(
                codigo=h.codigo,
                mensaje=h.mensaje,
                bloqueante=h.bloqueante,
                recurso_tipo=h.recurso_tipo,
                recurso_id=h.recurso_id,
            )
            (incidencias if h.bloqueante else advertencias).append(item)

        cliente = self.session.get(Cliente, viaje.cliente_id)
        if cliente is None or cliente.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Cliente del viaje no encontrado en la empresa.")
        if not cliente.activo:
            incidencias.append(
                IncidenciaOut(
                    codigo="CLIENTE_INACTIVO",
                    mensaje=f"El cliente {cliente.razon_social} está inactivo",
                    bloqueante=True,
                )
            )

        tarifa = self.session.get(Tarifa, viaje.tarifa_id) if viaje.tarifa_id else None
        if tarifa is not None and tarifa.empresa_id != self.empresa.id:
            tarifa = None
        for h in validar_tarifa(viaje, tarifa, inicio.astimezone(self.tz).date()):
            (incidencias if h.bloqueante else advertencias).append(
                IncidenciaOut(
                    codigo=h.codigo,
                    mensaje=h.mensaje,
                    bloqueante=h.bloqueante,
                    recurso_tipo=h.recurso_tipo,
                    recurso_id=h.recurso_id,
                )
            )

        oc = self.session.get(OrdenCompra, viaje.orden_compra_id) if viaje.orden_compra_id else None
        if oc is not None and oc.empresa_id != self.empresa.id:
            oc = None
        consumo_neto = self._consumo_neto_oc(viaje, oc) if oc is not None else Decimal("0")
        for h in validar_oc(
            viaje,
            oc,
            cliente,
            self.empresa,
            consumo_neto=consumo_neto,
            fecha_local_viaje=inicio.astimezone(self.tz).date(),
            fecha_local_fin=fin_reserva.astimezone(self.tz).date(),
        ):
            (incidencias if h.bloqueante else advertencias).append(
                IncidenciaOut(
                    codigo=h.codigo,
                    mensaje=h.mensaje,
                    bloqueante=h.bloqueante,
                    recurso_tipo=h.recurso_tipo,
                    recurso_id=h.recurso_id,
                )
            )

        # Deduplicar por (codigo, recurso, mensaje) para que la UI no muestre
        # el mismo bloqueo tres veces por un documento compartido.
        def _dedup(items: Iterable[IncidenciaOut]) -> list[IncidenciaOut]:
            vistos: set[tuple[str, str | None, str]] = set()
            salida: list[IncidenciaOut] = []
            for item in items:
                clave = (item.codigo, item.recurso_id, item.mensaje)
                if clave in vistos:
                    continue
                vistos.add(clave)
                salida.append(item)
            return salida

        incidencias = _dedup(incidencias)
        advertencias = _dedup(advertencias)
        bloqueantes = [i for i in incidencias if i.bloqueante]
        apto = not bloqueantes and not conflictos_todos

        libre = max(libres) if libres and len(libres) == 3 else None
        inicio_posible = (
            calcular_inicio_operativo(libre, propuesta.minutos_traslado)
            if libre is not None
            else None
        )

        if apto:
            mensaje = "Apto para asignar: recursos, documentos, capacidad, tarifa y OC validados."
        else:
            bloqueos_no_conflicto = [
                i for i in bloqueantes if i.codigo != "CONFLICTO_RESERVA"
            ]
            mensaje = (
                f"No apto: {len(bloqueos_no_conflicto)} bloqueo(s) y "
                f"{len(conflictos_todos)} conflicto(s)."
            )

        return ResultadoValidacion(
            apto=apto,
            viaje_id=viaje.id,
            numero_viaje=viaje.numero_viaje or "",
            estado=viaje.estado,
            empresa_id=self.empresa.id,
            zona_horaria=self.empresa.zona_horaria,
            ventana=VentanaOut(inicio=inicio, fin=fin_reserva, incluye_buffer=True),
            recursos=recursos,
            documentos=documentos_todos,
            conflictos=conflictos_todos,
            incidencias=incidencias,
            advertencias=advertencias,
            libre_desde=libre,
            inicio_operativo_posible=inicio_posible,
            flete_total=(viaje.valor_flete_neto or Decimal("0"))
            + (viaje.monto_recargos or Decimal("0")),
            oc_numero=oc.numero_oc if oc is not None else None,
            tarifa_codigo=tarifa.codigo if tarifa is not None else None,
            mensaje=mensaje,
        )

    # ------------------------------------------------------------------
    # Confirmación transaccional
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

    def _tomar_locks_asesoria(self, propuesta: SolicitudAsignacion) -> None:
        claves = sorted(
            [
                f"nucleo:tracto:{propuesta.tracto_id}",
                f"nucleo:rampla:{propuesta.rampla_id}",
                f"nucleo:chofer:{propuesta.chofer_id}",
            ]
        )
        for clave in claves:
            self.session.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:clave, 0))"),
                {"clave": clave},
            )

    def confirmar_asignacion(
        self,
        viaje_id: UUID,
        propuesta: SolicitudAsignacion,
    ) -> AsignacionConfirmada:
        try:
            self._fijar_contexto_bd()
            viaje = self._cargar_viaje(viaje_id, lock=True)
            if viaje.estado not in (EstadoViaje.confirmado, EstadoViaje.asignado):
                raise EstadoViajeInvalido(
                    f"El viaje {viaje.numero_viaje} no se puede asignar desde "
                    f"el estado {viaje.estado.value}.",
                    contexto={"estado": viaje.estado.value},
                )

            cambia_recursos = (
                propuesta.tracto_id != viaje.tracto_id
                or propuesta.rampla_id != viaje.rampla_id
                or propuesta.chofer_id != viaje.chofer_id
            )
            nuevo_fin_estimado = (
                a_utc(propuesta.fin_estimado)
                if propuesta.fin_estimado is not None
                else None
            )
            buffer_propuesto = (
                propuesta.buffer_minutos
                if propuesta.buffer_minutos is not None
                else (
                    viaje.buffer_minutos
                    if viaje.buffer_minutos is not None
                    else self.empresa.buffer_operacional_min
                )
            )
            cambia_ventana = (
                a_utc(propuesta.inicio_planificado) != viaje.inicio_planificado
                or a_utc(propuesta.fin_planificado) != viaje.fin_planificado
                or nuevo_fin_estimado != viaje.fin_estimado
                or buffer_propuesto != viaje.buffer_minutos
            )
            if (
                viaje.estado == EstadoViaje.asignado
                and (cambia_recursos or cambia_ventana)
                and not (propuesta.motivo_reasignacion or "").strip()
            ):
                raise DatosInvalidos(
                    "La reasignación de un viaje ya asignado requiere "
                    "`motivo_reasignacion`. Queda registrada en la auditoría.",
                    contexto={"viaje_id": str(viaje.id)},
                )

            self._tomar_locks_asesoria(propuesta)
            validacion = self.validar_asignacion(viaje_id, propuesta)
            if not validacion.apto:
                raise ConflictoDisponibilidad(
                    validacion.mensaje,
                    contexto={
                        "viaje_id": str(viaje_id),
                        "numero_viaje": viaje.numero_viaje,
                    },
                    # `incidencias` ya contiene los conflictos con código
                    # CONFLICTO_RESERVA; `conflictos` queda como detalle
                    # estructurado en la respuesta de previsualización.
                    errores=[i.model_dump(mode="json") for i in validacion.incidencias],
                )

            buffer = (
                propuesta.buffer_minutos
                if propuesta.buffer_minutos is not None
                else (
                    viaje.buffer_minutos
                    if viaje.buffer_minutos is not None
                    else self.empresa.buffer_operacional_min
                )
            )
            resultado = self.session.execute(
                update(Viaje)
                .where(Viaje.id == viaje.id, Viaje.version == viaje.version)
                .values(
                    tracto_id=propuesta.tracto_id,
                    rampla_id=propuesta.rampla_id,
                    chofer_id=propuesta.chofer_id,
                    inicio_planificado=a_utc(propuesta.inicio_planificado),
                    fin_planificado=a_utc(propuesta.fin_planificado),
                    fin_estimado=nuevo_fin_estimado,
                    buffer_minutos=buffer,
                    estado=EstadoViaje.asignado,
                    motivo_reasignacion=(
                        propuesta.motivo_reasignacion
                        if (cambia_recursos or cambia_ventana)
                        else viaje.motivo_reasignacion
                    ),
                )
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "El viaje fue modificado por otro usuario. Recargue y vuelva a intentar.",
                    contexto={"viaje_id": str(viaje.id)},
                )

            self.session.commit()
            self.session.refresh(viaje)

            reservas = self.session.exec(
                select(ReservaRecurso)
                .where(
                    ReservaRecurso.viaje_id == viaje.id,
                    ReservaRecurso.activa == True,
                )
                .order_by(ReservaRecurso.recurso_tipo)
            ).all()
            audit_ok = (
                self.session.exec(
                    select(func.count(Auditoria.id)).where(
                        Auditoria.tabla == "nucleo.viajes",
                        Auditoria.registro_id == viaje.id,
                    )
                ).one()
                > 0
            )

            fin_asignacion = a_utc(
                propuesta.fin_estimado or propuesta.fin_planificado
            ) + timedelta(minutes=buffer)
            recursos_respuesta = validacion.recursos
            for recurso_asignado in recursos_respuesta:
                recurso_asignado.disponible = False
                recurso_asignado.libre_desde = fin_asignacion
                recurso_asignado.inicio_operativo_posible = (
                    fin_asignacion
                    + timedelta(minutes=propuesta.minutos_traslado)
                )

            return AsignacionConfirmada(
                viaje_id=viaje.id,
                numero_viaje=viaje.numero_viaje or "",
                estado=viaje.estado,
                version=viaje.version,
                empresa_id=self.empresa.id,
                recursos=recursos_respuesta,
                ventana=VentanaOut(
                    inicio=a_utc(propuesta.inicio_planificado),
                    fin=fin_asignacion,
                    incluye_buffer=True,
                ),
                reservas=self._reservas_out(reservas),
                libre_desde=fin_asignacion,
                inicio_operativo_posible=(
                    fin_asignacion
                    + timedelta(minutes=propuesta.minutos_traslado)
                ),
                audit_ok=bool(audit_ok),
            )
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except SQLAlchemyError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
