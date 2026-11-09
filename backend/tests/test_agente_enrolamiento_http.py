"""Enrolamiento del agente por el admin (D-12, SEC-039) — capa HTTP real.

Flujo:
1. El admin crea el contacto; el backend genera el OTP, lo guarda como hash y
   lo envía por el notificador WhatsApp (modo `fake` en tests).
2. El admin verifica el código; `otp_estado` pasa a `verificado`.
3. El flag del módulo `modulos_empresa` es de plataforma: el endpoint del tenant
   se retiró (SEC-066) y `tei_app` no tiene EXECUTE sobre la función (0034).

Requiere Supabase local, `tei_test` y `TEST_ADMIN_*` (los pone `make test`).
"""

from __future__ import annotations

import base64
import json
from uuid import UUID, uuid4

import pytest
from app.core.config import settings
from app.nucleo.agente import whatsapp

pytestmark = pytest.mark.integracion

API = settings.API_V1_PREFIX
RUTA = f"{API}/nucleo/agente"


def _sub_del_token(headers: dict) -> str:
    token = headers["Authorization"].split(" ", 1)[1]
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]


@pytest.fixture(scope="module")
def empresa_admin(db, headers_admin) -> UUID:
    auth_id = UUID(_sub_del_token(headers_admin))
    fila = db.execute(
        "select empresa_id from nucleo.usuarios_empresa "
        "where auth_id = %s and activo limit 1",
        (auth_id,),
    ).fetchone()
    if fila is None:
        pytest.skip("el usuario admin del seed no tiene membresía en tei_test")
    return fila[0]


def test_admin_enrola_contacto_y_verifica_otp(
    client, headers_admin, db, empresa_admin, monkeypatch
) -> None:
    # Pepper de prueba: el HMAC del OTP no depende de un secreto de producción.
    monkeypatch.setattr(settings, "AGENTE_OTP_PEPPER", "pepper-test-enrolamiento")
    monkeypatch.setattr(whatsapp.settings, "WHATSAPP_MODE", "fake")
    whatsapp._OUTBOX.clear()

    headers = {**headers_admin, "X-Empresa-ID": str(empresa_admin)}
    telefono = f"+569{uuid4().int % 10**8:08d}"

    r = client.post(
        f"{RUTA}/contactos",
        headers=headers,
        json={
            "telefono": telefono,
            "nombre": "Contacto enrolamiento",
            "rol": "admin",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["otp_enviado"] is True
    contacto_id = data["contacto_id"]

    outbox = whatsapp.outbox_fake()
    assert outbox and outbox[-1]["telefono"] == telefono
    codigo = outbox[-1]["codigo"]
    assert len(codigo) == 6 and codigo.isdigit()

    # El código no se devuelve por la API (solo viaja al notificador).
    assert "codigo" not in data

    r2 = client.post(
        f"{RUTA}/contactos/{contacto_id}/verificar",
        headers=headers,
        json={"codigo": codigo},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["verificado"] is True

    estado = db.execute(
        "select otp_estado::text from nucleo.contactos_whatsapp where id = %s",
        (contacto_id,),
    ).fetchone()
    assert estado is not None and estado[0] == "verificado"

    # Un código ya usado no vuelve a verificar (idempotencia negativa).
    r3 = client.post(
        f"{RUTA}/contactos/{contacto_id}/verificar",
        headers=headers,
        json={"codigo": codigo},
    )
    assert r3.status_code == 200 and r3.json()["verificado"] is False

    # SEC-066: el flag del módulo es de plataforma; el tenant ya no tiene la
    # ruta HTTP (la función `admin_set_modulo_empresa` queda para RA-16).
    r4 = client.put(
        f"{RUTA}/modulos/agente-whatsapp",
        headers=headers,
        json={"habilitado": True},
    )
    assert r4.status_code == 404, r4.text

    db.execute(
        "update nucleo.modulos_empresa set habilitado = false "
        "where empresa_id = %s and modulo_id = 'agente-whatsapp'",
        (empresa_admin,),
    )
    db.execute(
        "delete from nucleo.contactos_whatsapp where id = %s", (contacto_id,)
    )
    db.commit()


def test_contacto_sin_permiso_no_puede_enrolar(
    client, headers_contabilidad, db, empresa_admin
) -> None:
    """Contabilidad no tiene `agente:contactos`: 403, no 500."""
    headers = {**headers_contabilidad, "X-Empresa-ID": str(empresa_admin)}
    r = client.post(
        f"{RUTA}/contactos",
        headers=headers,
        json={
            "telefono": f"+569{uuid4().int % 10**8:08d}",
            "nombre": "Sin permiso",
            "rol": "admin",
        },
    )
    assert r.status_code == 403, r.text
