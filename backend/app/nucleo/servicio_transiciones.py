"""Transiciones de estado de viaje para la oficina y anulación auditada.

La matriz de estados vive en `nucleo.transiciones_viaje`
(`supabase/migrations/0004_nucleo_operacional.sql:772-808`). Este servicio **no**
la duplica en Python: lee las filas de la empresa-agnóstica del catálogo y, si
la transición no existe, devuelve `EstadoViajeInvalido` con los destinos
permitidos. La garantía definitiva sigue en la base: el trigger
`nucleo.fn_viaje_transicion` (0004:1511-1547) vuelve a validar la misma tabla
dentro de la transacción y rechaza con `23514` lo que no esté en ella.

Alcance y límites
-----------------
- Solo viajes de la empresa del contexto (`empresa_id` resuelto en el servidor
  por `get_contexto_empresa` a partir de `X-Empresa-ID` + membresía).
- `facturado` y `cobrado` no se alcanzan por aquí: ese paso lo controla
  facturación (POD + OC) y el trigger `fn_viaje_facturacion`.
- `anulado` tampoco: tiene su propio endpoint/permiso y libera reservas con
  trazabilidad de motivo (ver `anular`).
- La PWA del conductor (`servicio_conductor.py`) mantiene su propio flujo y no
  pasa por este servicio.

Orden de escritura en la anulación
----------------------------------
1. `UPDATE` de `nucleo.reservas_recurso` (activa=false + motivo/actor/fecha).
2. `UPDATE` de `nucleo.viajes` (estado='anulado' + motivo_anulacion).

Ese orden importa: el trigger `fn_viaje_reservas` (0004:1621-1650) desactiva
todas las reservas activas del viaje en cada UPDATE de `viajes`, pero **sin**
motivo. Si se actualizara primero el viaje, las reservas quedarían inactivas
sin `cancelado_motivo`/`cancelado_por` y se perdería la trazabilidad.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    DatosInvalidos,
    EstadoViajeInvalido,
    RecursoNoEncontrado,
    traducir_integrity_error,
)
from app.nucleo.models import (
    EstadoViaje,
    ReservaRecurso,
    TransicionViaje,
    Viaje,
    ViajeEvento,
)
from app.nucleo.schemas import (
    SolicitudAnulacionViaje,
    SolicitudTransicionViaje,
    TransicionViajeOut,
)
from app.nucleo.tiempo import ahora_utc

# Estados que solo se alcanzan desde facturación (POD + OC), nunca por una
# transición manual de la mesa de despacho.
ESTADOS_SOLO_FACTURACION: frozenset[EstadoViaje] = frozenset(
    {EstadoViaje.facturado, EstadoViaje.cobrado}
)


class ServicioTransiciones:
    """Transiciones de oficina sobre `nucleo.viajes` (matriz en la base)."""

    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fijar_contexto_bd(self) -> None:
        """`nucleo.auth_id` para auditoría/triggers (0004, `fn_touch`)."""
        self.session.execute(
            text("select set_config('nucleo.auth_id', :auth_id, true)"),
            {"auth_id": self.contexto.auth_id},
        )
        if self.contexto.request_id:
            self.session.execute(
                text("select set_config('nucleo.request_id', :request_id, true)"),
                {"request_id": self.contexto.request_id},
            )

    def _cargar_viaje(self, viaje_id: UUID, *, lock: bool = False) -> Viaje:
        """Viaje de la empresa del contexto; 404 si es de otra empresa."""
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

    def _matriz_desde(self, origen: EstadoViaje) -> list[TransicionViaje]:
        """Filas de `nucleo.transiciones_viaje` con `estado_origen = origen`."""
        return list(
            self.session.exec(
                select(TransicionViaje).where(
                    TransicionViaje.estado_origen == origen
                )
            ).all()
        )

    @staticmethod
    def _destinos(transiciones: list[TransicionViaje], origen: EstadoViaje) -> list[str]:
        return sorted(
            t.estado_destino.value
            for t in transiciones
            if t.estado_origen == origen
        )

    def _respuesta(
        self,
        viaje: Viaje,
        origen: EstadoViaje,
        *,
        reservas_liberadas: int = 0,
    ) -> TransicionViajeOut:
        return TransicionViajeOut(
            viaje_id=viaje.id,
            numero_viaje=viaje.numero_viaje,
            estado=viaje.estado,
            estado_anterior=origen,
            version=viaje.version,
            reservas_liberadas=reservas_liberadas,
        )

    # ------------------------------------------------------------------
    # A. Transición de oficina (permiso operacion:escribir)
    # ------------------------------------------------------------------
    def transicionar(
        self,
        viaje_id: UUID,
        data: SolicitudTransicionViaje,
    ) -> TransicionViajeOut:
        viaje = self._cargar_viaje(viaje_id, lock=True)
        origen = viaje.estado
        destino = data.estado_destino
        motivo = (data.motivo or "").strip() or None

        if destino in ESTADOS_SOLO_FACTURACION:
            raise EstadoViajeInvalido(
                f"El paso a '{destino.value}' lo controla facturación "
                "(POD + OC), no la transición manual de oficina.",
                contexto={
                    "estado_origen": origen.value,
                    "estado_destino": destino.value,
                    "via": "facturacion",
                },
            )

        transiciones = self._matriz_desde(origen)
        transicion = next(
            (t for t in transiciones if t.estado_destino == destino), None
        )
        if transicion is None:
            raise EstadoViajeInvalido(
                f"Transición no permitida: {origen.value} → {destino.value}.",
                contexto={
                    "estado_origen": origen.value,
                    "estado_destino": destino.value,
                    "destinos_permitidos": self._destinos(transiciones, origen),
                },
            )

        # El motivo se exige según la matriz (hoy solo `* → anulado`), antes de
        # rechazar ese destino: la petición está incompleta de todos modos.
        if transicion.requiere_motivo and not motivo:
            raise DatosInvalidos(
                f"La transición {origen.value} → {destino.value} requiere motivo.",
                contexto={
                    "estado_origen": origen.value,
                    "estado_destino": destino.value,
                },
            )

        if destino == EstadoViaje.anulado:
            # La anulación exige otro permiso (`comercial:aprobar`) y libera
            # reservas con motivo. Permitirla aquí daría a despacho una vía
            # para anular saltándose ese control.
            raise EstadoViajeInvalido(
                "La anulación tiene su propio flujo: "
                "POST /api/v1/nucleo/viajes/{viaje_id}/anular "
                "(permiso comercial:aprobar, exige motivo y libera reservas).",
                contexto={
                    "estado_origen": origen.value,
                    "estado_destino": destino.value,
                    "via": "anulacion",
                },
            )

        # `fn_viaje_validar` (0004:1140-1144) exige tracto, rampla y chofer para
        # el estado 'asignado'. Un cambio de estado puro no los puede inventar:
        # la vía correcta es POST /viajes/{id}/asignar, que valida documentos,
        # ventana y crea las reservas en la misma transacción.
        if destino == EstadoViaje.asignado and None in (
            viaje.tracto_id,
            viaje.rampla_id,
            viaje.chofer_id,
        ):
            raise EstadoViajeInvalido(
                "El paso a 'asignado' requiere tracto, rampla y chofer: use "
                "POST /api/v1/nucleo/viajes/{viaje_id}/asignar.",
                contexto={
                    "estado_origen": origen.value,
                    "estado_destino": destino.value,
                    "via": "asignacion",
                },
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
                    "El viaje fue modificado por otro usuario. "
                    "Recargue e intente nuevamente.",
                    contexto={"viaje_id": str(viaje.id)},
                )
            self.session.add(
                ViajeEvento(
                    empresa_id=self.empresa.id,
                    viaje_id=viaje.id,
                    tipo="transicion_oficina",
                    descripcion=f"Oficina: {origen.value} → {destino.value}"
                    + (f" ({motivo})" if motivo else ""),
                    ocurrido_en=ahora_utc(),
                    payload={
                        "estado_origen": origen.value,
                        "estado_destino": destino.value,
                        "motivo": motivo,
                        "origen": "oficina",
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

        # Relee estado/version: `fn_viaje_transicion` y `fn_version` corren en
        # la base y son la fuente de verdad de lo que quedó guardado.
        self.session.refresh(viaje)
        return self._respuesta(viaje, origen)

    # ------------------------------------------------------------------
    # B. Anulación (permiso comercial:aprobar)
    # ------------------------------------------------------------------
    def anular(
        self,
        viaje_id: UUID,
        data: SolicitudAnulacionViaje,
        *,
        commit: bool = True,
    ) -> TransicionViajeOut:
        """Anula un viaje liberando reservas con trazabilidad.

        `commit=False` lo usa el buzón de aprobación: la anulación y el cambio
        de estado de la solicitud se confirman en una sola transacción
        (`agente/solicitudes.py`). En ese modo no se hace `rollback()` propio:
        la excepción propaga y el endpoint decide el rollback completo.
        """
        viaje = self._cargar_viaje(viaje_id, lock=True)
        origen = viaje.estado
        motivo = data.motivo

        transiciones = self._matriz_desde(origen)
        if not any(t.estado_destino == EstadoViaje.anulado for t in transiciones):
            raise EstadoViajeInvalido(
                f"El viaje {viaje.numero_viaje} está en '{origen.value}' y no "
                "admite anulación. Los estados cerrado/facturado/cobrado se "
                "corrigen con el flujo de facturación, no anulando el viaje.",
                contexto={
                    "estado_origen": origen.value,
                    "estado_destino": EstadoViaje.anulado.value,
                    "destinos_permitidos": self._destinos(transiciones, origen),
                },
            )

        self._fijar_contexto_bd()
        reservas_liberadas = 0
        try:
            # Primero las reservas: el trigger del viaje las desactivaría sin
            # motivo ni actor (ver docstring del módulo).
            reservas = self.session.execute(
                update(ReservaRecurso)
                .where(
                    ReservaRecurso.empresa_id == self.empresa.id,
                    ReservaRecurso.viaje_id == viaje.id,
                    ReservaRecurso.activa == True,  # noqa: E712
                )
                .values(
                    activa=False,
                    cancelado_motivo=motivo,
                    cancelado_por=self.contexto.auth_id,
                    cancelado_en=ahora_utc(),
                )
            )
            reservas_liberadas = max(reservas.rowcount or 0, 0)

            resultado = self.session.execute(
                update(Viaje)
                .where(
                    Viaje.id == viaje.id,
                    Viaje.empresa_id == self.empresa.id,
                    Viaje.version == viaje.version,
                )
                .values(
                    estado=EstadoViaje.anulado,
                    motivo_anulacion=motivo,
                )
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "El viaje fue modificado por otro usuario. "
                    "Recargue e intente nuevamente.",
                    contexto={"viaje_id": str(viaje.id)},
                )
            self.session.add(
                ViajeEvento(
                    empresa_id=self.empresa.id,
                    viaje_id=viaje.id,
                    tipo="anulado",
                    descripcion=(
                        f"Anulación de oficina: {origen.value} → anulado ({motivo})"
                    ),
                    ocurrido_en=ahora_utc(),
                    payload={
                        "estado_origen": origen.value,
                        "estado_destino": EstadoViaje.anulado.value,
                        "motivo": motivo,
                        "origen": "oficina",
                        "reservas_liberadas": reservas_liberadas,
                    },
                    auth_id=self.contexto.auth_id,
                )
            )
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except IntegrityError as exc:
            if commit:
                self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            if commit:
                self.session.rollback()
            raise

        self.session.refresh(viaje)
        return self._respuesta(
            viaje, origen, reservas_liberadas=reservas_liberadas
        )
