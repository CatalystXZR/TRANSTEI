"""Unitarias del chat in-app: configuración, prompts, cliente LLM y validadores.

No tocan base de datos ni red real: el cliente HTTP se ejercita con
`httpx.MockTransport`. Las pruebas de integración viven en
`test_agente_chat_http.py`.

Lo que se protege aquí:

- las claves de los agentes se leen de Settings y por defecto están vacías;
- ningún system prompt contiene el valor de una clave;
- la respuesta OpenAI (contenido, `tool_calls`, argumentos) se parsea bien y un
  JSON inválido es un error de dominio controlado;
- el cliente nunca devuelve la API key en el error (401, timeout, respuesta rota);
- los validadores de argumentos rechazan acciones, entidades y claves inválidas.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings, settings
from app.nucleo.agente.chat import herramientas, personas
from app.nucleo.agente.chat.llm import (
    AgenteLLMError,
    AgenteNoConfigurado,
    AgenteTimeout,
    ClienteOpenAICompatible,
)
from app.nucleo.agente.chat.modelos import MensajeLLM
from app.nucleo.errores import DatosInvalidos

CLAVE_FICTICIA = "sk-ficticia-" + "Z" * 48


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_settings_lee_claves_desde_entorno(monkeypatch) -> None:
    monkeypatch.setenv("GERENTE_API_KEY", "clave-gerente-test")
    monkeypatch.setenv("SECRETARIA_API_KEY", "clave-secretaria-test")
    monkeypatch.setenv("AGENTE_PLANES_PREMIUM", "premium, pro ,empresa")
    cargadas = Settings(_env_file=None)
    assert cargadas.GERENTE_API_KEY == "clave-gerente-test"
    assert cargadas.SECRETARIA_API_KEY == "clave-secretaria-test"
    assert cargadas.planes_premium_list == ["premium", "pro", "empresa"]


def test_settings_por_defecto_no_tiene_claves(monkeypatch) -> None:
    monkeypatch.delenv("GERENTE_API_KEY", raising=False)
    monkeypatch.delenv("SECRETARIA_API_KEY", raising=False)
    cargadas = Settings(_env_file=None)
    assert cargadas.GERENTE_API_KEY == ""
    assert cargadas.SECRETARIA_API_KEY == ""
    assert cargadas.planes_premium_list == ["premium", "pro"]


def test_prompts_no_contienen_claves() -> None:
    for persona in personas.AGENTES.values():
        prompt = persona.system_prompt
        assert "sk-" not in prompt
        assert CLAVE_FICTICIA not in prompt
        # El nombre de la variable puede mencionarse, el valor nunca.
        for clave in (settings.GERENTE_API_KEY, settings.SECRETARIA_API_KEY):
            if clave:
                assert clave not in prompt
        assert persona.api_key_setting.startswith(("GERENTE_", "SECRETARIA_"))


def test_catalogo_de_agentes_y_allowlist() -> None:
    assert set(personas.AGENTES) == {"gerente", "secretaria"}
    for persona in personas.AGENTES.values():
        assert persona.permiso == "agente:chat"
        assert persona.tools
        for nombre in persona.tools:
            assert nombre in herramientas.HERRAMIENTAS
            assert herramientas.HERRAMIENTAS[nombre].agente == persona.clave


def test_permiso_agente_chat_solo_para_admin() -> None:
    """AB-02: `gerente` queda excluido, igual que el resto del módulo agente."""
    from app.nucleo.models import RolEmpresa
    from app.nucleo.permisos import permisos_de

    assert "agente:chat" in permisos_de(RolEmpresa.admin)
    assert "agente:chat" not in permisos_de(RolEmpresa.gerente)
    for rol in RolEmpresa:
        if rol is not RolEmpresa.admin:
            assert "agente:chat" not in permisos_de(rol)


# ---------------------------------------------------------------------------
# Cliente LLM
# ---------------------------------------------------------------------------
def _cliente(handler) -> ClienteOpenAICompatible:
    return ClienteOpenAICompatible(
        "https://llm.test/v1", timeout_s=1, transport=httpx.MockTransport(handler)
    )


def _mensajes() -> list[MensajeLLM]:
    return [MensajeLLM(role="user", content="hola")]


def test_parsea_contenido_y_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {CLAVE_FICTICIA}"
        cuerpo = json.loads(request.content)
        assert cuerpo["model"] == "deepseek-chat"
        assert cuerpo["messages"] == [{"role": "user", "content": "hola"}]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "Hola, jefe."}}
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    respuesta = _cliente(handler).responder(
        _mensajes(), [], api_key=CLAVE_FICTICIA, modelo="deepseek-chat"
    )
    assert respuesta.contenido == "Hola, jefe."
    assert respuesta.llamadas == []
    assert respuesta.usage["completion_tokens"] == 4


def test_parsea_tool_calls_con_argumentos_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        assert cuerpo["tools"][0]["function"]["name"] == "gerente_leer_contexto"
        assert cuerpo["tool_choice"] == "auto"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "gerente_leer_contexto",
                                        "arguments": '{"limite": 5}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    respuesta = _cliente(handler).responder(
        _mensajes(),
        [herramientas.HERRAMIENTAS["gerente_leer_contexto"].especificacion_openai()],
        api_key=CLAVE_FICTICIA,
        modelo="deepseek-chat",
    )
    assert len(respuesta.llamadas) == 1
    llamada = respuesta.llamadas[0]
    assert llamada.id == "call_1"
    assert llamada.nombre == "gerente_leer_contexto"
    assert llamada.argumentos == {"limite": 5}


def test_argumentos_json_invalido_es_error_controlado() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "gerente_leer_contexto",
                                        "arguments": "{no-es-json",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    with pytest.raises(AgenteLLMError) as exc:
        _cliente(handler).responder(
            _mensajes(), [], api_key=CLAVE_FICTICIA, modelo="deepseek-chat"
        )
    assert exc.value.status_code == 502
    assert CLAVE_FICTICIA not in str(exc.value)


def test_respuesta_incompleta_es_502() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(AgenteLLMError):
        _cliente(handler).responder(
            _mensajes(), [], api_key=CLAVE_FICTICIA, modelo="deepseek-chat"
        )


def test_401_es_503_y_no_expone_la_clave() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key"})

    with pytest.raises(AgenteNoConfigurado) as exc:
        _cliente(handler).responder(
            _mensajes(), [], api_key=CLAVE_FICTICIA, modelo="deepseek-chat"
        )
    error = exc.value
    assert error.status_code == 503
    assert error.codigo == "AGENTE_NO_CONFIGURADO"
    assert CLAVE_FICTICIA not in error.mensaje
    assert CLAVE_FICTICIA not in json.dumps(error.contexto)
    assert CLAVE_FICTICIA not in str(error)
    assert "invalid api key" not in error.mensaje


def test_timeout_es_504_y_no_expone_la_clave() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout de prueba")

    with pytest.raises(AgenteTimeout) as exc:
        _cliente(handler).responder(
            _mensajes(), [], api_key=CLAVE_FICTICIA, modelo="deepseek-chat"
        )
    assert exc.value.status_code == 504
    assert CLAVE_FICTICIA not in str(exc.value)


def test_error_500_del_proveedor_es_502() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(AgenteLLMError) as exc:
        _cliente(handler).responder(
            _mensajes(), [], api_key=CLAVE_FICTICIA, modelo="deepseek-chat"
        )
    assert exc.value.status_code == 502


def test_sin_api_key_no_hace_la_llamada() -> None:
    llamado = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal llamado
        llamado = True
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(AgenteNoConfigurado):
        _cliente(handler).responder(
            _mensajes(), [], api_key="   ", modelo="deepseek-chat"
        )
    assert llamado is False


# ---------------------------------------------------------------------------
# Validadores de argumentos
# ---------------------------------------------------------------------------
def test_accion_critica_fuera_del_catalogo_es_422() -> None:
    assert herramientas.validar_accion_critica("anular_viaje") == "anular_viaje"
    with pytest.raises(DatosInvalidos) as exc:
        herramientas.validar_accion_critica("borrar_todo")
    assert exc.value.status_code == 422
    assert "acciones_permitidas" in exc.value.contexto


def test_entidad_invalida_es_422() -> None:
    assert herramientas.validar_entidad("cliente") == "cliente"
    with pytest.raises(DatosInvalidos):
        herramientas.validar_entidad("empresa")


def test_clave_de_directiva_reservada_o_mal_formada() -> None:
    assert (
        herramientas.validar_clave_directiva("directiva_horario_despacho")
        == "directiva_horario_despacho"
    )
    for invalida in ("Directiva_Horario", "directiva_", "clave"):
        with pytest.raises(DatosInvalidos):
            herramientas.validar_clave_directiva(invalida)

    # SEC-051: una clave del catálogo no se escribe por chat.
    with pytest.raises(DatosInvalidos) as exc:
        herramientas.validar_clave_directiva("iva_porcentaje")
    assert "flujo de configuración" in exc.value.mensaje
    assert exc.value.status_code == 422


def test_tool_directiva_rechaza_catalogo_sin_tocar_sesion() -> None:
    """La validación ocurre antes de instanciar el servicio (sin sesión)."""
    with pytest.raises(DatosInvalidos) as exc:
        herramientas.HERRAMIENTAS["gerente_upsert_directiva"].ejecutar(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            {"clave": "iva_porcentaje", "valor": 25},
        )
    assert "flujo de configuración" in exc.value.mensaje


def test_tool_premium_whatsapp_en_allowlist_de_secretaria() -> None:
    herramienta = herramientas.HERRAMIENTAS["secretaria_whatsapp_recordatorio"]
    assert herramienta.modulo == "whatsapp"
    assert herramienta.agente == "secretaria"
    assert "secretaria_whatsapp_recordatorio" in personas.AGENTES["secretaria"].tools
    assert "secretaria_whatsapp_recordatorio" not in personas.AGENTES["gerente"].tools


def test_cupo_chat_agotado_es_429_sin_liberar(monkeypatch) -> None:
    from app.nucleo.agente.chat import api as chat_api

    class SemaforoAgotado:
        def acquire(self, blocking=False):
            assert blocking is False
            return False

        def release(self):  # pragma: no cover - no debe llamarse
            raise AssertionError("no se libera un cupo que no se adquirió")

    monkeypatch.setattr(chat_api, "_SEMAFORO", SemaforoAgotado())
    with pytest.raises(chat_api.AgenteOcupado) as exc:
        next(chat_api.requiere_cupo_chat())
    assert exc.value.status_code == 429
    assert exc.value.codigo == "AGENTE_OCUPADO"


def test_clave_de_regla_mal_formada() -> None:
    assert herramientas.validar_clave_regla("horario_retiro") == "horario_retiro"
    for invalida in ("1horario", "Ho", "con espacio", "x" * 70):
        with pytest.raises(DatosInvalidos):
            herramientas.validar_clave_regla(invalida)


def test_predicado_propuesta_chat_endurecido() -> None:
    """SEC-061: `origen` no basta; exige `tipo='otra'` y acción crítica."""
    from types import SimpleNamespace

    from app.nucleo.agente.solicitudes import _es_propuesta_del_chat

    def solicitud(tipo: str, payload: dict):
        return SimpleNamespace(tipo=tipo, payload=payload)

    assert _es_propuesta_del_chat(
        solicitud("otra", {"origen": "chat_inapp", "accion": "anular_viaje"})
    )
    assert not _es_propuesta_del_chat(
        solicitud(
            "otra", {"origen": "chat_inapp", "accion": "accion_inventada"}
        )
    )
    assert not _es_propuesta_del_chat(
        solicitud(
            "hoja_de_ruta",
            {"origen": "chat_inapp", "accion": "anular_viaje"},
        )
    )
    assert not _es_propuesta_del_chat(
        solicitud("otra", {"accion": "anular_viaje"})
    )
