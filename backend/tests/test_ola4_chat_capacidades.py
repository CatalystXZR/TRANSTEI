"""Adversariales del chat in-app, capacidades y muro de pago (Ola 4).

Cubre los ataques que el camino feliz de `test_agente_chat_http.py` no ejerce:

1. SEC-052: una tool premium con una fila de override `habilitada=true` sigue
   devolviendo `upsell` y **no ejecuta** si el módulo no está activo (el muro de
   pago se evalúa antes del override; una fila vieja no enciende el módulo).
2. Una capacidad deshabilitada por fila devuelve error y **no** escribe.
3. Una fila que habilita una capacidad gerente para la **secretaria** no se
   concede: el límite duro es del catálogo (`capacidad.agentes`), no de la tabla.
4. El panel `/nucleo/agente/configuracion` documentado en ADR-0009 debe existir;
   esta prueba lo verifica y falla si el router no está montado (defecto real,
   no se omite).
5. SEC-055/061: aprobar como `admin` una propuesta del chat no salta el alcance
   por empresa: una anulación sobre un viaje ajeno devuelve 404 y la solicitud
   queda pendiente (rollback).
6. Idempotencia concurrente: dos POST simultáneos con la misma
   `clave_idempotencia` producen un solo turno y **una sola** llamada al LLM.

Las pruebas HTTP usan el `TestClient` real y un JWT real (`headers_admin`). La
empresa y la membresía se crean confirmadas porque los endpoints hacen
`commit()`; no se reutiliza el `escenario` transaccional de la suite existente.
"""

from __future__ import annotations

import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import ola4_helpers as h
import psycopg
import pytest
from conftest import _login as _login_supabase
from rut_helpers import rut_empresa
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.main import app
from app.nucleo.agente.chat import capacidades as catalogo
from app.nucleo.agente.chat.llm import get_cliente_llm
from app.nucleo.agente.chat.modelos import (
    LlamadaHerramienta,
    MensajeLLM,
    RespuestaLLM,
)
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import DatosInvalidos
from app.nucleo.models import (
    EstadoViaje,
    ModalidadTarifa,
    RolEmpresa,
    Tarifa,
)

pytestmark = pytest.mark.integracion

API = settings.API_V1_PREFIX
RUTA_CHAT = f"{API}/nucleo/agente/chat"
RUTA_CONFIG = f"{API}/nucleo/agente/configuracion"
RUTA_SOLICITUDES = f"{API}/nucleo/agente/solicitudes"

CLAVE_GERENTE = "sk-gerente-" + "A" * 60
CLAVE_SECRETARIA = "sk-secretaria-" + "B" * 60


# ---------------------------------------------------------------------------
# LLM falso (nunca se llama a DeepSeek)
# ---------------------------------------------------------------------------
class FakeLLM:
    def __init__(self) -> None:
        self.guion: list[RespuestaLLM] = []
        self.llamadas: list[dict] = []
        self.lock = threading.Lock()

    def responder(
        self,
        mensajes: list[MensajeLLM],
        herramientas: list[dict],
        *,
        api_key: str,
        modelo: str,
    ) -> RespuestaLLM:
        with self.lock:
            self.llamadas.append(
                {
                    "mensajes": list(mensajes),
                    "herramientas": herramientas,
                    "api_key": api_key,
                    "modelo": modelo,
                }
            )
            if not self.guion:
                raise AssertionError("el LLM fue llamado más veces que el guion")
            return self.guion.pop(0)


class FakeLLMConcurrente:
    """LLM sin guion: cuenta llamadas de forma atómica para la carrera."""

    def __init__(self) -> None:
        self.llamadas = 0
        self.lock = threading.Lock()

    def responder(self, mensajes, herramientas, *, api_key, modelo):
        with self.lock:
            self.llamadas += 1
        return RespuestaLLM(
            contenido="Respuesta idempotente.", llamadas=[], usage={"total_tokens": 1}
        )


def _texto(contenido: str) -> RespuestaLLM:
    return RespuestaLLM(contenido=contenido, llamadas=[], usage={"total_tokens": 1})


