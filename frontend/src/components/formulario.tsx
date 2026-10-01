"use client";

import { cn } from "cn";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/* Campo de formulario: etiqueta + control + ayuda/error */
export function Campo({
  etiqueta,
  htmlFor,
  requerido,
  ayuda,
  error,
  className,
  children,
}: {
  etiqueta: string;
  htmlFor?: string;
  requerido?: boolean;
  ayuda?: React.ReactNode;
  error?: string | null;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("space-y-s2", className)}>
      <Label htmlFor={htmlFor}>
        {etiqueta}
        {requerido && (
          <span className="text-critico" aria-hidden="true">
            *
          </span>
        )}
      </Label>
      {children}
      {error ? (
        <p className="text-[14px] text-critico" role="alert">
          {error}
        </p>
      ) : (
        ayuda && <p className="text-[14px] text-tinta-3">{ayuda}</p>
      )}
    </div>
  );
}

/* Select con opciones simples: muestra la etiqueta (no el id) en el disparador */
export function SelectSimple({
  id,
  valor,
  onCambio,
  opciones,
  placeholder = "Seleccione…",
  className,
  ariaLabel,
}: {
  id?: string;
  valor: string;
  onCambio: (v: string) => void;
  opciones: { valor: string; etiqueta: string }[];
  placeholder?: string;
  className?: string;
  ariaLabel?: string;
}) {
  const items = Object.fromEntries(opciones.map((o) => [o.valor, o.etiqueta]));
  return (
    <Select value={valor || null} onValueChange={(v) => onCambio((v as string | null) ?? "")} items={items}>
      <SelectTrigger id={id} className={cn("w-full", className)} aria-label={ariaLabel}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {opciones.map((o) => (
          <SelectItem key={o.valor} value={o.valor}>
            {o.etiqueta}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/* Área de texto con el mismo estilo que Input */
export function AreaTexto({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "w-full rounded-lg border border-borde-fuerte bg-superficie px-3 py-2.5 text-base text-tinta transition-[border-color,box-shadow] duration-150 outline-none placeholder:text-tinta-3/70 hover:border-tinta-3/50 focus-visible:border-marca focus-visible:shadow-[0_0_0_4px_rgb(42_35_122/0.12)] focus-visible:outline-none",
        className,
      )}
      {...props}
    />
  );
}
