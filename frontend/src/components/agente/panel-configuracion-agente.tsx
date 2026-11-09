"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Bot,
  Info,
  Loader2,
  PackagePlus,
  RotateCcw,
} from "lucide-react";
import { cn } from "cn";
import type {
  AgenteConfigNucleo,
  CapacidadAgenteNucleo,
  RiesgoCapacidad,
} from "@/types/agente-config";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Aviso,
  EstadoVacio,
  Panel,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import { ToggleCapacidad } from "@/components/agente/toggle-capacidad";

const TONO_RIESGO: Record<RiesgoCapacidad, Tono> = {
  bajo: "ok",
  medio: "atencion",
  alto: "critico",
};

const ETIQUETA_RIESGO: Record<RiesgoCapacidad, string> = {
  bajo: "Riesgo bajo",
  medio: "Riesgo medio",
  alto: "Riesgo alto",
};

/**
 * Frases de rol tomadas de los system prompts del backend
 * (`backend/app/nucleo/agente/chat/personas.py:51-101`). Son copy de UI, no
 * datos del contrato; si el backend agrega un agente desconocido se usa un
 * texto genérico.
 */
const ROL_AGENTE: Record<string, string> = {
  gerente:
    "Asistente estratégico del dueño: lee el estado del negocio y deja directivas por escrito. No ejecuta transacciones.",
  secretaria:
    "Asistente operativa: consulta viajes y prepara solicitudes para el buzón de aprobación. No ejecuta acciones críticas.",
};

function agruparCapacidades(capacidades: CapacidadAgenteNucleo[]) {
  const grupos = new Map<string, CapacidadAgenteNucleo[]>();
  for (const capacidad of capacidades) {
    const actuales = grupos.get(capacidad.grupo);
    if (actuales) actuales.push(capacidad);
    else grupos.set(capacidad.grupo, [capacidad]);
  }
  return [...grupos.entries()];
}

function motivoNoDisponible(capacidad: CapacidadAgenteNucleo): string | null {
  if (capacidad.disponible) return null;
  if (capacidad.motivo_no_disponible === "permiso") {
    return "Requiere un permiso que su rol no tiene.";
  }
  if (capacidad.motivo_no_disponible === "modulo_inactivo") {
    return capacidad.modulo
      ? `Requiere el módulo ${capacidad.modulo} activo.`
      : "Requiere un módulo activo.";
  }
  return "No disponible en esta empresa.";
}

function estadoVisible(
  capacidad: CapacidadAgenteNucleo,
  guardando: boolean,
): string {
  if (guardando) return "Guardando…";
  if (!capacidad.disponible) return "No disponible";
  return capacidad.habilitada ? "Habilitada" : "Deshabilitada";
}

