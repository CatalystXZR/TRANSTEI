"""Chat in-app del dueño con agentes LLM (`gerente`, `secretaria`).

Paquete de la Ola 3. No reutiliza las tablas del agente WhatsApp: la memoria
vive en `nucleo.agente_chat_conversaciones` / `nucleo.agente_chat_mensajes`
(migración `0031`). El paquete expone:

- `llm.py`        cliente genérico compatible con la API de OpenAI (DeepSeek);
- `personas.py`   catálogo de agentes, claves por agente y system prompts;
- `herramientas.py` tools de lectura/escritura con allowlist por agente;
- `servicio_modulos.py` muro de pago de módulos premium;
- `runtime.py`    orquestación de un turno (memoria, bucle de tools, idempotencia);
- `api.py`        endpoints `/api/v1/nucleo/agente/chat`.

El backend es la autoridad: ninguna tool confía en un `empresa_id` del body.
"""

from app.nucleo.agente.chat.api import router

__all__ = ["router"]
