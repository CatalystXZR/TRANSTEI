"use client";

import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { nucleo, NucleoError } from "@/lib/nucleo";
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
import { Campo, SelectSimple } from "@/components/formulario";
import { Aviso } from "@/components/sistema";
import {
  CAMPOS,
  ETIQUETA_MAESTRO,
  bodyDesdeForm,
  formDesdeRegistro,
  formInicial,
  type TipoMaestro,
} from "@/components/maestros/config";

export function MaestroDialog({
  tipo,
  empresaId,
  registro,
  onClose,
  onGuardado,
}: {
  tipo: TipoMaestro;
  empresaId: string;
  registro?: Record<string, unknown> | null;
  onClose: () => void;
  onGuardado: () => void;
}) {
  const editando = Boolean(registro?.id);
  const [form, setForm] = useState<Record<string, string | boolean>>(
    registro ? formDesdeRegistro(tipo, registro) : formInicial(tipo),
  );
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errores, setErrores] = useState<string[]>([]);

  const campos = CAMPOS[tipo];
  const faltan = campos.filter(
    (c) => c.required && String(form[c.key] ?? "").trim() === "",
  );
  const puedeGuardar = faltan.length === 0 && !guardando;

  async function guardar() {
    if (!puedeGuardar) {
      setError(`Complete los campos obligatorios: ${faltan.map((c) => c.label).join(", ")}`);
      return;
    }
    setGuardando(true);
    setError(null);
    setErrores([]);
    try {
      const body = bodyDesdeForm(tipo, form);
      if (editando) {
        await nucleo.put(`/nucleo/${tipo}/${registro?.id}`, empresaId, body);
        toast.success("Registro actualizado");
      } else {
        await nucleo.post(`/nucleo/${tipo}`, empresaId, body);
        toast.success("Registro creado");
      }
      onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
      if (e instanceof NucleoError) setErrores(e.errores.map((i) => i.mensaje));
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
      <DialogContent
        showCloseButton={!guardando}
        className="max-h-[92vh] overflow-y-auto sm:max-w-3xl"
      >
        <DialogHeader>
          <DialogTitle>
            {editando ? "Editar" : "Nuevo"} {ETIQUETA_MAESTRO[tipo].slice(0, -1)}
          </DialogTitle>
          <DialogDescription>
            {editando
              ? "Los cambios quedan auditados y protegidos por versión."
              : "Complete los datos maestros. Los campos con * son obligatorios."}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Aviso tono="critico" icono={AlertTriangle}>
            {error}
          </Aviso>
        )}
        {errores.length > 0 && (
          <ul className="list-inside list-disc space-y-s1 rounded-xl border border-critico/20 bg-critico-tenue p-s3 text-[14px] text-critico">
            {errores.map((e, idx) => (
              <li key={idx}>{e}</li>
            ))}
          </ul>
        )}

        <div className="grid gap-s3 sm:grid-cols-2">
          {campos.map((campo) => {
            if (campo.type === "checkbox") {
              return (
                <label
                  key={campo.key}
                  className="flex items-center gap-s2 self-end rounded-lg border border-borde px-s3 py-2.5 text-[15px]"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-marca"
                    checked={Boolean(form[campo.key])}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, [campo.key]: e.target.checked }))
                    }
                  />
                  {campo.label}
                </label>
              );
            }
            return (
              <Campo
                key={campo.key}
                etiqueta={campo.label}
                htmlFor={`maestro-${campo.key}`}
                requerido={campo.required}
                ayuda={campo.help}
                className={campo.full ? "sm:col-span-2" : undefined}
              >
                {campo.type === "select" ? (
                  <SelectSimple
                    id={`maestro-${campo.key}`}
                    valor={String(form[campo.key] ?? "")}
                    onCambio={(v) => setForm((f) => ({ ...f, [campo.key]: v }))}
                    opciones={campo.options ?? []}
                  />
                ) : (
                  <Input
                    id={`maestro-${campo.key}`}
                    type={
                      campo.type === "number" || campo.type === "percent"
                        ? "number"
                        : campo.type === "date"
                          ? "date"
                          : "text"
                    }
                    step={campo.step}
                    min={campo.min}
                    value={String(form[campo.key] ?? "")}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, [campo.key]: e.target.value }))
                    }
                    placeholder={campo.placeholder}
                  />
                )}
              </Campo>
            );
          })}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={guardando}>
            Cancelar
          </Button>
          <Button onClick={() => void guardar()} disabled={!puedeGuardar}>
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