export function PanelConfiguracionAgente({
  agente,
  puedeConfigurar,
  idPermiso,
  guardando,
  restableciendo,
  onCambio,
  onRestablecer,
}: {
  agente: AgenteConfigNucleo;
  puedeConfigurar: boolean;
  /** Id del aviso de falta de permiso que la página renderiza sobre los paneles. */
  idPermiso: string;
  /** Claves `${agente}:${capacidad}` con una escritura en curso. */
  guardando: Record<string, boolean>;
  restableciendo: boolean;
  onCambio: (capacidad: string, habilitada: boolean) => void;
  onRestablecer: () => Promise<void>;
}) {
  const [dialogoAbierto, setDialogoAbierto] = useState(false);
  const [errorRestablecer, setErrorRestablecer] = useState<string | null>(null);

  const guardandoAgente = Object.keys(guardando).some((clave) =>
    clave.startsWith(`${agente.clave}:`),
  );
  const grupos = agruparCapacidades(agente.capacidades);
  const hayNotas = agente.clave === "secretaria";

  function abrirDialogo() {
    setErrorRestablecer(null);
    setDialogoAbierto(true);
  }

  async function confirmarRestablecer() {
    setErrorRestablecer(null);
    try {
      await onRestablecer();
      setDialogoAbierto(false);
    } catch (e) {
      setErrorRestablecer(
        e instanceof Error
          ? e.message
          : "No se pudo restablecer la configuración del agente.",
      );
    }
  }

  return (
    <>
      <Panel
        titulo={agente.nombre}
        descripcion={ROL_AGENTE[agente.clave] ?? "Agente del núcleo."}
        acciones={
          <>
            <StatusBadge tono="neutro">
              {agente.capacidades.length}{" "}
              {agente.capacidades.length === 1 ? "capacidad" : "capacidades"}
            </StatusBadge>
            <Button
              variant="outline"
              size="sm"
              onClick={abrirDialogo}
              disabled={
                !puedeConfigurar || guardandoAgente || restableciendo
              }
            >
              {restableciendo ? (
                <>
                  <Loader2 className="animate-spin" /> Restableciendo…
                </>
              ) : (
                <>
                  <RotateCcw /> Restablecer
                </>
              )}
            </Button>
          </>
        }
      >
        {hayNotas && (
          <div className="space-y-s3 px-s4 pt-s4">
            {agente.clave === "secretaria" && (
              <Aviso tono="neutro" icono={Info}>
                Las capacidades financieras estratégicas no están disponibles
                para la secretaria.
              </Aviso>
            )}
          </div>
        )}

        {agente.capacidades.length === 0 ? (
          <EstadoVacio
            icono={Bot}
            titulo="Sin capacidades configuradas"
            descripcion="El servidor no devolvió capacidades para este agente en esta empresa."
          />
        ) : (
          <div
            className={cn(
              "divide-y divide-borde border-t border-borde",
              hayNotas && "mt-s4",
            )}
          >
            {grupos.map(([grupo, capacidades], indiceGrupo) => {
              const idGrupo = `grupo-${agente.clave}-${indiceGrupo}`;
              return (
                <section key={grupo} aria-labelledby={idGrupo}>
                  <h3
                    id={idGrupo}
                    className="bg-superficie-hundida/60 px-s4 py-s2 font-mono text-[12px] font-semibold tracking-[0.08em] text-tinta-3 uppercase"
                  >
                    {grupo || "General"}
                  </h3>
                  <ul className="divide-y divide-borde">
                    {capacidades.map((capacidad) => {
                      const idBase = `capacidad-${agente.clave}-${capacidad.clave}`;
                      const ocupado = Boolean(
                        guardando[`${agente.clave}:${capacidad.clave}`],
                      );
                      const bloqueado =
                        !puedeConfigurar ||
                        !capacidad.disponible ||
                        guardandoAgente;
                      const motivo = motivoNoDisponible(capacidad);
                      const idsDescripcion = [`${idBase}-descripcion`];
                      if (motivo) idsDescripcion.push(`${idBase}-motivo`);
                      if (!puedeConfigurar) idsDescripcion.push(idPermiso);
                      const mostrarUpsell =
                        capacidad.modulo !== null &&
                        capacidad.modulo_activo === false;

                      return (
                        <li
                          key={capacidad.clave}
                          className="flex flex-wrap items-start gap-s4 px-s4 py-s4"
                        >
                          <div className="min-w-[240px] flex-1">
                            <p className="text-[16px] font-semibold text-tinta">
                              {capacidad.nombre}
                            </p>
                            <p
                              id={`${idBase}-descripcion`}
                              className="text-[14px] leading-relaxed text-tinta-3"
                            >
                              {capacidad.descripcion}
                            </p>
                            <div className="mt-s2 flex flex-wrap items-center gap-s2">
                              <StatusBadge
                                tono={TONO_RIESGO[capacidad.riesgo]}
                              >
                                {ETIQUETA_RIESGO[capacidad.riesgo]}
                              </StatusBadge>
                              {capacidad.modulo && (
                                <Badge variant="secondary">
                                  Módulo {capacidad.modulo}
                                </Badge>
                              )}
                              <span className="text-[13px] text-tinta-3">
                                Por defecto:{" "}
                                {capacidad.por_defecto
                                  ? "habilitada"
                                  : "deshabilitada"}
                              </span>
                            </div>
                            {motivo && (
                              <p
                                id={`${idBase}-motivo`}
                                className="mt-s2 text-[14px] font-medium text-atencion"
                              >
                                {motivo}
                              </p>
                            )}
                            {mostrarUpsell && (
                              <div className="mt-s3">
                                <Aviso tono="atencion" icono={PackagePlus}>
                                  El módulo{" "}
                                  <span className="font-semibold">
                                    {capacidad.modulo}
                                  </span>{" "}
                                  no está activo en esta empresa. Esta capacidad
                                  se habilita cuando el módulo esté activo;
                                  puede solicitar su activación.
                                </Aviso>
                              </div>
                            )}
                          </div>
                          <div className="flex min-w-[130px] flex-col items-end gap-s1">
                            <ToggleCapacidad
                              id={`${idBase}-toggle`}
                              nombre={`${capacidad.nombre} (${agente.nombre})`}
                              checked={capacidad.habilitada}
                              bloqueado={bloqueado}
                              guardando={ocupado}
                              descritoPor={idsDescripcion.join(" ")}
                              onCambio={(habilitada) =>
                                onCambio(capacidad.clave, habilitada)
                              }
                            />
                            <p
                              className="text-[13px] text-tinta-3"
                              role="status"
                              aria-live="polite"
                            >
                              {estadoVisible(capacidad, ocupado)}
                            </p>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </Panel>

      <Dialog
        open={dialogoAbierto}
        onOpenChange={(open) => {
          if (!open && !restableciendo) setDialogoAbierto(false);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Restablecer {agente.nombre}</DialogTitle>
            <DialogDescription>
              Se volverán a aplicar los valores por defecto de todas las
              capacidades de {agente.nombre} en esta empresa. Los cambios
              manuales se perderán.
            </DialogDescription>
          </DialogHeader>

          {errorRestablecer && (
            <div role="alert">
              <Aviso tono="critico" icono={AlertTriangle}>
                {errorRestablecer}
              </Aviso>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDialogoAbierto(false)}
              disabled={restableciendo}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => void confirmarRestablecer()}
              disabled={restableciendo}
            >
              {restableciendo ? (
                <>
                  <Loader2 className="animate-spin" /> Restableciendo…
                </>
              ) : (
                <>
                  <RotateCcw /> Sí, restablecer
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
