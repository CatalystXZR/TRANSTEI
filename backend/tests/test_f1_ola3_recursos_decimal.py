"""F1-Ola3 (2026-10-30): SEC-023 — tope de fotos del POD.

Cubre las dos capas del control:
- unitaria: `ServicioPOD._validar_cantidad_fotos` (límite por envío y
  acumulado del POD), que es la regla de dominio reutilizable;
- HTTP: 11 fotos → 422 antes de leer/validar bytes; 10 fotos → 201.

F-04 (precisión decimal en KPIs) se probaba en `test_kpi_engine.py`, retirado en
la Ola C con el router `kpis` y el motor `app/services/kpi_engine.py` (no tenía
más consumidores). La precisión decimal vigente se prueba en el núcleo
(`test_nucleo_ola_b_modulos.py`: CN-04 HALF_UP, y
`test_nucleo_gastos.py`: costos con `Decimal`).
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.main import app
from app.nucleo.deps import ContextoEmpresa, RolEmpresa, get_contexto_empresa
from app.nucleo.errores import DatosInvalidos
from app.nucleo.models import (
    Chofer,
    Cliente,
    Documento,
    Empresa,
    EstadoViaje,
    ModalidadTarifa,
    OrdenCompra,
    Rampla,
    Tarifa,
    TipoDocumento,
    TipoRampla,
    TipoRecurso,
    Tracto,
    Viaje,
)
from app.nucleo.servicio_pod import MAX_FOTOS, ServicioPOD
from contexto_helpers import contexto_de_prueba
from rut_helpers import rut_empresa

API = "/api/v1"

PNG_OK = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de POD")
    return url


# ---------------------------------------------------------------------------
# SEC-023 — regla de dominio (sin base)
# ---------------------------------------------------------------------------


def test_limite_fotos_por_envio():
    ServicioPOD._validar_cantidad_fotos(MAX_FOTOS)  # exactamente el tope: acepta
    with pytest.raises(DatosInvalidos) as exc:
        ServicioPOD._validar_cantidad_fotos(MAX_FOTOS + 1)
    assert str(MAX_FOTOS) in exc.value.mensaje
    assert exc.value.status_code == 422
    assert exc.value.codigo == "DATOS_INVALIDOS"


def test_limite_fotos_acumuladas_del_pod():
    """Un POD lleno no admite más fotos: cierra el crecimiento por PUT repetidos."""
    with pytest.raises(DatosInvalidos):
        ServicioPOD._validar_cantidad_fotos(1, existentes=MAX_FOTOS)
    # Una actualización que reemplaza dentro del tope sigue permitida.
    ServicioPOD._validar_cantidad_fotos(1, existentes=MAX_FOTOS - 1)


# ---------------------------------------------------------------------------
# SEC-023 — HTTP (requiere tei_test y Storage local, igual que la suite POD)
# ---------------------------------------------------------------------------


def _crear_viaje_pod(engine, sufijo: str) -> tuple[Empresa, Viaje]:
    """Empresa + viaje en `pod_pendiente` (mismo patrón que test_nucleo_pod)."""
    token = uuid.uuid4().hex[:8]
    digitos = str(uuid.uuid4().int)[:10]
    vence = date.today() + timedelta(days=365)
    with Session(engine) as session:
        empresa = Empresa(
            codigo=f"R3-{sufijo}",
            razon_social=f"Empresa F1 Ola3 {sufijo}",
            # RUT numérico de 12 dígitos, único entre corridas (ver rut_helpers).
            rut=rut_empresa(),
        )
        session.add(empresa)
        session.commit()
        session.refresh(empresa)
        cliente = Cliente(
            empresa_id=empresa.id, razon_social=f"Cliente {sufijo}", rut=digitos
        )
        tracto = Tracto(
            empresa_id=empresa.id,
            patente=f"O{token[:6].upper()}",
            peso_bruto_kg=Decimal("39000"),
            tara_kg=Decimal("9000"),
            capacidad_carga_kg=Decimal("30000"),
        )
        rampla = Rampla(
            empresa_id=empresa.id,
            patente=f"D{token[:6].upper()}",
            tipo=TipoRampla.plana,
            capacidad_carga_kg=Decimal("30000"),
        )
        chofer = Chofer(
            empresa_id=empresa.id,
            rut=str(int(digitos) + 1),
            nombre=f"Chofer {sufijo}",
            numero_licencia=f"LIP-{token}",
            licencia_clase="A5",
        )
        tarifa = Tarifa(
            empresa_id=empresa.id,
            cliente_id=cliente.id,
            codigo=f"TP-{token}",
            nombre="Ruta Ola3",
            modalidad=ModalidadTarifa.viaje,
            vigencia_desde=date.today() - timedelta(days=30),
            vigencia_hasta=vence,
            precio_unitario=Decimal("100000"),
        )
        oc = OrdenCompra(
            empresa_id=empresa.id,
            cliente_id=cliente.id,
            numero_oc=f"OC3-{token}",
            vigencia_desde=date.today() - timedelta(days=30),
            vigencia_hasta=vence,
            monto_autorizado=Decimal("1000000"),
        )
        session.add_all([cliente, tracto, rampla, chofer])
        session.commit()
        docs = [
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.revision_tecnica, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.permiso_circulacion, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.seguro_obligatorio, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.soap, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.revision_tecnica, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.permiso_circulacion, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.seguro_carga, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.chofer, chofer_id=chofer.id, tipo=TipoDocumento.licencia_conducir, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.chofer, chofer_id=chofer.id, tipo=TipoDocumento.examen_medico, vence_en=vence),
        ]
        session.add_all(docs + [tarifa, oc])
        session.commit()
        ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        inicio = ahora - timedelta(days=1)
        viaje = Viaje(
            empresa_id=empresa.id,
            cliente_id=cliente.id,
            orden_compra_id=oc.id,
            tarifa_id=tarifa.id,
            tracto_id=tracto.id,
            rampla_id=rampla.id,
            chofer_id=chofer.id,
            estado=EstadoViaje.pod_pendiente,
            inicio_planificado=inicio,
            fin_planificado=inicio + timedelta(hours=5),
            buffer_minutos=60,
            peso_bruto_kg=Decimal("20000"),
            origen_nombre="Santiago",
            destino_nombre="Concepción",
            valor_flete_neto=Decimal("100000"),
        )
        session.add(viaje)
        session.commit()
        session.refresh(viaje)
        session.refresh(empresa)  # el commit anterior expiró los atributos
        return empresa, viaje


@pytest.fixture
def env_pod():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1 from nucleo.pod limit 1"))
    except SQLAlchemyError as exc:  # pragma: no cover
        pytest.skip(f"Falta aplicar la migración 0009: {exc}")
    empresa, viaje = _crear_viaje_pod(engine, uuid.uuid4().hex[:8])
    contexto = ContextoEmpresa(
        auth_id=str(uuid.uuid4()), empresa=empresa, rol=RolEmpresa.conductor
    )
    return engine, empresa, viaje, contexto


def _post_pod(client, empresa_id, viaje_id, cantidad_fotos):
    files = [("firma", ("firma.png", PNG_OK, "image/png"))]
    for i in range(cantidad_fotos):
        files.append(("fotos", (f"foto{i}.png", PNG_OK, "image/png")))
    return client.post(
        f"{API}/nucleo/expediente/viajes/{viaje_id}/pod",
        data={"receptor_nombre": "Receptora Ola3"},
        files=files,
        headers={"X-Empresa-ID": empresa_id},
    )


def test_pod_11_fotos_422(client, env_pod):
    """SEC-023: 11 fotos se rechazan antes de leer ningún byte de las fotos."""
    engine, empresa, viaje, contexto = env_pod
    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(contexto)
    try:
        resp = _post_pod(client, str(empresa.id), str(viaje.id), MAX_FOTOS + 1)
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["codigo"] == "DATOS_INVALIDOS"
        assert str(MAX_FOTOS) in body["mensaje"]
        with Session(engine) as session:
            total = session.execute(
                text("select count(*) from nucleo.pod where viaje_id = :v"),
                {"v": viaje.id},
            ).scalar_one()
        assert total == 0, "el rechazo no debe persistir un POD parcial"
    finally:
        app.dependency_overrides.clear()


def test_pod_10_fotos_acepta(client, env_pod):
    """El tope exacto se acepta: 10 fotos persisten en el POD."""
    engine, empresa, viaje, contexto = env_pod
    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(contexto)
    try:
        resp = _post_pod(client, str(empresa.id), str(viaje.id), MAX_FOTOS)
        assert resp.status_code == 201, resp.text
        assert len(resp.json()["fotos"]) == MAX_FOTOS
    finally:
        app.dependency_overrides.clear()
