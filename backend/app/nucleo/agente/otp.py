"""OTP de enrolamiento del agente (D-12).

Reglas:
- El código tiene 6 dígitos y se genera con `secrets` (no `random`).
- Nunca se guarda ni se devuelve en claro: en la tabla va solo el HMAC-SHA256.
- El pepper es un secreto compartido entre workers (`AGENTE_OTP_PEPPER`); si no
  está, se usa `SUPABASE_JWT_SECRET` como respaldo local. Sin ninguno de los
  dos, el flujo falla cerrado (`ErrorPersistencia`), no genera OTP adivinable.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.nucleo.errores import ErrorPersistencia

OTP_LARGO = 6
OTP_TTL_MINUTOS = 10


def _pepper() -> str:
    pepper = (settings.AGENTE_OTP_PEPPER or settings.SUPABASE_JWT_SECRET or "").strip()
    if not pepper:
        raise ErrorPersistencia(
            "OTP no configurado: defina AGENTE_OTP_PEPPER en el entorno."
        )
    return pepper


def generar_codigo() -> str:
    """Código numérico de 6 dígitos, criptográficamente aleatorio."""
    return f"{secrets.randbelow(10 ** OTP_LARGO):0{OTP_LARGO}d}"


def hash_codigo(codigo: str) -> str:
    """HMAC-SHA256 del código con el pepper del servidor."""
    return hmac.new(
        _pepper().encode("utf-8"),
        codigo.strip().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def expira_en() -> datetime:
    """Vencimiento UTC del OTP recién generado."""
    return datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTOS)
