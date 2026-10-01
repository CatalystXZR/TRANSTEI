"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Download, FileCheck2, FileText, Inbox, XCircle } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { api } from "@/lib/api";
import { descargarArchivo } from "@/lib/download";
import { formatCLP, formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  EstadoVacio,
  FilaVacia,
  FilasCargando,
  PageHeader,
  Panel,
  Segmentado,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import { Campo, SelectSimple } from "@/components/formulario";

interface GrupoFletes {
  cliente_id: string;
  cliente_nombre: string;
  dias_pago: number;
  total_neto: string;
  viajes: { id: string; origen: string; destino: string; valor_flete_neto: string; fecha_inicio: string }[];
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

const ESTADO_FACTURA: Record<Factura["estado"], { tono: Tono; label: string }> = {
  pendiente: { tono: "atencion", label: "Pendiente" },
  pagada: { tono: "ok", label: "Pagada" },
  anulada: { tono: "neutro", label: "Anulada" },
};

function hoyISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function FacturacionPage() {
  const { usuario } = useAuth();
  const [pestana, setPestana] = useState<"fletes" | "facturas">("fletes");
  const [grupos, setGrupos] = useState<GrupoFletes[]>([]);
  const [facturas, setFacturas] = useState<Factura[]>([]);
  const [tasaIva, setTasaIva] = useState(19);
  const [cargando, setCargando] = useState(true);

  const [dialogo, setDialogo] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [intento, setIntento] = useState(false);
  const [form, setForm] = useState({
    numero_sii: "",
    tipo: "afecta" as "afecta" | "exenta",
    fecha_emision: "",
    cliente_id: "",
    viaje_ids: [] as string[],
  });
  const [anulando, setAnulando] = useState<Factura | null>(null);

  const puedeEscribir = !!usuario && ["admin", "operacion", "contabilidad"].includes(usuario.rol);

  function recargar() {
    Promise.all([api.get<GrupoFletes[]>("/facturacion/fletes-por-facturar"), api.get<Factura[]>("/facturas")])
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
      api.get<Record<string, string>>("/configuracion").catch(() => null),
    ])
      .then(([g, f, c]) => {
        if (!activo) return;
        setGrupos(g ?? []);
        setFacturas(f ?? []);
        const t = Number(c?.iva_porcentaje);
        if (!Number.isNaN(t) && t >= 0) setTasaIva(t);
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

  const grupoActual = grupos.find((g) => g.cliente_id === form.cliente_id);
  const totalPorFacturar = useMemo(() => grupos.reduce((a, g) => a + Number(g.total_neto), 0), [grupos]);

  function abrirFacturar(grupo: GrupoFletes) {
    setForm({ numero_sii: "", tipo: "afecta", fecha_emision: hoyISO(), cliente_id: grupo.cliente_id, viaje_ids: grupo.viajes.map((v) => v.id) });
    setIntento(false);
    setDialogo(true);
  }

  async function crearFactura() {
    setIntento(true);
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
        fecha_emision: form.fecha_emision || hoyISO(),
        viaje_ids: form.viaje_ids,
      });
      toast.success("Factura registrada");
      setDialogo(false);
      setPestana("facturas");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al registrar la factura");
    } finally {
      setGuardando(false);
    }
  }

  async function marcarPagada(f: Factura) {
    try {
      await api.patch(`/facturas/${f.id}/estado`, { estado: "pagada" });
      toast.success(`Factura ${f.numero_sii} marcada como pagada`);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function confirmarAnular() {
    if (!anulando) return;
    try {
      await api.patch(`/facturas/${anulando.id}/estado`, { estado: "anulada" });
      toast.success("Factura anulada");
      setAnulando(null);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  function toggleViaje(id: string) {
    setForm((f) => ({ ...f, viaje_ids: f.viaje_ids.includes(id) ? f.viaje_ids.filter((x) => x !== id) : [...f.viaje_ids, id] }));
  }

  const neto = form.viaje_ids.reduce((acc, id) => {
    const v = grupoActual?.viajes.find((x) => x.id === id);
    return acc + (v ? Number(v.valor_flete_neto) : 0);
  }, 0);
  const iva = form.tipo === "afecta" ? Math.round((neto * tasaIva) / 100) : 0;

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Finanzas"
        titulo="Facturación"
        descripcion="Asocie los viajes finalizados a la factura emitida en el SII. El sistema calcula neto, IVA y vencimiento."
        acciones={
          <Button
            variant="outline"
            onClick={() =>
              descargarArchivo("/export/facturas", "facturas.csv").catch((e) => toast.error(e instanceof Error ? e.message : "Error al exportar"))
            }
          >
            <Download /> Exportar
          </Button>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-s3">
        <Segmentado
          etiqueta="Vista"
          valor={pestana}
          onCambio={setPestana}
          opciones={[
            { valor: "fletes", etiqueta: "Por facturar", contador: grupos.reduce((a, g) => a + g.viajes.length, 0) },
            { valor: "facturas", etiqueta: "Facturas emitidas", contador: facturas.length },
          ]}
        />
        {pestana === "fletes" && !cargando && grupos.length > 0 && (
          <p className="text-[15px] text-tinta-3">
            Total por facturar <span className="cifra ml-1 text-[18px] font-semibold text-tinta">{formatCLP(totalPorFacturar)}</span>
          </p>
        )}
      </div>

      {pestana === "fletes" ? (
        cargando ? (
          <div className="space-y-s3">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-40 w-full rounded-xl" />
            ))}
          </div>
        ) : grupos.length === 0 ? (
          <Panel>
            <EstadoVacio
              icono={Inbox}
              titulo="No hay fletes pendientes de facturar"
              descripcion="Cuando un viaje se finaliza, aparece aquí agrupado por cliente."
              accion={
                <Link href="/viajes" className="inline-flex items-center gap-1 text-[15px] font-medium text-marca hover:underline">
                  Ir a viajes <ArrowRight className="size-4" />
                </Link>
              }
            />
          </Panel>
        ) : (
          <div className="space-y-s4">
            {grupos.map((g) => (
              <Panel
                key={g.cliente_id}
                titulo={g.cliente_nombre}
                descripcion={`${g.viajes.length} ${g.viajes.length === 1 ? "viaje" : "viajes"} · pago a ${g.dias_pago} días`}
                acciones={
                  <>
                    <span className="cifra mr-s2 text-[22px] font-semibold">{formatCLP(g.total_neto)}</span>
                    {puedeEscribir && (
                      <Button onClick={() => abrirFacturar(g)}>
                        <FileText /> Registrar factura
                      </Button>
                    )}
                  </>
                }
              >
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Fecha</TableHead>
                      <TableHead>Ruta</TableHead>
                      <TableHead className="text-right">Valor neto</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {g.viajes.map((v) => (
                      <TableRow key={v.id}>
                        <TableCell className="text-tinta-2">{formatFecha(v.fecha_inicio)}</TableCell>
                        <TableCell>
                          <Link href={`/viajes/${v.id}`} className="inline-flex items-center gap-1.5 font-medium hover:text-marca">
                            {v.origen} <ArrowRight className="size-3.5 text-tinta-3" /> {v.destino}
                          </Link>
                        </TableCell>
                        <TableCell className="cifra text-right">{formatCLP(v.valor_flete_neto)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Panel>
            ))}
          </div>
        )
      ) : (
        <Panel>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>N° SII</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead className="text-right">Neto</TableHead>
                <TableHead className="text-right">IVA</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Emisión</TableHead>
                <TableHead>Vence</TableHead>
                <TableHead>Estado</TableHead>
                {puedeEscribir && <TableHead className="text-right">Acciones</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <FilasCargando columnas={puedeEscribir ? 9 : 8} />
              ) : facturas.length === 0 ? (
                <FilaVacia columnas={puedeEscribir ? 9 : 8} icono={FileCheck2} titulo="Aún no hay facturas" descripcion="Registre facturas desde la pestaña “Por facturar”." />
              ) : (
                facturas.map((f) => (
                  <TableRow key={f.id} className={cn(f.estado === "anulada" && "opacity-60")}>
                    <TableCell className="font-mono font-semibold">{f.numero_sii}</TableCell>
                    <TableCell>
                      <span className="font-medium">{f.cliente_nombre}</span>
                      <span className="block text-[13px] text-tinta-3">
                        {f.viajes.length} {f.viajes.length === 1 ? "viaje" : "viajes"} · {f.tipo === "afecta" ? "afecta" : "exenta"}
                      </span>
                    </TableCell>
                    <TableCell className="cifra text-right text-tinta-2">{formatCLP(f.monto_neto)}</TableCell>
                    <TableCell className="cifra text-right text-tinta-2">{formatCLP(f.iva)}</TableCell>
                    <TableCell className="cifra text-right font-semibold">{formatCLP(f.total)}</TableCell>
                    <TableCell className="text-tinta-2">{formatFecha(f.fecha_emision)}</TableCell>
                    <TableCell className="text-tinta-2">{f.estado === "pagada" ? `Pagada ${formatFecha(f.fecha_pago)}` : formatFecha(f.fecha_vencimiento)}</TableCell>
                    <TableCell>
                      <StatusBadge tono={ESTADO_FACTURA[f.estado].tono}>{ESTADO_FACTURA[f.estado].label}</StatusBadge>
                    </TableCell>
                    {puedeEscribir && (
                      <TableCell>
                        {f.estado === "pendiente" && (
                          <div className="flex justify-end gap-1">
                            <Button variant="success" size="xs" onClick={() => marcarPagada(f)}>
                              <CheckCircle2 /> Pagada
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-xs"
                              className="text-tinta-3 hover:bg-critico-tenue hover:text-critico"
                              onClick={() => setAnulando(f)}
                              aria-label={`Anular factura ${f.numero_sii}`}
                            >
                              <XCircle />
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Panel>
      )}

      <Dialog open={dialogo} onOpenChange={setDialogo}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Registrar factura</DialogTitle>
            <DialogDescription>
              {grupoActual?.cliente_nombre}. El sistema no emite al SII: ingrese el número de la factura ya emitida.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <div className="grid gap-s3 sm:grid-cols-3">
              <Campo etiqueta="N° factura SII" htmlFor="f-num" requerido error={intento && !form.numero_sii.trim() ? "Obligatorio" : null}>
                <Input id="f-num" inputMode="numeric" value={form.numero_sii} onChange={(e) => setForm({ ...form, numero_sii: e.target.value })} className="font-mono" placeholder="123456" />
              </Campo>
              <Campo etiqueta="Tipo" htmlFor="f-tipo">
                <SelectSimple
                  id="f-tipo"
                  valor={form.tipo}
                  onCambio={(v) => setForm({ ...form, tipo: (v || "afecta") as "afecta" | "exenta" })}
                  opciones={[
                    { valor: "afecta", etiqueta: `Afecta (${tasaIva} %)` },
                    { valor: "exenta", etiqueta: "Exenta" },
                  ]}
                />
              </Campo>
              <Campo etiqueta="Emisión" htmlFor="f-fecha">
                <Input id="f-fecha" type="date" value={form.fecha_emision} onChange={(e) => setForm({ ...form, fecha_emision: e.target.value })} />
              </Campo>
            </div>

            <fieldset>
              <legend className="mb-s2 text-[15px] font-medium text-tinta-2">Viajes incluidos</legend>
              <div className="max-h-56 divide-y divide-borde overflow-y-auto rounded-xl border border-borde">
                {grupoActual?.viajes.map((v) => {
                  const sel = form.viaje_ids.includes(v.id);
                  return (
                    <label
                      key={v.id}
                      className={cn(
                        "flex cursor-pointer items-center gap-s3 px-s3 py-s3 text-[15.5px] transition-colors",
                        sel ? "bg-marca-tenue/50" : "hover:bg-superficie-hundida",
                      )}
                    >
                      <input type="checkbox" checked={sel} onChange={() => toggleViaje(v.id)} className="size-[18px]" />
                      <span className="flex-1">
                        {v.origen} → {v.destino}
                        <span className="block text-[13px] text-tinta-3">{formatFecha(v.fecha_inicio)}</span>
                      </span>
                      <span className="cifra font-medium">{formatCLP(v.valor_flete_neto)}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <dl className="space-y-s2 rounded-xl bg-superficie-hundida px-s4 py-s3 text-[15.5px]">
              <div className="flex justify-between">
                <dt className="text-tinta-3">Neto</dt>
                <dd className="cifra">{formatCLP(neto)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-tinta-3">IVA {form.tipo === "afecta" ? `(${tasaIva} %)` : "(exenta)"}</dt>
                <dd className="cifra">{formatCLP(iva)}</dd>
              </div>
              <div className="flex items-baseline justify-between border-t border-borde-fuerte pt-s2">
                <dt className="font-medium">Total</dt>
                <dd className="cifra text-[22px] font-semibold text-marca">{formatCLP(neto + iva)}</dd>
              </div>
            </dl>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogo(false)}>
              Cancelar
            </Button>
            <Button onClick={crearFactura} disabled={guardando || form.viaje_ids.length === 0}>
              {guardando ? "Guardando…" : "Registrar factura"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!anulando} onOpenChange={(o) => !o && setAnulando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Anular factura {anulando?.numero_sii}</DialogTitle>
            <DialogDescription>
              Los {anulando?.viajes.length} viajes asociados volverán al estado <strong>Finalizado</strong> y podrán
              facturarse nuevamente.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAnulando(null)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={confirmarAnular}>
              <XCircle /> Anular factura
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