def _tool(nombre: str, argumentos: dict, identificador: str = "call_1") -> RespuestaLLM:
    return RespuestaLLM(
        contenido=None,
        llamadas=[
            LlamadaHerramienta(
                id=identificador, nombre=nombre, argumentos=argumentos
            )
        ],
    )


def _sub_del_token(headers: dict) -> str:
    token = headers["Authorization"].split(" ", 1)[1]
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return str(json.loads(base64.urlsafe_b64decode(payload))["sub"])


# ---------------------------------------------------------------------------
# Fixture: empresa + membresía reales y confirmadas
# ---------------------------------------------------------------------------
@pytest.fixture
def entorno_chat(db, headers_admin, monkeypatch):
    monkeypatch.setattr(settings, "GERENTE_API_KEY", CLAVE_GERENTE)
    monkeypatch.setattr(settings, "SECRETARIA_API_KEY", CLAVE_SECRETARIA)
    monkeypatch.setattr(settings, "AGENTE_PLANES_PREMIUM", "premium,pro")

    auth_id = _sub_del_token(headers_admin)
    sufijo = uuid4().hex[:8]
    db.rollback()
    with db.cursor() as cur:
        cur.execute(
            "insert into nucleo.empresas (codigo, razon_social, rut) "
            "values (%s, %s, %s) returning id",
            (f"CHAT4-{sufijo}", f"Empresa chat4 {sufijo}", rut_empresa()),
        )
        empresa_id = cur.fetchone()[0]
        cur.execute(
            "insert into nucleo.usuarios_empresa "
            "  (empresa_id, auth_id, rol, activo) "
            "values (%s, %s, 'admin', true) returning id",
            (empresa_id, auth_id),
        )
        membresia_id = cur.fetchone()[0]
    db.commit()

    fake = FakeLLM()
    app.dependency_overrides[get_cliente_llm] = lambda: fake
    try:
        yield {
            "empresa_id": empresa_id,
            "membresia_id": membresia_id,
            "auth_id": auth_id,
            "sufijo": sufijo,
            "fake": fake,
            "headers": {**headers_admin, "X-Empresa-ID": str(empresa_id)},
        }
    finally:
        app.dependency_overrides.pop(get_cliente_llm, None)


def _chat(client, headers, **body):
    body.setdefault("clave_idempotencia", f"ola4-{uuid4()}")
    return client.post(RUTA_CHAT, headers=headers, json=body)


def _ultimo_tool(db, empresa_id, conversacion_id, nombre: str) -> dict:
    fila = db.execute(
        "select contenido from nucleo.agente_chat_mensajes "
        " where empresa_id = %s and conversacion_id = %s and rol = 'tool' "
        "   and nombre_herramienta = %s "
        " order by created_at desc, id desc limit 1",
        (empresa_id, conversacion_id, nombre),
    ).fetchone()
    assert fila is not None
    return json.loads(fila[0])


