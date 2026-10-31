"""Pruebas unitarias de la Ola 2 (Fase 1) de seguridad e higiene del backend.

Cubre:
- F-01: `legacy_congelado()` fail-closed ante error de lectura o fila ausente.
- F-03: handler global de IntegrityError con mapeo por sqlstate.
- F-08: `get_config_decimal` y `valores` de KPI ya no tragan errores en silencio.
- F0-05: firma por magic bytes, content-type canónico y lectura acotada.
"""

from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.nucleo import storage
from app.nucleo.errores import DatosInvalidos
from app.nucleo.servicio_cutover import invalidar_cache, legacy_congelado

# ---------------------------------------------------------------------------
# F-01: fail-closed del flag de cutover
# ---------------------------------------------------------------------------


class _ResultadoNone:
    def scalar_one_or_none(self):
        return None


class _SesionFalsa:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return _ResultadoNone()


def test_legacy_congelado_fail_closed_ante_error_de_lectura(monkeypatch, caplog):
    invalidar_cache()

    def boom():
        raise RuntimeError("sin conexión a la base")

    monkeypatch.setattr("app.core.database.get_engine", boom)
    with caplog.at_level(logging.ERROR, logger="app.nucleo.servicio_cutover"):
        resultado = legacy_congelado()
    assert resultado is True
    assert any("fail-closed" in m for m in caplog.messages)
    invalidar_cache()


def test_legacy_congelado_fail_closed_ante_fila_ausente(monkeypatch, caplog):
    invalidar_cache()
    monkeypatch.setattr(
        "app.nucleo.servicio_cutover.Session", lambda engine: _SesionFalsa()
    )
    monkeypatch.setattr("app.core.database.get_engine", lambda: object())
    with caplog.at_level(logging.WARNING, logger="app.nucleo.servicio_cutover"):
        resultado = legacy_congelado()
    assert resultado is True
    assert any("fail-closed" in m for m in caplog.messages)
    invalidar_cache()


def test_legacy_congelado_respeta_cache_sin_reconsultar(monkeypatch):
    invalidar_cache()
    llamadas = 0

    def boom():
        nonlocal llamadas
        llamadas += 1
        raise RuntimeError("no debería consultarse")

    monkeypatch.setattr("app.core.database.get_engine", boom)
    assert legacy_congelado() is True  # llena la caché fail-closed
    assert llamadas == 1

    # Con caché fresca no consulta la base: el fallo de arriba no se repite.
    assert legacy_congelado() is True
    assert llamadas == 1
    invalidar_cache()


# ---------------------------------------------------------------------------
# F-03: handler global de IntegrityError
# ---------------------------------------------------------------------------


def _integrity(sqlstate: str | None) -> IntegrityError:
    _Orig = type(
        "_Orig", (), {"sqlstate": sqlstate, "pgcode": None, "diag": None}
    )
    return IntegrityError("INSERT INTO x ...", {}, _Orig())


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/clientes",
            "raw_path": b"/api/v1/clientes",
            "query_string": b"",
            "headers": [],
            "server": ("test", 80),
            "client": ("test", 1),
            "scheme": "http",
            "root_path": "",
            "http_version": "1.1",
        }
    )


@pytest.mark.parametrize(
    "sqlstate, esperado",
    [
        ("23505", 409),
        ("23P01", 409),
        ("23514", 422),
        ("23502", 422),
        ("23503", 422),
        ("40001", 500),
        ("99999", 500),
        (None, 500),
    ],
)
def test_handler_integrity_mapea_sqlstate(sqlstate, esperado):
    from app.main import manejador_integrity_error

    respuesta = asyncio.run(
        manejador_integrity_error(_request(), _integrity(sqlstate))
    )
    assert respuesta.status_code == esperado
    body = json.loads(respuesta.body)
    assert "detail" in body
    assert "codigo" in body
    # Nunca filtrar mensajes crudos de PostgreSQL al cliente.
    assert "psycopg" not in json.dumps(body)
    assert "postgres" not in json.dumps(body).lower()


