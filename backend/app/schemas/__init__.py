from enum import Enum

from pydantic import BaseModel


class RolMenu(str, Enum):
    """Rol de menú que entiende el shell (`frontend/src/types/index.ts`).

    No es el rol de autorización: el núcleo autoriza por `RolEmpresa` y
    membresía por empresa. Este valor solo decide qué navegación se muestra y
    se deriva de las membresías activas del usuario (`app/api/deps.py`).
    """

    admin = "admin"
    operacion = "operacion"
    contabilidad = "contabilidad"


class UsuarioOut(BaseModel):
    """Contrato de `GET /api/v1/auth/me` (F2 Ola E1, 2026-11-01).

    `id` es el `sub` del JWT (Supabase Auth). Ya no existe `es_legacy`: el
    legacy monoempresa se retiró junto con `public.usuarios`.
    """

    id: str
    nombre: str
    email: str | None
    rol: RolMenu


class Message(BaseModel):
    message: str