# ---------------------------------------------------------------------------
# 1. SEC-052 con override habilitado
# ---------------------------------------------------------------------------
def test_tool_premium_con_override_sin_modulo_devuelve_upsell_y_no_ejecuta(
    client, db, entorno_chat
):
    empresa_id = entorno_chat["empresa_id"]
    db.execute(
        "insert into nucleo.agente_capacidades "
        "  (empresa_id, agente, capacidad, habilitada) "
        "values (%s, 'secretaria', 'whatsapp.recordatorio', true)",
        (empresa_id,),
    )
    db.commit()

    entorno_chat["fake"].guion = [
        _tool(
            "secretaria_whatsapp_recordatorio",
            {"viaje_id": str(uuid4()), "mensaje": "Sale a las 08:00"},
        ),
        _texto("WhatsApp requiere un plan premium."),
    ]
    r = _chat(
        client,
        entorno_chat["headers"],
        agente="secretaria",
        mensaje="Manda el recordatorio",
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["herramientas"][0]["estado"] == "upsell", data
    assert data["upsell"]["modulo"] == "whatsapp", data
    assert "premium" in data["upsell"]["mensaje"]

    resultado = _ultimo_tool(
        db,
        empresa_id,
        data["conversacion_id"],
        "secretaria_whatsapp_recordatorio",
    )
    assert resultado["activo"] is False, resultado
    assert "preparado" not in json.dumps(resultado), resultado


# ---------------------------------------------------------------------------
# 2. Capacidad deshabilitada por fila: error y sin escritura
# ---------------------------------------------------------------------------
def test_capacidad_deshabilitada_por_fila_no_ejecuta(client, db, entorno_chat):
    empresa_id = entorno_chat["empresa_id"]
    clave = f"directiva_{entorno_chat['sufijo']}"
    db.execute(
        "insert into nucleo.agente_capacidades "
        "  (empresa_id, agente, capacidad, habilitada) "
        "values (%s, 'gerente', 'configuracion.escribir_reglas', false)",
        (empresa_id,),
    )
    db.commit()

    entorno_chat["fake"].guion = [
        _tool(
            "gerente_upsert_directiva",
            {"clave": clave, "valor": "07:00", "motivo": "Prueba"},
        ),
        _texto("Esa capacidad está deshabilitada."),
    ]
    r = _chat(
        client,
        entorno_chat["headers"],
        agente="gerente",
        mensaje="Cambia el horario",
    )
    assert r.status_code == 200, r.text
    assert r.json()["herramientas"][0]["estado"] == "error", r.json()
    filas = db.execute(
        "select count(*) from nucleo.configuracion_empresa "
        " where empresa_id = %s and clave = %s",
        (empresa_id, clave),
    ).fetchone()[0]
    assert filas == 0, "una tool deshabilitada no debe escribir la directiva"


# ---------------------------------------------------------------------------
# 3. Límite duro por agente: la fila no concede lo que el catálogo prohíbe
# ---------------------------------------------------------------------------
def test_capacidad_gerente_no_se_concede_a_la_secretaria_por_fila(
    db, entorno_chat
):
    empresa_id = entorno_chat["empresa_id"]
    db.execute(
        "insert into nucleo.agente_capacidades "
        "  (empresa_id, agente, capacidad, habilitada) "
        "values (%s, 'secretaria', 'operacion.anular_viaje', true)",
        (empresa_id,),
    )
    db.commit()

    engine = create_engine(h.url_test(), future=True)
    try:
        with Session(engine) as session:
            contexto = ContextoEmpresa(
                auth_id="test-ola4",
                empresa=SimpleNamespace(  # type: ignore[arg-type]
                    id=empresa_id, razon_social="Empresa chat4"
                ),
                rol=RolEmpresa.admin,
            )
            efectivas = catalogo.habilitadas(session, contexto, "secretaria")
            assert "operacion.anular_viaje" not in efectivas, sorted(efectivas)

            with pytest.raises(DatosInvalidos) as excinfo:
                catalogo.actualizar(
                    session,
                    contexto,
                    "secretaria",
                    [
                        {
                            "capacidad": "operacion.anular_viaje",
                            "habilitada": True,
                        }
                    ],
                )
            assert "no aplica" in excinfo.value.mensaje, excinfo.value.mensaje
    finally:
        engine.dispose()

    # La fila insertada a mano sigue siendo la única; `actualizar` no escribió.
    filas = db.execute(
        "select count(*) from nucleo.agente_capacidades "
        " where empresa_id = %s and agente = 'secretaria' "
        "   and capacidad = 'operacion.anular_viaje'",
        (empresa_id,),
    ).fetchone()[0]
    assert filas == 1


# ---------------------------------------------------------------------------
# 4. El panel documentado en ADR-0009 debe estar montado
# ---------------------------------------------------------------------------
def test_panel_configuracion_agente_esta_montado(client, entorno_chat):
    """ADR-0009 §8: `GET/PUT /nucleo/agente/configuracion` con `agente:configurar`.

    Si el router no está incluido en `app/api/router.py`, la respuesta es 404 y
    el panel `/configuracion/agentes` queda inservible. El defecto se reporta;
    no se omite ni se marca `xfail`.
    """
    r = client.get(RUTA_CONFIG, headers=entorno_chat["headers"])
    assert r.status_code == 200, (
        "ADR-0009 exige GET /nucleo/agente/configuracion para admin; "
        f"respuesta real: {r.status_code} {r.text[:200]}"
    )
    assert "agentes" in r.json()


# ---------------------------------------------------------------------------
# 5. SEC-055/061: la excepción del chat no salta el alcance por empresa
# ---------------------------------------------------------------------------
def test_aprobar_solicitud_chat_de_viaje_ajeno_es_404_y_no_anula(
    client, db, entorno_chat
):
    from agente_helpers import asegurar_segunda_empresa

    empresa_id = entorno_chat["empresa_id"]
    otra_empresa_id = asegurar_segunda_empresa(db)

    # Viaje confirmado en OTRA empresa, creado con datos confirmados.
    from ola4_helpers import sesion_confirmada

    with sesion_confirmada() as setup:
        otra = setup.get(h.Empresa, UUID(otra_empresa_id))
        cli = h.cliente(setup, otra, uuid4().hex[:6])
        viaje_ajeno = h.viaje(setup, otra, cli, EstadoViaje.confirmado)
        viaje_ajeno_id = viaje_ajeno.id

    # La FK `fk_solicitud_viaje` es compuesta por empresa: una solicitud de TEI
    # no puede apuntar a un viaje de otra empresa por la columna `viaje_id`.
    # El ataque realista es dejar `viaje_id` NULL y poner el UUID ajeno en el
    # payload (`datos.viaje_id`), que es lo que el ejecutor usa cuando la
    # columna es NULL. Así se prueba el filtro del servicio, no la FK.
    payload = {
        "accion": "anular_viaje",
        "datos": {
            "viaje_id": str(viaje_ajeno_id),
            "motivo": "Anulación propuesta desde el chat",
        },
        "origen": "chat_inapp",
        "agente": "secretaria",
    }
    with db.cursor() as cur:
        cur.execute(
            "insert into nucleo.solicitudes "
            "  (empresa_id, tipo, solicitante_usuario_empresa_id, payload) "
            "values (%s, 'otra', %s, cast(%s as jsonb)) "
            "returning id::text",
            (
                empresa_id,
                entorno_chat["membresia_id"],
                json.dumps(payload),
            ),
        )
        solicitud_id = cur.fetchone()[0]
    db.commit()

    r = client.post(
        f"{RUTA_SOLICITUDES}/{solicitud_id}/decidir",
        headers=entorno_chat["headers"],
        json={"accion": "confirmar", "version": 1},
    )
    assert r.status_code == 404, r.text
    assert r.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

    estado_solicitud = db.execute(
        "select estado::text from nucleo.solicitudes where id = %s",
        (solicitud_id,),
    ).fetchone()[0]
    assert estado_solicitud == "pendiente", "el fallo debe revertir la decisión"
    estado_viaje = db.execute(
        "select estado::text from nucleo.viajes where id = %s",
        (viaje_ajeno_id,),
    ).fetchone()[0]
    assert estado_viaje == "confirmado"
    eventos = db.execute(
        "select count(*) from nucleo.viaje_eventos "
        " where viaje_id = %s and tipo = 'anulado'",
        (viaje_ajeno_id,),
    ).fetchone()[0]
    assert eventos == 0


# ---------------------------------------------------------------------------
# 6. Idempotencia concurrente del turno
# ---------------------------------------------------------------------------
def test_idempotencia_concurrente_una_sola_llamada_al_llm(client, db, entorno_chat):
    fake = FakeLLMConcurrente()
    app.dependency_overrides[get_cliente_llm] = lambda: fake
    clave = f"ola4-concurrente-{uuid4()}"
    headers = entorno_chat["headers"]
    body = {
        "agente": "gerente",
        "mensaje": "Mensaje idempotente concurrente",
        "clave_idempotencia": clave,
    }
    barrera = threading.Barrier(2)

    def enviar():
        barrera.wait(timeout=10)
        return client.post(RUTA_CHAT, headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        respuestas = list(pool.map(lambda _: enviar(), range(2)))

    assert [r.status_code for r in respuestas] == [200, 200], [
        (r.status_code, r.text) for r in respuestas
    ]
    ids = {r.json()["mensaje_id"] for r in respuestas}
    conversaciones = {r.json()["conversacion_id"] for r in respuestas}
    assert len(ids) == 1, [r.json() for r in respuestas]
    assert len(conversaciones) == 1
    assert fake.llamadas == 1, "un reintento no debe volver a llamar al LLM"

    filas = db.execute(
        "select count(*) from nucleo.agente_chat_mensajes "
        " where empresa_id = %s and clave_idempotencia = %s",
        (entorno_chat["empresa_id"], clave),
    ).fetchone()[0]
    assert filas == 1, "una sola fila con la clave de idempotencia"
    assistant = db.execute(
        "select count(*) from nucleo.agente_chat_mensajes "
        " where empresa_id = %s and conversacion_id = %s and rol = 'assistant'",
        (entorno_chat["empresa_id"], next(iter(conversaciones))),
    ).fetchone()[0]
    assert assistant == 1


# ===========================================================================
# Regresiones de la revisión independiente 2026-11-09
# (SEC-063/064/065/066/069 y migración 0033)
# ===========================================================================
def _insertar_solicitud_otra(
    db,
    *,
    empresa_id,
    membresia_id,
    payload: dict,
    viaje_id=None,
) -> str:
    with db.cursor() as cur:
        cur.execute(
            "insert into nucleo.solicitudes "
            "  (empresa_id, tipo, solicitante_usuario_empresa_id, viaje_id, payload) "
            "values (%s, cast('otra' as nucleo.tipo_solicitud), %s, %s, "
            "        cast(%s as jsonb)) returning id::text",
            (empresa_id, membresia_id, viaje_id, json.dumps(payload)),
        )
        solicitud_id = cur.fetchone()[0]
    db.commit()
    return solicitud_id


def _decidir(client, headers, solicitud_id: str, body: dict):
    return client.post(
        f"{RUTA_SOLICITUDES}/{solicitud_id}/decidir",
        headers=headers,
        json=body,
    )


def _cliente_y_tarifa(empresa_id, sufijo: str) -> tuple[str, str]:
    """Cliente y tarifa vigentes en la empresa del escenario (datos confirmados)."""
    with h.sesion_confirmada() as session:
        empresa = session.get(h.Empresa, empresa_id)
        cli = h.cliente(session, empresa, sufijo)
        tarifa = Tarifa(
            empresa_id=empresa_id,
            cliente_id=cli.id,
            codigo=f"TSEC-{sufijo}",
            nombre="Ruta SEC-064",
            modalidad=ModalidadTarifa.viaje,
            vigencia_desde=date.today(),
            vigencia_hasta=date.today() + timedelta(days=365),
            precio_unitario=Decimal(100000),
        )
        session.add(tarifa)
        session.commit()
        session.refresh(tarifa)
        return str(cli.id), str(tarifa.id)


def _llamadas_directiva(cantidad: int, prefijo: str) -> list[LlamadaHerramienta]:
    return [
        LlamadaHerramienta(
            id=f"call_{prefijo}_{i}",
            nombre="gerente_upsert_directiva",
            argumentos={"clave": f"directiva_{prefijo}_{i}", "valor": "07:00"},
        )
        for i in range(cantidad)
    ]


# ---------------------------------------------------------------------------
# SEC-064: la corrección del aprobador manda en `tipo='otra'`
# ---------------------------------------------------------------------------
def test_sec_064_modificar_crear_viaje_usa_el_valor_corregido(
    client, db, entorno_chat
):
    empresa_id = entorno_chat["empresa_id"]
    sufijo = entorno_chat["sufijo"]
    cliente_id, tarifa_id = _cliente_y_tarifa(empresa_id, sufijo)
    inicio = datetime.now(UTC) + timedelta(days=40)
    origen = f"Origen SEC064 {sufijo}"
    payload = {
        "accion": "crear_viaje",
        "datos": {
            "cliente_id": cliente_id,
            "tarifa_id": tarifa_id,
            "inicio_planificado": inicio.isoformat(),
            "fin_planificado": (inicio + timedelta(hours=4)).isoformat(),
            "origen_nombre": origen,
            "destino_nombre": f"Destino SEC064 {sufijo}",
            "peso_bruto_kg": "18000",
            "valor_declarado": "100000",
        },
        "origen": "chat_inapp",
        "agente": "secretaria",
    }
    solicitud_id = _insertar_solicitud_otra(
        db,
        empresa_id=empresa_id,
        membresia_id=entorno_chat["membresia_id"],
        payload=payload,
    )

    modificacion = _decidir(
        client,
        entorno_chat["headers"],
        solicitud_id,
        {
            "accion": "modificar",
            "version": 1,
            "valores_modificados": {"valor_declarado": "250000"},
        },
    )
    assert modificacion.status_code == 200, modificacion.text
    assert modificacion.json()["solicitud"]["estado"] == "pendiente"
    version = modificacion.json()["solicitud"]["version"]
    assert version == 2

    confirmacion = _decidir(
        client,
        entorno_chat["headers"],
        solicitud_id,
        {"accion": "confirmar", "version": version},
    )
    assert confirmacion.status_code == 200, confirmacion.text
    assert confirmacion.json()["resultado"]["estado"] == "confirmado"

    fila = db.execute(
        "select estado::text, valor_declarado from nucleo.viajes "
        " where empresa_id = %s and origen_nombre = %s",
        (empresa_id, origen),
    ).fetchone()
    assert fila is not None
    assert fila[0] == "confirmado"
    assert Decimal(fila[1]) == Decimal("250000.00"), (
        "SEC-064: confirmar debe usar valores_modificados, no el payload original"
    )


def test_sec_064_modificar_anular_viaje_usa_el_motivo_corregido(
    client, db, entorno_chat
):
    empresa_id = entorno_chat["empresa_id"]
    sufijo = entorno_chat["sufijo"]
    with h.sesion_confirmada() as session:
        empresa = session.get(h.Empresa, empresa_id)
        cli = h.cliente(session, empresa, f"{sufijo}a")
        viaje = h.viaje(session, empresa, cli, EstadoViaje.confirmado)
        viaje_id = viaje.id

    motivo_corregido = "Motivo corregido por el dueño"
    payload = {
        "accion": "anular_viaje",
        "datos": {"motivo": "Motivo original del agente"},
        "origen": "chat_inapp",
        "agente": "secretaria",
    }
    solicitud_id = _insertar_solicitud_otra(
        db,
        empresa_id=empresa_id,
        membresia_id=entorno_chat["membresia_id"],
        payload=payload,
        viaje_id=viaje_id,
    )

    modificacion = _decidir(
        client,
        entorno_chat["headers"],
        solicitud_id,
        {
            "accion": "modificar",
            "version": 1,
            "valores_modificados": {"motivo": motivo_corregido},
        },
    )
    assert modificacion.status_code == 200, modificacion.text
    version = modificacion.json()["solicitud"]["version"]

    confirmacion = _decidir(
        client,
        entorno_chat["headers"],
        solicitud_id,
        {"accion": "confirmar", "version": version},
    )
    assert confirmacion.status_code == 200, confirmacion.text
    assert confirmacion.json()["resultado"]["estado"] == "anulado"

    fila = db.execute(
        "select estado::text, motivo_anulacion from nucleo.viajes where id = %s",
        (viaje_id,),
    ).fetchone()
    assert fila[0] == "anulado"
    assert fila[1] == motivo_corregido, (
        "SEC-064: la anulación debe usar el motivo corregido, no el del payload"
    )
    evento = db.execute(
        "select payload from nucleo.viaje_eventos "
        " where viaje_id = %s and tipo = 'anulado' "
        " order by ocurrido_en desc, id desc limit 1",
        (viaje_id,),
    ).fetchone()
    assert evento is not None
    assert evento[0]["motivo"] == motivo_corregido


# ---------------------------------------------------------------------------
# SEC-065: topes de tool_calls por respuesta y por turno
# ---------------------------------------------------------------------------
def test_sec_065_respuesta_sobre_el_tope_no_ejecuta_ninguna_tool(
    client, db, entorno_chat
):
    empresa_id = entorno_chat["empresa_id"]
    sufijo = entorno_chat["sufijo"]
    prefijo = f"sec065_{sufijo}"
    clave_idem = f"sec065-{uuid4()}"
    entorno_chat["fake"].guion = [
        RespuestaLLM(
            contenido=None,
            llamadas=_llamadas_directiva(
                settings.AGENTE_LLM_MAX_TOOL_CALLS + 1, prefijo
            ),
        ),
    ]

    r = _chat(
        client,
        entorno_chat["headers"],
        agente="gerente",
        mensaje="Ejecuta muchas acciones",
        clave_idempotencia=clave_idem,
    )
    assert r.status_code == 502, r.text
    assert r.json()["codigo"] == "AGENTE_LLM_ERROR"

    filas = db.execute(
        "select count(*) from nucleo.configuracion_empresa "
        " where empresa_id = %s and clave like %s",
        (empresa_id, f"directiva_{prefijo}_%"),
    ).fetchone()[0]
    assert filas == 0, "SEC-065: ninguna tool debe ejecutarse sobre el tope"
    mensajes = db.execute(
        "select count(*) from nucleo.agente_chat_mensajes "
        " where empresa_id = %s and clave_idempotencia = %s",
        (empresa_id, clave_idem),
    ).fetchone()[0]
    assert mensajes == 0, "el turno rechazado se revierte completo"


def test_sec_065_turno_bajo_el_tope_sigue_funcionando(client, db, entorno_chat):
    empresa_id = entorno_chat["empresa_id"]
    sufijo = entorno_chat["sufijo"]
    prefijo = f"sec065ok_{sufijo}"
    cantidad = settings.AGENTE_LLM_MAX_TOOL_CALLS
    entorno_chat["fake"].guion = [
        RespuestaLLM(
            contenido=None,
            llamadas=_llamadas_directiva(cantidad, prefijo),
        ),
        _texto("Acciones registradas."),
    ]

    r = _chat(
        client,
        entorno_chat["headers"],
        agente="gerente",
        mensaje="Registra las directivas",
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["herramientas"]) == cantidad
    assert all(h["estado"] == "ok" for h in r.json()["herramientas"])

    filas = db.execute(
        "select count(*) from nucleo.configuracion_empresa "
        " where empresa_id = %s and clave like %s",
        (empresa_id, f"directiva_{prefijo}_%"),
    ).fetchone()[0]
    assert filas == cantidad


def test_sec_065_tope_por_turno_impide_pasarse_de_16(client, db, entorno_chat):
    empresa_id = entorno_chat["empresa_id"]
    sufijo = entorno_chat["sufijo"]
    prefijo = f"sec065turno_{sufijo}"
    max_turno = settings.AGENTE_LLM_MAX_TOOL_CALLS_TURNO
    por_respuesta = settings.AGENTE_LLM_MAX_TOOL_CALLS
    # 8 + 8 + 1 = 17 > 16: la tercera respuesta excede el tope del turno.
    entorno_chat["fake"].guion = [
        RespuestaLLM(
            contenido=None, llamadas=_llamadas_directiva(por_respuesta, f"{prefijo}a")
        ),
        RespuestaLLM(
            contenido=None, llamadas=_llamadas_directiva(por_respuesta, f"{prefijo}b")
        ),
        RespuestaLLM(
            contenido=None, llamadas=_llamadas_directiva(1, f"{prefijo}c")
        ),
    ]
    assert 2 * por_respuesta + 1 > max_turno

    r = _chat(
        client,
        entorno_chat["headers"],
        agente="gerente",
        mensaje="Ejecuta más de lo permitido en el turno",
    )
    assert r.status_code == 502, r.text
    assert r.json()["codigo"] == "AGENTE_LLM_ERROR"

    filas = db.execute(
        "select count(*) from nucleo.configuracion_empresa "
        " where empresa_id = %s and clave like %s",
        (empresa_id, f"directiva_{prefijo}%"),
    ).fetchone()[0]
    assert filas == 0, "el rollback del turno revierte las tools ya ejecutadas"


# ---------------------------------------------------------------------------
# SEC-063: el catálogo fiscal nace apagado y no se escribe por chat
# ---------------------------------------------------------------------------
def test_sec_063_catalogo_nace_deshabilitado_y_no_escribe(client, db, entorno_chat):
    config = client.get(RUTA_CONFIG, headers=entorno_chat["headers"])
    assert config.status_code == 200, config.text
    agentes = {a["clave"]: a for a in config.json()["agentes"]}
    capacidad = next(
        c
        for c in agentes["gerente"]["capacidades"]
        if c["clave"] == "configuracion.escribir_catalogo"
    )
    assert capacidad["por_defecto"] is False
    assert capacidad["habilitada"] is False

    empresa_id = entorno_chat["empresa_id"]
    antes = db.execute(
        "select count(*) from nucleo.configuracion_empresa "
        " where empresa_id = %s and clave = 'iva_porcentaje'",
        (empresa_id,),
    ).fetchone()[0]

    entorno_chat["fake"].guion = [
        _tool(
            "gerente_actualizar_catalogo",
            {"clave": "iva_porcentaje", "valor": 25},
        ),
        _texto("No puedo cambiar el IVA sin habilitar la capacidad."),
    ]
    r = _chat(
        client,
        entorno_chat["headers"],
        agente="gerente",
        mensaje="Sube el IVA a 25%",
    )
    assert r.status_code == 200, r.text
    assert r.json()["herramientas"][0]["estado"] == "error"

    despues = db.execute(
        "select count(*) from nucleo.configuracion_empresa "
        " where empresa_id = %s and clave = 'iva_porcentaje'",
        (empresa_id,),
    ).fetchone()[0]
    assert despues == antes == 0, "SEC-063: la tool deshabilitada no debe escribir"


# ---------------------------------------------------------------------------
# SEC-066: la activación de módulos ya no es una ruta del tenant
# ---------------------------------------------------------------------------
def test_sec_066_put_modulos_retirado_es_404(client, entorno_chat):
    r = client.put(
        f"{API}/nucleo/agente/modulos/agente-whatsapp",
        headers=entorno_chat["headers"],
        json={"habilitado": True},
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# SEC-069: el panel existe y respeta `agente:configurar`
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def headers_gerente() -> dict:
    return {
        "Authorization": f"Bearer {_login_supabase('gerente@tei.local', 'TEI2026!')}"
    }


def test_sec_069_gerente_sin_agente_configurar_es_403(client, db, headers_gerente):
    tei = db.execute(
        "select id::text from nucleo.empresas where codigo = 'TEI'"
    ).fetchone()
    assert tei is not None, "tei_test sin la empresa TEI; ejecute `make seed`"
    r = client.get(
        RUTA_CONFIG,
        headers={**headers_gerente, "X-Empresa-ID": tei[0]},
    )
    assert r.status_code == 403, r.text
    assert r.json()["codigo"] == "ACCESO_DENEGADO"


# ---------------------------------------------------------------------------
# 0033: privilegios de `tei_app` (historial append-only y suscripción de solo
# lectura). La suite SQL ya lo cubre; aquí se comprueba con el rol real.
# ---------------------------------------------------------------------------
def test_0033_tei_app_no_actualiza_historial_ni_escribe_suscripcion():
    dsn = (settings.NUCLEO_DATABASE_URL or "").strip()
    assert dsn, "NUCLEO_DATABASE_URL debe apuntar a tei_app en `make test`"
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")

    with psycopg.connect(dsn, connect_timeout=10) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as historial:
            conn.execute(
                "update nucleo.agente_chat_mensajes "
                "   set contenido = contenido where false"
            )
        assert historial.value.sqlstate == "42501"
        conn.rollback()

        with pytest.raises(psycopg.errors.InsufficientPrivilege) as suscripcion:
            conn.execute(
                "insert into nucleo.tenant_suscripciones "
                "  (empresa_id, plan_codigo, estado, vigente_desde) "
                "values (%s, 'premium', 'activa', now())",
                (uuid4(),),
            )
        assert suscripcion.value.sqlstate == "42501"
        conn.rollback()
