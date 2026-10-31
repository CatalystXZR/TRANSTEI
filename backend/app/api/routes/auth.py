from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import tiene_membresia_activa
from app.models import Usuario
from app.schemas import UsuarioOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UsuarioOut)
def me(user: Usuario = Depends(get_current_user)) -> UsuarioOut:
    """Perfil del usuario autenticado (rol y acceso al legacy).

    `es_legacy` es `True` solo si el usuario tiene membresía activa en la
    empresa dueña del legacy monoempresa. Es informativo para la UI: el
    backend bloquea el legacy por su cuenta (`GateLegacyMiddleware`).
    """
    return UsuarioOut(
        id=str(user.id),
        nombre=user.nombre,
        email=user.email,
        rol=user.rol,
        es_legacy=tiene_membresia_activa(
            str(user.auth_id), settings.LEGACY_EMPRESA_ID
        ),
    )
