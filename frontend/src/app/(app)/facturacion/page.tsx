"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Download, FileText, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { descargarArchivo } from "@/lib/download";
import { formatCLP, formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface GrupoFletes {
  cliente_id: string;
  cliente_nombre: string;
  dias_pago: number;
  total_neto: string;
  viajes: {
    id: string;
    origen: string;
    destino: string;
    valor_flete_neto: string;
    fecha_inicio: string;
  }[];
}

interface Factura {
  id: string;
  numero_sii: string;
  cliente_nombre: string;
  tipo: "afecta" | "exenta";
  monto_neto: string;
  iva: string;
  total: string;
  fecha_emision: string;
  fecha_vencimiento: string | null;
  fecha_pago: string | null;
  estado: "pendiente" | "pagada" | "anulada";
  notas: string | null;
  viajes: { id: string; origen: string; destino: string; valor_flete_neto: string }[];
}

const ESTADO_FACTURA_COLOR: Record<string, string> = {
  pendiente: "bg-yellow-500 text-black",
  pagada: "bg-green-600 text-white",
  anulada: "bg-red-100 text-red-700",
};

export default function FacturacionPage() {
  const { usuario } = useAuth();
  const [pestana, setPestana] = useState<"fletes" | "facturas">("fletes");
  const [grupos, setGrupos] = useState<GrupoFletes[]>([]);
  const [facturas, setFacturas] = useState<Factura[]>([]);
  const [cargando, setCargando] = useState(true);

  const [dialogo, setDialogo] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [form, setForm] = useState({
    numero_sii: "",
    tipo: "afecta",
    fecha_emision: new Date().toISOString().slice(0, 10),
    cliente_id: "",
    viaje_ids: [] as string[],
  });

  const puedeEscribir = usuario && ["admin", "operacion", "contabilidad"].includes(usuario.rol);

  function recargar() {
    Promise.all([
      api.get<GrupoFletes[]>("/facturacion/fletes-por-facturar"),
      api.get<Factura[]>("/facturas"),
    ])
      .then(([g, f]) => {
        setGrupos(g ?? []);
        setFacturas(f ?? []);
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar"))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    Promise.all([
      api.get<GrupoFletes[]>("/facturacion/fletes-por-facturar"),
      api.get<Factura[]>("/facturas"),
    ])
      .then(([g, f]) => {
        if (!activo) return;
        setGrupos(g ?? []);
        setFacturas(f ?? []);
      })
      .catch((e) => {
        if (activo) toast.error(e instanceof Error ? e.message : "Error al cargar");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  function abrirFacturar(grupo: GrupoFletes) {
    setForm({
      numero_sii: "",
      tipo: "afecta",
      fecha_emision: new Date().toISOString().slice(0, 10),
      cliente_id: grupo.cliente_id,
      viaje_ids: grupo.viajes.map((v) => v.id),
    });
    setDialogo(true);
  }

  async function crearFactura() {
    if (!form.numero_sii.trim()) {
      toast.error("Ingrese el número de factura emitido en el SII");
      return;
    }
    if (form.viaje_ids.length === 0) {
      toast.error("Seleccione al menos un viaje");
      return;
    }
    setGuardando(true);
    try {
      await api.post("/facturas", {
        numero_sii: form.numero_sii.trim(),
        cliente_id: form.cliente_id,
        tipo: form.tipo,
        fecha_emision: form.fecha_emision,
        viaje_ids: form.viaje_ids,
      });
      toast.success("Factura asociada correctamente");
      setDialogo(false);
      setPestana("facturas");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al crear factura");
    } finally {
      setGuardando(false);
    }
  }

  async function marcarPagada(factura: Factura) {
    try {
      await api.patch(`/facturas/${factura.id}/estado`, { estado: "pagada" });
      toast.success("Factura marcada como pagada");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function anular(factura: Factura) {
    if (!confirm(`¿Anular la factura ${factura.numero_sii}? Los viajes volverán a estar finalizados.`))
      return;
    try {
      await api.patch(`/facturas/${factura.id}/estado`, { estado: "anulada" });
      toast.success("Factura anulada");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  function toggleViaje(id: string) {
    setForm((f) => ({
      ...f,
      viaje_ids: f.viaje_ids.includes(id)
        ? f.viaje_ids.filter((x) => x !== id)
        : [...f.viaje_ids, id],
    }));
  }

  const totalSeleccionado = form.viaje_ids
    .reduce((acc, id) => {
      const v = grupos
        .flatMap((g) => g.viajes)
        .find((x) => x.id === id);
      return acc + (v ? Number(v.valor_flete_neto) : 0);
    }, 0);
  const ivaEstimado = form.tipo === "afecta" ? Math.round(totalSeleccionado * 0.19) : 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-[#2A237A]">Facturación</h1>
        <Button
          variant="outline"
          onClick={() =>
            descargarArchivo("/export/facturas", "facturas.csv").catch((e) =>
              toast.error(e instanceof Error ? e.message : "Error al exportar"),
            )
          }
          className="text-base"
        >
          <Download className="h-5 w-5" />
          Exportar Facturas
        </Button>
      </div>

      <div className="flex rounded-lg border bg-white p-1 sm:w-fit">
        <button
          onClick={() => setPestana("fletes")}
          className={`rounded-md px-4 py-2 text-base font-medium ${
            pestana === "fletes" ? "bg-[#2A237A] text-white" : "text-gray-600 hover:bg-gray-100"
          }`}
        >
          Fletes por Facturar ({grupos.length})
        </button>
        <button
          onClick={() => setPestana("facturas")}
          className={`rounded-md px-4 py-2 text-base font-medium ${
            pestana === "facturas" ? "bg-[#2A237A] text-white" : "text-gray-600 hover:bg-gray-100"
          }`}
        >
          Facturas ({facturas.length})
        </button>
      </div>

      {pestana === "fletes" ? (
        <div className="space-y-4">
          {cargando ? (
            <p className="py-8 text-center text-gray-500">Cargando…</p>
          ) : grupos.length === 0 ? (
            <div className="rounded-lg border bg-white p-8 text-center">
              <p className="text-lg text-gray-500">No hay fletes pendientes de facturar ✓</p>
            </div>
          ) : (
            grupos.map((g) => (
              <div key={g.cliente_id} className="rounded-lg border bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-lg font-bold text-[#2A237A]">{g.cliente_nombre}</p>
                    <p className="text-sm text-gray-500">
                      {g.viajes.length} viaje(s) · pago a {g.dias_pago} días
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    <p className="text-xl font-bold text-green-700">{formatCLP(g.total_neto)}</p>
                    {puedeEscribir && (
                      <Button
                        onClick={() => abrirFacturar(g)}
                        className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
                      >
                        <FileText className="h-5 w-5" />
                        Asociar Factura
                      </Button>
                    )}
                  </div>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-base">Fecha</TableHead>
                      <TableHead className="text-base">Ruta</TableHead>
                      <TableHead className="text-base">Valor</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {g.viajes.map((v) => (
                      <TableRow key={v.id}>
                        <TableCell className="text-base">{formatFecha(v.fecha_inicio)}</TableCell>
                        <TableCell className="text-base">
                          {v.origen} → {v.destino}
                        </TableCell>
                        <TableCell className="text-base">{formatCLP(v.valor_flete_neto)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-white">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-base">N° SII</TableHead>
                <TableHead className="text-base">Cliente</TableHead>
                <TableHead className="text-base">Neto</TableHead>
                <TableHead className="text-base">IVA</TableHead>
                <TableHead className="text-base">Total</TableHead>
                <TableHead className="text-base">Emisión</TableHead>
                <TableHead className="text-base">Vencimiento</TableHead>
                <TableHead className="text-base">Estado</TableHead>
                {puedeEscribir && <TableHead className="w-40 text-base">Acciones</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {facturas.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="py-8 text-center text-gray-500">
                    No hay facturas registradas
                  </TableCell>
                </TableRow>
              ) : (
                facturas.map((f) => (
                  <TableRow key={f.id}>
                    <TableCell className="text-base font-semibold">{f.numero_sii}</TableCell>
                    <TableCell className="text-base">{f.cliente_nombre}</TableCell>
                    <TableCell className="text-base">{formatCLP(f.monto_neto)}</TableCell>
                    <TableCell className="text-base">{formatCLP(f.iva)}</TableCell>
                    <TableCell className="text-base font-semibold">{formatCLP(f.total)}</TableCell>
                    <TableCell className="text-base">{formatFecha(f.fecha_emision)}</TableCell>
                    <TableCell className="text-base">{formatFecha(f.fecha_vencimiento)}</TableCell>
                    <TableCell>
                      <Badge className={`${ESTADO_FACTURA_COLOR[f.estado]} text-sm`}>
                        {f.estado === "pendiente"
                          ? "Pendiente"
                          : f.estado === "pagada"
                            ? "Pagada"
                            : "Anulada"}
                      </Badge>
                    </TableCell>
                    {puedeEscribir && (
                      <TableCell>
                        <div className="flex gap-2">
                          {f.estado === "pendiente" && (
                            <>
                              <Button
                                size="sm"
                                className="bg-green-600 text-white hover:bg-green-700"
                                onClick={() => marcarPagada(f)}
                              >
                                <CheckCircle2 className="h-4 w-4" />
                                Pagar
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="border-red-200 text-red-600 hover:bg-red-50"
                                onClick={() => anular(f)}
                              >
                                <XCircle className="h-4 w-4" />
                              </Button>
                            </>
                          )}
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={dialogo} onOpenChange={setDialogo}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl">Asociar Factura SII</DialogTitle>
            <DialogDescription className="text-base">
              El sistema no emite facturas: registre aquí la factura ya emitida en el SII.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Número Factura SII *</Label>
                <Input
                  value={form.numero_sii}
                  onChange={(e) => setForm({ ...form, numero_sii: e.target.value })}
                  className="text-base"
                  placeholder="123456"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-base">Tipo</Label>
                <Select value={form.tipo} onValueChange={(v) => setForm({ ...form, tipo: v ?? "afecta" })}>
                  <SelectTrigger className="text-base">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="afecta" className="text-base">
                      Afecta (IVA 19%)
                    </SelectItem>
                    <SelectItem value="exenta" className="text-base">
                      Exenta
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Fecha Emisión</Label>
              <Input
                type="date"
                value={form.fecha_emision}
                onChange={(e) => setForm({ ...form, fecha_emision: e.target.value })}
                className="text-base"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base">Viajes a facturar</Label>
              <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border p-2">
                {grupos
                  .find((g) => g.cliente_id === form.cliente_id)
                  ?.viajes.map((v) => (
                    <label
                      key={v.id}
                      className="flex items-center justify-between rounded-md border p-2 text-base"
                    >
                      <span>
                        {v.origen} → {v.destino} · {formatCLP(v.valor_flete_neto)}
                      </span>
                      <input
                        type="checkbox"
                        checked={form.viaje_ids.includes(v.id)}
                        onChange={() => toggleViaje(v.id)}
                        className="h-5 w-5 accent-[#2A237A]"
                      />
                    </label>
                  ))}
              </div>
            </div>
            <div className="rounded-lg bg-gray-50 p-4 text-base">
              <p>
                Neto: <strong>{formatCLP(totalSeleccionado)}</strong>
              </p>
              <p>
                IVA ({form.tipo === "afecta" ? "19%" : "exento"}):{" "}
                <strong>{formatCLP(ivaEstimado)}</strong>
              </p>
              <p className="text-lg">
                Total:{" "}
                <strong className="text-[#2A237A]">
                  {formatCLP(totalSeleccionado + ivaEstimado)}
                </strong>
              </p>
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogo(false)} className="text-base">
              Cancelar
            </Button>
            <Button
              onClick={crearFactura}
              disabled={guardando}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              {guardando ? "Guardando…" : "Asociar Factura"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
