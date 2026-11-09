"""Cliente LLM genérico compatible con la API de OpenAI (DeepSeek por defecto).

Reglas de seguridad que este módulo mantiene:

- la API key **solo** viaja en la cabecera `Authorization`; nunca se incluye en
  mensajes, logs, excepciones ni en el cuerpo de una respuesta;
- un 401/403 del proveedor se traduce a `AgenteNoConfigurado` (503) con un
  mensaje fijo, sin eco de la clave ni del cuerpo del proveedor;
- un timeout se traduce a `AgenteTimeout` (504) y cualquier otro fallo a
  `AgenteLLMError` (502), nunca a un 500 con stack trace;
- los argumentos de `tool_calls` se parsean aquí: un JSON inválido es un error
  controlado del proveedor, no una excepción de `json` que llegue al cliente.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.nucleo.agente.chat.modelos import (
    LlamadaHerramienta,
    MensajeLLM,
    RespuestaLLM,
)
from app.nucleo.errores import ErrorNucleo


class AgenteNoConfigurado(ErrorNucleo):
    """El agente no tiene API key configurada o el proveedor la rechaza."""

    status_code = 503
    codigo = "AGENTE_NO_CONFIGURADO"


class AgenteTimeout(ErrorNucleo):
    """El proveedor LLM no respondió dentro del timeout configurado."""

    status_code = 504
    codigo = "AGENTE_TIMEOUT"


class AgenteLLMError(ErrorNucleo):
    """Respuesta inválida o fallo no clasificable del proveedor LLM."""

    status_code = 502
    codigo = "AGENTE_LLM_ERROR"


class ClienteLLM(Protocol):
    def responder(
        self,
        mensajes: list[MensajeLLM],
        herramientas: list[dict[str, Any]],
        *,
        api_key: str,
        modelo: str,
    ) -> RespuestaLLM:  # pragma: no cover - protocolo
        ...


class ClienteOpenAICompatible:
    """`POST {base_url}/chat/completions` con el contrato de OpenAI."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 45.0,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._transport = transport

    def _post(
        self, cuerpo: dict[str, Any], api_key: str
    ) -> httpx.Response:
        # El `httpx.Client` se crea por llamada: el runtime es síncrono y el
        # turno del chat dura segundos, no vale la pena un pool persistente.
        with httpx.Client(
            timeout=self.timeout_s, transport=self._transport
        ) as cliente:
            return cliente.post(
                f"{self.base_url}/chat/completions",
                json=cuerpo,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )

    def responder(
        self,
        mensajes: list[MensajeLLM],
        herramientas: list[dict[str, Any]],
        *,
        api_key: str,
        modelo: str,
    ) -> RespuestaLLM:
        if not api_key or not api_key.strip():
            raise AgenteNoConfigurado(
                "El agente no tiene una API key configurada."
            )

        cuerpo: dict[str, Any] = {
            "model": modelo,
            "messages": [m.a_openai() for m in mensajes],
            "temperature": 0.2,
        }
        if herramientas:
            cuerpo["tools"] = herramientas
            cuerpo["tool_choice"] = "auto"

        try:
            respuesta = self._post(cuerpo, api_key)
        except httpx.TimeoutException as exc:
            raise AgenteTimeout(
                "El proveedor del agente no respondió a tiempo. Reintente."
            ) from exc
        except httpx.HTTPError as exc:
            raise AgenteLLMError(
                "No fue posible comunicarse con el proveedor del agente."
            ) from exc

        if respuesta.status_code in (401, 403):
            # Mensaje fijo: no se reenvía el cuerpo del proveedor (podría
            # incluir detalles internos y nunca debe incluir la clave).
            raise AgenteNoConfigurado(
                "El proveedor rechazó la credencial del agente. "
                "Revise la configuración en el servidor."
            )
        if respuesta.status_code >= 400:
            raise AgenteLLMError(
                "El proveedor del agente devolvió un error. Reintente más tarde."
            )

        try:
            datos = respuesta.json()
        except ValueError as exc:
            raise AgenteLLMError(
                "El proveedor del agente devolvió una respuesta ilegible."
            ) from exc

        try:
            mensaje = datos["choices"][0]["message"]
            contenido = mensaje.get("content")
            crudas = mensaje.get("tool_calls") or []
        except (KeyError, IndexError, TypeError) as exc:
            raise AgenteLLMError(
                "El proveedor del agente devolvió una respuesta incompleta."
            ) from exc

        llamadas: list[LlamadaHerramienta] = []
        for cruda in crudas:
            llamadas.append(_parsear_llamada(cruda))

        usage = datos.get("usage")
        return RespuestaLLM(
            contenido=contenido if isinstance(contenido, str) else None,
            llamadas=llamadas,
            usage=usage if isinstance(usage, dict) else {},
        )


def _parsear_llamada(cruda: Any) -> LlamadaHerramienta:
    try:
        identificador = str(cruda["id"])
        funcion = cruda["function"]
        nombre = str(funcion["name"])
        argumentos_crudos = funcion.get("arguments")
    except (KeyError, TypeError) as exc:
        raise AgenteLLMError(
            "El proveedor del agente devolvió una llamada a herramienta inválida."
        ) from exc

    if isinstance(argumentos_crudos, str):
        try:
            argumentos = json.loads(argumentos_crudos or "{}")
        except json.JSONDecodeError as exc:
            raise AgenteLLMError(
                "El proveedor del agente devolvió argumentos de herramienta "
                "que no son JSON válido."
            ) from exc
    else:
        argumentos = argumentos_crudos if argumentos_crudos is not None else {}
    if not isinstance(argumentos, dict):
        raise AgenteLLMError(
            "El proveedor del agente devolvió argumentos de herramienta "
            "que no son un objeto JSON."
        )
    return LlamadaHerramienta(
        id=identificador, nombre=nombre, argumentos=argumentos
    )


def get_cliente_llm() -> ClienteLLM:
    """Dependencia FastAPI sobreescribible en pruebas."""
    return ClienteOpenAICompatible(
        settings.AGENTE_LLM_BASE_URL, settings.AGENTE_LLM_TIMEOUT_S
    )
