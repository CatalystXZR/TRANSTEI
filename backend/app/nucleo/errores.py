"""Errores de dominio y traducción de violaciones PostgreSQL.

El servicio NUNCA confía en su propia validación como única defensa: la base
puede rechazar una asignación por una restricción EXCLUDE, un CHECK o una
transición. Aquí se traduce ese rechazo a una respuesta 409/422 explicable,
sin filtrar SQL interno al cliente.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class ErrorNucleo(Exception):
    status_code: int = 400
    codigo: str = "ERROR_NUCLEO"

    def __init__(
        self,
        mensaje: str,
        *,
        contexto: dict[str, Any] | None = None,
        errores: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.contexto = contexto or {}
        self.errores = errores or []

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "codigo": self.codigo,
            "mensaje": self.mensaje,
        }
        if self.contexto:
            body["contexto"] = self.contexto
        if self.errores:
            body["errores"] = self.errores
        return body


class DatosInvalidos(ErrorNucleo):
    status_code = 422
    codigo = "DATOS_INVALIDOS"


class AccesoDenegado(ErrorNucleo):
    status_code = 403
    codigo = "ACCESO_DENEGADO"


class RecursoNoEncontrado(ErrorNucleo):
    status_code = 404
    codigo = "RECURSO_NO_ENCONTRADO"


class EmpresaNoEncontrada(ErrorNucleo):
    status_code = 404
    codigo = "EMPRESA_NO_ENCONTRADA"


class EstadoViajeInvalido(ErrorNucleo):
    status_code = 409
    codigo = "ESTADO_VIAJE_INVALIDO"


class ConflictoDisponibilidad(ErrorNucleo):
    status_code = 409
    codigo = "CONFLICTO_DISPONIBILIDAD"


class DocumentoNoVigente(ErrorNucleo):
    status_code = 409
    codigo = "DOCUMENTO_NO_VIGENTE"


class CapacidadInsuficiente(ErrorNucleo):
    status_code = 422
    codigo = "CAPACIDAD_INSUFICIENTE"


class OCInvalida(ErrorNucleo):
    status_code = 422
    codigo = "OC_INVALIDA"


class ConflictoConcurrencia(ErrorNucleo):
    status_code = 409
    codigo = "CONFLICTO_CONCURRENCIA"


class RegistroDuplicado(ErrorNucleo):
    status_code = 409
    codigo = "REGISTRO_DUPLICADO"


class ErrorPersistencia(ErrorNucleo):
    status_code = 500
    codigo = "ERROR_PERSISTENCIA"


class ReglaNegocioViolada(ErrorNucleo):
    status_code = 409
    codigo = "REGLA_NEGOCIO_VIOLADA"


_MENSAJES_EXCLUSION = {
    "ex_reserva_tracto": "El tracto ya tiene una reserva activa en esa ventana.",
    "ex_reserva_rampla": "La rampla ya tiene una reserva activa en esa ventana.",
    "ex_reserva_chofer": "El chofer ya tiene una reserva activa en esa ventana.",
}


def _sqlstate(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def _constraint(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def _mensaje_primario(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    return getattr(diag, "message_primary", None)


def traducir_integrity_error(exc: IntegrityError) -> ErrorNucleo:
    state = _sqlstate(exc)
    constraint = _constraint(exc)
    mensaje_db = _mensaje_primario(exc)

    if state == "23P01" or (constraint or "").startswith("ex_reserva_"):
        mensaje = _MENSAJES_EXCLUSION.get(
            constraint, "El recurso ya está ocupado en la ventana solicitada."
        )
        return ConflictoDisponibilidad(
            mensaje,
            contexto={"constraint": constraint},
        )

    if state == "23505":
        c = (constraint or "").lower()
        if "rut" in c:
            mensaje = "Ya existe un registro con ese RUT en la empresa."
        elif "patente" in c:
            mensaje = "Ya existe un tracto o rampla con esa patente en la empresa."
        elif "licencia" in c:
            mensaje = "Ya existe un chofer con ese número de licencia en la empresa."
        elif "numero_oc" in c:
            mensaje = "Ya existe una OC con ese número para el cliente."
        elif "codigo" in c:
            mensaje = "Ya existe un registro con ese código para el cliente."
        else:
            mensaje = "Ya existe un registro con esos datos en la empresa."
        return RegistroDuplicado(mensaje, contexto={"constraint": constraint})

    if state == "23514":
        return ReglaNegocioViolada(
            mensaje_db or "La operación viola una regla de negocio de la base de datos.",
            contexto={"constraint": constraint},
        )

    if state in {"40001", "40P01"}:
        return ConflictoConcurrencia(
            "La operación compitió con otra transacción. Reintente en unos segundos.",
            contexto={"sqlstate": state},
        )

    if state == "23503":
        return DatosInvalidos(
            "El registro referencia una entidad inexistente o de otra empresa.",
            contexto={"constraint": constraint},
        )

    return ErrorPersistencia(
        "No fue posible guardar la operación. El cambio fue revertido.",
        contexto={"sqlstate": state, "constraint": constraint},
    )


async def manejador_error_nucleo(request: Request, exc: ErrorNucleo) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())
