from pydantic import BaseModel

from app.models import RolUsuario


class UsuarioOut(BaseModel):
    id: str
    nombre: str
    email: str | None
    rol: RolUsuario
    # `True` si el usuario pertenece a la empresa dueña del legacy monoempresa
    # (`settings.LEGACY_EMPRESA_ID`). El frontend lo usa para ocultar las
    # pantallas legacy; la autorización real la impone `GateLegacyMiddleware`.
    es_legacy: bool = False


class Message(BaseModel):
    message: str
