from app.core.database import get_session
from app.models import Configuracion


def get_config(session, clave: str, default: str) -> str:
    fila = session.get(Configuracion, clave)
    return fila.valor if fila else default


def get_config_decimal(session, clave: str, default: str):
    from decimal import Decimal

    try:
        return Decimal(get_config(session, clave, default))
    except Exception:
        return Decimal(default)
