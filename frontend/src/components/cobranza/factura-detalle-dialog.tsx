"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Banknote, FileMinus, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { nucleo } from "@/lib/nucleo";
import { formatCLP, formatFecha } from "@/lib/format";
import type { FacturaNucleo } from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AreaTexto, Campo, SelectSimple } from "@/components/formulario";
import { Aviso, Panel, StatusBadge, type Tono } from "@/components/sistema";

function fechaISO(dias = 0): string {
  const fecha = new Date();
  fecha.setDate(fecha.getDate() + dias);
  return fecha.toISOString().slice(0, 10);
}

function tonoEstado(estado: string): Tono {
  if (estado === "pagada") return "ok";
  if (estado === "parcial") return "atencion";
  if (estado === "vencida" || estado === "anulada") return "critico";
  return "info";
}

export function FacturaDetalleDialog({
  empresaId,
  facturaId,
  puedeEscribir,
  onClose,
  onCambio,
}: {
  empresaId: string;
  facturaId: string;
  puedeEscribir: boolean;
  onClose: () => void;
  onCambio: () => void;
}) {
  const [factura, setFactura] = useState<FacturaNucleo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accion, setAccion] = useState<"pago" | "nota" | "promesa" | null>(null);
  const [form, setForm] = useState({
    monto: "",
    fecha: fechaISO(),
    metodo: "transferencia",
    referencia: "",
    motivo: "",
    fecha_prometida: fechaISO(7),
    notas: "",
  });

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const data = await nucleo.get<FacturaNucleo>(
        `/nucleo/cobranza/facturas/${facturaId}`,
        empresaId,
      );
      setFactura(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la factura");
    } finally {
      setCargando(false);
    }
  }, [empresaId, facturaId]);

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  async function enviar() {
    if (!factura) return;
    setProcesando(true);
    setError(null);
    try {
      if (accion === "pago") {
        await nucleo.post(`/nucleo/cobranza/facturas/${factura.id}/pagos`, empresaId, {
          fecha: form.fecha,
          monto: Number(form.monto),
          metodo: form.metodo,
          referencia: form.referencia.trim() || null,
        });
        toast.success("Pago registrado");
      } else if (accion === "nota") {
        await nucleo.post(
          `/nucleo/cobranza/facturas/${factura.id}/notas-credito`,
          empresaId,
          {
            fecha: form.fecha,
            monto: Number(form.monto),
            motivo: form.motivo.trim(),
          },
        );
        toast.success("Nota de crédito aplicada");
      } else if (accion === "promesa") {
        await nucleo.post(
          `/nucleo/cobranza/facturas/${factura.id}/promesas`,
          empresaId,
          {
            fecha_prometida: form.fecha_prometida,
            monto: Number(form.monto),
            notas: form.notas.trim() || null,
          },
        );
        toast.success("Promesa de pago registrada");
      }
      setAccion(null);
      setForm((f) => ({ ...f, monto: "", referencia: "", motivo: "", notas: "" }));
      await cargar();
      onCambio();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo completar la operación");
    } finally {
      setProcesando(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-s3">
            Factura {factura?.numero_factura ?? "…"}
            {factura && <StatusBadge tono={tonoEstado(factura.estado)}>{factura.estado}</StatusBadge>}
          </DialogTitle>
          <DialogDescription>
            {factura
              ? `${factura.cliente_nombre} · ${factura.oc_numero ?? "sin OC"} · vence ${formatFecha(factura.fecha_vencimiento)}`
              : "Cargando factura…"}
          </DialogDescription>
        </DialogHeader>

        {error && <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>}

        {cargando && !factura ? (
          <div className="flex items-center gap-2 py-s5 text-tinta-3">
            <Loader2 className="animate-spin" /> Cargando factura…
          </div>
        ) : factura ? (
          <div className="space-y-s4">
            <div className="grid gap-s3 rounded-xl border border-borde bg-superficie-hundida/50 p-s4 sm:grid-cols-4">
              <div>
                <p className="rotulo">Total</p>
                <p className="cifra text-[22px] font-semibold">{formatCLP(factura.total)}</p>
                <p className="text-[13px] text-tinta-3">Neto {formatCLP(factura.neto)} + IVA {formatCLP(factura.iva)}</p>
              </div>
              <div>
                <p className="rotulo">Pagado</p>
                <p className="cifra text-[22px] font-semibold">{formatCLP(factura.pagado)}</p>
                <p className="text-[13px] text-tinta-3">{factura.pagos.length} pago(s)</p>
              </div>
              <div>
                <p className="rotulo">Notas de crédito</p>
                <p className="cifra text-[22px] font-semibold">{formatCLP(factura.notas_credito)}</p>
                <p className="text-[13px] text-tinta-3">{factura.notas.length} nota(s)</p>
              </div>
              <div>
                <p className="rotulo">Saldo</p>
                <p className={`cifra text-[22px] font-semibold ${Number(factura.saldo) <= 0 ? "text-ok" : "text-critico"}`}>
                  {formatCLP(factura.saldo)}
                </p>
                <p className="text-[13px] text-tinta-3">
                  {factura.dias_atraso > 0 ? `${factura.dias_atraso} día(s) de atraso` : "Al día"}
                </p>
              </div>
            </div>

            {puedeEscribir && factura.estado !== "pagada" && (
              <div className="flex flex-wrap gap-s2">
                <Button size="sm" onClick={() => setAccion("pago")}>
                  <Banknote /> Registrar pago
                </Button>
                <Button size="sm" variant="outline" onClick={() => setAccion("nota")}>
                  <FileMinus /> Nota de crédito
                </Button>
                <Button size="sm" variant="outline" onClick={() => setAccion("promesa")}>
                  Promesa de pago
                </Button>
              </div>
            )}

            {accion && (
              <Panel
                titulo={
                  accion === "pago"
                    ? "Registrar pago"
                    : accion === "nota"
                      ? "Nota de crédito"
                      : "Promesa de pago"
                }
                acciones={
                  <Button size="sm" variant="ghost" onClick={() => setAccion(null)}>
                    Cerrar
                  </Button>
                }
              >
                <div className="grid gap-s3 p-s4 sm:grid-cols-3">
                  <Campo etiqueta="Monto" requerido>
                    <Input
                      type="number"
                      min={0}
                      step="0.01"
                      value={form.monto}
                      onChange={(e) => setForm((f) => ({ ...f, monto: e.target.value }))}
                    />
                  </Campo>
                  <Campo etiqueta={accion === "promesa" ? "Fecha prometida" : "Fecha"}>
                    <Input
                      type="date"
                      value={accion === "promesa" ? form.fecha_prometida : form.fecha}
                      onChange={(e) =>
                        setForm((f) =>
                          accion === "promesa"
                            ? { ...f, fecha_prometida: e.target.value }
                            : { ...f, fecha: e.target.value },
                        )
                      }
                    />
                  </Campo>
                  {accion === "pago" && (
                    <Campo etiqueta="Método">
                      <SelectSimple
                        valor={form.metodo}
                        onCambio={(v) => setForm((f) => ({ ...f, metodo: v }))}
                        opciones={[
                          { valor: "transferencia", etiqueta: "Transferencia" },
                          { valor: "cheque", etiqueta: "Cheque" },
                          { valor: "efectivo", etiqueta: "Efectivo" },
                          { valor: "tarjeta", etiqueta: "Tarjeta" },
                          { valor: "condonacion", etiqueta: "Condonación" },
                          { valor: "otro", etiqueta: "Otro" },
                        ]}
                      />
                    </Campo>
                  )}
                  {accion === "pago" && (
                    <Campo etiqueta="Referencia" className="sm:col-span-2">
                      <Input
                        value={form.referencia}
                        onChange={(e) => setForm((f) => ({ ...f, referencia: e.target.value }))}
                      />
                    </Campo>
                  )}
                  {accion === "nota" && (
                    <Campo etiqueta="Motivo" className="sm:col-span-2" requerido>
                      <Input
                        value={form.motivo}
                        onChange={(e) => setForm((f) => ({ ...f, motivo: e.target.value }))}
                      />
                    </Campo>
                  )}
                  {accion === "promesa" && (
                    <Campo etiqueta="Notas" className="sm:col-span-2">
                      <AreaTexto
                        rows={2}
                        value={form.notas}
                        onChange={(e) => setForm((f) => ({ ...f, notas: e.target.value }))}
                      />
                    </Campo>
                  )}
                  <div className="flex items-end">
                    <Button onClick={() => void enviar()} disabled={procesando || Number(form.monto) <= 0}>
                      {procesando ? <Loader2 className="animate-spin" /> : "Guardar"}
                    </Button>
                  </div>
                </div>
              </Panel>
            )}

            <Panel titulo="Viajes facturados">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Viaje</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead className="text-right">Monto</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {factura.viajes.map((viaje) => (
                      <TableRow key={viaje.viaje_id}>
                        <TableCell className="font-mono text-[13px]">{viaje.numero_viaje}</TableCell>
                        <TableCell>{viaje.estado.replaceAll("_", " ")}</TableCell>
                        <TableCell className="text-right">{formatCLP(viaje.monto)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </Panel>

            <div className="grid gap-s4 xl:grid-cols-3">
              <Panel titulo={`Pagos (${factura.pagos.length})`}>
                <div className="divide-y divide-borde">
                  {factura.pagos.length === 0 ? (
                    <p className="p-s4 text-[14px] text-tinta-3">Sin pagos.</p>
                  ) : (
                    factura.pagos.map((pago) => (
                      <div key={pago.id} className="p-s3 text-[14px]">
                        <p className="flex justify-between font-medium">
                          <span>{formatFecha(pago.fecha)} · {pago.metodo}</span>
                          <span className="cifra">{formatCLP(pago.monto)}</span>
                        </p>
                        {pago.referencia && <p className="text-[13px] text-tinta-3">{pago.referencia}</p>}
                      </div>
                    ))
                  )}
                </div>
              </Panel>
              <Panel titulo={`Notas de crédito (${factura.notas.length})`}>
                <div className="divide-y divide-borde">
                  {factura.notas.length === 0 ? (
                    <p className="p-s4 text-[14px] text-tinta-3">Sin notas.</p>
                  ) : (
                    factura.notas.map((nota) => (
                      <div key={nota.id} className="p-s3 text-[14px]">
                        <p className="flex justify-between font-medium">
                          <span>{nota.numero}</span>
                          <span className="cifra">{formatCLP(nota.monto)}</span>
                        </p>
                        <p className="text-[13px] text-tinta-3">{nota.motivo}</p>
                      </div>
                    ))
                  )}
                </div>
              </Panel>
              <Panel titulo={`Promesas (${factura.promesas.length})`}>
                <div className="divide-y divide-borde">
                  {factura.promesas.length === 0 ? (
                    <p className="p-s4 text-[14px] text-tinta-3">Sin promesas.</p>
                  ) : (
                    factura.promesas.map((promesa) => (
                      <div key={promesa.id} className="p-s3 text-[14px]">
                        <p className="flex justify-between font-medium">
                          <span>{formatFecha(promesa.fecha_prometida)}</span>
                          <span className="cifra">{formatCLP(promesa.monto)}</span>
                        </p>
                        <p className="text-[13px] text-tinta-3">{promesa.estado}</p>
                      </div>
                    ))
                  )}
                </div>
              </Panel>
            </div>

            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={() => void cargar()}>
                <RefreshCw className={cargando ? "animate-spin" : undefined} /> Actualizar
              </Button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
