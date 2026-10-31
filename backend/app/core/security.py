import logging
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_engine

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(url, cache_keys=True)
    return _jwks_client


def decode_token(token: str) -> dict:
    """Valida el JWT emitido por Supabase Auth y devuelve su payload."""
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
            options={"verify_aud": True},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada, vuelva a iniciar sesión",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )
    return payload


def auth_id_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación",
        )
    payload = decode_token(credentials.credentials)
    auth_id = payload.get("sub")
    if not auth_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )
    return auth_id


def tiene_membresia_activa(auth_id: str, empresa_id: str) -> bool:
    """¿El `auth_id` tiene membresía activa en `nucleo.usuarios_empresa`?

    Se consulta con el motor **legacy** (`settings.DATABASE_URL`, rol con
    `BYPASSRLS`) a propósito: la membresía vive en `nucleo` y las políticas RLS
    de `0020_rls_multiempresa.sql` solo dejan ver la empresa del contexto
    (`app.empresa_id`), que en el legacy no existe. Con `tei_app` sin contexto
    esta consulta vería 0 filas y negaría el acceso a todos.

    Fail-closed: cualquier identificador mal formado devuelve `False` (no se
    concede acceso por un error de parseo). Los errores de base de datos **no**
    se capturan: un fallo de conexión debe verse como error, no como "sin
    membresía".
    """
    try:
        empresa_uuid = UUID(str(empresa_id))
    except (AttributeError, TypeError, ValueError):
        logger.warning(
            "LEGACY_EMPRESA_ID no es un UUID válido: se deniega el acceso "
            "legacy (fail-closed)."
        )
        return False

    try:
        auth_uuid = UUID(str(auth_id))
    except (AttributeError, TypeError, ValueError):
        # Token sin `sub` UUID: no puede existir membresía. No es un error de
        # configuración; el legacy simplemente no le corresponde.
        return False

    with get_engine().connect() as connection:
        fila = connection.execute(
            text(
                "select 1 from nucleo.usuarios_empresa"
                " where auth_id = :auth_id"
                "   and empresa_id = :empresa_id"
                "   and activo"
            ),
            {"auth_id": auth_uuid, "empresa_id": empresa_uuid},
        ).first()
    return fila is not None
