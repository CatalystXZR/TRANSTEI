from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import auth_id_from_credentials, bearer_scheme
from app.models import RolUsuario, Usuario


def get_current_user(
    credentials=Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> Usuario:
    """Obtiene el usuario autenticado desde el JWT de Supabase."""
    auth_id = auth_id_from_credentials(credentials)
    usuario = session.exec(
        select(Usuario).where(Usuario.auth_id == auth_id)
    ).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no registrado en el sistema",
        )
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado",
        )
    return usuario


def require_roles(*roles: RolUsuario):
    """Factory de dependencia: restringe el acceso a los roles indicados."""

    def checker(user: Usuario = Depends(get_current_user)) -> Usuario:
        if user.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para realizar esta acción",
            )
        return user

    return checker
