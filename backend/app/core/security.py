import jwt
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(url, cache_keys=True)
    return _jwks_client


def decode_token(token: str) -> dict:
    """Valida el JWT emitido por Supabase Auth y devuelve su payload.

    Además de firma y audiencia, valida el emisor (`iss`) cuando se conoce
    (`SUPABASE_JWT_ISSUER` o derivado de `SUPABASE_URL`). Sin esa validación,
    un token firmado por otro emisor con la misma audiencia podría aceptarse.
    """
    issuer = settings.jwt_issuer
    opciones = {"verify_aud": True, "verify_iss": bool(issuer)}
    kwargs = {"issuer": issuer} if issuer else {}
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
            options=opciones,
            **kwargs,
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


def payload_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> dict:
    """Payload verificado del JWT; 401 si falta el token o el `sub`.

    Devuelve el payload completo porque `/auth/me` necesita además `email` y
    `user_metadata` (la identidad vive en Supabase Auth, no en `public`).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación",
        )
    payload = decode_token(credentials.credentials)
    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )
    return payload


def auth_id_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    """`sub` (auth_id) verificado del JWT."""
    return str(payload_from_credentials(credentials)["sub"])
