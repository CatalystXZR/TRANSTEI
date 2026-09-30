"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { formatRut, limpiarRut, validarRut } from "@/lib/format";

interface InputRutProps {
  value: string;
  onChange: (value: string) => void;
  onValidez?: (valido: boolean) => void;
  id?: string;
  required?: boolean;
  placeholder?: string;
  className?: string;
}

export function InputRut({ value, onChange, onValidez, ...props }: InputRutProps) {
  const [texto, setTexto] = useState(() => (value ? formatRut(value) : ""));
  const [valido, setValido] = useState(true);

  function manejarCambio(raw: string) {
    const limpio = limpiarRut(raw).slice(0, 10);
    const formateado = limpio.length > 0 ? formatRut(limpio) : "";
    setTexto(formateado);
    const esValido = validarRut(limpio);
    setValido(limpio.length === 0 || esValido);
    onChange(limpio);
    onValidez?.(limpio.length === 0 || esValido);
  }

  return (
    <Input
      {...props}
      value={texto}
      onChange={(e) => manejarCambio(e.target.value)}
      className={`${props.className ?? ""} ${!valido ? "border-red-500" : ""}`}
      aria-invalid={!valido}
    />
  );
}
