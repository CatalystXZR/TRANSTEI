"""Identidad del usuario autenticado (F2 Ola E1, 2026-11-01).

`GET /api/v1/auth/me` es el único consumidor de esta dependencia. La identidad
no vive en `public.usuarios` (retirado): sale del JWT de Supabase Auth y el rol
de menú, de las membresías activas en `nucleo.usuarios_empresa`.

Reglas:
- `auth_id` = claim `sub`; `email` = claim `email`; `nombre` =
  `user_metadata.nombre`, con el email como respaldo.
- `rol` = rol **de menú** derivado de la membresía activa (en una empresa
  activa, misma semántica que `GET /nucleo/mis-empresas`). Sin membresía
  utilizable → **403**.
- La autorización real sigue siendo por empresa en el núcleo
  (`get_contexto_empresa` + permisos); este rol solo decide la navegación.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.core.contexto import aplicar_contexto_sesion, fijar_auth_id
from app.core.database import get_session_nucleo
from app.core.security import bearer_scheme, payload_from_credentials
from app.nucleo.models import RolEmpresa
from app.nucleo.servicio_disponibilidad import listar_empresas_usuario
from app.schemas import RolMenu

# Rol del núcleo → rol de menú del shell. `admin` y `gerente` administran;
# `despacho`, `taller` y `conductor` operan; `contador`, `tesoreria` y
# `auditor` ven contabilidad. Un rol nuevo sin mapear no concede menú (None).
ROL_MENU_POR_ROL_EMPRESA: dict[RolEmpresa, RolMenu] = {
    RolEmpresa.admin: RolMenu.admin,
    RolEmpresa.gerente: RolMenu.admin,
    RolEmpresa.despacho: RolMenu.operacion,
    RolEmpresa.taller: RolMenu.operacion,
    RolEmpresa.conductor: RolMenu.operacion,
    RolEmpresa.contador: RolMenu.contabilidad,
    RolEmpresa.tesoreria: RolMenu.contabilidad,
    RolEmpresa.auditor: RolMenu.contabilidad,
}

# Desempate determinista cuando el usuario pertenece a varias empresas con
# roles distintos: gana el menú más amplio. Es solo presentación; la
# autorización se resuelve por empresa en cada request del núcleo.
_PRIORIDAD_ROL_MENU = {
    RolMenu.admin: 3,
    RolMenu.operacion: 2,
    RolMenu.contabilidad: 1,
}


@dataclass(frozen=True, slots=True)
class Identidad:
    """Identidad efectiva del request de `/auth/me`."""

    auth_id: str
    nombre: str
    email: str | None
    rol: RolMenu


def rol_menu_efectivo(roles: Iterable[RolEmpresa]) -> RolMenu | None:
    """Rol de menú de mayor prioridad entre los roles de membresía dados."""
    mejor: RolMenu | None = None
    for rol in roles:
        menu = ROL_MENU_POR_ROL_EMPRESA.get(rol)
        if menu is None:
            continue
        if mejor is None or _PRIORIDAD_ROL_MENU[menu] > _PRIORIDAD_ROL_MENU[mejor]:
            mejor = menu
    return mejor


def _membresias_utilizables(session: Session, auth_id: str):
    """Membresías activas del `auth_id` en empresas activas.

    RLS (0020): `usuarios_empresa_lectura` resuelve por `nucleo.auth_id`, así
    que el GUC se fija antes de la primera consulta. Reutiliza
    `listar_empresas_usuario`, que ya aplica la regla "membresía activa +
    empresa activa" del núcleo.
    """
    fijar_auth_id(auth_id)
    aplicar_contexto_sesion(session)
    return listar_empresas_usuario(session, auth_id)


def get_current_user(
    credentials=Depends(bearer_scheme),
    session: Session = Depends(get_session_nucleo),
) -> Identidad:
    """Identidad del usuario autenticado, sin leer `public.usuarios`."""
    payload = payload_from_credentials(credentials)
    auth_id = str(payload["sub"])
    try:
        UUID(auth_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        ) from exc

    membresias = _membresias_utilizables(session, auth_id)
    rol = rol_menu_efectivo(membresia.rol for membresia in membresias)
    if rol is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no tiene una membresía activa.",
        )

    email = payload.get("email") or None
    metadatos = payload.get("user_metadata")
    nombre_meta = metadatos.get("nombre") if isinstance(metadatos, dict) else None
    nombre = str(nombre_meta).strip() if nombre_meta else ""
    return Identidad(
        auth_id=auth_id,
        nombre=nombre or email or auth_id,
        email=email,
        rol=rol,
    )
