"use client";

import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { nucleo } from "@/lib/nucleo";
import type { CentroCostoNucleo } from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AreaTexto, Campo } from "@/components/formulario";
import { Aviso } from "@/components/sistema";

export function CentroCostoDialog({
  empresaId,
  centro,
  onClose,
  onGuardado,
}: {
  empresaId: string;
  centro: CentroCostoNucleo | null;
  onClose: () => void;
  onGuardado: () => void;
}) {
  const editando = Boolean(centro);
  const [codigo, setCodigo] = useState(centro?.codigo ?? "");
  const [nombre, setNombre] = useState(centro?.nombre ?? "");
  const [descripcion, setDescripcion] = useState(centro?.descripcion ?? "");
  const [activo, setActivo] = useState(centro?.activo ?? true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function guardar() {
    if (!codigo.trim() || !nombre.trim()) {
      setError("Código y nombre son obligatorios.");
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const body = {
        codigo: codigo.trim(),
        nombre: nombre.trim(),
        descripcion: descripcion.trim() || null,
        activo,
        ...(editando ? { version: centro?.version } : {}),
      };
      if (editando) {
        await nucleo.put(`/nucleo/centros-costo/${centro?.id}`, empresaId, body);
        toast.success("Centro de costo actualizado");
      } else {
        await nucleo.post("/nucleo/centros-costo", empresaId, body);
        toast.success("Centro de costo creado");
      }
      onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !guardando) onClose();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {editando ? "Editar centro de costo" : "Nuevo centro de costo"}
          </DialogTitle>
          <DialogDescription>
            Se usa para imputar OC y líneas a una faena, proyecto o sucursal.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Aviso tono="critico" icono={AlertTriangle}>
            {error}
          </Aviso>
        )}

        <div className="space-y-s3">
          <Campo etiqueta="Código" requerido>
            <Input
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              placeholder="CC-NORTE"
            />
          </Campo>
          <Campo etiqueta="Nombre" requerido>
            <Input
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Operaciones norte"
            />
          </Campo>
          <Campo etiqueta="Descripción">
            <AreaTexto
              rows={3}
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
            />
          </Campo>
          <label className="flex items-center gap-s2 text-[15px]">
            <input
              type="checkbox"
              className="size-4 accent-marca"
              checked={activo}
              onChange={(e) => setActivo(e.target.checked)}
            />
            Activo
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={guardando}>
            Cancelar
          </Button>
          <Button onClick={() => void guardar()} disabled={guardando}>
            {guardando ? (
              <>
                <Loader2 className="animate-spin" /> Guardando…
              </>
            ) : (
              "Guardar"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
