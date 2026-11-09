"use client";

import { cn } from "cn";

/**
 * Interruptor accesible para una capacidad del agente.
 *
 * No existe `switch.tsx` en `components/ui`, así que se implementa con un
 * `button` nativo y `role="switch"` (sin agregar dependencias). Cuando el
 * control está bloqueado se usa `aria-disabled` en vez de `disabled` para que
 * siga siendo enfocable y el lector de pantalla pueda anunciar el motivo.
 */
export function ToggleCapacidad({
  id,
  nombre,
  checked,
  bloqueado = false,
  guardando = false,
  descritoPor,
  onCambio,
}: {
  id: string;
  nombre: string;
  checked: boolean;
  bloqueado?: boolean;
  guardando?: boolean;
  descritoPor?: string;
  onCambio: (habilitada: boolean) => void;
}) {
  const inactivo = bloqueado || guardando;

  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={nombre}
      aria-describedby={descritoPor}
      aria-disabled={inactivo || undefined}
      onClick={() => {
        if (inactivo) return;
        onCambio(!checked);
      }}
      className={cn(
        "relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors duration-150 outline-none",
        "focus-visible:ring-[3px] focus-visible:ring-marca/35 focus-visible:ring-offset-2 focus-visible:ring-offset-superficie",
        checked
          ? "border-marca bg-marca"
          : "border-borde-fuerte bg-superficie-hundida",
        inactivo
          ? "cursor-not-allowed opacity-45"
          : "cursor-pointer hover:border-marca/60",
      )}
    >
      <span
        className={cn(
          "block size-5 rounded-full bg-white shadow-elev-1 transition-transform duration-150",
          checked ? "translate-x-[22px]" : "translate-x-1",
        )}
        aria-hidden="true"
      />
    </button>
  );
}
