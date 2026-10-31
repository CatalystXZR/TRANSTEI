"""Adversarial F1-Ola2 (2026-10-29): intentos de romper los controles nuevos.

Revisión independiente de QA sobre los cambios del agente backend (Ola 2):

1. Fail-closed del cutover (`servicio_cutover.legacy_congelado`) y middleware
   `app.main` que bloquea escrituras legacy con 409 CUTOVER_LEGACY_CONGELADO.
2. Mapeo SQLSTATE->HTTP global (23505/23P01->409, 23514/23502/23503->422).
3. Validación de firma (magic bytes) y content-type canónico en uploads
   (`storage.py`, `api_pod.py`, `api_maestros.py`, `servicio_maestros.py`).
4. DEBUG=False por defecto (`config.py`).

Estrategia: el camino feliz ya está cubierto por `test_seguridad_ola2.py`.
Acá se atacan los supuestos: firma vs extensión vs content-type declarado,
tamaños límite, poliglotas, concurrencia real (2 hilos), datos de otra empresa
y el contrato HTTP del middleware (antes/después de congelar).

Los casos que esperan 201/200 suben archivos reales al bucket local de Storage
(mismo patrón que `test_nucleo_pod.py`, datos de prueba desechables). Los casos
negativos no llegan a Storage.

Requiere `NUCLEO_TEST_DATABASE_URL` (tei_test). Los casos con credenciales reales
Supabase se omiten si faltan TEST_ADMIN_EMAIL/PASSWORD (nunca un skip disfrazado).
"""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.main import app
from app.nucleo.deps import ContextoEmpresa, RolEmpresa, get_contexto_empresa
from app.nucleo.models import (
    Chofer,
    Cliente,
    Documento,
    Empresa,
    EstadoViaje,
    FacturaNucleo,
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
from app.nucleo.servicio_cutover import invalidar_cache, legacy_congelado
from contexto_helpers import contexto_de_prueba
from rut_helpers import rut_empresa

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

API = "/api/v1"

PDF_OK = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
JPEG_OK = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00resto de bytes"
PNG_OK = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
HEIC_OK = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1"
POLYGLOT = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    b"<html><body><script>document.title='xss'</script></body></html>"
)

_10MB = 10 * 1024 * 1024
_5MB = 5 * 1024 * 1024
_CRITERIO_10M = 10_000_000

# Contenido propio del test de concurrencia: si reutilizara PDF_OK chocaría con
# la deduplicación del documento ya subido al mismo tracto por otro test.
PDF_DUPLICADO = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Prueba (duplicado) >>\nendobj\n%%EOF\n"


def _pdf_de_tamano(total: int) -> bytes:
    """PDF con firma válida (`%PDF-` … `%%EOF`) de exactamente `total` bytes."""
    inicio = b"%PDF-1.7\n"
    fin = b"\n%%EOF\n"
    assert total > len(inicio) + len(fin)
    return inicio + b"x" * (total - len(inicio) - len(fin)) + fin


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración adversarial")
    return url


def _override(contexto: ContextoEmpresa):
    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(contexto)


def _limpiar_override():
    app.dependency_overrides.clear()


def _crear_empresa_tracto(engine, sufijo: str) -> tuple[Empresa, Tracto]:
    with Session(engine) as session:
        empresa = Empresa(
            codigo=f"ADV-{sufijo}",
            razon_social=f"Empresa ADV {sufijo}",
            rut=rut_empresa(),
        )
        session.add(empresa)
        session.commit()
        session.refresh(empresa)
        tracto = Tracto(
            empresa_id=empresa.id,
            patente=f"T{sufijo[:6].upper()}",
            peso_bruto_kg=Decimal("39000"),
            tara_kg=Decimal("9000"),
            capacidad_carga_kg=Decimal("30000"),
        )
        session.add(tracto)
        session.commit()
        session.refresh(tracto)
        session.refresh(empresa)  # el commit anterior expiró los atributos
        return empresa, tracto


