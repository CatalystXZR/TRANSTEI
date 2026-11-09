"""Alta y enrolamiento de contactos del agente (D-12, SEC-039).

El admin inicia el alta; el OTP viaja por WhatsApp y se verifica con el código.
Las escrituras de identidad/ACL/flag pasan por las funciones
`nucleo.admin_*` (0029), porque `tei_app` ya no tiene INSERT/UPDATE directo.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.agente.otp import expira_en, generar_codigo, hash_codigo
from app.nucleo.agente.whatsapp import enviar_otp
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import ErrorPersistencia
from app.nucleo.permisos import requiere_permiso

router = APIRouter(prefix="/nucleo/agente", tags=["agente"])

_TELEFONO = r"^\+[1-9][0-9]{7,14}$"


class _Cerrado(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContactoCreate(_Cerrado):
    telefono: str = Field(pattern=_TELEFONO)
    nombre: str = Field(min_length=1, max_length=200)
    rol: Literal["cliente_final", "conductor", "admin"]
    cliente_id: uuid.UUID | None = None
    chofer_id: uuid.UUID | None = None
    usuario_empresa_id: uuid.UUID | None = None


class ContactoOut(_Cerrado):
    contacto_id: uuid.UUID
    otp_expira_en: datetime
    otp_enviado: bool


class VerificarOtpIn(_Cerrado):
    codigo: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class VerificarOtpOut(_Cerrado):
    verificado: bool


class PermisoIn(_Cerrado):
    componente: str = Field(min_length=1, max_length=100)
    variable: str | None = Field(default=None, max_length=200)
    permitido: bool


class ModuloIn(_Cerrado):
    habilitado: bool


@router.post(
    "/contactos",
    response_model=ContactoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_contacto(
    body: ContactoCreate,
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:contactos")),
    session: Session = Depends(get_session_nucleo),
) -> ContactoOut:
    """Alta/actualización de contacto y envío del OTP por WhatsApp.

    No devuelve el código. Si el proveedor de WhatsApp falla, el contacto queda
    creado con OTP pendiente y `otp_enviado=false`; el admin puede reintentar.
    """
    codigo = generar_codigo()
    expira = expira_en()

    contacto_id = session.execute(
        text(
            """
            select nucleo.admin_upsert_contacto(
              :empresa_id, :telefono, :nombre,
              cast(:rol as nucleo.rol_contacto_whatsapp),
              :cliente_id, :chofer_id, :usuario_empresa_id,
              :otp_hash, :otp_expira_en
            )
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "telefono": body.telefono,
            "nombre": body.nombre,
            "rol": body.rol,
            "cliente_id": body.cliente_id,
            "chofer_id": body.chofer_id,
            "usuario_empresa_id": body.usuario_empresa_id,
            "otp_hash": hash_codigo(codigo),
            "otp_expira_en": expira,
        },
    ).scalar_one()
    session.commit()

    try:
        enviado = enviar_otp(body.telefono, codigo)
    except ErrorPersistencia:
        enviado = False

    return ContactoOut(
        contacto_id=contacto_id,
        otp_expira_en=expira,
        otp_enviado=enviado,
    )


@router.post(
    "/contactos/{contacto_id}/verificar",
    response_model=VerificarOtpOut,
)
def verificar_otp(
    contacto_id: uuid.UUID,
    body: VerificarOtpIn,
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:contactos")),
    session: Session = Depends(get_session_nucleo),
) -> VerificarOtpOut:
    verificado = session.execute(
        text(
            "select nucleo.admin_verificar_otp(:empresa_id, :contacto_id, :otp_hash)"
        ),
        {
            "empresa_id": contexto.empresa_id,
            "contacto_id": contacto_id,
            "otp_hash": hash_codigo(body.codigo),
        },
    ).scalar_one()
    session.commit()
    return VerificarOtpOut(verificado=bool(verificado))


@router.put(
    "/contactos/{contacto_id}/permisos",
    status_code=status.HTTP_204_NO_CONTENT,
)
def set_permiso(
    contacto_id: uuid.UUID,
    body: PermisoIn,
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:contactos")),
    session: Session = Depends(get_session_nucleo),
) -> None:
    session.execute(
        text(
            """
            select nucleo.admin_set_permiso_contacto(
              :empresa_id, :contacto_id, :componente, :variable, :permitido
            )
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "contacto_id": contacto_id,
            "componente": body.componente,
            "variable": body.variable,
            "permitido": body.permitido,
        },
    ).scalar_one()
    session.commit()


@router.put(
    "/modulos/{modulo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def set_modulo(
    modulo_id: str,
    body: ModuloIn,
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:contactos")),
    session: Session = Depends(get_session_nucleo),
) -> None:
    session.execute(
        text(
            "select nucleo.admin_set_modulo_empresa(:empresa_id, :modulo_id, :habilitado)"
        ),
        {
            "empresa_id": contexto.empresa_id,
            "modulo_id": modulo_id,
            "habilitado": body.habilitado,
        },
    )
    session.commit()
