"""Consulta de auditoría visible (P0-12).

La tabla `nucleo.auditoria` es append-only. Este servicio solo lee, filtra y
pagina; nunca modifica ni borra registros.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import DatosInvalidos
from app.nucleo.models import Auditoria
from app.nucleo.schemas import (
    HistorialCambioOut,
    PaginaAuditoriaOut,
    TablaAuditoriaOut,
)


class ServicioAuditoria:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa

    def listar(
        self,
        *,
        tabla: str | None = None,
        registro_id: UUID | None = None,
        operacion: str | None = None,
        auth_id: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> PaginaAuditoriaOut:
        if limit < 1 or limit > 500:
            raise DatosInvalidos("limit debe estar entre 1 y 500.")
        if offset < 0:
            raise DatosInvalidos("offset no puede ser negativo.")
        if desde is not None and hasta is not None and hasta <= desde:
            raise DatosInvalidos("La fecha 'hasta' debe ser posterior a 'desde'.")
        if operacion is not None and operacion not in {"INSERT", "UPDATE", "DELETE"}:
            raise DatosInvalidos("operación no válida.")
        filtros = [Auditoria.empresa_id == self.empresa.id]
        if tabla:
            filtros.append(Auditoria.tabla == tabla)
        if registro_id is not None:
            filtros.append(Auditoria.registro_id == registro_id)
        if operacion is not None:
            filtros.append(Auditoria.operacion == operacion)
        if auth_id:
            filtros.append(Auditoria.auth_id == auth_id)
        if desde is not None:
            filtros.append(Auditoria.ocurrido_en >= desde)
        if hasta is not None:
            filtros.append(Auditoria.ocurrido_en <= hasta)
        total = int(
            self.session.exec(select(func.count(Auditoria.id)).where(*filtros)).one()
        )
        filas = self.session.exec(
            select(Auditoria)
            .where(*filtros)
            .order_by(Auditoria.ocurrido_en.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        items = [
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
        return PaginaAuditoriaOut(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            hay_mas=offset + len(items) < total,
        )

    def tablas(self) -> list[TablaAuditoriaOut]:
        filas = self.session.exec(
            select(Auditoria.tabla, func.count(Auditoria.id))
            .where(Auditoria.empresa_id == self.empresa.id)
            .group_by(Auditoria.tabla)
            .order_by(Auditoria.tabla)
        ).all()
        return [
            TablaAuditoriaOut(tabla=tabla, total=int(total))
            for tabla, total in filas
        ]