def _crear_viaje_pod(engine, sufijo: str) -> tuple[Empresa, Viaje]:
    """Empresa + viaje en estado pod_pendiente (espejo de test_nucleo_pod)."""
    token = uuid.uuid4().hex[:8]
    digitos = str(uuid.uuid4().int)[:10]
    vence = date.today() + timedelta(days=365)
    with Session(engine) as session:
        empresa = Empresa(
            codigo=f"POD-{sufijo}",
            razon_social=f"Empresa POD ADV {sufijo}",
            rut=rut_empresa(),
        )
        session.add(empresa)
        session.commit()
        session.refresh(empresa)
        cliente = Cliente(empresa_id=empresa.id, razon_social=f"Cliente {sufijo}", rut=digitos)
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
            nombre="Ruta ADV",
            modalidad=ModalidadTarifa.viaje,
            vigencia_desde=date.today() - timedelta(days=30),
            vigencia_hasta=vence,
            precio_unitario=Decimal("100000"),
        )
        oc = OrdenCompra(
            empresa_id=empresa.id,
            cliente_id=cliente.id,
            numero_oc=f"OCA-{token}",
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


def _head_content_type(url: str) -> str | None:
    """HEAD a una URL firmada y devuelve el Content-Type servido."""
    with httpx.Client(timeout=20) as h:
        r = h.head(url, follow_redirects=True)
        return r.headers.get("content-type")


# ---------------------------------------------------------------------------
# A. Uploads: firma manipulada, tamaños, content-type del cliente
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env_docs():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1 from nucleo.documentos limit 1"))
    except SQLAlchemyError as exc:  # pragma: no cover
        pytest.skip(f"Falta aplicar la migración 0007: {exc}")
    empresa, tracto = _crear_empresa_tracto(engine, uuid.uuid4().hex[:8])
    contexto = ContextoEmpresa(
        auth_id=str(uuid.uuid4()), empresa=empresa, rol=RolEmpresa.admin
    )
    return engine, empresa, tracto, contexto


def _post_documento(client, empresa_id, tracto_id, nombre, contenido, content_type=None):
    files = {"archivo": (nombre, contenido, content_type or "application/octet-stream")}
    return client.post(
        f"{API}/nucleo/documentos",
        data={
            "recurso_tipo": "tracto",
            "recurso_id": tracto_id,
            "tipo": "revision_tecnica",
            "vence_en": (date.today() + timedelta(days=30)).isoformat(),
        },
        files=files,
        headers={"X-Empresa-ID": empresa_id},
    )


@pytest.mark.parametrize(
    "nombre, contenido",
    [
        # Extensión .pdf con contenido JPEG
        ("documento.pdf", JPEG_OK),
        # Extensión .jpg con contenido PNG
        ("documento.jpg", PNG_OK),
        # PNG renombrado a .jpg
        ("foto.jpg", PNG_OK),
        # Extensión .png con contenido JPEG
        ("foto.png", JPEG_OK),
        # Texto plano con extensión .pdf
        ("documento.pdf", b"esto no es un PDF"),
        # Solo whitespace
        ("documento.pdf", b"   \n\t  "),
        # Vacío
        ("documento.pdf", b""),
        # Extensión no permitida
        ("documento.exe", b"MZ\x90\x00\x03\x00\x00\x00"),
        # Sin extensión
        ("documento", PDF_OK),
    ],
)
def test_documento_firma_manipulada_422(client, env_docs, nombre, contenido):
    engine, empresa, tracto, contexto = env_docs
    _override(contexto)
    try:
        resp = _post_documento(client, str(empresa.id), str(tracto.id), nombre, contenido)
        assert resp.status_code == 422, resp.text
        assert resp.json()["codigo"] == "DATOS_INVALIDOS"
    finally:
        _limpiar_override()


def test_documento_pdf_con_bytes_extra_aceptado_y_content_type_canonico(
    client, env_docs
):
    engine, empresa, tracto, contexto = env_docs
    contenido = b"%PDF-1.4\xe2\xe3\xcf\xd3" + b"x" * 500 + b"\n%%EOF\n"
    _override(contexto)
    try:
        resp = _post_documento(
            client, str(empresa.id), str(tracto.id), "documento.pdf", contenido,
            content_type="text/html",  # declarado por el cliente; se ignora
        )
        assert resp.status_code == 201, resp.text
        doc_id = resp.json()["id"]
        # El content-type almacenado lo fija el servidor según la firma.
        url_resp = client.get(
            f"{API}/nucleo/documentos/{doc_id}/url",
            headers={"X-Empresa-ID": str(empresa.id)},
        )
        assert url_resp.status_code == 200, url_resp.text
        ct = _head_content_type(url_resp.json()["url"])
        assert ct == "application/pdf", f"content-type servido: {ct!r}"
    finally:
        _limpiar_override()
        # nucleo.documentos es append-only (fn_documento_no_borrar): no se limpia;
        # las filas quedan aisladas por empresa/tracto con token único.


def test_documento_extension_mayuscula_aceptada(client, env_docs):
    engine, empresa, tracto, contexto = env_docs
    _override(contexto)
    try:
        resp = _post_documento(
            client, str(empresa.id), str(tracto.id), "DOC.PDF", PDF_OK
        )
        assert resp.status_code == 201, resp.text
    finally:
        _limpiar_override()
        # nucleo.documentos es append-only (fn_documento_no_borrar): no se limpia;
        # las filas quedan aisladas por empresa/tracto con token único.


def test_documento_poliglota_pdf_html_aceptado(client, env_docs):
    """%PDF al inicio + HTML embebido: la validación por magic bytes lo acepta.

    HALLAZGO (severidad baja): la firma solo mira los primeros bytes; un PDF
    con HTML embebido pasa y se sirve como application/pdf.
    """
    engine, empresa, tracto, contexto = env_docs
    _override(contexto)
    try:
        resp = _post_documento(
            client, str(empresa.id), str(tracto.id), "poliglota.pdf", POLYGLOT
        )
        assert resp.status_code == 201, resp.text
        url_resp = client.get(
            f"{API}/nucleo/documentos/{resp.json()['id']}/url",
            headers={"X-Empresa-ID": str(empresa.id)},
        )
        ct = _head_content_type(url_resp.json()["url"])
        assert ct == "application/pdf", f"content-type servido: {ct!r}"
    finally:
        _limpiar_override()
        # nucleo.documentos es append-only (fn_documento_no_borrar): no se limpia;
        # las filas quedan aisladas por empresa/tracto con token único.


@pytest.mark.parametrize(
    "tamano, etiqueta",
    [
        (_10MB, "límite del código (10 MiB)"),
        (_CRITERIO_10M, "criterio del dueño (10.000.000 bytes)"),
    ],
)
def test_documento_10mb_exacto_aceptado(client, env_docs, tamano, etiqueta):
    """Exactamente el límite se acepta (borde cerrado).

    Causa raíz del fallo anterior: el test construía `%PDF-1.4\\n` (9 bytes) +
    `_10MB - 8`, es decir _10MB + 1 byte, y esperaba 201.
    """
    engine, empresa, tracto, contexto = env_docs
    contenido = _pdf_de_tamano(tamano)
    assert len(contenido) == tamano, f"{etiqueta}: {len(contenido)} bytes"
    _override(contexto)
    try:
        resp = _post_documento(
            client, str(empresa.id), str(tracto.id), "grande.pdf", contenido
        )
        assert resp.status_code == 201, resp.text
    finally:
        _limpiar_override()
        # nucleo.documentos es append-only (fn_documento_no_borrar): no se limpia;
        # las filas quedan aisladas por empresa/tracto con token único.


def test_documento_10mb_mas_1_byte_422(client, env_docs):
    engine, empresa, tracto, contexto = env_docs
    contenido = _pdf_de_tamano(_10MB + 1)
    assert len(contenido) == _10MB + 1
    _override(contexto)
    try:
        resp = _post_documento(
            client, str(empresa.id), str(tracto.id), "enorme.pdf", contenido
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["codigo"] == "DATOS_INVALIDOS"
    finally:
        _limpiar_override()


def test_documento_doble_envio_concurrente(client, env_docs):
    """Concurrencia real (2 hilos): el mismo documento enviado dos veces.

    Contrato (Ola 2.1): idempotente. Un POST idéntico devuelve 200 con el
    registro existente; el ganador 201. Exactamente UNA fila por contenido.
    (No hay constraint de BD nueva: la determinación viene del lock de la fila
    del recurso en `ServicioMaestros.subir_documento`.)
    """
    import hashlib

    engine, empresa, tracto, contexto = env_docs
    hash_objetivo = hashlib.sha256(PDF_DUPLICADO).hexdigest()
    _override(contexto)
    try:
        barrera = threading.Barrier(2)
        resultados: list[tuple[int, str]] = []

        def enviar():
            barrera.wait()
            r = _post_documento(
                client, str(empresa.id), str(tracto.id), "duplicado.pdf", PDF_DUPLICADO
            )
            resultados.append((r.status_code, r.json().get("id", "")))

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: enviar(), range(2)))
        estados = sorted(estado for estado, _ in resultados)
        assert estados == [200, 201], f"estados: {resultados}"
        assert len({doc_id for _, doc_id in resultados}) == 1, resultados
        with Session(engine) as session:
            total = session.execute(
                text(
                    "select count(*) from nucleo.documentos "
                    "where tracto_id = :t and hash_sha256 = :h"
                ),
                {"t": tracto.id, "h": hash_objetivo},
            ).scalar_one()
        assert total == 1, f"filas idénticas en nucleo.documentos: {total}"
        with Session(engine) as session:
            vigentes = session.execute(
                text(
                    "select count(*) from nucleo.documentos "
                    "where tracto_id = :t and hash_sha256 = :h and es_vigente"
                ),
                {"t": tracto.id, "h": hash_objetivo},
            ).scalar_one()
        assert vigentes == 1, f"documentos vigentes idénticos: {vigentes}"
    finally:
        _limpiar_override()
        # nucleo.documentos es append-only (fn_documento_no_borrar): no se limpia;
        # las filas quedan aisladas por empresa/tracto con token único.


