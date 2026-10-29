"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { nucleo } from "@/lib/nucleo";
import { formatCLP, formatFechaHora } from "@/lib/format";
import type { FacturaNucleo, ViajeFacturableNucleo } from "@/types/nucleo";
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
import { Aviso, StatusBadge } from "@/components/sistema";

function hoyISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function masDiasISO(dias: number): string {
  return new Date(Date.now() + dias * 86400000).toISOString().slice(0, 10);
}

export function NuevaFacturaDialog({
  empresaId,
  onClose,
  onCreada,
}: {
  empresaId: string;
  onClose: () => void;
  onCreada: (factura: FacturaNucleo) => void;
}) {
  const [viajes, setViajes] = useState<ViajeFacturableNucleo[]>([]);
  const [clienteId, setClienteId] = useState("");
  const [seleccion, setSeleccion] = useState<string[]>([]);
  const [fechaEmision, setFechaEmision] = useState(hoyISO());
  const [fechaVencimiento, setFechaVencimiento] = useState(masDiasISO(30));
  const [tasaIva, setTasaIva] = useState("19");
  const [observaciones, setObservaciones] = useState("");
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    nucleo
      .get<ViajeFacturableNucleo[]>("/nucleo/cobranza/viajes-facturables", empresaId)
      .then((data) => {
        if (!activo) return;
        setViajes(data);
        const primero = data[0];
        if (primero) setClienteId(primero.cliente_id);
      })
      .catch((e) => {
        if (!activo) return;
        setError(e instanceof Error ? e.message : "No se pudieron cargar los viajes");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [empresaId]);

  const clientes = useMemo(() => {
    const mapa = new Map<string, string>();
    for (const viaje of viajes) mapa.set(viaje.cliente_id, viaje.cliente_nombre);
    return [...mapa.entries()].map(([valor, etiqueta]) => ({ valor, etiqueta }));
  }, [viajes]);

  const disponibles = viajes.filter((v) => v.cliente_id === clienteId);
  const seleccionados = disponibles.filter((v) => seleccion.includes(v.viaje_id));
  const neto = seleccionados.reduce((acc, v) => acc + Number(v.monto), 0);
  const iva = neto * (Number(tasaIva) / 100);
  const total = neto + iva;
  const ocs = new Set(seleccionados.map((v) => v.orden_compra_id ?? "sin"));

  function alternar(viajeId: string) {
    setSeleccion((actual) =>
      actual.includes(viajeId)
        ? actual.filter((id) => id !== viajeId)
        : [...actual, viajeId],
    );
  }

  async function crear() {
    if (seleccion.length === 0) {
      setError("Seleccione al menos un viaje cerrado con POD.");
      return;
    }
    if (ocs.size !== 1) {
      setError("Todos los viajes seleccionados deben pertenecer a la misma OC.");
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const factura = await nucleo.post<FacturaNucleo>(
        "/nucleo/cobranza/facturas",
        empresaId,
        {
          cliente_id: clienteId,
          orden_compra_id: seleccionados[0]?.orden_compra_id ?? null,
          viaje_ids: seleccion,
          fecha_emision: fechaEmision,
          fecha_vencimiento: fechaVencimiento,
          tasa_iva: Number(tasaIva) / 100,
          observaciones: observaciones.trim() || null,
        },
      );
      toast.success(`Factura ${factura.numero_factura} emitida`);
      onCreada(factura);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo emitir la factura");
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
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Nueva factura del núcleo</DialogTitle>
          <DialogDescription>
            Agrupa viajes cerrados con POD y OC. El folio se simula en PostgreSQL;
            no se emite DTE real en el piloto.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>
        )}

        <div className="grid gap-s3 sm:grid-cols-4">
          <Campo etiqueta="Cliente" requerido className="sm:col-span-2">
            <SelectSimple
              valor={clienteId}
              onCambio={(v) => {
                setClienteId(v);
                setSeleccion([]);
              }}
              placeholder="Seleccione cliente"
              opciones={clientes}
            />
          </Campo>
          <Campo etiqueta="Emisión" requerido>
            <Input type="date" value={fechaEmision} onChange={(e) => setFechaEmision(e.target.value)} />
          </Campo>
          <Campo etiqueta="Vencimiento" requerido>
            <Input type="date" value={fechaVencimiento} onChange={(e) => setFechaVencimiento(e.target.value)} />
          </Campo>
          <Campo etiqueta="IVA (%)">
            <Input type="number" min={0} max={100} value={tasaIva} onChange={(e) => setTasaIva(e.target.value)} />
          </Campo>
          <Campo etiqueta="Observaciones" className="sm:col-span-3">
            <Input value={observaciones} onChange={(e) => setObservaciones(e.target.value)} />
          </Campo>
        </div>

        <div className="overflow-hidden rounded-xl border border-borde">
          <div className="flex items-center justify-between border-b border-borde bg-superficie-hundida/50 px-s3 py-s2 text-[14px] font-medium">
            <span>Viajes cerrados disponibles</span>
            <span className="text-tinta-3">{disponibles.length} viaje(s)</span>
          </div>
          {cargando ? (
            <div className="flex items-center gap-2 p-s4 text-tinta-3">
              <Loader2 className="animate-spin" /> Cargando viajes…
            </div>
          ) : disponibles.length === 0 ? (
            <p className="p-s4 text-[14px] text-tinta-3">
              No hay viajes cerrados con POD y OC para este cliente.
            </p>
          ) : (
            <div className="max-h-[300px] divide-y divide-borde overflow-y-auto">
              {disponibles.map((viaje) => (
                <div
                  key={viaje.viaje_id}
                  role="checkbox"
                  aria-checked={seleccion.includes(viaje.viaje_id)}
                  tabIndex={0}
                  onClick={() => alternar(viaje.viaje_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      alternar(viaje.viaje_id);
                    }
                  }}
                  className="flex cursor-pointer items-center gap-s3 p-s3 hover:bg-superficie-hundida/40"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-marca"
                    checked={seleccion.includes(viaje.viaje_id)}
                    onChange={() => alternar(viaje.viaje_id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="font-mono text-[13px] font-semibold">{viaje.numero_viaje}</p>
                    <p className="text-[13px] text-tinta-3">
                      {viaje.oc_numero ?? "Sin OC"} · {formatFechaHora(viaje.fecha_inicio)}
                    </p>
                  </div>
                  <StatusBadge tono={viaje.tiene_pod ? "ok" : "critico"}>
                    {viaje.tiene_pod ? "POD OK" : "Sin POD"}
                  </StatusBadge>
                  <p className="w-28 text-right text-[14px] font-semibold">{formatCLP(viaje.monto)}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-s5 rounded-xl border border-borde bg-superficie-hundida/40 p-s3 text-[14px]">
          <span>Neto: <strong>{formatCLP(neto)}</strong></span>
          <span>IVA: <strong>{formatCLP(iva)}</strong></span>
          <span>Total: <strong>{formatCLP(total)}</strong></span>
          <StatusBadge tono={ocs.size > 1 ? "critico" : "info"}>
            {ocs.size > 1 ? "Mezcla de OC" : `${seleccion.length} viaje(s)`}
          </StatusBadge>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={guardando}>Cancelar</Button>
          <Button onClick={() => void crear()} disabled={guardando || seleccion.length === 0}>
            {guardando ? <><Loader2 className="animate-spin" /> Emitiendo…</> : "Emitir factura"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
