"""PWA del conductor: perfil, mi viaje y transiciones operativas (P0-07).

El conductor se identifica por `auth_id` contra `nucleo.choferes`; nunca por un
`chofer_id` enviado desde el navegador. Las transiciones permitidas son solo
las del ciclo operativo hacia adelante.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    AccesoDenegado,
    ConflictoConcurrencia,
    EstadoViajeInvalido,
    RecursoNoEncontrado,
    traducir_integrity_error,
)
from app.nucleo.models import (
    Chofer,
    EstadoViaje,
    RolEmpresa,
    Viaje,
    ViajeEvento,
)
from app.nucleo.schemas import (
    CheckInOutConductor,
    ConductorPerfilOut,
    MiViajeOut,
    TransicionConductor,
)
from app.nucleo.servicio_expediente import ServicioExpediente
from app.nucleo.tiempo import ahora_utc

ESTADOS_ACTIVOS_CONDUCTOR = [
    EstadoViaje.asignado,
    EstadoViaje.en_carga,
    EstadoViaje.cargado,
    EstadoViaje.en_ruta,
    EstadoViaje.en_descarga,
    EstadoViaje.descargado,
    EstadoViaje.pod_pendiente,
]

TRANSICIONES_CONDUCTOR: dict[EstadoViaje, EstadoViaje] = {
    EstadoViaje.asignado: EstadoViaje.en_carga,
    EstadoViaje.en_carga: EstadoViaje.cargado,
    EstadoViaje.cargado: EstadoViaje.en_ruta,
    EstadoViaje.en_ruta: EstadoViaje.en_descarga,
    EstadoViaje.en_descarga: EstadoViaje.descargado,
    EstadoViaje.descargado: EstadoViaje.pod_pendiente,
}

SIGUIENTE_ACCION: dict[EstadoViaje, str] = {
    EstadoViaje.asignado: "Llegué al origen / iniciar carga",
    EstadoViaje.en_carga: "Carga completada",
    EstadoViaje.cargado: "Iniciar ruta",
    EstadoViaje.en_ruta: "Llegué al destino / iniciar descarga",
    EstadoViaje.en_descarga: "Descarga completada",
    EstadoViaje.descargado: "Registrar POD y cerrar entrega",
    EstadoViaje.pod_pendiente: "POD registrado; espere el cierre del despacho",
}

ROLES_PREVIEW = {RolEmpresa.admin, RolEmpresa.gerente, RolEmpresa.despacho}


class ServicioConductor:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa

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

    def _chofer(self, chofer_id: UUID | None = None) -> Chofer:
        try:
            auth_uuid = UUID(self.contexto.auth_id)
        except ValueError as exc:
            raise AccesoDenegado("El token no contiene un usuario válido.") from exc

        chofer = self.session.exec(
            select(Chofer).where(
                Chofer.empresa_id == self.empresa.id,
                Chofer.auth_id == auth_uuid,
                Chofer.activo == True,  # noqa: E712
            )
        ).first()
        if chofer is not None:
            return chofer

        if chofer_id is not None and self.contexto.rol in ROLES_PREVIEW:
            chofer = self.session.get(Chofer, chofer_id)
            if chofer is None or chofer.empresa_id != self.empresa.id:
                raise RecursoNoEncontrado("Chofer no encontrado en la empresa.")
            return chofer

        raise AccesoDenegado(
            "Su usuario no está vinculado a una ficha de chofer. "
            "Pida a administración que asocie su cuenta en Maestros → Choferes."
        )

    def _perfil(self, chofer: Chofer) -> ConductorPerfilOut:
        return ConductorPerfilOut(
            id=chofer.id,
            nombre=" ".join(
                p
                for p in [chofer.nombre, chofer.apellido_paterno, chofer.apellido_materno]
                if p
            ).strip(),
            rut=chofer.rut,
            telefono=chofer.telefono,
            licencia_clase=chofer.licencia_clase,
            numero_licencia=chofer.numero_licencia,
            estado=chofer.estado.value,
        )

    def _viaje_activo(self, chofer_id: UUID) -> Viaje | None:
        return self.session.exec(
            select(Viaje)
            .where(
                Viaje.empresa_id == self.empresa.id,
                Viaje.chofer_id == chofer_id,
                Viaje.estado.in_(ESTADOS_ACTIVOS_CONDUCTOR),
            )
            .order_by(Viaje.inicio_planificado)
            .limit(1)
        ).first()

    def mi_viaje(self, chofer_id: UUID | None = None) -> MiViajeOut:
        chofer = self._chofer(chofer_id)
        viaje = self._viaje_activo(chofer.id)
        if viaje is None:
            return MiViajeOut(
                chofer=self._perfil(chofer),
                viaje=None,
                mensaje="No tiene viajes activos asignados.",
                siguiente_accion=None,
                acciones_disponibles=[],
            )
        detalle = ServicioExpediente(self.session, self.contexto).obtener(viaje.id)
        siguiente_estado = TRANSICIONES_CONDUCTOR.get(viaje.estado)
        return MiViajeOut(
            chofer=self._perfil(chofer),
            viaje=detalle,
            mensaje=f"Viaje {detalle.numero_viaje} en estado {viaje.estado.value}.",
            siguiente_accion=SIGUIENTE_ACCION.get(viaje.estado),
            acciones_disponibles=(
                [siguiente_estado.value] if siguiente_estado is not None else []
            ),
        )

    def _get_viaje_propio(self, viaje_id: UUID, chofer: Chofer) -> Viaje:
        viaje = self.session.exec(
            select(Viaje).where(
                Viaje.id == viaje_id,
                Viaje.empresa_id == self.empresa.id,
            )
        ).first()
        if viaje is None:
            raise RecursoNoEncontrado("Viaje no encontrado en la empresa.")
        if viaje.chofer_id != chofer.id:
            raise AccesoDenegado("El viaje no está asignado a su ficha de chofer.")
        return viaje

    def _ejecutar_transicion(
        self,
        viaje: Viaje,
        destino: EstadoViaje,
        *,
        motivo: str | None,
        lat: Decimal | None,
        lon: Decimal | None,
        evento_tipo: str,
    ) -> MiViajeOut:
        esperado = TRANSICIONES_CONDUCTOR.get(viaje.estado)
        if esperado is None:
            raise EstadoViajeInvalido(
                f"El viaje {viaje.numero_viaje} está en {viaje.estado.value}; "
                "no tiene una acción de conductor disponible."
            )
        if destino != esperado:
            raise EstadoViajeInvalido(
                f"Desde {viaje.estado.value} el siguiente paso es {esperado.value}, "
                f"no {destino.value}."
            )
        valores: dict[str, object] = {"estado": destino}
        if destino == EstadoViaje.en_carga and viaje.inicio_real is None:
            valores["inicio_real"] = ahora_utc()
        if destino == EstadoViaje.descargado and viaje.fin_real is None:
            valores["fin_real"] = ahora_utc()

        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                update(Viaje)
                .where(
                    Viaje.id == viaje.id,
                    Viaje.empresa_id == self.empresa.id,
                    Viaje.version == viaje.version,
                )
                .values(**valores)
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "El viaje fue modificado por otro usuario. Recargue e intente nuevamente."
                )
            self.session.add(
                ViajeEvento(
                    empresa_id=self.empresa.id,
                    viaje_id=viaje.id,
                    tipo=evento_tipo,
                    descripcion=f"Conductor: {viaje.estado.value} → {destino.value}"
                    + (f" ({motivo})" if motivo else ""),
                    ocurrido_en=ahora_utc(),
                    payload={
                        "estado_origen": viaje.estado.value,
                        "estado_destino": destino.value,
                        "lat": str(lat) if lat is not None else None,
                        "lon": str(lon) if lon is not None else None,
                        "motivo": motivo,
                    },
                    auth_id=self.contexto.auth_id,
                )
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.mi_viaje()

    def transicion(
        self,
        viaje_id: UUID,
        data: TransicionConductor,
        *,
        chofer_id: UUID | None = None,
    ) -> MiViajeOut:
        chofer = self._chofer(chofer_id)
        viaje = self._get_viaje_propio(viaje_id, chofer)
        return self._ejecutar_transicion(
            viaje,
            data.estado_destino,
            motivo=data.motivo,
            lat=data.lat,
            lon=data.lon,
            evento_tipo="transicion_conductor",
        )

    def check_in(
        self,
        viaje_id: UUID,
        data: CheckInOutConductor,
        *,
        chofer_id: UUID | None = None,
    ) -> MiViajeOut:
        chofer = self._chofer(chofer_id)
        viaje = self._get_viaje_propio(viaje_id, chofer)
        if viaje.estado != EstadoViaje.asignado:
            raise EstadoViajeInvalido(
                f"El check-in solo aplica desde 'asignado'; el viaje está en {viaje.estado.value}."
            )
        return self._ejecutar_transicion(
            viaje,
            EstadoViaje.en_carga,
            motivo=data.nota,
            lat=data.lat,
            lon=data.lon,
            evento_tipo="check_in",
        )

    def check_out(
        self,
        viaje_id: UUID,
        data: CheckInOutConductor,
        *,
        chofer_id: UUID | None = None,
    ) -> MiViajeOut:
        chofer = self._chofer(chofer_id)
        viaje = self._get_viaje_propio(viaje_id, chofer)
        if viaje.estado != EstadoViaje.en_descarga:
            raise EstadoViajeInvalido(
                "El check-out solo aplica desde 'en_descarga'; "
                f"el viaje está en {viaje.estado.value}."
            )
        return self._ejecutar_transicion(
            viaje,
            EstadoViaje.descargado,
            motivo=data.nota,
            lat=data.lat,
            lon=data.lon,
            evento_tipo="check_out",
        )