# --- POD ------------------------------------------------------------------


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


def _post_pod(client, empresa_id, viaje_id, firma_nombre, firma_contenido,
              firma_ct=None, fotos=None):
    files = [("firma", (firma_nombre, firma_contenido, firma_ct or "application/octet-stream"))]
    for nombre, contenido, ct in fotos or []:
        files.append(("fotos", (nombre, contenido, ct)))
    return client.post(
        f"{API}/nucleo/expediente/viajes/{viaje_id}/pod",
        data={"receptor_nombre": "María Receptor", "receptor_rut": "11.111.111-1"},
        files=files,
        headers={"X-Empresa-ID": empresa_id},
    )


def test_pod_firma_con_contenido_no_imagen(client, env_pod):
    """Firma .jpg con contenido PDF: RECHAZADA (Ola 2.1).

    Hallazgo de qa (Media) cerrado: la firma del POD es SOLO imagen. Se valida
    la firma detectada del contenido en `api_pod.py` y otra vez en
    `servicio_pod._validar_firma`; un PDF renombrado `.jpg` devuelve 422.
    """
    engine, empresa, viaje, contexto = env_pod
    _override(contexto)
    try:
        resp = _post_pod(
            client, str(empresa.id), str(viaje.id), "firma.jpg", PDF_OK
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["codigo"] == "DATOS_INVALIDOS"
    finally:
        _limpiar_override()
        # nucleo.pod es append-only (fn_pod_no_borrar): no se limpia; cada test
        # usa un viaje nuevo (fixture por función).


def test_pod_firma_png_con_contenido_jpeg(client, env_pod):
    """Firma .png con contenido JPEG: es imagen, se acepta y se sirve con el
    content-type DETECTADO (image/jpeg), no con el que declare el cliente."""
    engine, empresa, viaje, contexto = env_pod
    _override(contexto)
    try:
        resp = _post_pod(
            client, str(empresa.id), str(viaje.id), "firma.png", JPEG_OK
        )
        assert resp.status_code == 201, resp.text
        ct = _head_content_type(resp.json()["firma_url_firmada"])
        assert ct == "image/jpeg", f"firma servida como: {ct!r}"
    finally:
        _limpiar_override()
        # nucleo.pod es append-only (fn_pod_no_borrar): no se limpia; cada test
        # usa un viaje nuevo (fixture por función).


def test_pod_firma_5mb_mas_1_422(client, env_pod):
    engine, empresa, viaje, contexto = env_pod
    contenido = PNG_OK + b"x" * (_5MB - len(PNG_OK) + 1)
    _override(contexto)
    try:
        resp = _post_pod(
            client, str(empresa.id), str(viaje.id), "firma.png", contenido
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["codigo"] == "DATOS_INVALIDOS"
    finally:
        _limpiar_override()


def test_pod_foto_10mb_mas_1_422(client, env_pod):
    engine, empresa, viaje, contexto = env_pod
    contenido = JPEG_OK + b"x" * (_10MB - len(JPEG_OK) + 1)
    _override(contexto)
    try:
        resp = _post_pod(
            client, str(empresa.id), str(viaje.id), "firma.png", PNG_OK,
            fotos=[("foto.jpg", contenido, "image/jpeg")],
        )
        assert resp.status_code == 422, resp.text
    finally:
        _limpiar_override()


def test_pod_foto_pdf_aceptada_como_foto(client, env_pod):
    """Foto .pdf con contenido PDF: `validar_archivo` acepta PDF/HEIC también
    para las fotos del POD.

    HALLAZGO (severidad baja): el dominio de "fotos" espera imágenes; un PDF
    pasa como foto y se sirve como application/pdf.
    """
    engine, empresa, viaje, contexto = env_pod
    _override(contexto)
    try:
        resp = _post_pod(
            client, str(empresa.id), str(viaje.id), "firma.png", PNG_OK,
            fotos=[("foto.pdf", PDF_OK, "application/pdf")],
        )
        assert resp.status_code == 201, resp.text
        fotos = resp.json()["fotos"]
        assert len(fotos) == 1
        assert _head_content_type(fotos[0]["url_firmada"]) == "application/pdf"
    finally:
        _limpiar_override()
        # nucleo.pod es append-only (fn_pod_no_borrar): no se limpia; cada test
        # usa un viaje nuevo (fixture por función).


def test_pod_foto_contenido_basura_422(client, env_pod):
    engine, empresa, viaje, contexto = env_pod
    _override(contexto)
    try:
        resp = _post_pod(
            client, str(empresa.id), str(viaje.id), "firma.png", PNG_OK,
            fotos=[("foto.jpg", b"MZ\x90 basura", "image/jpeg")],
        )
        assert resp.status_code == 422, resp.text
    finally:
        _limpiar_override()


def test_pod_doble_envio_concurrente(client, env_pod):
    """Concurrencia real: dos POST simultáneos del POD del mismo viaje.

    Esperado: exactamente uno 201 y el otro 409 (unique viaje_id en
    nucleo.pod). El perdedor debe limpiar sus archivos subidos.
    """
    engine, empresa, viaje, contexto = env_pod
    _override(contexto)
    try:
        barrera = threading.Barrier(2)
        resultados: list[int] = []

        def enviar():
            barrera.wait()
            r = _post_pod(
                client, str(empresa.id), str(viaje.id), "firma.png", PNG_OK,
                fotos=[("foto.png", PNG_OK, "image/png")],
            )
            resultados.append(r.status_code)

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: enviar(), range(2)))
        assert sorted(resultados) == [201, 409], f"estados: {resultados}"
        with Session(engine) as session:
            total = session.execute(
                text("select count(*) from nucleo.pod where viaje_id = :v"),
                {"v": viaje.id},
            ).scalar_one()
        assert total == 1, f"filas en nucleo.pod: {total}"
    finally:
        _limpiar_override()
        # nucleo.pod es append-only (fn_pod_no_borrar): no se limpia; cada test
        # usa un viaje nuevo (fixture por función).


