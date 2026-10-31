"""Mantenimiento preventivo del núcleo (migración 0024).

Paridad con el legacy (las tablas legacy `pautas_mantenimiento` + `mantenimientos` (schema `public`)),
con las correcciones de `docs/negocio/retiro-legacy-modulos.md` §5.4:

- `costo >= 0` y `km >= 0` se validan aquí y en la base;
- el intervalo se copia en un **snapshot** al registrar (editar la pauta no
  reescribe el histórico);
- el semáforo se lee de `nucleo.v_mantenimiento_estado` —una sola definición— y
  nunca se almacena;
- el registro no se borra: se anula con motivo (trigger de la base).

No se implementa el bloqueo del despacho por mantención vencida: el negocio no
lo definió (`RET-08`, abierto) y el legacy tampoco lo hacía.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    DatosInvalidos,
    RecursoNoEncontrado,
    RegistroDuplicado,
    ReglaNegocioViolada,
    traducir_integrity_error,
)
from app.nucleo.models import TipoRecurso
from app.nucleo.schemas import (
    EstadoMantenimientoOut,
    MantenimientoCreate,
    MantenimientoOut,
    PautaMantenimientoCreate,
    PautaMantenimientoOut,
)

ESTADOS_MANTENIMIENTO = {"realizado", "anulado"}
ESTADOS_SEMAFORO = {
    "sin_registro",
    "sin_odometro",
    "pendiente",
    "por_vencer",
    "ok",
}

_COLUMNAS_PAUTA = """
    id, recurso_tipo, item, intervalo_km, intervalo_meses, alerta_km, orden,
    activo, version, created_at, updated_at
"""

_COLUMNAS_MANTENIMIENTO = """
    id, pauta_id, tracto_id, rampla_id, fecha, km, costo, estado, observaciones,
    respaldo_url, intervalo_km_snapshot, intervalo_meses_snapshot,
    alerta_km_snapshot, motivo_anulacion, anulada_en, version, created_at
