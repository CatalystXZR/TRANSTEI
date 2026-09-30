"use client";

import { useRef, useState } from "react";
import { FileUp, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { apiUpload } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface ImportarCsvProps {
  endpoint: string;
  onImportado: () => void;
  aceptar?: string;
}

export function ImportarCsv({
  endpoint,
  onImportado,
  aceptar = ".csv,text/csv",
}: ImportarCsvProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);

  async function manejarArchivo(archivo: File | null) {
    if (!archivo) return;
    setSubiendo(true);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const resultado = await apiUpload<{ importados: number; omitidos: { fila: number; motivo: string }[] }>(
        endpoint,
        fd,
      );
      if (!resultado) return;
      if (resultado.omitidos.length === 0) {
        toast.success(`Se importaron ${resultado.importados} registros correctamente`);
      } else {
        toast.warning(
          `Importados: ${resultado.importados} · Omitidos: ${resultado.omitidos.length} — ` +
            resultado.omitidos[0].motivo,
        );
      }
      onImportado();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al importar");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={aceptar}
        className="hidden"
        onChange={(e) => manejarArchivo(e.target.files?.[0] ?? null)}
      />
      <Button
        variant="outline"
        onClick={() => inputRef.current?.click()}
        disabled={subiendo}
        className="text-base"
      >
        {subiendo ? <Loader2 className="h-5 w-5 animate-spin" /> : <FileUp className="h-5 w-5" />}
        Importar CSV
      </Button>
    </>
  );
}
