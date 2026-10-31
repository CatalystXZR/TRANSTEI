"""Liquidaciones, anticipos y ajustes del núcleo (migración 0025).

Paridad con el legacy (las tablas legacy `liquidaciones`, `anticipos_chofer` y
`ajustes_liquidacion` (schema `public`)) corregida según
`docs/negocio/retiro-legacy-modulos.md` §3.4–§3.5:

- comisión = % del chofer sobre la producción **facturada** del mes, atribuida
  por la primera emisión de factura no anulada (`R-01`/`R-05`); el redondeo es
  el canónico de la base, `nucleo.redondear_half_up(numeric, 2)` (HALF_UP).
  No se usa `quantize` de Python (defecto CN-04).
- `total_liquido` es columna generada en la base
  (`base + comisión + bonos − descuentos − anticipos`); el servicio no la escribe.
- emitir es un snapshot inmutable: fija comisión/ajustes/anticipos del período,
  imputa los anticipos pendientes y congela el documento. Repetir la emisión
  devuelve el mismo documento (idempotencia).
- anular exige motivo y sella autor; el documento anulado es terminal.
- anticipos y ajustes no se borran.

Lo que **no** se implementa (P-02, P-10, D-19, P-12 abiertas):
AFP/salud/cesantía/impuesto, arrastre de anticipos de meses cerrados, rechazo
de `total_liquido` negativo y reimputación al anular una liquidación.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
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
from app.nucleo.schemas import (
    AjusteCreate,
    AjusteOut,
    AnticipoCreate,
    AnticipoOut,
    LiquidacionCreate,
    LiquidacionOut,
)

_RE_MES = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
CERO = Decimal("0.00")

_COLUMNAS_LIQUIDACION = """
    l.id, l.chofer_id,
    btrim(concat_ws(' ', c.nombre, c.apellido_paterno)) as chofer_nombre,
    l.mes, l.sueldo_base, l.comision, l.bonos, l.descuentos, l.anticipos,
    l.total_liquido, l.estado, l.emitida_en, l.emitida_por, l.anulada_en,
    l.anulada_por, l.motivo_anulacion, l.notas, l.version, l.created_at
"""

_COLUMNAS_ANTICIPO = """
    id, chofer_id, fecha, monto, mes_imputacion, estado, liquidacion_id,
    motivo_anulacion, anulada_en, notas, version, created_at
"""

_COLUMNAS_AJUSTE = """
    id, chofer_id, mes, tipo, concepto, monto, estado, liquidacion_id,
    motivo_anulacion, anulada_en, version, created_at