"""


def _mensaje_duplicado(exc: IntegrityError) -> str | None:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = (getattr(diag, "constraint_name", None) or "").lower()
    if "pautas" in constraint and "item" in constraint:
        return "Ya existe una pauta activa para ese ítem y tipo de recurso."
    return None


def _validar_tipo_recurso(recurso_tipo: TipoRecurso | None) -> None:
    if recurso_tipo is not None and recurso_tipo not in (
        TipoRecurso.tracto,
        TipoRecurso.rampla,
    ):
        raise DatosInvalidos("El mantenimiento solo aplica a tracto o rampla.")


class ServicioMantenimiento:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa_id = contexto.empresa_id

    # ------------------------------------------------------------------
    # Pautas
    # ------------------------------------------------------------------
    def listar_pautas(
        self,
        *,
        recurso_tipo: TipoRecurso | None = None,
        incluir_inactivas: bool = False,
        limite: int = 200,
    ) -> list[PautaMantenimientoOut]:
        _validar_tipo_recurso(recurso_tipo)
        filtros = ["empresa_id = :empresa_id"]
        params: dict = {"empresa_id": self.empresa_id, "limite": limite}
        if recurso_tipo is not None:
            filtros.append("recurso_tipo = cast(:recurso_tipo as nucleo.tipo_recurso)")
            params["recurso_tipo"] = recurso_tipo.value
        if not incluir_inactivas:
            filtros.append("activo")
        filas = self.session.execute(
            text(
                f"""
                select {_COLUMNAS_PAUTA}
                  from nucleo.pautas_mantenimiento
                 where {' and '.join(filtros)}
                 order by orden, lower(item), id
                 limit :limite
                """
            ),
            params,
        ).mappings()
        return [PautaMantenimientoOut.model_validate(dict(f)) for f in filas]

    def crear_pauta(self, data: PautaMantenimientoCreate) -> PautaMantenimientoOut:
        try:
            fila = self.session.execute(
                text(
                    f"""
                    insert into nucleo.pautas_mantenimiento
                        (empresa_id, recurso_tipo, item, intervalo_km,
                         intervalo_meses, alerta_km, orden, created_by)
                    values
                        (:empresa_id, cast(:recurso_tipo as nucleo.tipo_recurso),
                         :item, :intervalo_km, :intervalo_meses, :alerta_km, :orden,
                         :auth_id)
                    returning {_COLUMNAS_PAUTA}
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "recurso_tipo": data.recurso_tipo.value,
                    "item": data.item,
                    "intervalo_km": data.intervalo_km,
                    "intervalo_meses": data.intervalo_meses,
                    "alerta_km": data.alerta_km,
                    "orden": data.orden,
                    "auth_id": self.contexto.auth_id,
                },
            ).mappings().one()
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            mensaje = _mensaje_duplicado(exc)
            if mensaje is not None:
                raise RegistroDuplicado(mensaje) from exc
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return PautaMantenimientoOut.model_validate(dict(fila))

    # ------------------------------------------------------------------
    # Registros de mantención
    # ------------------------------------------------------------------
    def listar_mantenimientos(
        self,
        *,
        recurso_tipo: TipoRecurso | None = None,
        recurso_id: UUID | None = None,
        pauta_id: UUID | None = None,
        estado: str | None = None,
        desde: date | None = None,
        hasta: date | None = None,
        limite: int = 200,
    ) -> list[MantenimientoOut]:
        _validar_tipo_recurso(recurso_tipo)
        if estado is not None and estado not in ESTADOS_MANTENIMIENTO:
            raise DatosInvalidos("Estado de mantención no válido; use realizado o anulado.")
        filtros = ["empresa_id = :empresa_id"]
        params: dict = {"empresa_id": self.empresa_id, "limite": limite}
        if pauta_id is not None:
            filtros.append("pauta_id = :pauta_id")
            params["pauta_id"] = pauta_id
        if recurso_id is not None:
            if recurso_tipo is TipoRecurso.rampla:
                filtros.append("rampla_id = :recurso_id")
            elif recurso_tipo is TipoRecurso.tracto:
                filtros.append("tracto_id = :recurso_id")
            else:
                filtros.append("(tracto_id = :recurso_id or rampla_id = :recurso_id)")
            params["recurso_id"] = recurso_id
        elif recurso_tipo is TipoRecurso.rampla:
            filtros.append("rampla_id is not null")
        elif recurso_tipo is TipoRecurso.tracto:
            filtros.append("tracto_id is not null")
        if estado is not None:
            filtros.append("estado = :estado")
            params["estado"] = estado
        if desde is not None:
            filtros.append("fecha >= :desde")
            params["desde"] = desde
        if hasta is not None:
            filtros.append("fecha <= :hasta")
            params["hasta"] = hasta
        filas = self.session.execute(
            text(
                f"""
                select {_COLUMNAS_MANTENIMIENTO}
                  from nucleo.mantenimientos
                 where {' and '.join(filtros)}
                 order by fecha desc, created_at desc, id
                 limit :limite
                """
            ),
            params,
        ).mappings()
        return [MantenimientoOut.model_validate(dict(f)) for f in filas]

    def _pauta(self, pauta_id: UUID) -> dict:
        fila = self.session.execute(
            text(
                """
                select id, recurso_tipo, intervalo_km, intervalo_meses, alerta_km,
                       activo
                  from nucleo.pautas_mantenimiento
                 where empresa_id = :empresa_id and id = :pauta_id
                """
            ),
            {"empresa_id": self.empresa_id, "pauta_id": pauta_id},
        ).mappings().first()
        if fila is None:
            raise RecursoNoEncontrado("Pauta de mantenimiento no encontrada en la empresa.")
        if not fila["activo"]:
            raise ReglaNegocioViolada(
                "La pauta está inactiva; cree una pauta nueva antes de registrar."
            )
        return dict(fila)

    def _validar_recurso(self, data: MantenimientoCreate, pauta: dict) -> None:
        tipo_pauta = pauta["recurso_tipo"]
        if tipo_pauta == "tracto" and data.tracto_id is None:
            raise DatosInvalidos("La pauta es de tracto; envíe tracto_id.")
        if tipo_pauta == "rampla" and data.rampla_id is None:
            raise DatosInvalidos("La pauta es de rampla; envíe rampla_id.")

        if data.tracto_id is not None:
            fila = self.session.execute(
                text(
                    "select km_actual from nucleo.tractos"
                    " where empresa_id = :empresa_id and id = :id"
                ),
                {"empresa_id": self.empresa_id, "id": data.tracto_id},
            ).mappings().first()
            if fila is None:
                raise RecursoNoEncontrado("Tracto no encontrado en la empresa.")
            km_actual = fila["km_actual"]
            # Coherencia del odómetro: un registro no puede quedar por debajo
            # del km ya conocido del tracto (el trigger solo lo sube).
            if km_actual is not None and data.km < km_actual:
                raise DatosInvalidos(
                    "El km registrado no puede ser menor al odómetro actual del tracto.",
                    contexto={"km_actual": str(km_actual), "km": str(data.km)},
                )
        if data.rampla_id is not None:
            existe = self.session.execute(
                text(
                    "select 1 from nucleo.ramplas"
                    " where empresa_id = :empresa_id and id = :id"
                ),
                {"empresa_id": self.empresa_id, "id": data.rampla_id},
            ).first()
            if existe is None:
                raise RecursoNoEncontrado("Rampla no encontrada en la empresa.")

    def crear_mantenimiento(self, data: MantenimientoCreate) -> MantenimientoOut:
        pauta = self._pauta(data.pauta_id)
        self._validar_recurso(data, pauta)
        try:
            fila = self.session.execute(
                text(
                    f"""
                    insert into nucleo.mantenimientos
                        (empresa_id, pauta_id, tracto_id, rampla_id, fecha, km, costo,
                         observaciones, respaldo_url, created_by)
                    values
                        (:empresa_id, :pauta_id, :tracto_id, :rampla_id, :fecha, :km,
                         :costo, :observaciones, :respaldo_url, :auth_id)
                    returning {_COLUMNAS_MANTENIMIENTO}
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "pauta_id": data.pauta_id,
                    "tracto_id": data.tracto_id,
                    "rampla_id": data.rampla_id,
                    "fecha": data.fecha,
                    "km": data.km,
                    "costo": data.costo,
                    "observaciones": data.observaciones,
                    "respaldo_url": data.respaldo_url,
                    "auth_id": self.contexto.auth_id,
                },
            ).mappings().one()
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return MantenimientoOut.model_validate(dict(fila))

    # ------------------------------------------------------------------
    # Semáforo (vista única, 0024)
    # ------------------------------------------------------------------
    def estado(
        self,
        *,
        recurso_tipo: TipoRecurso | None = None,
        recurso_id: UUID | None = None,
        estado: str | None = None,
        limite: int = 500,
    ) -> list[EstadoMantenimientoOut]:
        _validar_tipo_recurso(recurso_tipo)
        if estado is not None and estado not in ESTADOS_SEMAFORO:
            raise DatosInvalidos(
                "Estado de semáforo no válido; use "
                + ", ".join(sorted(ESTADOS_SEMAFORO))
                + "."
            )
        filtros = ["empresa_id = :empresa_id"]
        params: dict = {"empresa_id": self.empresa_id, "limite": limite}
        if recurso_tipo is not None:
            filtros.append("recurso_tipo = cast(:recurso_tipo as nucleo.tipo_recurso)")
            params["recurso_tipo"] = recurso_tipo.value
        if recurso_id is not None:
            filtros.append("recurso_id = :recurso_id")
            params["recurso_id"] = recurso_id
        if estado is not None:
            filtros.append("estado = :estado")
            params["estado"] = estado
        filas = self.session.execute(
            text(
                f"""
                select recurso_tipo, recurso_id, pauta_id, item, ultimo_km,
                       ultima_fecha, intervalo_km, alerta_km, proximo_km,
                       proxima_fecha, restante_km, estado
                  from nucleo.v_mantenimiento_estado
                 where {' and '.join(filtros)}
                 order by case estado
                            when 'pendiente' then 1
                            when 'por_vencer' then 2
                            when 'sin_registro' then 3
                            when 'sin_odometro' then 4
                            else 5
                          end,
                          restante_km nulls last, recurso_tipo, recurso_id, item
                 limit :limite
                """
            ),
            params,
        ).mappings()
        return [EstadoMantenimientoOut.model_validate(dict(f)) for f in filas]

    # ------------------------------------------------------------------
    # Anulación (el histórico no se borra)
    # ------------------------------------------------------------------
    def anular_mantenimiento(self, mantenimiento_id: UUID, motivo: str) -> MantenimientoOut:
        motivo = motivo.strip()
        if not motivo:
            raise DatosInvalidos("La anulación exige un motivo.")
        try:
            fila = self.session.execute(
                text(
                    f"""
                    update nucleo.mantenimientos
                       set estado = 'anulado',
                           motivo_anulacion = :motivo,
                           updated_by = :auth_id
                     where empresa_id = :empresa_id and id = :id
                       and estado = 'realizado'
                    returning {_COLUMNAS_MANTENIMIENTO}
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "id": mantenimiento_id,
                    "motivo": motivo,
                    "auth_id": self.contexto.auth_id,
                },
            ).mappings().first()
            if fila is None:
                actual = self.session.execute(
                    text(
                        "select estado from nucleo.mantenimientos"
                        " where empresa_id = :empresa_id and id = :id"
                    ),
                    {"empresa_id": self.empresa_id, "id": mantenimiento_id},
                ).mappings().first()
                if actual is None:
                    raise RecursoNoEncontrado(
                        "Registro de mantención no encontrado en la empresa."
                    )
                raise ReglaNegocioViolada(
                    f"El registro está {actual['estado']}; un anulado es terminal."
                )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return MantenimientoOut.model_validate(dict(fila))
