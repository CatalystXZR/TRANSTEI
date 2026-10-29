"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { nucleo } from "@/lib/nucleo";
import { toDatetimeLocal } from "@/lib/format";
import type {
  BloqueoNucleo,
  ChoferNucleo,
  RamplaNucleo,
  TipoRecurso,
  TipoReservaNucleo,
  TractoNucleo,
} from "@/types/nucleo";
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
import { AreaTexto, Campo, SelectSimple } from "@/components/formulario";
import { Aviso } from "@/components/sistema";

const TIPOS: { valor: TipoReservaNucleo; etiqueta: string }[] = [
  { valor: "mantenimiento", etiqueta: "Mantención / taller" },
  { valor: "descanso", etiqueta: "Descanso" },
  { valor: "vacaciones", etiqueta: "Vacaciones" },
  { valor: "siniestro", etiqueta: "Siniestro" },
  { valor: "bloqueo_manual", etiqueta: "Bloqueo manual" },
  { valor: "otro", etiqueta: "Otro" },
];

const ENDPOINT: Record<TipoRecurso, string> = {
  tracto: "tractos",
  rampla: "ramplas",
  chofer: "choferes",
};

type Recurso = TractoNucleo | RamplaNucleo | ChoferNucleo;

function etiquetaRecurso(tipo: TipoRecurso, recurso: Recurso): string {
  if (tipo === "chofer") {
    const c = recurso as ChoferNucleo;
    return [c.nombre, c.apellido_paterno].filter(Boolean).join(" ");
  }
  return (recurso as TractoNucleo | RamplaNucleo).patente;
}

function inicioPorDefecto(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(8, 0, 0, 0);
  return toDatetimeLocal(d);
}

function finPorDefecto(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(12, 0, 0, 0);
  return toDatetimeLocal(d);
}

export function BloqueoDialog({
  empresaId,
  recursoTipo,
  bloqueo,
  onClose,
  onGuardado,
}: {
  empresaId: string;
  recursoTipo: TipoRecurso;
  bloqueo: BloqueoNucleo | null;
  onClose: () => void;
  onGuardado: () => void;
}) {
  const editando = Boolean(bloqueo);
  const [recursos, setRecursos] = useState<Recurso[]>([]);
  const [recursoId, setRecursoId] = useState(bloqueo?.recurso_id ?? "");
  const [tipo, setTipo] = useState<TipoReservaNucleo>(
    bloqueo?.tipo_reserva ?? "mantenimiento",
  );
  const [inicio, setInicio] = useState(
    bloqueo ? toDatetimeLocal(bloqueo.inicio) : inicioPorDefecto(),
  );
  const [fin, setFin] = useState(
    bloqueo ? toDatetimeLocal(bloqueo.fin) : finPorDefecto(),
  );
  const [motivo, setMotivo] = useState(bloqueo?.motivo ?? "");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    nucleo
      .get<Recurso[]>(`/nucleo/${ENDPOINT[recursoTipo]}?activo=true`, empresaId)
      .then((data) => {
        if (activo) setRecursos(data);
      })
      .catch(() => {
        if (activo) setError("No se pudieron cargar los recursos.");
      });
    return () => {
      activo = false;
    };
  }, [empresaId, recursoTipo]);

  async function guardar() {
    if (!recursoId) {
      setError("Seleccione el recurso.");
      return;
    }
    if (motivo.trim().length < 5) {
      setError("El motivo debe tener al menos 5 caracteres.");
      return;
    }
    const inicioISO = new Date(inicio).toISOString();
    const finISO = new Date(fin).toISOString();
    if (new Date(finISO) <= new Date(inicioISO)) {
      setError("El fin debe ser posterior al inicio.");
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const body = {
        recurso_tipo: recursoTipo,
        recurso_id: recursoId,
        inicio: inicioISO,
        fin: finISO,
        tipo_reserva: tipo,
        motivo: motivo.trim(),
        ...(editando ? { version: bloqueo?.version } : {}),
      };
      if (editando) {
        await nucleo.put(`/nucleo/bloqueos/${bloqueo?.id}`, empresaId, body);
        toast.success("Bloqueo actualizado");
      } else {
        await nucleo.post("/nucleo/bloqueos", empresaId, body);
        toast.success("Bloqueo creado");
      }
      onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar el bloqueo");
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
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {editando ? "Editar bloqueo" : "Nuevo bloqueo de recurso"}
          </DialogTitle>
          <DialogDescription>
            Mantención, descanso, vacaciones o bloqueo manual. La base impide que
            se solape con un viaje u otro bloqueo.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Aviso tono="critico" icono={AlertTriangle}>
            {error}
          </Aviso>
        )}

        <div className="grid gap-s3 sm:grid-cols-2">
          <Campo etiqueta="Recurso" requerido className="sm:col-span-2">
            <SelectSimple
              valor={recursoId}
              onCambio={setRecursoId}
              placeholder="Seleccione recurso"
              opciones={recursos.map((r) => ({
                valor: r.id,
                etiqueta: etiquetaRecurso(recursoTipo, r),
              }))}
            />
          </Campo>
          <Campo etiqueta="Tipo de bloqueo" requerido>
            <SelectSimple
              valor={tipo}
              onCambio={(v) => setTipo(v as TipoReservaNucleo)}
              opciones={TIPOS}
            />
          </Campo>
          <Campo etiqueta="Inicio" requerido>
            <Input
              type="datetime-local"
              value={inicio}
              onChange={(e) => setInicio(e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Fin" requerido>
            <Input
              type="datetime-local"
              value={fin}
              onChange={(e) => setFin(e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Motivo" requerido className="sm:col-span-2">
            <AreaTexto
              rows={3}
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Ej: mantención preventiva 250.000 km, descanso legal…"
            />
          </Campo>
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
              "Guardar bloqueo"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
