"use client";

import { MessageSquare, ShieldAlert } from "lucide-react";
import { useNucleoEmpresa } from "@/lib/use-nucleo-empresa";
import { ChatPanel } from "@/components/agente/chat-panel";
import { ErrorNucleo } from "@/components/nucleo/estado-error";
import { Aviso, PageHeader, Panel } from "@/components/sistema";
import { Skeleton } from "@/components/ui/skeleton";

export default function ChatAgentesPage() {
  const { empresa, empresaId, permisos, cargando, error } = useNucleoEmpresa();
  const permisosListos = !cargando && error === null;
  const puedeUsarChat = permisos.includes("agente:chat");

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Agente"
        titulo="Chat con agentes"
        descripcion="Conversa con el gerente y la secretaria del núcleo. El servidor conserva el historial, valida cada turno, aplica el muro de pago y es la autoridad del permiso agente:chat; esta pantalla solo muestra el estado real."
      />

      {cargando ? (
        <Panel
          titulo="Chat con agentes"
          descripcion="Resolviendo la empresa activa y sus permisos…"
        >
          <div className="space-y-s4 p-s4" aria-busy="true">
            <span className="sr-only">
              Cargando la empresa activa y los permisos…
            </span>
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-56 w-full rounded-xl" />
          </div>
        </Panel>
      ) : !empresaId ? (
        error ? (
          <ErrorNucleo error={error} />
        ) : (
          <div role="alert">
            <Aviso tono="atencion" icono={ShieldAlert}>
              El usuario no tiene una empresa activa asignada.
            </Aviso>
          </div>
        )
      ) : permisosListos && !puedeUsarChat ? (
        <div role="alert">
          <Aviso tono="atencion" icono={ShieldAlert}>
            <p className="font-medium">Tu rol no permite usar el chat</p>
            <p className="mt-s1">
              El chat con agentes requiere el permiso <code>agente:chat</code>.
              Solicita acceso a un administrador.
            </p>
          </Aviso>
        </div>
      ) : (
        <ChatPanel
          key={empresaId}
          empresaId={empresaId}
          empresaNombre={empresa?.razon_social}
        />
      )}

      {!cargando &&
        empresaId &&
        (!permisosListos || puedeUsarChat) && (
          <Aviso tono="neutro" icono={MessageSquare}>
            Las respuestas y los cambios propuestos provienen del agente y las
            herramientas del servidor. Las acciones críticas quedan en el buzón
            para aprobación del dueño; las claves de API nunca se muestran aquí.
          </Aviso>
        )}
    </div>
  );
}
