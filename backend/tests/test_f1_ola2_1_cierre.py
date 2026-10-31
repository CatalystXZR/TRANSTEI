"""Cierre de hallazgos de la revisión independiente F1-Ola2 (2026-10-30).

Cubre, con evidencia ejecutable, los hallazgos asignados al agente `backend`:

- SEC-016: `congelar()`/`descongelar()` verifican `rowcount` (fila de control).
- SEC-017: el 23514 no interpola el mensaje crudo de PostgreSQL (ver
  `tests/test_seguridad_ola2.py::test_traducir_23514_sin_texto_de_postgres`).
- Hallazgo qa (Media): la firma del POD es SOLO imagen (PDF renombrado `.jpg`
  → 422), validada por firma detectada y servida con el content-type detectado.
- Hallazgo qa (Media-baja): alta de documento idempotente (reenvío idéntico →
  200 con el registro existente, sin duplicar fila).

SEC-018/SEC-019 (content-type del cliente y lectura acotada) se cubren por HTTP
en los tests de expediente/maestros; acá se prueba la unidad que los habilita.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.main import app
from app.nucleo.deps import ContextoEmpresa, RolEmpresa, get_contexto_empresa
from app.nucleo.errores import DatosInvalidos, ErrorPersistencia
from app.nucleo.models import Empresa, Tracto
from app.nucleo.servicio_cutover import ServicioCutover, invalidar_cache
from app.nucleo.servicio_pod import ServicioPOD
from contexto_helpers import contexto_de_prueba
from rut_helpers import rut_empresa

API = "/api/v1"

PDF_OK = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
JPEG_OK = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00resto de bytes"
PNG_OK = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _limite_pdf(total: int) -> bytes:
    """PDF válido de exactamente `total` bytes (para los bordes de tamaño)."""
    inicio = b"%PDF-1.7\n"
    fin = b"\n%%EOF\n"
    return inicio + b"x" * (total - len(inicio) - len(fin)) + fin


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración")
    return url


# ---------------------------------------------------------------------------
# SEC-016 — congelar() no puede "triunfar" sin la fila de control
# ---------------------------------------------------------------------------


class _ResultadoRowcount:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _SesionFalsa:
    def __init__(self, rowcount: int) -> None:
        self._rowcount = rowcount
        self.commits = 0
        self.rollbacks = 0
        self.sentencias: list[str] = []

    def execute(self, *args, **kwargs):
        self.sentencias.append(str(args[0] if args else kwargs.get("statement")))
        return _ResultadoRowcount(self._rowcount)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _Contexto:
    auth_id = "auth-test"
    request_id = None
    empresa = None


@pytest.mark.parametrize("metodo", ["congelar", "descongelar"])
def test_cutover_sin_fila_de_control_falla(metodo):
    """rowcount == 0 → ErrorPersistencia clara, sin commit (SEC-016)."""
    invalidar_cache()
    session = _SesionFalsa(rowcount=0)
    servicio = ServicioCutover(session, _Contexto())  # type: ignore[arg-type]

    with pytest.raises(ErrorPersistencia) as excinfo:
        getattr(servicio, metodo)("prueba unitaria")

    assert session.commits == 0, "no debe commitear un update que no afectó filas"
    assert session.rollbacks == 1
    assert "nucleo.cutover_control" in excinfo.value.mensaje
    assert "no se pudo" in excinfo.value.mensaje.lower()


@pytest.mark.parametrize("metodo", ["congelar", "descongelar"])
def test_cutover_con_fila_de_control_commitea(metodo):
    """rowcount == 1 → commit e invalidación de caché (camino normal)."""
    invalidar_cache()
    session = _SesionFalsa(rowcount=1)
    servicio = ServicioCutover(session, _Contexto())  # type: ignore[arg-type]
    servicio.estado = lambda: "estado-falso"  # type: ignore[method-assign]

    assert getattr(servicio, metodo)("prueba unitaria") == "estado-falso"
    assert session.commits == 1
    assert session.rollbacks == 0


# ---------------------------------------------------------------------------
# Hallazgo qa — firma del POD: SOLO imagen
# ---------------------------------------------------------------------------


def test_pod_firma_pdf_renombrado_jpg_rechazada():
    with pytest.raises(DatosInvalidos):
        ServicioPOD._validar_firma("firma.jpg", PDF_OK)


def test_pod_firma_heic_rechazada():
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1"
    with pytest.raises(DatosInvalidos):
        ServicioPOD._validar_firma("firma.heic", heic)


def test_pod_firma_texto_rechazada():
    with pytest.raises(DatosInvalidos):
        ServicioPOD._validar_firma("firma.png", b"no soy una imagen")


def test_pod_firma_png_valida_devuelve_ct_detectado():
    ext, content_type = ServicioPOD._validar_firma("firma.png", PNG_OK)
    assert (ext, content_type) == (".png", "image/png")


def test_pod_firma_jpg_con_contenido_png_usa_ct_detectado():
    """Extensión y contenido discrepan: manda el contenido (content-type)."""
    ext, content_type = ServicioPOD._validar_firma("firma.jpg", PNG_OK)
    assert (ext, content_type) == (".jpg", "image/png")


def test_pod_firma_5mb_mas_1_rechazada():
    contenido = PNG_OK + b"x" * (5 * 1024 * 1024 - len(PNG_OK) + 1)
    with pytest.raises(DatosInvalidos):
        ServicioPOD._validar_firma("firma.png", contenido)


# ---------------------------------------------------------------------------
# Hallazgo qa — alta de documento idempotente (reenvío secuencial)
# ---------------------------------------------------------------------------


@pytest.fixture()
def env_docs():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1 from nucleo.documentos limit 1"))
    except SQLAlchemyError as exc:  # pragma: no cover
        pytest.skip(f"Falta aplicar la migración 0004: {exc}")
    sufijo = uuid.uuid4().hex[:8]
    with Session(engine) as session:
        empresa = Empresa(
            codigo=f"IDEM-{sufijo}",
            razon_social=f"Empresa Idem {sufijo}",
            rut=rut_empresa(),
        )
        session.add(empresa)
        session.commit()
        session.refresh(empresa)
        tracto = Tracto(
            empresa_id=empresa.id,
            patente=f"I{sufijo[:6].upper()}",
            peso_bruto_kg=Decimal("39000"),
            tara_kg=Decimal("9000"),
            capacidad_carga_kg=Decimal("30000"),
        )
        session.add(tracto)
        session.commit()
        session.refresh(tracto)
        session.refresh(empresa)
    contexto = ContextoEmpresa(
        auth_id=str(uuid.uuid4()), empresa=empresa, rol=RolEmpresa.admin
    )
    return engine, empresa, tracto, contexto


def _post(client, empresa_id, tracto_id, nombre, contenido, vence):
    return client.post(
        f"{API}/nucleo/documentos",
        data={
            "recurso_tipo": "tracto",
            "recurso_id": tracto_id,
            "tipo": "revision_tecnica",
            "vence_en": vence,
        },
        files={
            "archivo": (nombre, contenido, "application/pdf"),
        },
        headers={"X-Empresa-ID": empresa_id},
    )


def test_documento_reenvio_identico_es_idempotente(client, env_docs):
    """Mismo contenido + metadatos: 201 la primera vez, 200 la segunda, 1 fila."""
    engine, empresa, tracto, contexto = env_docs
    vence = (date.today() + timedelta(days=30)).isoformat()
    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(contexto)
    try:
        primera = _post(client, str(empresa.id), str(tracto.id), "rt.pdf", PDF_OK, vence)
        assert primera.status_code == 201, primera.text
        segunda = _post(client, str(empresa.id), str(tracto.id), "rt.pdf", PDF_OK, vence)
        assert segunda.status_code == 200, segunda.text
        assert primera.json()["id"] == segunda.json()["id"]
        assert segunda.json()["hash_sha256"] == hashlib.sha256(PDF_OK).hexdigest()
        with Session(engine) as session:
            total = session.execute(
                text(
                    "select count(*) from nucleo.documentos "
                    "where tracto_id = :t and hash_sha256 = :h"
                ),
                {"t": tracto.id, "h": hashlib.sha256(PDF_OK).hexdigest()},
            ).scalar_one()
        assert total == 1, f"filas duplicadas en nucleo.documentos: {total}"
    finally:
        app.dependency_overrides.clear()


def test_documento_mismo_contenido_otra_vigencia_crea_otro_registro(client, env_docs):
    """La deduplicación no puede confundir una renovación con un duplicado."""
    engine, empresa, tracto, contexto = env_docs
    hoy = date.today()
    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(contexto)
    try:
        uno = _post(
            client,
            str(empresa.id),
            str(tracto.id),
            "rt.pdf",
            PDF_OK,
            (hoy + timedelta(days=30)).isoformat(),
        )
        dos = _post(
            client,
            str(empresa.id),
            str(tracto.id),
            "rt.pdf",
            PDF_OK,
            (hoy + timedelta(days=400)).isoformat(),
        )
        assert (uno.status_code, dos.status_code) == (201, 201)
        assert uno.json()["id"] != dos.json()["id"]
        with Session(engine) as session:
            vigentes = session.execute(
                text(
                    "select count(*) from nucleo.documentos "
                    "where tracto_id = :t and es_vigente"
                ),
                {"t": tracto.id},
            ).scalar_one()
        assert vigentes == 1, "solo la última revisión debe quedar vigente"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# SEC-018 — el content-type servido es el detectado, no el del cliente
# ---------------------------------------------------------------------------


def test_documento_servido_con_content_type_detectado(client, env_docs):
    """Cliente declara text/html; el servidor sirve application/pdf."""
    import httpx

    engine, empresa, tracto, contexto = env_docs
    vence = (date.today() + timedelta(days=30)).isoformat()
    contenido = PDF_OK
    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(contexto)
    try:
        resp = client.post(
            f"{API}/nucleo/documentos",
            data={
                "recurso_tipo": "tracto",
                "recurso_id": str(tracto.id),
                "tipo": "permiso_circulacion",
                "vence_en": vence,
            },
            files={"archivo": ("pc.html.pdf", contenido, "text/html")},
            headers={"X-Empresa-ID": str(empresa.id)},
        )
        assert resp.status_code == 201, resp.text
        url = client.get(
            f"{API}/nucleo/documentos/{resp.json()['id']}/url",
            headers={"X-Empresa-ID": str(empresa.id)},
        ).json()["url"]
        with httpx.Client(timeout=20) as h:
            ct = h.head(url, follow_redirects=True).headers.get("content-type")
        assert ct == "application/pdf", f"content-type servido: {ct!r}"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# SEC-019 — lectura acotada en los endpoints de expediente y gastos
# ---------------------------------------------------------------------------


class _UploadFileFalso:
    """Imita lo mínimo de `UploadFile` que usan los endpoints."""

    def __init__(self, contenido: bytes, nombre: str, content_type: str) -> None:
        self._contenido = contenido
        self._pos = 0
        self.filename = nombre
        self.content_type = content_type

    async def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            trozo = self._contenido[self._pos :]
        else:
            trozo = self._contenido[self._pos : self._pos + n]
        self._pos += len(trozo)
        return trozo


class _ServicioCaptura:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def subir_documento(self, viaje_id, **kwargs):
        self.kwargs = {"viaje_id": viaje_id, **kwargs}
        return "ok"

    def adjuntar_comprobante(self, gasto_id, **kwargs):
        self.kwargs = {"gasto_id": gasto_id, **kwargs}
        return "ok"


def test_expediente_ignora_content_type_del_cliente():
    """SEC-018: expediente guarda el CT detectado, no el header multipart."""
    import asyncio

    from app.nucleo import api_expediente

    servicio = _ServicioCaptura()
    archivo = _UploadFileFalso(PDF_OK, "doc.pdf", "text/html")
    viaje_id = uuid.uuid4()

    resultado = asyncio.run(
        api_expediente.subir_documento(
            viaje_id=viaje_id,
            tipo="otro",
            observaciones=None,
            archivo=archivo,  # type: ignore[arg-type]
            servicio=servicio,  # type: ignore[arg-type]
        )
    )

    assert resultado == "ok"
    assert servicio.kwargs["content_type"] == "application/pdf"
    assert servicio.kwargs["contenido"] == PDF_OK
    assert servicio.kwargs["nombre_archivo"] == "doc.pdf"


def test_expediente_rechaza_contenido_no_reconocido():
    import asyncio

    from app.nucleo import api_expediente

    archivo = _UploadFileFalso(b"<html>no soy archivo</html>", "doc.pdf", "text/html")
    with pytest.raises(DatosInvalidos):
        asyncio.run(
            api_expediente.subir_documento(
                viaje_id=uuid.uuid4(),
                tipo="otro",
                observaciones=None,
                archivo=archivo,  # type: ignore[arg-type]
                servicio=_ServicioCaptura(),  # type: ignore[arg-type]
            )
        )


def test_expediente_lectura_acotada_rechaza_exceso():
    """SEC-019: el endpoint corta en el límite antes de bufferizar todo."""
    import asyncio

    from app.nucleo import api_expediente

    contenido = _limite_pdf(10 * 1024 * 1024 + 1)
    archivo = _UploadFileFalso(contenido, "grande.pdf", "application/pdf")
    with pytest.raises(DatosInvalidos):
        asyncio.run(
            api_expediente.subir_documento(
                viaje_id=uuid.uuid4(),
                tipo="otro",
                observaciones=None,
                archivo=archivo,  # type: ignore[arg-type]
                servicio=_ServicioCaptura(),  # type: ignore[arg-type]
            )
        )


def test_gastos_ignora_content_type_del_cliente():
    """SEC-018: comprobante de gasto con el mismo criterio."""
    import asyncio

    from app.nucleo import api_gastos

    servicio = _ServicioCaptura()
    archivo = _UploadFileFalso(JPEG_OK, "boleta.jpg", "text/html")
    gasto_id = uuid.uuid4()

    resultado = asyncio.run(
        api_gastos.adjuntar_comprobante(
            gasto_id=gasto_id,
            archivo=archivo,  # type: ignore[arg-type]
            servicio=servicio,  # type: ignore[arg-type]
        )
    )

    assert resultado == "ok"
    assert servicio.kwargs["content_type"] == "image/jpeg"
    assert servicio.kwargs["contenido"] == JPEG_OK


def test_gastos_lectura_acotada_rechaza_exceso():
    import asyncio

    from app.nucleo import api_gastos

    archivo = _UploadFileFalso(
        JPEG_OK + b"x" * (10 * 1024 * 1024 - len(JPEG_OK) + 1), "boleta.jpg", "image/jpeg"
    )
    with pytest.raises(DatosInvalidos):
        asyncio.run(
            api_gastos.adjuntar_comprobante(
                gasto_id=uuid.uuid4(),
                archivo=archivo,  # type: ignore[arg-type]
                servicio=_ServicioCaptura(),  # type: ignore[arg-type]
            )
        )
