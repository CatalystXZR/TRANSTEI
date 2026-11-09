"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Bot,
  Check,
  KeyRound,
  Loader2,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  Wrench,
} from "lucide-react";
import { cn } from "cn";
import { NucleoError, nucleo } from "@/lib/nucleo";
import { formatFechaHora } from "@/lib/format";
import type {
  AgenteChatClave,
  AgenteChatNucleo,
  ChatEnvioNucleo,
  ChatRespuestaNucleo,
  HerramientaChatNucleo,
  HistorialChatNucleo,
  MensajeChatNucleo,
  UpsellChatNucleo,
} from "@/types/agente-chat";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AreaTexto } from "@/components/formulario";
import {
  Aviso,
  EstadoVacio,
  Panel,
  StatusBadge,
  type Tono,
} from "@/components/sistema";

const LIMITE_MENSAJE = 4000;

const DESCRIPCION_AGENTE: Record<AgenteChatClave, string> = {
  gerente:
    "Revisa el contexto del negocio y ajusta directivas o reglas por entidad.",
  secretaria:
    "Consulta viajes y solicitudes, y prepara acciones para tu aprobación.",
};

const ETIQUETA_HERRAMIENTA: Record<string, string> = {
  ok: "OK",
  sin_cambios: "Sin cambios",
  upsell: "Upsell",
  error: "Error",
};

const TONO_HERRAMIENTA: Record<string, Tono> = {
  ok: "ok",
  sin_cambios: "neutro",
  upsell: "info",
  error: "critico",
};

type TipoErrorChat = "permiso" | "sesion" | "red" | "dominio";
type AccionErrorChat = "reintentar" | "login" | "nueva" | "ninguna";

interface ErrorChat {
  tipo: TipoErrorChat;
  titulo: string;
  mensaje: string;
  accion: AccionErrorChat;
}

interface MensajeVista {
  id: string;
  rol: "user" | "assistant";
  contenido: string;
  creado_en: string | null;
  herramientas: HerramientaChatNucleo[];
  upsell: UpsellChatNucleo | null;
}

interface HiloChat {
  conversacionId: string | null;
  mensajes: MensajeVista[];
}

interface EnvioPendiente {
  agente: AgenteChatClave;
  mensaje: string;
  clave: string;
}

const HILO_VACIO: HiloChat = { conversacionId: null, mensajes: [] };

/**
 * Mapa de errores del backend a mensajes propios. No se muestra el texto crudo
 * del proveedor ni la API key: el backend ya entrega mensajes fijos y códigos.
 */
function clasificarErrorChat(error: unknown): ErrorChat {
  if (error instanceof NucleoError) {
    if (error.status === 401) {
      return {
        tipo: "sesion",
        titulo: "Sesión expirada",
        mensaje: "Su sesión expiró. Vuelva a iniciar sesión para continuar.",
        accion: "login",
      };
    }
    if (error.status === 403) {
      return {
        tipo: "permiso",
        titulo: "Sin permiso",
        mensaje: "Tu rol no permite usar el chat.",
        accion: "ninguna",
      };
    }
    if (error.status === 503 || error.codigo === "AGENTE_NO_CONFIGURADO") {
      return {
        tipo: "dominio",
        titulo: "Agente sin configurar",
        mensaje: "Falta configurar la API key del agente en el servidor.",
        accion: "reintentar",
      };
    }
    if (error.status === 504 || error.codigo === "AGENTE_TIMEOUT") {
      return {
        tipo: "dominio",
        titulo: "El agente tardó demasiado",
        mensaje: "El agente tardó demasiado; reintenta.",
        accion: "reintentar",
      };
    }
    if (error.status === 502 || error.codigo === "AGENTE_LLM_ERROR") {
      return {
        tipo: "dominio",
        titulo: "Falla del proveedor",
        mensaje: "El proveedor del agente falló.",
        accion: "reintentar",
      };
    }
    if (error.status === 404) {
      return {
        tipo: "dominio",
        titulo: "Conversación no disponible",
        mensaje:
          "La conversación ya no está disponible para esta empresa. Inicia una conversación nueva.",
        accion: "nueva",
      };
    }
    if (error.status === 422) {
      return {
        tipo: "dominio",
        titulo: "Mensaje no procesado",
        mensaje:
          "El mensaje no se pudo procesar. Revisa el texto e inténtalo de nuevo.",
        accion: "ninguna",
      };
    }
    return {
      tipo: "dominio",
      titulo: "No se pudo completar la operación",
      mensaje: "El servidor devolvió un error. Reintenta en unos momentos.",
      accion: "reintentar",
    };
  }

  return {
    tipo: "red",
    titulo: "Sin conexión",
    mensaje:
      "No se pudo conectar con el servidor. Revise su conexión y reintente; si el mensaje falló, se reutiliza la misma clave de idempotencia.",
    accion: "reintentar",
  };
}

