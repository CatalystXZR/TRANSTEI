"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { formatCLP } from "@/lib/format";

interface InputCLPProps {
  value: number;
  onChange: (value: number) => void;
  placeholder?: string;
  id?: string;
  required?: boolean;
  className?: string;
}

export function InputCLP({ value, onChange, ...props }: InputCLPProps) {
  const [texto, setTexto] = useState(() => (value ? formatCLP(value) : ""));

  return (
    <Input
      {...props}
      inputMode="numeric"
      value={texto}
      onChange={(e) => {
        const limpio = e.target.value.replace(/\D/g, "");
        if (limpio.length > 12) return;
        const numero = Number(limpio) || 0;
        setTexto(limpio ? formatCLP(numero) : "");
        onChange(numero);
      }}
    />
  );
}
