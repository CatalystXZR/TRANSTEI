from pydantic import BaseModel

from app.models import RolUsuario


class UsuarioOut(BaseModel):
    id: str
    nombre: str
    email: str | None
    rol: RolUsuario


class Message(BaseModel):
    message: str
