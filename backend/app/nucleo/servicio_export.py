"""Export CSV de solo lectura del núcleo (Ola B, módulo 5).

Se porta el export del legacy **sin recálculo**: cada fila sale de lo almacenado
en `nucleo`, no de una comisión recalculada (defecto CN-09 del legacy). El
import CSV del legacy **no** se porta (`docs/negocio/retiro-legacy-modulos.md`
§7.4).

Formato de paridad con el legacy: UTF-8 con BOM, separador `;`, decimal con
coma. Protección contra inyección de fórmulas: toda celda de texto que empiece
con `=`, `+`, `-` o `@` se prefija con `'` (guía OWASP CSV injection).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal

from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlmodel import Session

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import DatosInvalidos

PREFIJOS_FORMULA = ("=", "+", "-", "@")
LIMITE_FILAS = 5000
_RE_MES = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")


def _celda(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, Decimal):
        texto = f"{valor:.2f}".replace(".", ",")
    elif isinstance(valor, date):
        texto = valor.isoformat()
    else:
        texto = str(valor)
    if texto.startswith(PREFIJOS_FORMULA):
        return "'" + texto
    return texto


def respuesta_csv(nombre: str, fieldnames: list[str], filas: list[dict]) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=fieldnames, delimiter=";", quoting=csv.QUOTE_MINIMAL,
        extrasaction="ignore",
    )
    writer.writeheader()
    for fila in filas:
        writer.writerow({clave: _celda(fila.get(clave)) for clave in fieldnames})
    contenido = "\ufeff" + buffer.getvalue()  # BOM para Excel
    return StreamingResponse(
        iter([contenido.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


class ServicioExport:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa_id = contexto.empresa_id

    # ------------------------------------------------------------------
    def liquidaciones(self, *, mes: str | None = None) -> StreamingResponse:
        filtros = ["l.empresa_id = :empresa_id"]
        params: dict = {"empresa_id": self.empresa_id, "limite": LIMITE_FILAS}
        if mes is not None:
            if not _RE_MES.match(mes):
                raise DatosInvalidos("El mes debe tener formato YYYY-MM.")
            filtros.append("l.mes = :mes")
            params["mes"] = mes
        filas = self.session.execute(
            text(
                f"""
                select c.rut, btrim(concat_ws(' ', c.nombre, c.apellido_paterno))
                           as nombre,
                       l.mes, l.sueldo_base, l.comision, l.bonos, l.descuentos,
                       l.anticipos, l.total_liquido, l.estado, l.emitida_en
                  from nucleo.liquidaciones l
                  join nucleo.choferes c
                    on c.empresa_id = l.empresa_id and c.id = l.chofer_id
                 where {' and '.join(filtros)}
                 order by l.mes desc, c.nombre, l.id
                 limit :limite
                """
            ),
            params,
        ).mappings().all()
        sufijo = f"_{mes}" if mes else ""
        return respuesta_csv(
            f"liquidaciones{sufijo}.csv",
            [
                "rut", "nombre", "mes", "sueldo_base", "comision", "bonos",
                "descuentos", "anticipos", "total_liquido", "estado",
                "emitida_en",
            ],
            [dict(f) for f in filas],
        )

    def viajes(
        self, *, desde: date | None = None, hasta: date | None = None
    ) -> StreamingResponse:
        if desde is not None and hasta is not None and desde > hasta:
            raise DatosInvalidos(
                "El rango es inválido: `desde` no puede ser posterior a `hasta`."
            )
        filtros = ["v.empresa_id = :empresa_id"]
        params: dict = {"empresa_id": self.empresa_id, "limite": LIMITE_FILAS}
        if desde is not None:
            filtros.append(
                "(v.inicio_planificado at time zone 'America/Santiago')::date >= :desde"
            )
            params["desde"] = desde
        if hasta is not None:
            filtros.append(
                "(v.inicio_planificado at time zone 'America/Santiago')::date <= :hasta"
            )
            params["hasta"] = hasta
        filas = self.session.execute(
            text(
                f"""
                select v.numero_viaje,
                       to_char(v.inicio_planificado at time zone 'America/Santiago',
                               'YYYY-MM-DD') as fecha_inicio,
                       to_char(v.fin_real at time zone 'America/Santiago',
                               'YYYY-MM-DD') as fecha_fin,
                       v.origen_nombre, v.destino_nombre, v.estado,
                       v.valor_flete_neto,
                       cl.razon_social as cliente,
                       btrim(concat_ws(' ', ch.nombre, ch.apellido_paterno))
                           as chofer
                  from nucleo.viajes v
                  join nucleo.clientes cl
                    on cl.empresa_id = v.empresa_id and cl.id = v.cliente_id
                  left join nucleo.choferes ch
                    on ch.empresa_id = v.empresa_id and ch.id = v.chofer_id
                 where {' and '.join(filtros)}
                 order by v.inicio_planificado, v.id
                 limit :limite
                """
            ),
            params,
        ).mappings().all()
        return respuesta_csv(
            "viajes.csv",
            [
                "numero_viaje", "fecha_inicio", "fecha_fin", "origen_nombre",
                "destino_nombre", "estado", "valor_flete_neto", "cliente",
                "chofer",
            ],
            [dict(f) for f in filas],
        )

    def facturas(self) -> StreamingResponse:
        filas = self.session.execute(
            text(
                """
                select f.numero_factura, cl.razon_social as cliente,
                       f.fecha_emision, f.fecha_vencimiento, f.neto, f.iva,
                       f.total, f.estado
                  from nucleo.facturas_nucleo f
                  join nucleo.clientes cl
                    on cl.empresa_id = f.empresa_id and cl.id = f.cliente_id
                 where f.empresa_id = :empresa_id
                 order by f.fecha_emision, f.numero_factura
                 limit :limite
                """
            ),
            {"empresa_id": self.empresa_id, "limite": LIMITE_FILAS},
        ).mappings().all()
        return respuesta_csv(
            "facturas.csv",
            [
                "numero_factura", "cliente", "fecha_emision", "fecha_vencimiento",
                "neto", "iva", "total", "estado",
            ],
            [dict(f) for f in filas],
        )