"""


def rango_mes(mes: str) -> tuple[date, date]:
    """Ventana semiabierta `[inicio, fin)` del mes `YYYY-MM` (regla del núcleo)."""
    if not isinstance(mes, str) or not _RE_MES.match(mes):
        raise DatosInvalidos("El mes debe tener formato YYYY-MM.")
    anio, numero = map(int, mes.split("-"))
    inicio = date(anio, numero, 1)
    fin = date(anio + 1, 1, 1) if numero == 12 else date(anio, numero + 1, 1)
    return inicio, fin


class ServicioNomina:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa_id = contexto.empresa_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _chofer(self, chofer_id: UUID) -> dict:
        fila = self.session.execute(
            text(
                """
                select id, rut, nombre, apellido_paterno, sueldo_base,
                       porcentaje_comision
                  from nucleo.choferes
                 where empresa_id = :empresa_id and id = :chofer_id
                """
            ),
            {"empresa_id": self.empresa_id, "chofer_id": chofer_id},
        ).mappings().first()
        if fila is None:
            raise RecursoNoEncontrado("Chofer no encontrado en la empresa.")
        return dict(fila)

    def _comision(self, chofer: dict, mes: str) -> tuple[Decimal, Decimal, int]:
        """(comisión, base neta, nº de viajes) con la regla R-01/R-05.

        La atribución del mes es por `facturas_nucleo.fecha_emision` de la
        primera factura no anulada del viaje (SEC-001). Sin factura, se conserva
        el fallback legacy para viajes ya marcados `facturado`/`cobrado`,
        atribuidos por la fecha de fin (o inicio) del viaje.
        """
        inicio, fin = rango_mes(mes)
        fila = self.session.execute(
            text(
                """
                with candidatos as (
                    select v.id, v.valor_flete_neto, v.estado, v.fin_real,
                           v.inicio_planificado,
                           (select min(f.fecha_emision)
                              from nucleo.factura_viajes fv
                              join nucleo.facturas_nucleo f
                                on f.empresa_id = fv.empresa_id
                               and f.id = fv.factura_id
                             where fv.empresa_id = v.empresa_id
                               and fv.viaje_id = v.id
                               and f.estado <> 'anulada') as primera_emision
                      from nucleo.viajes v
                     where v.empresa_id = :empresa_id
                       and v.chofer_id = :chofer_id
                ), elegibles as (
                    select valor_flete_neto
                      from candidatos
                     where (primera_emision is not null
                            and primera_emision >= :inicio
                            and primera_emision < :fin)
                        or (primera_emision is null
                            and estado in ('facturado', 'cobrado')
                            and (coalesce(fin_real, inicio_planificado)
                                 at time zone 'America/Santiago')::date >= :inicio
                            and (coalesce(fin_real, inicio_planificado)
                                 at time zone 'America/Santiago')::date < :fin)
                )
                select coalesce(sum(valor_flete_neto), 0) as base,
                       count(*) as viajes,
                       nucleo.redondear_half_up(
                           coalesce(sum(valor_flete_neto), 0) * :porcentaje, 2
                       ) as comision
                  from elegibles
                """
            ),
            {
                "empresa_id": self.empresa_id,
                "chofer_id": chofer["id"],
                "inicio": inicio,
                "fin": fin,
                "porcentaje": chofer["porcentaje_comision"],
            },
        ).mappings().one()
        return (
            Decimal(fila["comision"]),
            Decimal(fila["base"]),
            int(fila["viajes"]),
        )

    def _ajustes_vigentes(self, chofer_id: UUID, mes: str) -> tuple[Decimal, Decimal]:
        filas = self.session.execute(
            text(
                """
                select tipo, coalesce(sum(monto), 0) as total
                  from nucleo.ajustes_liquidacion
                 where empresa_id = :empresa_id and chofer_id = :chofer_id
                   and mes = :mes and estado = 'vigente'
                 group by tipo
                """
            ),
            {"empresa_id": self.empresa_id, "chofer_id": chofer_id, "mes": mes},
        ).mappings()
        totales = {f["tipo"]: Decimal(f["total"]) for f in filas}
        return totales.get("bono", CERO), totales.get("descuento", CERO)

    def _anticipos_pendientes(self, chofer_id: UUID, mes: str) -> Decimal:
        total = self.session.execute(
            text(
                """
                select coalesce(sum(monto), 0)
                  from nucleo.anticipos_chofer
                 where empresa_id = :empresa_id and chofer_id = :chofer_id
                   and mes_imputacion = :mes and estado = 'pendiente'
                """
            ),
            {"empresa_id": self.empresa_id, "chofer_id": chofer_id, "mes": mes},
        ).scalar_one()
        return Decimal(total)

    def _obtener(self, liquidacion_id: UUID, *, bloquear: bool = False) -> dict:
        bloqueo = " for update of l" if bloquear else ""
        fila = self.session.execute(
            text(
                f"""
                select {_COLUMNAS_LIQUIDACION}
                  from nucleo.liquidaciones l
                  join nucleo.choferes c
                    on c.empresa_id = l.empresa_id and c.id = l.chofer_id
                 where l.empresa_id = :empresa_id and l.id = :id
                 {bloqueo}
                """
            ),
            {"empresa_id": self.empresa_id, "id": liquidacion_id},
        ).mappings().first()
        if fila is None:
            raise RecursoNoEncontrado("Liquidación no encontrada en la empresa.")
        return dict(fila)

    # ------------------------------------------------------------------
    # Liquidaciones
    # ------------------------------------------------------------------
    def listar_liquidaciones(
        self,
        *,
        mes: str | None = None,
        chofer_id: UUID | None = None,
        estado: str | None = None,
        limite: int = 200,
    ) -> list[LiquidacionOut]:
        filtros = ["l.empresa_id = :empresa_id"]
        params: dict = {"empresa_id": self.empresa_id, "limite": limite}
        if mes is not None:
            rango_mes(mes)  # valida el formato con el mismo criterio que la base
            filtros.append("l.mes = :mes")
            params["mes"] = mes
        if chofer_id is not None:
            filtros.append("l.chofer_id = :chofer_id")
            params["chofer_id"] = chofer_id
        if estado is not None:
            if estado not in {"borrador", "emitida", "anulada"}:
                raise DatosInvalidos("Estado de liquidación no válido.")
            filtros.append("l.estado = :estado")
            params["estado"] = estado
        filas = self.session.execute(
            text(
                f"""
                select {_COLUMNAS_LIQUIDACION}
                  from nucleo.liquidaciones l
                  join nucleo.choferes c
                    on c.empresa_id = l.empresa_id and c.id = l.chofer_id
                 where {' and '.join(filtros)}
                 order by l.mes desc, c.nombre, l.id
                 limit :limite
                """
            ),
            params,
        ).mappings()
        return [LiquidacionOut.model_validate(dict(f)) for f in filas]

    def crear_liquidacion(self, data: LiquidacionCreate) -> LiquidacionOut:
        chofer = self._chofer(data.chofer_id)
        comision, _base, _viajes = self._comision(chofer, data.mes)
        bonos, descuentos = self._ajustes_vigentes(data.chofer_id, data.mes)
        anticipos = self._anticipos_pendientes(data.chofer_id, data.mes)
        sueldo_base = (
            data.sueldo_base
            if data.sueldo_base is not None
            else Decimal(chofer["sueldo_base"])
        )
        try:
            fila = self.session.execute(
                text(
                    """
                    insert into nucleo.liquidaciones
                        (empresa_id, chofer_id, mes, sueldo_base, comision, bonos,
                         descuentos, anticipos, notas, created_by)
                    values
                        (:empresa_id, :chofer_id, :mes, :sueldo_base, :comision,
                         :bonos, :descuentos, :anticipos, :notas, :auth_id)
                    returning id
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "chofer_id": data.chofer_id,
                    "mes": data.mes,
                    "sueldo_base": sueldo_base,
                    "comision": comision,
                    "bonos": bonos,
                    "descuentos": descuentos,
                    "anticipos": anticipos,
                    "notas": data.notas,
                    "auth_id": self.contexto.auth_id,
                },
            ).scalar_one()
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            if _sqlstate(exc) == "23505":
                raise RegistroDuplicado(
                    "Ya existe una liquidación para ese chofer y mes.",
                    contexto={"chofer_id": str(data.chofer_id), "mes": data.mes},
                ) from exc
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return LiquidacionOut.model_validate(self._obtener(fila))

    def emitir(self, liquidacion_id: UUID) -> LiquidacionOut:
        """Congela la liquidación y la imputa.

        Idempotente: si ya está emitida devuelve el mismo documento sin volver a
        imputar. El `SELECT … FOR UPDATE` serializa dos emisiones concurrentes:
        la segunda espera y observa el estado `emitida`.
        """
        actual = self._obtener(liquidacion_id, bloquear=True)
        if actual["estado"] == "emitida":
            self.session.rollback()
            return LiquidacionOut.model_validate(actual)
        if actual["estado"] == "anulada":
            raise ReglaNegocioViolada(
                "La liquidación está anulada; no se puede emitir."
            )

        chofer = self._chofer(actual["chofer_id"])
        comision, _base, _viajes = self._comision(chofer, actual["mes"])
        try:
            # Imputación única: se toman los anticipos pendientes del período y
            # el total devuelto es el que se congela en la cabecera.
            anticipos = Decimal(
                self.session.execute(
                    text(
                        """
                        with tomados as (
                            update nucleo.anticipos_chofer
                               set estado = 'descontado',
                                   liquidacion_id = :liquidacion_id,
                                   updated_by = :auth_id
                             where empresa_id = :empresa_id
                               and chofer_id = :chofer_id
                               and mes_imputacion = :mes
                               and estado = 'pendiente'
                            returning monto
                        )
                        select coalesce(sum(monto), 0) from tomados
                        """
                    ),
                    {
                        "empresa_id": self.empresa_id,
                        "liquidacion_id": liquidacion_id,
                        "chofer_id": actual["chofer_id"],
                        "mes": actual["mes"],
                        "auth_id": self.contexto.auth_id,
                    },
                ).scalar_one()
            )
            bonos = CERO
            descuentos = CERO
            for fila in self.session.execute(
                text(
                    """
                    update nucleo.ajustes_liquidacion
                       set liquidacion_id = :liquidacion_id,
                           updated_by = :auth_id
                     where empresa_id = :empresa_id
                       and chofer_id = :chofer_id
                       and mes = :mes
                       and estado = 'vigente'
                       and liquidacion_id is null
                    returning tipo, monto
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "liquidacion_id": liquidacion_id,
                    "chofer_id": actual["chofer_id"],
                    "mes": actual["mes"],
                    "auth_id": self.contexto.auth_id,
                },
            ).mappings():
                if fila["tipo"] == "bono":
                    bonos += Decimal(fila["monto"])
                else:
                    descuentos += Decimal(fila["monto"])

            actualizado = self.session.execute(
                text(
                    """
                    update nucleo.liquidaciones
                       set comision = :comision,
                           bonos = :bonos,
                           descuentos = :descuentos,
                           anticipos = :anticipos,
                           estado = 'emitida',
                           updated_by = :auth_id
                     where empresa_id = :empresa_id and id = :id
                       and estado = 'borrador'
                    returning id
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "id": liquidacion_id,
                    "comision": comision,
                    "bonos": bonos,
                    "descuentos": descuentos,
                    "anticipos": anticipos,
                    "auth_id": self.contexto.auth_id,
                },
            ).first()
            if actualizado is None:  # pragma: no cover - el lock lo impide
                raise ReglaNegocioViolada(
                    "La liquidación cambió de estado durante la emisión."
                )
            fila = self._obtener(liquidacion_id)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return LiquidacionOut.model_validate(fila)

    def anular(self, liquidacion_id: UUID, motivo: str) -> LiquidacionOut:
        motivo = motivo.strip()
        if not motivo:
            raise DatosInvalidos("La anulación exige un motivo.")
        actual = self._obtener(liquidacion_id, bloquear=True)
        if actual["estado"] == "anulada":
            if (actual["motivo_anulacion"] or "") == motivo:
                self.session.rollback()
                return LiquidacionOut.model_validate(actual)
            raise ReglaNegocioViolada(
                "La liquidación ya está anulada con otro motivo."
            )
        try:
            fila = self.session.execute(
                text(
                    """
                    update nucleo.liquidaciones
                       set estado = 'anulada',
                           motivo_anulacion = :motivo,
                           updated_by = :auth_id
                     where empresa_id = :empresa_id and id = :id
                       and estado <> 'anulada'
                    returning id
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "id": liquidacion_id,
                    "motivo": motivo,
                    "auth_id": self.contexto.auth_id,
                },
            ).first()
            if fila is None:  # pragma: no cover - el lock lo impide
                raise ReglaNegocioViolada("La liquidación ya está anulada.")
            resultado = self._obtener(liquidacion_id)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return LiquidacionOut.model_validate(resultado)

    # ------------------------------------------------------------------
    # Anticipos
    # ------------------------------------------------------------------
    def listar_anticipos(
        self,
        *,
        chofer_id: UUID | None = None,
        mes: str | None = None,
        estado: str | None = None,
        limite: int = 200,
    ) -> list[AnticipoOut]:
        filtros = ["empresa_id = :empresa_id"]
        params: dict = {"empresa_id": self.empresa_id, "limite": limite}
        if chofer_id is not None:
            filtros.append("chofer_id = :chofer_id")
            params["chofer_id"] = chofer_id
        if mes is not None:
            rango_mes(mes)
            filtros.append("mes_imputacion = :mes")
            params["mes"] = mes
        if estado is not None:
            if estado not in {"pendiente", "descontado", "anulado"}:
                raise DatosInvalidos("Estado de anticipo no válido.")
            filtros.append("estado = :estado")
            params["estado"] = estado
        filas = self.session.execute(
            text(
                f"""
                select {_COLUMNAS_ANTICIPO}
                  from nucleo.anticipos_chofer
                 where {' and '.join(filtros)}
                 order by fecha desc, created_at desc, id
                 limit :limite
                """
            ),
            params,
        ).mappings()
        return [AnticipoOut.model_validate(dict(f)) for f in filas]

    def crear_anticipo(self, data: AnticipoCreate) -> AnticipoOut:
        self._chofer(data.chofer_id)
        try:
            fila = self.session.execute(
                text(
                    f"""
                    insert into nucleo.anticipos_chofer
                        (empresa_id, chofer_id, fecha, monto, mes_imputacion,
                         notas, created_by)
                    values
                        (:empresa_id, :chofer_id, :fecha, :monto, :mes_imputacion,
                         :notas, :auth_id)
                    returning {_COLUMNAS_ANTICIPO}
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "chofer_id": data.chofer_id,
                    "fecha": data.fecha,
                    "monto": data.monto,
                    "mes_imputacion": data.mes_imputacion,
                    "notas": data.notas,
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
        return AnticipoOut.model_validate(dict(fila))

    # ------------------------------------------------------------------
    # Ajustes
    # ------------------------------------------------------------------
    def listar_ajustes(
        self,
        *,
        chofer_id: UUID | None = None,
        mes: str | None = None,
        estado: str | None = None,
        limite: int = 200,
    ) -> list[AjusteOut]:
        filtros = ["empresa_id = :empresa_id"]
        params: dict = {"empresa_id": self.empresa_id, "limite": limite}
        if chofer_id is not None:
            filtros.append("chofer_id = :chofer_id")
            params["chofer_id"] = chofer_id
        if mes is not None:
            rango_mes(mes)
            filtros.append("mes = :mes")
            params["mes"] = mes
        if estado is not None:
            if estado not in {"vigente", "anulado"}:
                raise DatosInvalidos("Estado de ajuste no válido.")
            filtros.append("estado = :estado")
            params["estado"] = estado
        filas = self.session.execute(
            text(
                f"""
                select {_COLUMNAS_AJUSTE}
                  from nucleo.ajustes_liquidacion
                 where {' and '.join(filtros)}
                 order by mes desc, created_at desc, id
                 limit :limite
                """
            ),
            params,
        ).mappings()
        return [AjusteOut.model_validate(dict(f)) for f in filas]

    def crear_ajuste(self, data: AjusteCreate) -> AjusteOut:
        self._chofer(data.chofer_id)
        try:
            fila = self.session.execute(
                text(
                    f"""
                    insert into nucleo.ajustes_liquidacion
                        (empresa_id, chofer_id, mes, tipo, concepto, monto,
                         created_by)
                    values
                        (:empresa_id, :chofer_id, :mes, :tipo, :concepto, :monto,
                         :auth_id)
                    returning {_COLUMNAS_AJUSTE}
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "chofer_id": data.chofer_id,
                    "mes": data.mes,
                    "tipo": data.tipo,
                    "concepto": data.concepto,
                    "monto": data.monto,
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
        return AjusteOut.model_validate(dict(fila))


def _sqlstate(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
