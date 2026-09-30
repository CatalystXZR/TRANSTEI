from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models import Usuario
from app.schemas import UsuarioOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UsuarioOut)
def me(user: Usuario = Depends(get_current_user)) -> UsuarioOut:
    """Perfil del usuario autenticado (incluye su rol)."""
    return UsuarioOut(
        id=str(user.id),
        nombre=user.nombre,
        email=user.email,
        rol=user.rol,
    )