# ---------------------------------------------------------------------------
# B. Cutover fail-closed
# ---------------------------------------------------------------------------


class _ResultadoValor:
    def __init__(self, valor):
        self._valor = valor

    def scalar_one_or_none(self):
        return self._valor


class _SesionValor:
    def __init__(self, valor):
        self._valor = valor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return _ResultadoValor(self._valor)


@pytest.mark.parametrize("valor, esperado", [(True, True), (False, False)])
def test_legacy_congelado_fila_presente(monkeypatch, valor, esperado):
    invalidar_cache()
    monkeypatch.setattr(
        "app.nucleo.servicio_cutover.Session", lambda engine: _SesionValor(valor)
    )
    monkeypatch.setattr("app.core.database.get_engine", lambda: object())
    assert legacy_congelado() is esperado
    invalidar_cache()


def test_middleware_congelado_bloquea_escritura_legacy(client, db):
    """HTTP real (in-process): flag true -> POST legacy -> 409 CUTOVER_LEGACY_CONGELADO."""
    with db.cursor() as cur:
        cur.execute("select 1 from nucleo.cutover_control where id = true")
        if cur.fetchone() is None:
            cur.execute("insert into nucleo.cutover_control (id) values (true)")
        cur.execute(
            "select legacy_escritura_congelada from nucleo.cutover_control where id = true"
        )
        original = cur.fetchone()[0]
    invalidar_cache()
    try:
        with db.cursor() as cur:
            cur.execute(
                "update nucleo.cutover_control set legacy_escritura_congelada = true where id = true"
            )
            db.commit()
        # Sin token: el middleware corta antes del auth.
        resp = client.post(f"{API}/viajes", json={"origen": "X"})
        assert resp.status_code == 409, resp.text
        assert resp.json()["codigo"] == "CUTOVER_LEGACY_CONGELADO"
        # Lecturas legacy no se bloquean (401 de auth, no 409).
        resp_get = client.get(f"{API}/viajes")
        assert resp_get.status_code == 401, resp_get.text
        # Las escrituras del núcleo NO se bloquean (422 de validación, no 409).
        resp_nucleo = client.post(f"{API}/nucleo/documentos", data={})
        assert resp_nucleo.status_code != 409
        assert resp_nucleo.json().get("codigo") != "CUTOVER_LEGACY_CONGELADO"
    finally:
        with db.cursor() as cur:
            cur.execute(
                "update nucleo.cutover_control set legacy_escritura_congelada = %s where id = true",
                (original,),
            )
            db.commit()
        invalidar_cache()


