"use client";

import { AlertTriangle, ShieldAlert } from "lucide-react";
import { NucleoError } from "@/lib/nucleo";
import { Aviso } from "@/components/sistema";

/**
 * Error de carga de una pantalla del núcleo. Un 403 se muestra como falta de
 * permiso explícita, nunca como "sin datos".
 */
export function ErrorNucleo({ error }: { error: unknown }) {
  if (!error) return null;
  const status = error instanceof NucleoError ? error.status : null;
  const mensaje =
    error instanceof Error ? error.message : "Ocurrió un error inesperado.";
  if (status === 403) {
    return (
      <div role="alert">
        <Aviso tono="atencion" icono={ShieldAlert}>
          <strong>Sin permiso.</strong> {mensaje}
        </Aviso>
      </div>
    );
  }
  return (
    <div role="alert">
      <Aviso tono="critico" icono={AlertTriangle}>
        {mensaje}
      </Aviso>
    </div>
  );
}