def test_handler_integrity_23505_usa_mensaje_de_dominio():
    from app.main import manejador_integrity_error

    respuesta = asyncio.run(
        manejador_integrity_error(_request(), _integrity("23505"))
    )
    body = json.loads(respuesta.body)
    assert body["codigo"] == "REGISTRO_DUPLICADO"
    assert "Ya existe un registro" in body["detail"]


# ---------------------------------------------------------------------------
# F-08: sin swallows silenciosos
# ---------------------------------------------------------------------------


def test_get_config_decimal_registra_y_devuelve_default(monkeypatch, caplog):
    from app.core.settings_db import get_config_decimal

    class _Sesion:
        def get(self, modelo, clave):
            raise RuntimeError("tabla inexistente")

    with caplog.at_level(logging.WARNING, logger="app.core.settings_db"):
        resultado = get_config_decimal(_Sesion(), "iva_porcentaje", "19")
    assert resultado == Decimal("19")
    assert any("iva_porcentaje" in m for m in caplog.messages)


def test_kpi_valores_registra_fallo_de_metricas(monkeypatch, caplog):
    from app.api.routes import kpis as mod_kpis
    from app.services import kpi_engine

    class _ResultadoVacio:
        def all(self):
            return []

    class _Sesion:
        def exec(self, stmt):
            return _ResultadoVacio()

    def boom(session, periodo):
        raise RuntimeError("no hay métricas")

    monkeypatch.setattr(kpi_engine, "metricas_global", boom)
    with caplog.at_level(logging.WARNING, logger="app.api.routes.kpis"):
        resultado = mod_kpis.valores(periodo=None, session=_Sesion(), _=None)
    assert resultado == []
    assert any("métricas globales" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# F0-05: magic bytes, content-type canónico y lectura acotada
# ---------------------------------------------------------------------------

PDF_OK = (
    b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
)
JPEG_OK = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00resto de bytes"
PNG_OK = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRcontenido"
WEBP_OK = b"RIFF\x24\x00\x00\x00WEBPVP8 contenido"
HEIC_OK = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1"


@pytest.mark.parametrize(
    "ext, contenido",
    [
        (".pdf", PDF_OK),
        (".jpg", JPEG_OK),
        (".jpeg", JPEG_OK),
        (".png", PNG_OK),
        (".webp", WEBP_OK),
        (".heic", HEIC_OK),
    ],
)
def test_firma_valida_acepta_formato_correcto(ext, contenido):
    assert storage.firma_valida(ext, contenido) is True


@pytest.mark.parametrize(
    "ext, contenido",
    [
        (".pdf", b"esto no es un pdf"),
        (".pdf", b"\x89PNG\r\n\x1a\nbytes PNG con extension PDF"),
        (".png", PDF_OK),
        (".jpg", PDF_OK),
        (".webp", b"RIFF\x24\x00\x00\x00AVI contenido"),
        (".heic", b"bytes sin caja ftyp"),
    ],
)
def test_firma_valida_rechaza_formato_incorrecto(ext, contenido):
    assert storage.firma_valida(ext, contenido) is False


def test_pdf_con_bytes_extra_es_valido():
    # Un PDF válido tiene %PDF- al inicio, contenido arbitrario y %%EOF al final.
    assert storage.firma_valida(
        ".pdf", b"%PDF-1.4\xe2\xe3\xcf\xd3" + b"x" * 500 + b"\n%%EOF\n"
    )


def test_firma_pdf_sin_marca_fin_se_rechaza():
    # SEC-018: `%PDF` (o `%PDF-`) sin `%%EOF` no acredita un PDF.
    assert storage.firma_valida(".pdf", b"%PDF-1.4\n<html><script>x</script>") is False
    assert storage.detectar_content_type(b"%PDF-1.4\n<html>x</html>") is None


def test_firma_pdf_marca_fin_fuera_de_la_ventana_se_rechaza():
    # %%EOF solo cuenta dentro de la cola acotada (VENTANA_FIN_PDF).
    relleno = b"x" * (storage.VENTANA_FIN_PDF + 10)
    contenido = b"%PDF-1.7\n%%EOF\n" + relleno
    assert storage.firma_valida(".pdf", contenido) is False


def test_detectar_content_type_imagen_rechaza_pdf():
    assert storage.detectar_content_type_imagen(PDF_OK) is None
    assert storage.detectar_content_type_imagen(PNG_OK) == "image/png"
    assert storage.es_imagen("application/pdf") is False


def test_validar_imagen_rechaza_pdf_renombrado():
    with pytest.raises(DatosInvalidos):
        storage.validar_imagen("firma.jpg", PDF_OK)


def test_validar_archivo_rechaza_firma_que_no_calza():
    with pytest.raises(DatosInvalidos):
        storage.validar_archivo("evidencia.png", b"esto no es una imagen")


def test_validar_archivo_acepta_png_con_firma():
    assert storage.validar_archivo("evidencia.png", PNG_OK) == ".png"


@pytest.mark.parametrize(
    "ext, esperado",
    [
        (".pdf", "application/pdf"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".png", "image/png"),
        (".webp", "image/webp"),
        (".heic", "image/heic"),
    ],
)
def test_content_type_canonico(ext, esperado):
    assert storage.content_type_para(ext) == esperado


def test_detectar_content_type_por_firma():
    assert storage.detectar_content_type(PNG_OK) == "image/png"
    assert storage.detectar_content_type(JPEG_OK) == "image/jpeg"
    assert storage.detectar_content_type(PDF_OK) == "application/pdf"
    assert storage.detectar_content_type(b"basura binaria") is None


def test_leer_archivo_acotado_rechaza_exceso():
    class _UploadFile:
        async def read(self, n):
            if n <= 0:
                return b""
            return b"x" * 20

    archivo = _UploadFile()
    with pytest.raises(DatosInvalidos):
        asyncio.run(storage.leer_archivo_acotado(archivo, max_bytes=100))


def test_leer_archivo_acotado_acepta_exacto():
    """10 MB exactos se aceptan; un byte más se rechaza (borde cerrado)."""

    class _UploadFile:
        def __init__(self, contenido: bytes):
            self._contenido = contenido
            self._pos = 0

        async def read(self, n):
            trozo = self._contenido[self._pos : self._pos + n]
            self._pos += len(trozo)
            return trozo

    limite = 100
    assert (
        len(asyncio.run(storage.leer_archivo_acotado(_UploadFile(b"x" * limite), limite)))
        == limite
    )
    with pytest.raises(DatosInvalidos):
        asyncio.run(storage.leer_archivo_acotado(_UploadFile(b"x" * (limite + 1)), limite))


def test_leer_archivo_acotado_sync_rechaza_exceso():
    class _Fichero:
        def read(self, n):
            return b"x" * n

    class _UploadFileSync:
        file = _Fichero()

    with pytest.raises(DatosInvalidos):
        storage.leer_archivo_acotado_sync(_UploadFileSync(), max_bytes=100)


# ---------------------------------------------------------------------------
# SEC-017: el 23514 no interpola el mensaje crudo de PostgreSQL
# ---------------------------------------------------------------------------


def test_traducir_23514_sin_texto_de_postgres():
    from app.nucleo.errores import ReglaNegocioViolada, traducir_integrity_error

    class _Diag:
        constraint_name = "ck_maestros_tractos_peso"
        message_primary = (
            'new row for relation "nucleo.maestros_tractos" violates check '
            'constraint "ck_maestros_tractos_peso"'
        )

    class _Orig:
        sqlstate = "23514"
        pgcode = "23514"
        diag = _Diag()

    error = traducir_integrity_error(IntegrityError("update", {}, _Orig()))

    assert isinstance(error, ReglaNegocioViolada)
    # El status HTTP actual no cambia (31 sitios dependen de él).
    assert error.status_code == 409
    assert error.codigo == "REGLA_NEGOCIO_VIOLADA"
    mensaje = error.mensaje.lower()
    for fuga in ("nucleo.", "violates", "constraint", "relation", "new row"):
        assert fuga not in mensaje, f"mensaje filtra PG: {error.mensaje!r}"
    assert "regla de negocio" in mensaje