function tonoError(error: ErrorChat): Tono {
  return error.tipo === "permiso" || error.tipo === "sesion"
    ? "atencion"
    : "critico";
}

function iconoError(error: ErrorChat) {
  return error.tipo === "permiso" || error.tipo === "sesion"
    ? ShieldAlert
    : AlertTriangle;
}

function etiquetaHerramienta(estado: string): string {
  return ETIQUETA_HERRAMIENTA[estado] ?? estado;
}

function tonoHerramienta(estado: string): Tono {
  return TONO_HERRAMIENTA[estado] ?? "neutro";
}

function descripcionAgente(clave: AgenteChatClave): string {
  return DESCRIPCION_AGENTE[clave] ?? "Agente disponible en el servidor.";
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

/** Reconstruye los chips desde `metadata.herramientas` al recargar historial. */
function herramientasDeMetadata(
  metadata: Record<string, unknown> | null | undefined,
): HerramientaChatNucleo[] {
  const valor = metadata?.herramientas;
  if (!Array.isArray(valor)) return [];
  return valor.flatMap((item) => {
    if (!esObjeto(item)) return [];
    const { nombre, estado, resumen } = item;
    if (
      typeof nombre !== "string" ||
      typeof estado !== "string" ||
      typeof resumen !== "string"
    ) {
      return [];
    }
    return [{ nombre, estado, resumen }];
  });
}

/** Reconstruye el upsell desde `metadata.upsell` al recargar historial. */
function upsellDeMetadata(
  metadata: Record<string, unknown> | null | undefined,
): UpsellChatNucleo | null {
  const valor = metadata?.upsell;
  if (!esObjeto(valor)) return null;
  const { modulo, mensaje } = valor;
  if (
    typeof modulo !== "string" ||
    typeof mensaje !== "string" ||
    !modulo ||
    !mensaje
  ) {
    return null;
  }
  return { modulo, mensaje };
}

function mensajesDeHistorial(mensajes: MensajeChatNucleo[]): MensajeVista[] {
  return mensajes.flatMap((mensaje) => {
    if (mensaje.rol !== "user" && mensaje.rol !== "assistant") return [];
    if (!mensaje.contenido) return [];
    const rol: "user" | "assistant" = mensaje.rol;
    return [
      {
        id: mensaje.id,
        rol,
        contenido: mensaje.contenido,
        creado_en: mensaje.creado_en,
        herramientas:
          rol === "assistant"
            ? herramientasDeMetadata(mensaje.metadata)
            : [],
        upsell: rol === "assistant" ? upsellDeMetadata(mensaje.metadata) : null,
      },
    ];
  });
}

function AccionesErrorChat({
  error,
  onReintentar,
  onLogin,
  onNueva,
  reintentoDeshabilitado = false,
}: {
  error: ErrorChat;
  onReintentar: () => void;
  onLogin: () => void;
  onNueva: () => void;
  reintentoDeshabilitado?: boolean;
}) {
  if (error.accion === "login") {
    return (
      <Button type="button" size="sm" variant="outline" onClick={onLogin}>
        Iniciar sesión
      </Button>
    );
  }
  if (error.accion === "reintentar") {
    return (
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={onReintentar}
        disabled={reintentoDeshabilitado}
      >
        Reintentar
      </Button>
    );
  }
  if (error.accion === "nueva") {
    return (
      <Button type="button" size="sm" variant="outline" onClick={onNueva}>
        Nueva conversación
      </Button>
    );
  }
  return null;
}

function DetalleHerramientas({
  herramientas,
}: {
  herramientas: HerramientaChatNucleo[];
}) {
  return (
    <details className="rounded-lg border border-borde bg-superficie/70 px-s3 py-s2 text-[13px]">
      <summary className="flex cursor-pointer list-none items-center gap-s2 text-tinta-3 select-none hover:text-tinta">
        <Wrench className="size-3.5" aria-hidden="true" />
        Herramientas del turno ({herramientas.length})
      </summary>
      <ul className="mt-s2 flex flex-col gap-s2">
        {herramientas.map((herramienta, indice) => (
          <li
            key={`${herramienta.nombre}-${indice}`}
            className="rounded-md border border-borde bg-superficie px-s2 py-s2"
          >
            <div className="flex flex-wrap items-center gap-s2">
              <span className="font-mono text-[12px] text-tinta-2">
                {herramienta.nombre}
              </span>
              <StatusBadge tono={tonoHerramienta(herramienta.estado)}>
                {etiquetaHerramienta(herramienta.estado)}
              </StatusBadge>
            </div>
            <p className="mt-s1 text-tinta-3">{herramienta.resumen}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

function TarjetaUpsell({ upsell }: { upsell: UpsellChatNucleo }) {
  return (
    <div className="rounded-xl border border-marca/30 bg-marca-tenue px-s4 py-s3">
      <p className="flex items-center gap-s2 text-[14px] font-semibold text-marca">
        <Sparkles className="size-4" aria-hidden="true" />
        Módulo {upsell.modulo}
      </p>
      <p className="mt-s1 text-[15px] text-tinta-2">{upsell.mensaje}</p>
    </div>
  );
}

function BurbujaMensaje({
  mensaje,
  nombreAgente,
  pendiente = false,
}: {
  mensaje: MensajeVista;
  nombreAgente: string;
  pendiente?: boolean;
}) {
  const esUsuario = mensaje.rol === "user";
  return (
    <div
      className={cn(
        "flex items-start gap-s2",
        esUsuario ? "justify-end" : "justify-start",
      )}
    >
      {!esUsuario && (
        <span
          className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-marca-tenue text-marca"
          aria-hidden="true"
        >
          <Bot className="size-4" />
        </span>
      )}
      <div className="min-w-0 max-w-[88%] space-y-s2 sm:max-w-[78%]">
        <div
          className={cn(
            "rounded-2xl px-s4 py-s3 text-[15.5px] leading-relaxed break-words whitespace-pre-wrap",
            esUsuario
              ? "rounded-br-md bg-marca text-white"
              : "rounded-bl-md border border-borde bg-superficie-hundida text-tinta",
          )}
        >
          {mensaje.contenido}
        </div>
        {!esUsuario && mensaje.herramientas.length > 0 && (
          <DetalleHerramientas herramientas={mensaje.herramientas} />
        )}
        {!esUsuario && mensaje.upsell && (
          <TarjetaUpsell upsell={mensaje.upsell} />
        )}
        <p
          className={cn(
            "px-1 text-[12.5px] text-tinta-3",
            esUsuario ? "text-right" : "text-left",
          )}
        >
          {esUsuario ? "Tú" : nombreAgente}
          {pendiente
            ? " · Enviando…"
            : mensaje.creado_en
              ? ` · ${formatFechaHora(mensaje.creado_en)}`
              : ""}
        </p>
      </div>
    </div>
  );
}

function BurbujaPensando({ nombreAgente }: { nombreAgente: string }) {
  return (
    <div className="flex items-start gap-s2" role="status">
      <span
        className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-marca-tenue text-marca"
        aria-hidden="true"
      >
        <Bot className="size-4" />
      </span>
      <div className="rounded-2xl rounded-bl-md border border-borde bg-superficie-hundida px-s4 py-s3 text-[14.5px] text-tinta-3">
        <span className="inline-flex items-center gap-s2">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          {nombreAgente} está respondiendo…
        </span>
      </div>
    </div>
  );
}

export function ChatPanel({
  empresaId,
  empresaNombre,
}: {
  empresaId: string;
  empresaNombre?: string;
}) {
  const router = useRouter();

  const [agentes, setAgentes] = useState<AgenteChatNucleo[]>([]);
  const [agenteClave, setAgenteClave] = useState<AgenteChatClave | "">("");
  const [cargandoAgentes, setCargandoAgentes] = useState(true);
  const [errorAgentes, setErrorAgentes] = useState<ErrorChat | null>(null);

  const [hilos, setHilos] = useState<
    Partial<Record<AgenteChatClave, HiloChat>>
  >({});
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [enviandoTexto, setEnviandoTexto] = useState<string | null>(null);
  const [pendiente, setPendiente] = useState<EnvioPendiente | null>(null);
  const [errorEnvio, setErrorEnvio] = useState<ErrorChat | null>(null);
  const [cargandoHistorial, setCargandoHistorial] = useState(false);
  const [errorHistorial, setErrorHistorial] = useState<ErrorChat | null>(null);

  const finRef = useRef<HTMLDivElement | null>(null);

  const hilo = agenteClave ? (hilos[agenteClave] ?? HILO_VACIO) : HILO_VACIO;
  const mensajes = hilo.mensajes;
  const agenteActual =
    agentes.find((agente) => agente.clave === agenteClave) ?? null;
  const nombreAgente = agenteActual?.nombre ?? "El agente";
  const configurado = agenteActual?.configurado === true;
  const restantes = LIMITE_MENSAJE - texto.length;

  const cargarAgentes = useCallback(async () => {
    setCargandoAgentes(true);
    setErrorAgentes(null);
    try {
      const lista = await nucleo.get<AgenteChatNucleo[]>(
        "/nucleo/agente/chat/agentes",
        empresaId,
      );
      setAgentes(lista);
      setAgenteClave((anterior) =>
        anterior && lista.some((agente) => agente.clave === anterior)
          ? anterior
          : (lista[0]?.clave ?? ""),
      );
    } catch (e) {
      setErrorAgentes(clasificarErrorChat(e));
    } finally {
      setCargandoAgentes(false);
    }
  }, [empresaId]);

  useEffect(() => {
    const t = setTimeout(() => {
      void cargarAgentes();
    }, 0);
    return () => clearTimeout(t);
  }, [cargarAgentes]);

  useEffect(() => {
    const nodo = finRef.current;
    if (!nodo) return;
    nodo.scrollIntoView({ block: "end" });
  }, [mensajes, enviando, agenteClave]);

  const irALogin = useCallback(() => {
    router.replace(`/login?next=${encodeURIComponent("/agente/chat")}`);
  }, [router]);

  const cargarHistorial = useCallback(async () => {
    if (!agenteClave || enviando) return;
    const conversacionId = (hilos[agenteClave] ?? HILO_VACIO).conversacionId;
    if (!conversacionId) return;
    setCargandoHistorial(true);
    setErrorHistorial(null);
    try {
      const data = await nucleo.get<HistorialChatNucleo>(
        `/nucleo/agente/chat/${conversacionId}`,
        empresaId,
      );
      const mensajesServidor = mensajesDeHistorial(data.mensajes);
      setHilos((previo) => ({
        ...previo,
        [agenteClave]: {
          conversacionId: data.conversacion.id,
          mensajes: mensajesServidor,
        },
      }));
    } catch (e) {
      setErrorHistorial(clasificarErrorChat(e));
    } finally {
      setCargandoHistorial(false);
    }
  }, [agenteClave, empresaId, enviando, hilos]);

  function cambiarAgente(clave: AgenteChatClave) {
    if (enviando) return;
    setAgenteClave(clave);
    setErrorEnvio(null);
    setErrorHistorial(null);
  }

  function cambiarTexto(valor: string) {
    setTexto(valor);
    // El cuerpo se envía con `trim()`: solo un cambio de contenido invalida la
    // clave de idempotencia del envío anterior.
    if (pendiente && valor.trim() !== pendiente.mensaje) {
      setPendiente(null);
    }
  }

  function nuevaConversacion() {
    if (!agenteClave || enviando) return;
    setHilos((previo) => ({
      ...previo,
      [agenteClave]: { conversacionId: null, mensajes: [] },
    }));
    setPendiente(null);
    setErrorEnvio(null);
    setErrorHistorial(null);
  }

  async function enviar() {
    if (enviando || !agenteClave) return;
    const mensaje = texto.trim();
    if (!mensaje || !configurado) return;
    if (mensaje.length > LIMITE_MENSAJE) {
      setErrorEnvio({
        tipo: "dominio",
        titulo: "Mensaje demasiado largo",
        mensaje: `El mensaje supera los ${LIMITE_MENSAJE} caracteres.`,
        accion: "ninguna",
      });
      return;
    }

    const agenteEnvio = agenteClave;
    const hiloEnvio = hilos[agenteEnvio] ?? HILO_VACIO;
    // Misma clave solo para reintentar el mismo texto con el mismo agente.
    const clave =
      pendiente &&
      pendiente.agente === agenteEnvio &&
      pendiente.mensaje === mensaje
        ? pendiente.clave
        : crypto.randomUUID();
    const cuerpo: ChatEnvioNucleo = {
      agente: agenteEnvio,
      mensaje,
      conversacion_id: hiloEnvio.conversacionId,
      clave_idempotencia: clave,
    };

    setEnviando(true);
    setEnviandoTexto(mensaje);
    setErrorEnvio(null);
    // La clave queda guardada mientras el turno está en curso. Si falla, se
    // conserva para reintentar el mismo texto de forma idempotente.
    setPendiente({ agente: agenteEnvio, mensaje, clave });

    try {
      const respuesta = await nucleo.post<ChatRespuestaNucleo>(
        "/nucleo/agente/chat",
        empresaId,
        cuerpo,
      );
      const mensajeUsuario: MensajeVista = {
        id: `local-user-${clave}`,
        rol: "user",
        contenido: mensaje,
        creado_en: null,
        herramientas: [],
        upsell: null,
      };
      const mensajeAgente: MensajeVista = {
        id: respuesta.mensaje_id,
        rol: "assistant",
        contenido: respuesta.respuesta,
        creado_en: null,
        herramientas: respuesta.herramientas,
        upsell: respuesta.upsell,
      };
      setHilos((previo) => {
        const actual = previo[agenteEnvio] ?? HILO_VACIO;
        return {
          ...previo,
          [agenteEnvio]: {
            conversacionId: respuesta.conversacion_id,
            mensajes: [...actual.mensajes, mensajeUsuario, mensajeAgente],
          },
        };
      });
      setTexto("");
      setPendiente(null);
    } catch (e) {
      setErrorEnvio(clasificarErrorChat(e));
      // `pendiente` ya conserva la clave: un reintento del mismo texto es
      // idempotente aunque la respuesta se haya perdido después de persistir.
    } finally {
      setEnviando(false);
      setEnviandoTexto(null);
    }
  }

  function manejarEnvio(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    void enviar();
  }

  function manejarTecla(evento: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (
      evento.key === "Enter" &&
      !evento.shiftKey &&
      !evento.nativeEvent.isComposing
    ) {
      evento.preventDefault();
      if (!enviando) void enviar();
    }
  }

  if (cargandoAgentes) {
    return (
      <Panel
        titulo="Chat con agentes"
        descripcion="Cargando agentes disponibles…"
      >
        <div className="space-y-s4 p-s4" aria-busy="true">
          <span className="sr-only">Cargando agentes y conversación…</span>
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-48 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      </Panel>
    );
  }

  if (errorAgentes) {
    const Icono = iconoError(errorAgentes);
    return (
      <Panel
        titulo="Chat con agentes"
        descripcion="No se pudieron cargar los agentes disponibles."
      >
        <div className="p-s4" role="alert">
          <Aviso tono={tonoError(errorAgentes)} icono={Icono}>
            <p className="font-medium">{errorAgentes.titulo}</p>
            <p className="mt-s1">{errorAgentes.mensaje}</p>
            <div className="mt-s2 flex flex-wrap gap-s2">
              <AccionesErrorChat
                error={errorAgentes}
                onReintentar={() => void cargarAgentes()}
                onLogin={irALogin}
                onNueva={nuevaConversacion}
              />
            </div>
          </Aviso>
        </div>
      </Panel>
    );
  }

  if (agentes.length === 0) {
    return (
      <Panel titulo="Chat con agentes">
        <EstadoVacio
          icono={Bot}
          titulo="No hay agentes disponibles"
          descripcion="El servidor no devolvió agentes para esta empresa."
          accion={
            <Button
              type="button"
              variant="outline"
              onClick={() => void cargarAgentes()}
            >
              Reintentar
            </Button>
          }
        />
      </Panel>
    );
  }

  const conversacionActiva = Boolean(hilo.conversacionId);
  const hayMensajes = mensajes.length > 0;

  return (
    <div className="space-y-s4">
      <Panel
        titulo="Agente"
        descripcion="Elige con quién conversar. El servidor valida el permiso agente:chat y el estado de configuración."
      >
        <div className="space-y-s3 p-s4">
          <fieldset className="space-y-s2">
            <legend className="text-[14px] font-medium text-tinta-2">
              Agente
            </legend>
            <div className="grid gap-s3 sm:grid-cols-2">
              {agentes.map((agente) => {
                const activo = agente.clave === agenteClave;
                return (
                  <label
                    key={agente.clave}
                    className={cn(
                      "relative flex cursor-pointer gap-s3 rounded-xl border p-s3 transition-[border-color,background-color] duration-150 focus-within:ring-2 focus-within:ring-marca/35",
                      activo
                        ? "border-marca bg-marca-tenue"
                        : "border-borde bg-superficie hover:border-borde-fuerte",
                      enviando && "cursor-not-allowed opacity-60",
                    )}
                  >
                    <input
                      type="radio"
                      name="agente-chat"
                      value={agente.clave}
                      checked={activo}
                      onChange={() => cambiarAgente(agente.clave)}
                      disabled={enviando}
                      className="sr-only"
                    />
                    <span
                      className={cn(
                        "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border",
                        activo
                          ? "border-marca bg-marca text-white"
                          : "border-borde-fuerte",
                      )}
                      aria-hidden="true"
                    >
                      {activo && <Check className="size-3.5" />}
                    </span>
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-s2">
                        <span className="text-[16px] font-semibold">
                          {agente.nombre}
                        </span>
                        <StatusBadge
                          tono={agente.configurado ? "ok" : "atencion"}
                        >
                          {agente.configurado ? "Configurado" : "Sin API key"}
                        </StatusBadge>
                      </span>
                      <span className="mt-s1 block text-[14px] text-tinta-3">
                        {descripcionAgente(agente.clave)}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {!configurado && (
            <Aviso tono="atencion" icono={KeyRound}>
              <p className="font-medium">
                El agente no tiene API key configurada en el servidor
              </p>
              <p className="mt-s1">
                Un administrador debe configurar la clave en el servidor. Esta
                pantalla nunca muestra ni solicita API keys.
              </p>
            </Aviso>
          )}
        </div>
      </Panel>

      <Panel
        titulo={`Conversación con ${nombreAgente}`}
        descripcion={
          empresaNombre
            ? `${empresaNombre} · el servidor conserva el historial y valida cada turno.`
            : "El servidor conserva el historial y valida cada turno."
        }
        acciones={
          <div className="flex flex-wrap items-center gap-s2">
            <StatusBadge tono={configurado ? "ok" : "atencion"}>
              {configurado ? "API key configurada" : "Sin API key"}
            </StatusBadge>
            {conversacionActiva && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => void cargarHistorial()}
                disabled={cargandoHistorial || enviando}
              >
                <RefreshCw
                  className={cargandoHistorial ? "animate-spin" : undefined}
                />
                Actualizar
              </Button>
            )}
            {(conversacionActiva || hayMensajes) && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={nuevaConversacion}
                disabled={enviando}
              >
                <Plus /> Nueva conversación
              </Button>
            )}
          </div>
        }
      >
        {errorHistorial && (
          <div className="border-b border-borde px-s4 py-s3" role="alert">
            <Aviso tono={tonoError(errorHistorial)} icono={iconoError(errorHistorial)}>
              <p className="font-medium">{errorHistorial.titulo}</p>
              <p className="mt-s1">{errorHistorial.mensaje}</p>
              <div className="mt-s2 flex flex-wrap gap-s2">
                <AccionesErrorChat
                  error={errorHistorial}
                  onReintentar={() => void cargarHistorial()}
                  onLogin={irALogin}
                  onNueva={nuevaConversacion}
                  reintentoDeshabilitado={cargandoHistorial}
                />
              </div>
            </Aviso>
          </div>
        )}

        <div
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          aria-label={`Conversación con ${nombreAgente}`}
          aria-busy={enviando}
          className="max-h-[52vh] min-h-[280px] space-y-s4 overflow-y-auto px-s4 py-s4"
        >
          {!hayMensajes && !enviando ? (
            <EstadoVacio
              icono={MessageSquare}
              titulo="Sin mensajes todavía"
              descripcion={`Escribe el primer mensaje para ${nombreAgente}.`}
            />
          ) : (
            <>
              {mensajes.map((mensaje) => (
                <BurbujaMensaje
                  key={mensaje.id}
                  mensaje={mensaje}
                  nombreAgente={nombreAgente}
                />
              ))}
              {enviando && enviandoTexto && (
                <>
                  <BurbujaMensaje
                    mensaje={{
                      id: "local-pendiente",
                      rol: "user",
                      contenido: enviandoTexto,
                      creado_en: null,
                      herramientas: [],
                      upsell: null,
                    }}
                    nombreAgente={nombreAgente}
                    pendiente
                  />
                  <BurbujaPensando nombreAgente={nombreAgente} />
                </>
              )}
            </>
          )}
          <div ref={finRef} />
        </div>

        <div className="space-y-s3 border-t border-borde px-s4 py-s4">
          {errorEnvio && (
            <div role="alert">
              <Aviso tono={tonoError(errorEnvio)} icono={iconoError(errorEnvio)}>
                <p className="font-medium">{errorEnvio.titulo}</p>
                <p className="mt-s1">{errorEnvio.mensaje}</p>
                <div className="mt-s2 flex flex-wrap gap-s2">
                  <AccionesErrorChat
                    error={errorEnvio}
                    onReintentar={() => void enviar()}
                    onLogin={irALogin}
                    onNueva={nuevaConversacion}
                    reintentoDeshabilitado={enviando || !texto.trim()}
                  />
                </div>
              </Aviso>
            </div>
          )}

          <form onSubmit={manejarEnvio} className="space-y-s2">
            <label
              htmlFor="chat-mensaje"
              className="block text-[14px] font-medium text-tinta-2"
            >
              Mensaje para {nombreAgente}
            </label>
            <AreaTexto
              id="chat-mensaje"
              value={texto}
              onChange={(evento) => cambiarTexto(evento.target.value)}
              onKeyDown={manejarTecla}
              maxLength={LIMITE_MENSAJE}
              rows={3}
              disabled={enviando || !configurado}
              placeholder={
                configurado
                  ? "Escribe tu mensaje. Enter envía · Shift+Enter agrega una línea."
                  : "El agente no está configurado; no se pueden enviar mensajes."
              }
              aria-describedby="chat-ayuda chat-contador"
            />
            <div className="flex flex-wrap items-center justify-between gap-s2">
              <p id="chat-ayuda" className="text-[13px] text-tinta-3">
                Enter envía · Shift+Enter salto de línea. El servidor vuelve a
                validar el permiso <code>agente:chat</code>.
              </p>
              <p
                id="chat-contador"
                className={cn(
                  "text-[13px] tabular-nums",
                  restantes < 200 ? "text-atencion" : "text-tinta-3",
                )}
              >
                {texto.length} / {LIMITE_MENSAJE}
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-s2">
              <Button
                type="submit"
                disabled={
                  enviando ||
                  !configurado ||
                  !texto.trim() ||
                  texto.length > LIMITE_MENSAJE
                }
              >
                {enviando ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : (
                  <Send aria-hidden="true" />
                )}
                {enviando ? "Enviando…" : "Enviar"}
              </Button>
            </div>
          </form>
        </div>
      </Panel>
    </div>
  );
}
