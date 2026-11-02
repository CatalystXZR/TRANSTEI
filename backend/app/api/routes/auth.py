from fastapi import APIRouter, Depends

from app.api.deps import Identidad, get_current_user
from app.schemas import UsuarioOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UsuarioOut)
def me(identidad: Identidad = Depends(get_current_user)) -> UsuarioOut:
    """Perfil del usuario autenticado.

    La identidad sale del JWT de Supabase (`sub`, `email`, `user_metadata`) y
    el rol de menú de `nucleo.usuarios_empresa`. No lee `public.usuarios`.
    """
    return UsuarioOut(
        id=identidad.auth_id,
        nombre=identidad.nombre,
        email=identidad.email,
        rol=identidad.rol,
    )
