"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileImage,
  Paperclip,
  Plus,
  Receipt,
  Trash2,
  Truck,
  Undo2,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { api, apiUpload } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { CategoriaGasto, EstadoViaje, Gasto, PreviewRentabilidad, Viaje } from "@/types";
import { CATEGORIA_GASTO_LABEL, ESTADO_VIAJE_LABEL, ESTADO_VIAJE_TONO, TONO_KPI, formatValorKpi } from "@/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputCLP } from "@/components/ui-inputs/input-clp";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EstadoVacio, FilaVacia, Panel, Patente, StatTile, StatusBadge } from "@/components/sistema";
import { Campo, SelectSimple } from "@/components/formulario";

const CATEGORIAS = Object.keys(CATEGORIA_GASTO_LABEL) as CategoriaGasto[];
const PASOS: EstadoViaje[] = ["programado", "en_ruta", "finalizado", "facturado"];

const AVANZAR: Partial<Record<EstadoViaje, { destino: EstadoViaje; etiqueta: string }>> = {
  programado: { destino: "en_ruta", etiqueta: "Iniciar viaje" },
  en_ruta: { destino: "finalizado", etiqueta: "Finalizar viaje" },
};
const RETROCEDER: Partial<Record<EstadoViaje, { destino: EstadoViaje; etiqueta: string }>> = {
  en_ruta: { destino: "programado", etiqueta: "Volver a programado" },
  finalizado: { destino: "en_ruta", etiqueta: "Reabrir (en ruta)" },
};

function hoyISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function Progreso({ estado }: { estado: EstadoViaje }) {
  const idx = PASOS.indexOf(estado);
  return (
    <ol className="grid grid-cols-4 gap-s2" aria-label="Progreso del viaje">
      {PASOS.map((p, i) => {
        const hecho = i < idx;
        const actual = i === idx;
        return (
          <li key={p} className="min-w-0" aria-current={actual ? "step" : undefined}>
            <div
              className={cn(
                "h-1.5 rounded-full transition-colors duration-500",
                hecho ? "bg-marca" : actual ? "bg-senal" : "bg-borde",
              )}
            />
            <p
              className={cn(
                "mt-s2 flex items-center gap-1 truncate text-[13.5px]",
                actual ? "font-semibold text-tinta" : hecho ? "text-tinta-2" : "text-tinta-3",
              )}
            >
              {hecho && <Check className="size-3.5 text-marca" />}
              {ESTADO_VIAJE_LABEL[p]}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

export default function ViajeDetallePage() {
  const params = useParams<{ id: string }>();
  const { usuario } = useAuth();
  const [viaje, setViaje] = useState<Viaje | null>(null);
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [renta, setRenta] = useState<PreviewRentabilidad | null>(null);
  const [cargando, setCargando] = useState(true);
  const [cambiando, setCambiando] = useState(false);

  const [dialogoGasto, setDialogoGasto] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [formGasto, setFormGasto] = useState({
    categoria: "combustible" as CategoriaGasto,
    monto: 0,
    iva_recuperable: false,
    fecha: "",
    notas: "",
  });
  const [archivo, setArchivo] = useState<File | null>(null);
  const [eliminando, setEliminando] = useState<Gasto | null>(null);

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  const cargar = useCallback(() => {
    return Promise.all([
      api.get<Viaje>(`/viajes/${params.id}`),
      api.get<Gasto[]>(`/viajes/${params.id}/gastos`),
      api.get<PreviewRentabilidad>(`/viajes/${params.id}/rentabilidad`).catch(() => null),
    ]).then(([v, g, r]) => {
      setViaje(v ?? null);
      setGastos(g ?? []);
      setRenta(r ?? null);
    });
  }, [params.id]);

  useEffect(() => {
    let activo = true;
    Promise.all([
      api.get<Viaje>(`/viajes/${params.id}`),
      api.get<Gasto[]>(`/viajes/${params.id}/gastos`),
      api.get<PreviewRentabilidad>(`/viajes/${params.id}/rentabilidad`).catch(() => null),
    ])
      .then(([v, g, r]) => {
        if (!activo) return;
        setViaje(v ?? null);
        setGastos(g ?? []);
        setRenta(r ?? null);
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
  }, [params.id]);

  async function cambiarEstado(destino: EstadoViaje) {
    setCambiando(true);
    try {
      await api.patch(`/viajes/${params.id}/estado`, { estado: destino });
      toast.success(`Estado actualizado: ${ESTADO_VIAJE_LABEL[destino]}`);
      await cargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al cambiar estado");
    } finally {
      setCambiando(false);
    }
  }

  function abrirGasto() {
    setFormGasto({ categoria: "combustible", monto: 0, iva_recuperable: false, fecha: hoyISO(), notas: "" });
    setArchivo(null);
    setDialogoGasto(true);
  }

  async function guardarGasto() {
    if (!formGasto.monto) {
      toast.error("Ingrese el monto del gasto");
      return;
    }
    setGuardando(true);
    const fd = new FormData();
    fd.append("categoria", formGasto.categoria);
    fd.append("monto", String(formGasto.monto));
    fd.append("iva_recuperable", String(formGasto.iva_recuperable));
    fd.append("fecha", formGasto.fecha || hoyISO());
    if (formGasto.notas.trim()) fd.append("notas", formGasto.notas.trim());
    if (archivo) fd.append("archivo", archivo);
    try {
      await apiUpload(`/viajes/${params.id}/gastos`, fd);
      toast.success("Gasto registrado");
      setDialogoGasto(false);
      await cargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar gasto");
    } finally {
      setGuardando(false);
    }
  }

  async function confirmarEliminar() {
    if (!eliminando) return;
    try {
      await api.del(`/gastos/${eliminando.id}`);
      toast.success("Gasto eliminado");
      setEliminando(null);
      await cargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al eliminar");
    }
  }

  async function verRespaldo(gasto: Gasto) {
    try {
      const res = await api.get<{ url: string }>(`/gastos/${gasto.id}/respaldo`);
      if (res?.url) window.open(res.url, "_blank", "noopener");
    } catch {
      toast.error("No se pudo obtener el respaldo");
    }
  }

  if (cargando) {
    return (
      <div className="space-y-s5" aria-busy="true">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-10 w-96 max-w-full" />
        <Skeleton className="h-2 w-full" />
        <div className="grid gap-s3 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (!viaje) {
    return (
      <Panel>
        <EstadoVacio
          icono={Truck}
          titulo="Viaje no encontrado"
          descripcion="Es posible que haya sido eliminado."
          accion={
            <Link href="/viajes" className={buttonVariants({ variant: "outline" })}>
              <ArrowLeft /> Volver a viajes
            </Link>
          }
        />
      </Panel>
    );
  }

  const totalGastos = gastos.reduce((acc, g) => acc + Number(g.monto), 0);
  const avanzar = AVANZAR[viaje.estado];
  const retroceder = RETROCEDER[viaje.estado];
  const tonoRenta = renta && !renta.error ? (TONO_KPI[renta.color] ?? "neutro") : "neutro";
  const margen = renta?.detalle?.margen_viaje;

  const datos: [string, React.ReactNode][] = [
    ["Cliente", viaje.cliente_nombre],
    ["Chofer", viaje.chofer_nombre],
    ["Tracto", <Patente key="t">{viaje.tracto_patente}</Patente>],
    ["Rampla", <Patente key="r">{viaje.rampla_patente}</Patente>],
    ["Inicio", formatFecha(viaje.fecha_inicio)],
    ["Término", viaje.fecha_fin ? formatFecha(viaje.fecha_fin) : "—"],
  ];

  return (
    <div className="space-y-s5">
      <div className="space-y-s4">
        <Link
          href="/viajes"
          className="inline-flex items-center gap-1.5 rounded-md text-[15px] font-medium text-tinta-3 transition-colors hover:text-marca"
        >
          <ArrowLeft className="size-4" /> Viajes
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-s4">
          <div className="min-w-0 space-y-s2">
            <div className="flex flex-wrap items-center gap-s2">
              <StatusBadge tono={ESTADO_VIAJE_TONO[viaje.estado]}>{ESTADO_VIAJE_LABEL[viaje.estado]}</StatusBadge>
              <span className="rotulo">Viaje · {formatFecha(viaje.fecha_inicio)}</span>
            </div>
            <h1 className="flex flex-wrap items-center gap-x-s3 text-[30px] leading-tight font-semibold sm:text-[38px]">
              {viaje.origen}
              <ArrowRight className="size-7 text-tinta-3" />
              {viaje.destino}
            </h1>
          </div>
          {puedeEscribir && (
            <div className="flex flex-wrap gap-s2">
              {retroceder && (
                <Button variant="ghost" onClick={() => cambiarEstado(retroceder.destino)} disabled={cambiando}>
                  <Undo2 /> {retroceder.etiqueta}
                </Button>
              )}
              {avanzar && (
                <Button size="lg" onClick={() => cambiarEstado(avanzar.destino)} disabled={cambiando}>
                  {avanzar.etiqueta} <ArrowRight />
                </Button>
              )}
              {viaje.estado === "finalizado" && (
                <Link href="/facturacion" className={buttonVariants({ size: "lg" })}>
                  <Receipt /> Facturar
                </Link>
              )}
            </div>
          )}
        </div>
        <Progreso estado={viaje.estado} />
      </div>

      <section className="grid gap-s3 md:grid-cols-3" aria-label="Resultado del viaje">
        <StatTile etiqueta="Valor del flete" valor={formatCLP(viaje.valor_flete_neto)} detalle="Neto, sin IVA" tono="info" />
        <StatTile
          etiqueta="Gastos de ruta"
          valor={formatCLP(totalGastos)}
          detalle={`${gastos.length} ${gastos.length === 1 ? "registro" : "registros"}`}
          tono={totalGastos > 0 ? "atencion" : "neutro"}
        />
        <StatTile
          etiqueta="Rentabilidad"
          valor={renta && !renta.error ? formatValorKpi(renta.valor, renta.formato) : "—"}
          detalle={margen !== undefined ? `Margen ${formatCLP(margen)} (incluye comisión)` : "Según indicador configurado"}
          tono={tonoRenta}
        />
      </section>

      <div className="grid gap-s4 xl:grid-cols-[1fr_2fr]">
        <Panel titulo="Detalle">
          <dl className="divide-y divide-borde">
            {datos.map(([k, v]) => (
              <div key={k} className="flex items-center justify-between gap-s3 px-s4 py-s3">
                <dt className="text-[15px] text-tinta-3">{k}</dt>
                <dd className="text-right text-[16px] font-medium">{v}</dd>
              </div>
            ))}
            {viaje.notas && (
              <div className="px-s4 py-s3">
                <dt className="text-[15px] text-tinta-3">Notas</dt>
                <dd className="mt-1 text-[15.5px]">{viaje.notas}</dd>
              </div>
            )}
          </dl>
        </Panel>

        <Panel
          titulo="Gastos del viaje"
          descripcion="Combustible, peajes, viáticos y otros, con su respaldo"
          acciones={
            puedeEscribir &&
            viaje.estado !== "facturado" && (
              <Button size="sm" onClick={abrirGasto}>
                <Plus /> Registrar gasto
              </Button>
            )
          }
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fecha</TableHead>
                <TableHead>Categoría</TableHead>
                <TableHead className="text-right">Monto</TableHead>
                <TableHead>IVA</TableHead>
                <TableHead>Respaldo</TableHead>
                {puedeEscribir && (
                  <TableHead className="w-12">
                    <span className="sr-only">Acciones</span>
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {gastos.length === 0 ? (
                <FilaVacia
                  columnas={puedeEscribir ? 6 : 5}
                  icono={Receipt}
                  titulo="Sin gastos registrados"
                  descripcion="Registre combustible, peajes y otros gastos para conocer la rentabilidad real."
                />
              ) : (
                gastos.map((g) => (
                  <TableRow key={g.id}>
                    <TableCell className="text-tinta-2">{formatFecha(g.fecha)}</TableCell>
                    <TableCell>
                      <span className="font-medium">{CATEGORIA_GASTO_LABEL[g.categoria]}</span>
                      {g.notas && <span className="block text-[13.5px] text-tinta-3">{g.notas}</span>}
                    </TableCell>
                    <TableCell className="cifra text-right font-semibold">{formatCLP(g.monto)}</TableCell>
                    <TableCell>
                      {g.iva_recuperable ? (
                        <StatusBadge tono="ok">Recuperable</StatusBadge>
                      ) : (
                        <span className="text-[14px] text-tinta-3">No</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {g.respaldo_url ? (
                        <Button variant="ghost" size="xs" onClick={() => verRespaldo(g)}>
                          <FileImage /> Ver
                        </Button>
                      ) : (
                        <span className="text-[14px] text-tinta-3">—</span>
                      )}
                    </TableCell>
                    {puedeEscribir && (
                      <TableCell>
                        {viaje.estado !== "facturado" && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="text-tinta-3 hover:bg-critico-tenue hover:text-critico"
                            onClick={() => setEliminando(g)}
                            aria-label={`Eliminar gasto de ${formatCLP(g.monto)}`}
                          >
                            <Trash2 />
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Panel>
      </div>

      <Dialog open={dialogoGasto} onOpenChange={setDialogoGasto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar gasto</DialogTitle>
            <DialogDescription>Adjunte la foto de la boleta si la tiene a mano.</DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Categoría" htmlFor="g-cat">
                <SelectSimple
                  id="g-cat"
                  valor={formGasto.categoria}
                  onCambio={(v) => setFormGasto({ ...formGasto, categoria: (v || "combustible") as CategoriaGasto })}
                  opciones={CATEGORIAS.map((c) => ({ valor: c, etiqueta: CATEGORIA_GASTO_LABEL[c] }))}
                />
              </Campo>
              <Campo etiqueta="Monto" htmlFor="g-monto" requerido>
                <InputCLP id="g-monto" value={formGasto.monto} onChange={(v) => setFormGasto({ ...formGasto, monto: v })} className="cifra font-semibold" />
              </Campo>
              <Campo etiqueta="Fecha" htmlFor="g-fecha">
                <Input id="g-fecha" type="date" value={formGasto.fecha} onChange={(e) => setFormGasto({ ...formGasto, fecha: e.target.value })} />
              </Campo>
              <div className="flex items-end">
                <label className="flex h-11 w-full cursor-pointer items-center gap-s3 rounded-lg border border-borde-fuerte bg-superficie px-3 text-[15.5px] transition-colors hover:border-marca/40 hover:bg-marca-tenue/40">
                  <input
                    type="checkbox"
                    checked={formGasto.iva_recuperable}
                    onChange={(e) => setFormGasto({ ...formGasto, iva_recuperable: e.target.checked })}
                    className="size-[18px]"
                  />
                  Tiene IVA recuperable
                </label>
              </div>
            </div>
            <Campo etiqueta="Notas" htmlFor="g-notas">
              <Input id="g-notas" value={formGasto.notas} onChange={(e) => setFormGasto({ ...formGasto, notas: e.target.value })} placeholder="Opcional" />
            </Campo>
            <Campo etiqueta="Boleta o factura (foto o PDF)" htmlFor="g-archivo" ayuda={archivo ? undefined : "JPG, PNG, HEIC o PDF"}>
              <Input id="g-archivo" type="file" accept="image/*,.pdf" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} className="h-auto py-2" />
              {archivo && (
                <p className="flex items-center gap-1.5 text-[14px] text-ok">
                  <Paperclip className="size-4" /> {archivo.name}
                </p>
              )}
            </Campo>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoGasto(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarGasto} disabled={guardando}>
              {guardando ? "Guardando…" : "Guardar gasto"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!eliminando} onOpenChange={(o) => !o && setEliminando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Eliminar gasto</DialogTitle>
            <DialogDescription>
              Se eliminará el gasto de <strong>{eliminando ? formatCLP(eliminando.monto) : ""}</strong>. Esta acción no
              se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEliminando(null)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={confirmarEliminar}>
              <Trash2 /> Eliminar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
