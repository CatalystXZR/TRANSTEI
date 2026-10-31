"use client";

import { useSearchParams } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { Aviso } from "@/components/sistema";
import { tituloDeRuta } from "@/lib/navigation";

export const PARAM_AVISO_LEGACY = "sin-acceso-legacy";

/**
 * Aviso que se muestra al llegar desde una pantalla legacy bloqueada
 * (redirige `app/(app)/layout.tsx`). El texto se deriva de la ruta solicitada;
 * nunca se renderiza HTML del query string.
 */
export function AvisoSinAccesoLegacy() {
  const searchParams = useSearchParams();
  if (searchParams.get("aviso") !== PARAM_AVISO_LEGACY) return null;

  const ruta = searchParams.get("ruta");
  const pantalla = ruta ? tituloDeRuta(ruta)?.label : null;

  return (
    <div role="alert">
      <Aviso tono="atencion" icono={ShieldAlert}>
        <p className="font-medium">Sin permiso para el sistema legacy</p>
        <p className="mt-s1 text-[14px]">
          {pantalla ? `«${pantalla}» pertenece` : "Esa pantalla pertenece"} al sistema legacy
          monoempresa de Transportes TEI y no está disponible para su empresa. La operación del
          núcleo continúa en esta mesa de despacho.
        </p>
      </Aviso>
    </div>
  );
}