def test_middleware_congelado_bloquea_con_credenciales(client, db, headers_admin):
    """Con token real de admin la escritura legacy congelada también se bloquea."""
    with db.cursor() as cur:
        cur.execute("select 1 from nucleo.cutover_control where id = true")
        if cur.fetchone() is None:
            cur.execute("insert into nucleo.cutover_control (id) values (true)")
        cur.execute(
            "select legacy_escritura_congelada from nucleo.cutover_control where id = true"
        )
        original = cur.fetchone()[0]
    invalidar_cache()
    try:
        with db.cursor() as cur:
            cur.execute(
                "update nucleo.cutover_control set legacy_escritura_congelada = true where id = true"
            )
            db.commit()
        resp = client.post(
            f"{API}/viajes",
            json={"origen": "X", "destino": "Y"},
            headers=headers_admin,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["codigo"] == "CUTOVER_LEGACY_CONGELADO"
    finally:
        with db.cursor() as cur:
            cur.execute(
                "update nucleo.cutover_control set legacy_escritura_congelada = %s where id = true",
                (original,),
            )
            db.commit()
        invalidar_cache()


def test_middleware_sin_flag_deja_pasar(client, db):
    """Flag false: el middleware deja pasar (401 de auth, no 409)."""
    with db.cursor() as cur:
        cur.execute(
            "update nucleo.cutover_control set legacy_escritura_congelada = false where id = true"
        )
        db.commit()
    invalidar_cache()
    try:
        resp = client.post(f"{API}/viajes", json={"origen": "X"})
        assert resp.status_code != 409
        assert resp.json().get("codigo") != "CUTOVER_LEGACY_CONGELADO"
    finally:
        invalidar_cache()


def test_middleware_mutacion_sin_garantia(monkeypatch, client, db):
    """Sanidad (mutación): si legacy_congelado() devuelve False (garantía
    retirada), el middleware NO bloquea aunque la fila esté congelada.

    Demuestra que el 409 de test_middleware_congelado_bloquea_* depende del
    mecanismo, no de un artefacto del test.
    """
    with db.cursor() as cur:
        cur.execute(
            "update nucleo.cutover_control set legacy_escritura_congelada = true where id = true"
        )
        db.commit()
    invalidar_cache()
    monkeypatch.setattr("app.main.legacy_congelado", lambda: False)
    try:
        resp = client.post(f"{API}/viajes", json={"origen": "X"})
        assert resp.status_code != 409
        assert resp.json().get("codigo") != "CUTOVER_LEGACY_CONGELADO"
    finally:
        invalidar_cache()
        with db.cursor() as cur:
            cur.execute(
                "update nucleo.cutover_control set legacy_escritura_congelada = false where id = true"
            )
            db.commit()
        invalidar_cache()


# ---------------------------------------------------------------------------
# C. Mapeo SQLSTATE -> HTTP (por HTTP real con credenciales)
# ---------------------------------------------------------------------------


def _sin_fuga_psycopg(body: dict) -> None:
    import json

    crudo = json.dumps(body).lower()
    assert "psycopg" not in crudo
    assert "postgres" not in crudo


def test_23505_rut_chofer_duplicado_409(client, headers_admin, db, etiqueta):
    """Duplicado legacy (choferes.rut unique) -> 409 REGISTRO_DUPLICADO."""
    body = {
        "nombre": f"Chofer {etiqueta}",
        "rut": f"{etiqueta}-RUT",
        "sueldo_base": 400000,
        "porcentaje_produccion": 0.10,
    }
    r1 = client.post(f"{API}/choferes", json=body, headers=headers_admin)
    assert r1.status_code == 201, r1.text
    try:
        r2 = client.post(f"{API}/choferes", json=body, headers=headers_admin)
        assert r2.status_code == 409, r2.text
        payload = r2.json()
        assert payload["codigo"] == "REGISTRO_DUPLICADO"
        _sin_fuga_psycopg(payload)
    finally:
        with db.cursor() as cur:
            cur.execute("delete from choferes where rut=%s", (body["rut"],))
            db.commit()


def test_23514_gasto_negativo_422(client, headers_admin, db, etiqueta):
    """CHECK monto >= 0 de public.gastos_viaje -> 422 DATOS_INVALIDOS (handler global)."""
    cl = client.post(
        f"{API}/clientes",
        json={"razon_social": f"Cliente {etiqueta}", "rut": f"{etiqueta}-1", "dias_pago": 30},
        headers=headers_admin,
    ).json()
    ch = client.post(
        f"{API}/choferes",
        json={
            "nombre": f"Chofer {etiqueta}",
            "rut": f"{etiqueta}-2",
            "sueldo_base": 400000,
            "porcentaje_produccion": 0.10,
        },
        headers=headers_admin,
    ).json()
    tr = client.post(
        f"{API}/tractos",
        json={"patente": f"{etiqueta}-A", "marca": "Test", "km_actual": 10000},
        headers=headers_admin,
    ).json()
    rp = client.post(
        f"{API}/ramplas",
        json={"patente": f"{etiqueta}-B", "tipo": "plana"},
        headers=headers_admin,
    ).json()
    viaje = client.post(
        f"{API}/viajes",
        json={
            "fecha_inicio": "2026-09-05",
            "origen": "Santiago",
            "destino": "Concepción",
            "valor_flete_neto": 500000,
            "cliente_id": cl["id"],
            "chofer_id": ch["id"],
            "tracto_id": tr["id"],
            "rampla_id": rp["id"],
        },
        headers=headers_admin,
    ).json()
    try:
        resp = client.post(
            f"{API}/viajes/{viaje['id']}/gastos",
            data={"categoria": "peaje", "monto": "-1000"},
            headers=headers_admin,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["codigo"] == "DATOS_INVALIDOS"
        _sin_fuga_psycopg(resp.json())
    finally:
        with db.cursor() as cur:
            cur.execute("delete from gastos_viaje where viaje_id=%s", (viaje["id"],))
            cur.execute("delete from viajes where id=%s", (viaje["id"],))
            cur.execute("delete from clientes where id=%s", (cl["id"],))
            cur.execute("delete from choferes where id=%s", (ch["id"],))
            cur.execute("delete from tractos where id=%s", (tr["id"],))
            cur.execute("delete from ramplas where id=%s", (rp["id"],))
            db.commit()


def test_23505_liquidacion_concurrente(client, headers_admin, db, etiqueta):
    """Concurrencia real: dos POST /liquidaciones/calcular simultáneos.

    La unicidad (chofer_id, mes) es la última defensa; esperado: un 200 y un
    409 REGISTRO_DUPLICADO (o ambos 200 si el perdedor relee la fila), y
    SIEMPRE exactamente una fila.
    """
    ch = client.post(
        f"{API}/choferes",
        json={
            "nombre": f"Chofer {etiqueta}",
            "rut": f"{etiqueta}-LQ",
            "sueldo_base": 400000,
            "porcentaje_produccion": 0.10,
        },
        headers=headers_admin,
    ).json()
    mes = "2026-09"
    barrera = threading.Barrier(2)
    estados: list[int] = []

    def calcular():
        barrera.wait()
        r = client.post(
            f"{API}/liquidaciones/calcular",
            params={"chofer_id": ch["id"], "mes": mes},
            headers=headers_admin,
        )
        estados.append(r.status_code)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: calcular(), range(2)))
        assert set(estados) <= {200, 409}, f"estados: {estados}"
        assert 200 in estados, f"estados: {estados}"
        with db.cursor() as cur:
            cur.execute(
                "select count(*) from liquidaciones where chofer_id=%s and mes=%s",
                (ch["id"], mes),
            )
            total = cur.fetchone()[0]
        assert total == 1, f"filas en liquidaciones: {total}"
    finally:
        with db.cursor() as cur:
            cur.execute("delete from liquidaciones where chofer_id=%s", (ch["id"],))
            cur.execute("delete from choferes where id=%s", (ch["id"],))
            db.commit()


