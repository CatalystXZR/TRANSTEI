/**
 * Tipos del contrato HTTP del chat in-app (`/nucleo/agente/chat`).
 *
 * Fuente: `backend/app/nucleo/agente/chat/api.py:37-97` y
 * `docs/backend/agente-chat-inapp.md`. La UI no inventa campos: si el backend
 * no lo devuelve, no se muestra.
 *
 * Nota de contrato: el mensaje del historial se llama `creado_en`
 * (`api.py:73-81`), no `created_at`. Se conserva el nombre real del backend.
 */

export type AgenteChatClave = "gerente" | "secretaria";

/** `GET /nucleo/agente/chat/agentes` */
export interface AgenteChatNucleo {
  clave: AgenteChatClave;
  nombre: string;
  configurado: boolean;
  herramientas: string[];
}

/** `POST /nucleo/agente/chat` (sin `empresa_id`: la empresa va en `X-Empresa-ID`). */
export interface ChatEnvioNucleo {
  agente: AgenteChatClave;
  /** 1 a 4000 caracteres. */
  mensaje: string;
  conversacion_id?: string | null;
  /** 1 a 120 caracteres. El backend la usa para idempotencia por empresa. */
  clave_idempotencia?: string | null;
}

export interface HerramientaChatNucleo {
  nombre: string;
  /**
   * Valores conocidos del backend: `ok`, `sin_cambios`, `upsell`, `error`.
   * Se tipa como `string` porque el modelo Pydantic lo declara `str`; la UI
   * normaliza y aplica un tono por defecto para valores futuros.
   */
  estado: string;
  resumen: string;
}

export interface UpsellChatNucleo {
  modulo: string;
  mensaje: string;
}

/** `POST /nucleo/agente/chat` → 200 */
export interface ChatRespuestaNucleo {
  conversacion_id: string;
  mensaje_id: string;
  agente: string;
  respuesta: string;
  herramientas: HerramientaChatNucleo[];
  upsell: UpsellChatNucleo | null;
}

export interface MensajeChatNucleo {
  id: string;
  /** `user`, `assistant`, `tool` (el runtime también escribe turnos de tool). */
  rol: string;
  contenido: string | null;
  /**
   * Llamadas de herramienta crudas del proveedor. La UI no las interpreta ni
   * las muestra: los chips salen de `herramientas` / `metadata.herramientas`.
   */
  tool_calls: unknown;
  tool_call_id: string | null;
  nombre_herramienta: string | null;
  /** En los turnos `assistant` incluye `herramientas`, `upsell` y `usage`. */
  metadata: Record<string, unknown>;
  creado_en: string | null;
}

export interface ConversacionChatNucleo {
  id: string;
  agente: string;
  activa: boolean;
  abierta_en: string | null;
  cerrada_en: string | null;
  resumen: string | null;
  resumen_en: string | null;
  version: number;
}

/** `GET /nucleo/agente/chat/{conversacion_id}` → 200 (hasta 100 turnos). */
export interface HistorialChatNucleo {
  conversacion: ConversacionChatNucleo;
  mensajes: MensajeChatNucleo[];
}
