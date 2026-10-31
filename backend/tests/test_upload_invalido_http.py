"""HTTP: upload de documento con firma inválida → 422 (F0-05).

Requiere `NUCLEO_TEST_DATABASE_URL` (tei_test). Se usa un override de
`get_contexto_empresa` para no depender de credenciales Supabase: lo que se
verifica es el contrato HTTP del endpoint (rechazo por firma ANTES de tocar
Storage, con content-type declarado por el cliente que es ignorado).
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.main import app
from app.nucleo.deps import ContextoEmpresa, RolEmpresa, get_contexto_empresa
from app.nucleo.models import Empresa, Tracto
from contexto_helpers import contexto_de_prueba
from rut_helpers import rut_empresa


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración HTTP de uploads")
    return url


def test_upload_documento_firma_invalida_422(client):
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.empresas limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0004: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"UPL-{sufijo}",
                razon_social=f"Empresa Upload {sufijo}",
                rut=rut_empresa(),
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)
            tracto = Tracto(
                empresa_id=empresa.id,
                patente=f"UPL{sufijo[:6].upper()}",
                peso_bruto_kg=Decimal("39000"),
                tara_kg=Decimal("9000"),
                capacidad_carga_kg=Decimal("30000"),
            )
            session.add(tracto)
            session.commit()
            session.refresh(tracto)
            empresa_id = str(empresa.id)
            tracto_id = str(tracto.id)

        contexto = ContextoEmpresa(
            auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.admin
        )
        app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(contexto)
        try:
            resp = client.post(
                "/api/v1/nucleo/documentos",
                data={
                    "recurso_tipo": "tracto",
                    "recurso_id": tracto_id,
                    "tipo": "revision_tecnica",
                    "vence_en": (date.today() + timedelta(days=30)).isoformat(),
                },
                files={
                    "archivo": (
                        "documento.pdf",
                        b"esto no es un PDF",
                        "application/pdf",  # declarado por el cliente; el servidor lo ignora
                    ),
                },
                headers={"X-Empresa-ID": empresa_id},
            )
            assert resp.status_code == 422, resp.text
            body = resp.json()
            assert body["codigo"] == "DATOS_INVALIDOS"
        finally:
            app.dependency_overrides.clear()
    finally:
        engine.dispose()
