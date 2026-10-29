"""Autenticación multiempresa del núcleo v2.

Supabase Auth entrega el `sub` (auth_id). La membresía y el rol se resuelven
contra `nucleo.usuarios_empresa`, NUNCA contra un `empresa_id` enviado en el
body. El cliente debe enviar `X-Empresa-ID`; el backend verifica que el usuario
pertenezca a esa empresa y que la empresa esté activa.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import auth_id_from_credentials, bearer_scheme
from app.nucleo.errores import AccesoDenegado, EmpresaNoEncontrada
from app.nucleo.models import Empresa, EstadoEmpresa, RolEmpresa, UsuarioEmpresa


@dataclass(frozen=True, slots=True)
class ContextoEmpresa:
    auth_id: str
    empresa: Empresa
    rol: RolEmpresa
    request_id: str | None = None

    @property
    def empresa_id(self) -> UUID:
        return self.empresa.id

    @property
    def puede_escribir(self) -> bool:
        return self.rol in {
            RolEmpresa.admin,
            RolEmpresa.gerente,
            RolEmpresa.despacho,
        }


def get_contexto_empresa(
    x_empresa_id: UUID = Header(..., alias="X-Empresa-ID"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    credentials=Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> ContextoEmpresa:
    auth_id = auth_id_from_credentials(credentials)
    try:
        auth_uuid = UUID(auth_id)
    except ValueError as exc:
        raise AccesoDenegado("El token no contiene un identificador de usuario válido.") from exc

    membresia = session.exec(
        select(UsuarioEmpresa).where(
            UsuarioEmpresa.empresa_id == x_empresa_id,
            UsuarioEmpresa.auth_id == auth_uuid,
            UsuarioEmpresa.activo == True,
        )
    ).first()
    if membresia is None:
        raise AccesoDenegado(
            "El usuario no tiene acceso a la empresa indicada.",
            contexto={"empresa_id": str(x_empresa_id)},
        )

    empresa = session.get(Empresa, x_empresa_id)
    if empresa is None:
        raise EmpresaNoEncontrada("La empresa indicada no existe.")
    if empresa.estado != EstadoEmpresa.activa:
        raise AccesoDenegado(
            "La empresa está inactiva.",
            contexto={"empresa_id": str(x_empresa_id)},
        )

    return ContextoEmpresa(
        auth_id=auth_id,
        empresa=empresa,
        rol=membresia.rol,
        request_id=x_request_id,
    )


def requiere_roles(*roles: RolEmpresa):
    permitidos = set(roles)

    def checker(contexto: ContextoEmpresa = Depends(get_contexto_empresa)) -> ContextoEmpresa:
        if contexto.rol not in permitidos:
            raise AccesoDenegado(
                "Su rol no permite realizar esta operación.",
                contexto={"rol": contexto.rol.value},
            )
        return contexto

    return checker


ROLES_LECTURA = {
    RolEmpresa.admin,
    RolEmpresa.gerente,
    RolEmpresa.despacho,
    RolEmpresa.contador,
    RolEmpresa.tesoreria,
    RolEmpresa.taller,
    RolEmpresa.auditor,
}

ROLES_ESCRITURA = {
    RolEmpresa.admin,
    RolEmpresa.gerente,
    RolEmpresa.despacho,
}
