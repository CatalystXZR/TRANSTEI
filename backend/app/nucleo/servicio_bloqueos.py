"""Bloqueos de recursos y agenda operativa (P0-04).

Un bloqueo es una reserva del libro único `nucleo.reservas_recurso` con
`tipo_reserva` distinto de `viaje`. La restricción EXCLUDE de PostgreSQL impide
que un bloqueo se solape con un viaje o con otro bloqueo del mismo recurso.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    ConflictoDisponibilidad,
    DatosInvalidos,
    RecursoNoEncontrado,
    traducir_integrity_error,
)
from app.nucleo.models import (
    Chofer,
    EstadoRecurso,
    Rampla,
    ReservaRecurso,
    TipoRecurso,
    TipoReserva,
    Tracto,
    Viaje,
)
from app.nucleo.schemas import (
    AgendaItemOut,
    AgendaOut,
    AgendaRecursoOut,
    BloqueoCreate,
    BloqueoOut,
    BloqueoUpdate,
    CancelarBloqueo,
)
from app.nucleo.tiempo import a_utc, ahora_utc, zona

MAX_BLOQUEO_DIAS = 365
MAX_RECURSOS_AGENDA = 300

MODELO_RECURSO = {
    TipoRecurso.tracto: Tracto,
    TipoRecurso.rampla: Rampla,
    TipoRecurso.chofer: Chofer,
}
CAMPO_RECURSO = {
    TipoRecurso.tracto: "tracto_id",
    TipoRecurso.rampla: "rampla_id",
    TipoRecurso.chofer: "chofer_id",
}


class ServicioBloqueos:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa
        self.tz = zona(self.empresa.zona_horaria)

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

    def _recurso(self, tipo: TipoRecurso, recurso_id: UUID) -> Any:
        modelo = MODELO_RECURSO[tipo]
        recurso = self.session.get(modelo, recurso_id)
        if recurso is None or recurso.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado(
                f"{tipo.value.capitalize()} no encontrado en la empresa."
            )
        if not recurso.activo:
            raise DatosInvalidos(
                f"{self._etiqueta(tipo, recurso)} está inactivo; no admite bloqueos."
            )
        if recurso.estado == EstadoRecurso.baja:
            raise DatosInvalidos(
                f"{self._etiqueta(tipo, recurso)} está dado de baja; no admite bloqueos."
            )
        return recurso

    def _etiqueta(self, tipo: TipoRecurso, recurso: Any) -> str:
        if tipo == TipoRecurso.chofer:
            partes = [recurso.nombre, recurso.apellido_paterno, recurso.apellido_materno]
            return " ".join(p for p in partes if p).strip()
        return getattr(recurso, "patente", str(recurso.id))

    def _get_bloqueo(self, bloqueo_id: UUID) -> ReservaRecurso:
        reserva = self.session.get(ReservaRecurso, bloqueo_id)
        if reserva is None or reserva.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Bloqueo no encontrado en la empresa.")
        if reserva.tipo_reserva == TipoReserva.viaje:
            raise DatosInvalidos("La reserva pertenece a un viaje, no a un bloqueo.")
        return reserva

    def _solapamiento(
        self,
        tipo: TipoRecurso,
        recurso_id: UUID,
        inicio: datetime,
        fin: datetime,
        *,
        excluir_id: UUID | None = None,
    ) -> ReservaRecurso | None:
        columna = getattr(ReservaRecurso, CAMPO_RECURSO[tipo])
        stmt = select(ReservaRecurso).where(
            ReservaRecurso.empresa_id == self.empresa.id,
            ReservaRecurso.recurso_tipo == tipo,
            ReservaRecurso.activa == True,  # noqa: E712
            columna == recurso_id,
            func.lower(ReservaRecurso.ventana) < fin,
            func.upper(ReservaRecurso.ventana) > inicio,
        )
        if excluir_id is not None:
            stmt = stmt.where(ReservaRecurso.id != excluir_id)
        return self.session.exec(stmt.limit(1)).first()

    def _out(self, reserva: ReservaRecurso) -> BloqueoOut:
        rango = reserva.ventana
        tipo = reserva.recurso_tipo
        recurso = self.session.get(MODELO_RECURSO[tipo], getattr(reserva, CAMPO_RECURSO[tipo]))
        return BloqueoOut(
            id=reserva.id,
            recurso_tipo=tipo,
            recurso_id=getattr(reserva, CAMPO_RECURSO[tipo]),
            etiqueta=self._etiqueta(tipo, recurso) if recurso else "-",
            inicio=rango.lower,
            fin=rango.upper,
            tipo_reserva=reserva.tipo_reserva,
            motivo=reserva.motivo,
            activa=reserva.activa,
            cancelado_motivo=reserva.cancelado_motivo,
            cancelado_por=reserva.cancelado_por,
            cancelado_en=reserva.cancelado_en,
            creado_por=reserva.creado_por,
            created_at=reserva.created_at,
            version=reserva.version,
        )

    def _validar_fechas(self, inicio: datetime, fin: datetime) -> tuple[datetime, datetime]:
        inicio_u = a_utc(inicio, "inicio")
        fin_u = a_utc(fin, "fin")
        if fin_u <= inicio_u:
            raise DatosInvalidos("El fin del bloqueo debe ser posterior al inicio.")
        if fin_u - inicio_u > timedelta(days=MAX_BLOQUEO_DIAS):
            raise DatosInvalidos(
                f"El bloqueo no puede superar {MAX_BLOQUEO_DIAS} días."
            )
        return inicio_u, fin_u

    def _validar_solapamiento(
        self,
        tipo: TipoRecurso,
        recurso_id: UUID,
        inicio: datetime,
        fin: datetime,
        *,
        excluir_id: UUID | None = None,
    ) -> None:
        choque = self._solapamiento(tipo, recurso_id, inicio, fin, excluir_id=excluir_id)
        if choque is not None:
            if choque.tipo_reserva == TipoReserva.viaje:
                viaje = self.session.get(Viaje, choque.viaje_id) if choque.viaje_id else None
                detalle = (
                    f"el viaje {viaje.numero_viaje}" if viaje is not None else "un viaje"
                )
            else:
                detalle = f"un bloqueo de {choque.tipo_reserva.value}"
            raise ConflictoDisponibilidad(
                f"El recurso ya está ocupado por {detalle} en esa ventana.",
                contexto={"reserva_id": str(choque.id)},
            )

    # ------------------------------------------------------------------
    # CRUD de bloqueos
    # ------------------------------------------------------------------
    def listar_bloqueos(
        self,
        *,
        desde: datetime,
        hasta: datetime,
        tipo_reserva: TipoReserva | None = None,
        recurso_tipo: TipoRecurso | None = None,
        recurso_id: UUID | None = None,
        incluir_inactivos: bool = False,
    ) -> list[BloqueoOut]:
        desde_u = a_utc(desde, "desde")
        hasta_u = a_utc(hasta, "hasta")
        if hasta_u <= desde_u:
            raise DatosInvalidos("La ventana debe tener hasta > desde.")
        filtros = [
            ReservaRecurso.empresa_id == self.empresa.id,
            ReservaRecurso.tipo_reserva != TipoReserva.viaje,
            func.lower(ReservaRecurso.ventana) < hasta_u,
            func.upper(ReservaRecurso.ventana) > desde_u,
        ]
        if not incluir_inactivos:
            filtros.append(ReservaRecurso.activa == True)  # noqa: E712
        if tipo_reserva is not None:
            filtros.append(ReservaRecurso.tipo_reserva == tipo_reserva)
        if recurso_tipo is not None:
            filtros.append(ReservaRecurso.recurso_tipo == recurso_tipo)
            if recurso_id is not None:
                filtros.append(
                    getattr(ReservaRecurso, CAMPO_RECURSO[recurso_tipo]) == recurso_id
                )
        reservas = self.session.exec(
            select(ReservaRecurso)
            .where(*filtros)
            .order_by(func.lower(ReservaRecurso.ventana))
            .limit(500)
        ).all()
        return [self._out(reserva) for reserva in reservas]

    def crear_bloqueo(self, data: BloqueoCreate) -> BloqueoOut:
        if data.tipo_reserva == TipoReserva.viaje:
            raise DatosInvalidos("Use la asignación de viaje para reservas de tipo viaje.")
        self._recurso(data.recurso_tipo, data.recurso_id)
        inicio, fin = self._validar_fechas(data.inicio, data.fin)
        self._validar_solapamiento(data.recurso_tipo, data.recurso_id, inicio, fin)
        self._fijar_contexto_bd()
        try:
            fila = self.session.execute(
                text(
                    """
                    insert into nucleo.reservas_recurso
                      (empresa_id, recurso_tipo, tracto_id, rampla_id, chofer_id,
                       ventana, tipo_reserva, motivo, activa, creado_por)
                    values
                      (:empresa_id, cast(:recurso_tipo as nucleo.tipo_recurso), :tracto_id, :rampla_id, :chofer_id,
                       tstzrange(:inicio, :fin, '[)'), cast(:tipo_reserva as nucleo.tipo_reserva), :motivo, true,
                       :creado_por)
                    returning id
                    """
                ),
                {
                    "empresa_id": self.empresa.id,
                    "recurso_tipo": data.recurso_tipo.value,
                    "tracto_id": data.recurso_id
                    if data.recurso_tipo == TipoRecurso.tracto
                    else None,
                    "rampla_id": data.recurso_id
                    if data.recurso_tipo == TipoRecurso.rampla
                    else None,
                    "chofer_id": data.recurso_id
                    if data.recurso_tipo == TipoRecurso.chofer
                    else None,
                    "inicio": inicio,
                    "fin": fin,
                    "tipo_reserva": data.tipo_reserva.value,
                    "motivo": data.motivo.strip(),
                    "creado_por": self.contexto.auth_id,
                },
            )
            reserva_id = fila.scalar_one()
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            error = traducir_integrity_error(exc)
            if error.codigo == "CONFLICTO_DISPONIBILIDAD":
                raise ConflictoDisponibilidad(
                    "El recurso ya está ocupado por otro viaje o bloqueo en esa ventana.",
                    contexto={"recurso_tipo": data.recurso_tipo.value},
                ) from exc
            raise error from exc
        except Exception:
            self.session.rollback()
            raise
        reserva = self.session.get(ReservaRecurso, reserva_id)
        if reserva is None:  # pragma: no cover - imposible tras el commit
            raise RecursoNoEncontrado("El bloqueo no pudo recuperarse.")
        return self._out(reserva)

    def actualizar_bloqueo(
        self, bloqueo_id: UUID, data: BloqueoUpdate
    ) -> BloqueoOut:
        reserva = self._get_bloqueo(bloqueo_id)
        if not reserva.activa:
            raise DatosInvalidos("El bloqueo está cancelado; no se puede editar.")
        version = data.version if data.version is not None else reserva.version
        if version != reserva.version:
            raise ConflictoConcurrencia(
                "El bloqueo fue modificado por otro usuario. Recargue e intente nuevamente."
            )
        if data.tipo_reserva == TipoReserva.viaje:
            raise DatosInvalidos("Use la asignación de viaje para reservas de tipo viaje.")
        self._recurso(data.recurso_tipo, data.recurso_id)
        inicio, fin = self._validar_fechas(data.inicio, data.fin)
        self._validar_solapamiento(
            data.recurso_tipo, data.recurso_id, inicio, fin, excluir_id=reserva.id
        )
        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                text(
                    """
                    update nucleo.reservas_recurso
                       set recurso_tipo = cast(:recurso_tipo as nucleo.tipo_recurso),
                           tracto_id = :tracto_id,
                           rampla_id = :rampla_id,
                           chofer_id = :chofer_id,
                           ventana = tstzrange(:inicio, :fin, '[)'),
                           tipo_reserva = cast(:tipo_reserva as nucleo.tipo_reserva),
                           motivo = :motivo
                     where id = :id and empresa_id = :empresa_id and version = :version
                    """
                ),
                {
                    "recurso_tipo": data.recurso_tipo.value,
                    "tracto_id": data.recurso_id
                    if data.recurso_tipo == TipoRecurso.tracto
                    else None,
                    "rampla_id": data.recurso_id
                    if data.recurso_tipo == TipoRecurso.rampla
                    else None,
                    "chofer_id": data.recurso_id
                    if data.recurso_tipo == TipoRecurso.chofer
                    else None,
                    "inicio": inicio,
                    "fin": fin,
                    "tipo_reserva": data.tipo_reserva.value,
                    "motivo": data.motivo.strip(),
                    "id": reserva.id,
                    "empresa_id": self.empresa.id,
                    "version": reserva.version,
                },
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "El bloqueo fue modificado por otro usuario."
                )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            error = traducir_integrity_error(exc)
            if error.codigo == "CONFLICTO_DISPONIBILIDAD":
                raise ConflictoDisponibilidad(
                    "El recurso ya está ocupado por otro viaje o bloqueo en esa ventana."
                ) from exc
            raise error from exc
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(reserva)
        return self._out(reserva)

    def cancelar_bloqueo(
        self, bloqueo_id: UUID, data: CancelarBloqueo
    ) -> BloqueoOut:
        reserva = self._get_bloqueo(bloqueo_id)
        if not reserva.activa:
            return self._out(reserva)
        self._fijar_contexto_bd()
        self.session.execute(
            update(ReservaRecurso)
            .where(
                ReservaRecurso.id == reserva.id,
                ReservaRecurso.empresa_id == self.empresa.id,
                ReservaRecurso.version == reserva.version,
            )
            .values(
                activa=False,
                cancelado_motivo=data.motivo.strip(),
                cancelado_por=self.contexto.auth_id,
                cancelado_en=ahora_utc(),
            )
        )
        self.session.commit()
        self.session.refresh(reserva)
        return self._out(reserva)

    # ------------------------------------------------------------------
    # Agenda
    # ------------------------------------------------------------------
    def _recursos(self, tipo: TipoRecurso) -> list[Any]:
        modelo = MODELO_RECURSO[tipo]
        return list(
            self.session.exec(
                select(modelo)
                .where(
                    modelo.empresa_id == self.empresa.id,
                    modelo.activo == True,  # noqa: E712
                )
                .order_by(modelo.id)
                .limit(MAX_RECURSOS_AGENDA)
            ).all()
        )

    def agenda(
        self,
        *,
        desde: datetime,
        hasta: datetime,
        recurso_tipo: TipoRecurso | None = None,
    ) -> AgendaOut:
        desde_u = a_utc(desde, "desde")
        hasta_u = a_utc(hasta, "hasta")
        if hasta_u <= desde_u:
            raise DatosInvalidos("La ventana debe tener hasta > desde.")
        if hasta_u - desde_u > timedelta(days=90):
            raise DatosInvalidos("La agenda no puede superar 90 días.")

        tipos = [recurso_tipo] if recurso_tipo is not None else list(TipoRecurso)
        recursos: list[AgendaRecursoOut] = []
        indice: dict[tuple[TipoRecurso, UUID], AgendaRecursoOut] = {}
        for tipo in tipos:
            for recurso in self._recursos(tipo):
                item = AgendaRecursoOut(
                    recurso_tipo=tipo,
                    recurso_id=recurso.id,
                    etiqueta=self._etiqueta(tipo, recurso),
                    estado=recurso.estado.value,
                    activo=recurso.activo,
                )
                recursos.append(item)
                indice[(tipo, recurso.id)] = item

        reservas = self.session.exec(
            select(ReservaRecurso)
            .where(
                ReservaRecurso.empresa_id == self.empresa.id,
                ReservaRecurso.activa == True,  # noqa: E712
                func.lower(ReservaRecurso.ventana) < hasta_u,
                func.upper(ReservaRecurso.ventana) > desde_u,
            )
            .order_by(func.lower(ReservaRecurso.ventana))
            .limit(5000)
        ).all()

        viaje_ids = {r.viaje_id for r in reservas if r.viaje_id is not None}
        viajes: dict[UUID, Viaje] = {}
        if viaje_ids:
            viajes = {
                v.id: v
                for v in self.session.exec(
                    select(Viaje).where(
                        Viaje.empresa_id == self.empresa.id,
                        Viaje.id.in_(viaje_ids),
                    )
                ).all()
            }

        total_bloqueos = 0
        total_viajes = 0
        for reserva in reservas:
            tipo = reserva.recurso_tipo
            recurso_id = getattr(reserva, CAMPO_RECURSO[tipo])
            destino = indice.get((tipo, recurso_id))
            if destino is None:
                continue
            rango = reserva.ventana
            viaje = viajes.get(reserva.viaje_id) if reserva.viaje_id else None
            es_viaje = reserva.tipo_reserva == TipoReserva.viaje
            if es_viaje:
                total_viajes += 1
            else:
                total_bloqueos += 1
            destino.items.append(
                AgendaItemOut(
                    id=reserva.id,
                    origen="viaje" if es_viaje else "bloqueo",
                    recurso_tipo=tipo,
                    recurso_id=recurso_id,
                    inicio=rango.lower,
                    fin=rango.upper,
                    tipo_reserva=reserva.tipo_reserva,
                    motivo=reserva.motivo,
                    viaje_id=reserva.viaje_id,
                    numero_viaje=viaje.numero_viaje if viaje else None,
                    estado_viaje=viaje.estado if viaje else None,
                    cancelable=not es_viaje,
                )
            )

        recursos.sort(key=lambda r: (r.recurso_tipo.value, r.etiqueta))
        return AgendaOut(
            desde=desde_u,
            hasta=hasta_u,
            zona_horaria=self.empresa.zona_horaria,
            recursos=recursos,
            total_bloqueos=total_bloqueos,
            total_viajes=total_viajes,
            mensaje=(
                f"{total_bloqueos} bloqueo(s) y {total_viajes} reserva(s) de viaje "
                "en la ventana consultada."
            ),
        )
