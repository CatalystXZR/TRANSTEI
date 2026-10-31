"""Resumen de IVA **débito** del núcleo (Ola B, módulo 2).

Decisión de alcance (`docs/negocio/retiro-legacy-modulos.md` §4.4 y
`docs/datos/retiro-legacy-modelo.md` §7.1):

- se porta solo el **débito fiscal** = Σ `nucleo.facturas_nucleo.iva` de las
  facturas no anuladas emitidas en el período. Es un dato almacenado y trazable
  a documentos.
- **no** se calcula el crédito fiscal ni el monto a pagar. El legacy lo estimaba
  con `Σ gasto.monto × tasa/(100+tasa)`, un supuesto no verificado (`P-09`) que
  puede subestimar el crédito en 16 % si el gasto está neto (CN-06). El arrastre
  de remanente y el cuadre con el F29 tampoco están definidos.
- **no** se descuentan notas de crédito: el documento no define el tratamiento
  y `P-06`/`P-09` siguen abiertas.
- la tasa vigente se lee de `nucleo.configuracion_empresa` (`iva_porcentaje`),
  no se hardcodea (`P-01`/`D-21`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlmodel import Session

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import DatosInvalidos
from app.nucleo.schemas import IvaResumenOut

ADVERTENCIA = (
    "Solo débito fiscal (IVA de facturas no anuladas). No incluye crédito "
    "fiscal ni monto a pagar: esas fórmulas dependen de P-09 (base bruta/neta "
    "del gasto, arrastre de remanente y cuadre con el F29) y no se implementan."
)


class ServicioIva:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa_id = contexto.empresa_id

    def tasa_vigente(self) -> Decimal | None:
        valor = self.session.execute(
            text("select nucleo.config_vigente(:empresa_id, 'iva_porcentaje')"),
            {"empresa_id": self.empresa_id},
        ).scalar_one()
        if valor is None:
            return None
        return Decimal(str(valor))

    def resumen(self, desde: date, hasta: date) -> IvaResumenOut:
        if desde > hasta:
            raise DatosInvalidos(
                "El rango es inválido: `desde` no puede ser posterior a `hasta`."
            )
        fila = self.session.execute(
            text(
                """
                select count(*) as facturas,
                       coalesce(sum(neto), 0) as base_neta,
                       coalesce(sum(iva), 0) as iva_debito
                  from nucleo.facturas_nucleo
                 where empresa_id = :empresa_id
                   and estado <> 'anulada'
                   and fecha_emision >= :desde
                   and fecha_emision <= :hasta
                """
            ),
            {"empresa_id": self.empresa_id, "desde": desde, "hasta": hasta},
        ).mappings().one()
        return IvaResumenOut(
            desde=desde,
            hasta=hasta,
            tasa_iva=self.tasa_vigente(),
            facturas=int(fila["facturas"]),
            base_neta=Decimal(fila["base_neta"]),
            iva_debito=Decimal(fila["iva_debito"]),
            advertencia=ADVERTENCIA,
        )
