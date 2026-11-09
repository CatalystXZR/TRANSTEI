"""Unitarias del OTP de enrolamiento (D-12) y del notificador fake."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.nucleo.agente import otp, whatsapp
from app.nucleo.errores import ErrorPersistencia


def test_generar_codigo_es_seis_digitos() -> None:
    for _ in range(20):
        assert re.fullmatch(r"[0-9]{6}", otp.generar_codigo())


def test_hash_es_determinista_y_depende_del_codigo(monkeypatch) -> None:
    monkeypatch.setattr(otp.settings, "AGENTE_OTP_PEPPER", "pepper-prueba")
    a = otp.hash_codigo("123456")
    assert a == otp.hash_codigo("123456")
    assert a != otp.hash_codigo("654321")


def test_hash_cambia_con_el_pepper(monkeypatch) -> None:
    monkeypatch.setattr(otp.settings, "AGENTE_OTP_PEPPER", "pepper-1")
    a = otp.hash_codigo("123456")
    monkeypatch.setattr(otp.settings, "AGENTE_OTP_PEPPER", "pepper-2")
    assert a != otp.hash_codigo("123456")


def test_sin_pepper_falla_cerrado(monkeypatch) -> None:
    monkeypatch.setattr(otp.settings, "AGENTE_OTP_PEPPER", "")
    monkeypatch.setattr(otp.settings, "SUPABASE_JWT_SECRET", "")
    with pytest.raises(ErrorPersistencia):
        otp.hash_codigo("123456")


def test_expira_en_es_futuro() -> None:
    assert otp.expira_en() > datetime.now(timezone.utc)


def test_whatsapp_fake_encola_y_no_expone(monkeypatch) -> None:
    monkeypatch.setattr(whatsapp.settings, "WHATSAPP_MODE", "fake")
    whatsapp._OUTBOX.clear()
    assert whatsapp.enviar_otp("+56911111111", "123456") is True
    assert whatsapp.outbox_fake() == [
        {"telefono": "+56911111111", "codigo": "123456"}
    ]


def test_whatsapp_modo_desconocido_falla(monkeypatch) -> None:
    monkeypatch.setattr(whatsapp.settings, "WHATSAPP_MODE", "otro")
    with pytest.raises(ErrorPersistencia):
        whatsapp.enviar_otp("+56911111111", "123456")