def test_promesa_monto_cero_422_y_monto_positivo_201(client, db):
    """Promesa con monto 0: el schema (gt=0) rechaza 422 antes de llegar al
    CHECK de la base (defensa en capas; el 23514 queda sombreado)."""
    engine = create_engine(_url(), future=True)
    sufijo = uuid.uuid4().hex[:8]
    with Session(engine) as session:
        empresa = Empresa(
            codigo=f"PRM-{sufijo}",
            razon_social=f"Empresa Promesa {sufijo}",
            rut=rut_empresa(),
        )
        session.add(empresa)
        session.commit()
        session.refresh(empresa)
        cliente = Cliente(
            empresa_id=empresa.id, razon_social=f"Cliente {sufijo}", rut=str(uuid.uuid4().int)[:10]
        )
        session.add(cliente)
        session.commit()
        session.refresh(cliente)
        factura = FacturaNucleo(
            empresa_id=empresa.id,
            cliente_id=cliente.id,
            numero_factura=f"FAC-{sufijo}",
            fecha_vencimiento=date.today() + timedelta(days=30),
            neto=Decimal("100000.00"),
            iva=Decimal("19000.00"),
            estado="emitida",
        )
        session.add(factura)
        session.commit()
        session.refresh(factura)
        session.refresh(empresa)  # el commit anterior expiró los atributos

    contexto = ContextoEmpresa(
        auth_id=str(uuid.uuid4()), empresa=empresa, rol=RolEmpresa.contador
    )
    _override(contexto)
    try:
        cero = client.post(
            f"{API}/nucleo/cobranza/facturas/{factura.id}/promesas",
            json={"fecha_prometida": (date.today() + timedelta(days=7)).isoformat(), "monto": 0},
            headers={"X-Empresa-ID": str(empresa.id)},
        )
        assert cero.status_code == 422, cero.text
        positivo = client.post(
            f"{API}/nucleo/cobranza/facturas/{factura.id}/promesas",
            json={"fecha_prometida": (date.today() + timedelta(days=7)).isoformat(), "monto": 1},
            headers={"X-Empresa-ID": str(empresa.id)},
        )
        assert positivo.status_code == 200, positivo.text
    finally:
        _limpiar_override()
        with Session(engine) as session:
            session.execute(
                text("delete from nucleo.promesas_pago_nucleo where factura_id = :f"),
                {"f": factura.id},
            )
            session.execute(
                text("delete from nucleo.facturas_nucleo where id = :f"),
                {"f": factura.id},
            )
            session.commit()
