"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, ChevronRight, Download, Plus, Search, Truck } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { api } from "@/lib/api";
import { descargarArchivo } from "@/lib/download";
import { formatCLP, formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { Chofer, Cliente, EstadoViaje, PreviewRentabilidad, Rampla, Tracto, Viaje } from "@/types";
import { ESTADO_VIAJE_LABEL, ESTADO_VIAJE_TONO, TONO_KPI, formatValorKpi } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputCLP } from "@/components/ui-inputs/input-clp";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FilaVacia, FilasCargando, PageHeader, Panel, Patente, Segmentado, StatusBadge } from "@/components/sistema";
import { Campo, SelectSimple } from "@/components/formulario";

const ESTADOS: EstadoViaje[] = ["programado", "en_ruta", "finalizado", "facturado"];

const FORM_VACIO = {
  fecha_inicio: "",
  origen: "",
  destino: "",
  valor_flete_neto: 0,
  cliente_id: "",
  chofer_id: "",
  tracto_id: "",
  rampla_id: "",
  notas: "",
};

const TONO_RENTA: Record<string, string> = {
  ok: "border-ok/25 bg-ok-tenue text-ok",
  atencion: "border-atencion/25 bg-atencion-tenue text-atencion",
  critico: "border-critico/25 bg-critico-tenue text-critico",
  info: "border-marca/15 bg-marca-tenue text-marca",
  neutro: "border-borde bg-superficie-hundida text-tinta-2",
};

function ViajesContenido() {
  const { usuario } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [viajes, setViajes] = useState<Viaje[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [choferes, setChoferes] = useState<Chofer[]>([]);
  const [tractos, setTractos] = useState<Tracto[]>([]);
  const [ramplas, setRamplas] = useState<Rampla[]>([]);
  const [cargando, setCargando] = useState(true);
  const [filtroEstado, setFiltroEstado] = useState<EstadoViaje | "todos">("todos");
  const [busqueda, setBusqueda] = useState("");

  const [dialogo, setDialogo] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [intento, setIntento] = useState(false);
  const [rentabilidad, setRentabilidad] = useState<PreviewRentabilidad | null>(null);
  const [form, setForm] = useState(FORM_VACIO);

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  useEffect(() => {
    if (params.get("nuevo") === "1" && puedeEscribir) {
      const t = setTimeout(() => {
        setDialogo(true);
        router.replace("/viajes");
      }, 0);
      return () => clearTimeout(t);
    }
  }, [params, puedeEscribir, router]);

  useEffect(() => {
    if (!dialogo || !form.valor_flete_neto || !form.chofer_id) {
      const limpiar = setTimeout(() => setRentabilidad(null), 0);
      return () => clearTimeout(limpiar);
    }
    const t = setTimeout(() => {
      api
        .post<PreviewRentabilidad>("/viajes/preview-rentabilidad", {
          flete_viaje: form.valor_flete_neto,
          chofer_id: form.chofer_id,
          gastos_viaje: 0,
        })
        .then((r) => setRentabilidad(r))
        .catch(() => setRentabilidad(null));
    }, 350);
    return () => clearTimeout(t);
  }, [dialogo, form.valor_flete_neto, form.chofer_id]);

  useEffect(() => {
    let activo = true;
    Promise.all([
      api.get<Viaje[]>("/viajes"),
      api.get<Cliente[]>("/clientes?activo=true"),
      api.get<Chofer[]>("/choferes?activo=true"),
      api.get<Tracto[]>("/tractos?activo=true"),
      api.get<Rampla[]>("/ramplas?activo=true"),
    ])
      .then(([v, c, ch, t, r]) => {
        if (!activo) return;
        setViajes(v ?? []);
        setClientes(c ?? []);
        setChoferes(ch ?? []);
        setTractos(t ?? []);
        setRamplas(r ?? []);
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar"))
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return viajes.filter(
      (v) =>
        (filtroEstado === "todos" || v.estado === filtroEstado) &&
        (!q ||
          [v.origen, v.destino, v.cliente_nombre, v.chofer_nombre, v.tracto_patente].some((x) =>
            x.toLowerCase().includes(q),
          )),
    );
  }, [viajes, filtroEstado, busqueda]);

  function abrir() {
    setForm(FORM_VACIO);
    setIntento(false);
    setDialogo(true);
  }

  const faltan = {
    fecha_inicio: !form.fecha_inicio,
    origen: !form.origen.trim(),
    destino: !form.destino.trim(),
    valor_flete_neto: !form.valor_flete_neto,
    cliente_id: !form.cliente_id,
    chofer_id: !form.chofer_id,
    tracto_id: !form.tracto_id,
    rampla_id: !form.rampla_id,
  };
  const err = (k: keyof typeof faltan, msg = "Campo obligatorio") => (intento && faltan[k] ? msg : null);

  async function guardar() {
    setIntento(true);
    if (Object.values(faltan).some(Boolean)) {
      toast.error("Complete los campos obligatorios");
      return;
    }
    setGuardando(true);
    try {
      await api.post("/viajes", {
        ...form,
        origen: form.origen.trim(),
        destino: form.destino.trim(),
        notas: form.notas.trim() || null,
      });
      toast.success("Viaje creado");
      setDialogo(false);
      const v = await api.get<Viaje[]>("/viajes");
      setViajes(v ?? []);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setGuardando(false);
    }
  }

  const tonoRenta = rentabilidad ? (TONO_KPI[rentabilidad.color] ?? "neutro") : "neutro";

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Operación"
        titulo="Viajes"
        descripcion="Registro de fletes: desde la programación hasta la facturación."
        acciones={
          <>
            <Button
              variant="outline"
              onClick={() =>
                descargarArchivo("/export/viajes", "viajes.csv").catch((e) =>
                  toast.error(e instanceof Error ? e.message : "Error al exportar"),
                )
              }
            >
              <Download /> Exportar
            </Button>
            {puedeEscribir && (
              <Button onClick={abrir}>
                <Plus /> Nuevo viaje
              </Button>
            )}
          </>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-s3">
        <Segmentado
          etiqueta="Filtrar por estado"
          valor={filtroEstado}
          onCambio={setFiltroEstado}
          opciones={[
            { valor: "todos", etiqueta: "Todos", contador: viajes.length },
            ...ESTADOS.map((e) => ({
              valor: e,
              etiqueta: ESTADO_VIAJE_LABEL[e],
              contador: viajes.filter((v) => v.estado === e).length,
            })),
          ]}
        />
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-[18px] -translate-y-1/2 text-tinta-3" />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar ruta, cliente, patente…"
            className="pl-10"
            aria-label="Buscar viajes"
          />
        </div>
      </div>

      <Panel>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Inicio</TableHead>
              <TableHead>Ruta</TableHead>
              <TableHead>Cliente</TableHead>
              <TableHead>Chofer</TableHead>
              <TableHead>Camión</TableHead>
              <TableHead className="text-right">Flete</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="w-10">
                <span className="sr-only">Abrir</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <FilasCargando columnas={8} />
            ) : filtrados.length === 0 ? (
              <FilaVacia
                columnas={8}
                icono={Truck}
                titulo={viajes.length === 0 ? "Aún no hay viajes" : "Sin resultados"}
                descripcion={
                  viajes.length === 0
                    ? "Registre el primer flete para comenzar a controlar la operación."
                    : "Pruebe con otro estado o término de búsqueda."
                }
                accion={
                  viajes.length === 0 && puedeEscribir ? (
                    <Button onClick={abrir}>
                      <Plus /> Nuevo viaje
                    </Button>
                  ) : undefined
                }
              />
            ) : (
              filtrados.map((v) => (
                <TableRow
                  key={v.id}
                  className="group cursor-pointer"
                  onClick={() => router.push(`/viajes/${v.id}`)}
                >
                  <TableCell className="text-tinta-2">{formatFecha(v.fecha_inicio)}</TableCell>
                  <TableCell>
                    <Link
                      href={`/viajes/${v.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center gap-1.5 font-medium text-tinta hover:text-marca"
                    >
                      {v.origen}
                      <ArrowRight className="size-3.5 text-tinta-3" />
                      {v.destino}
                    </Link>
                  </TableCell>
                  <TableCell className="text-tinta-2">{v.cliente_nombre}</TableCell>
                  <TableCell className="text-tinta-2">{v.chofer_nombre}</TableCell>
                  <TableCell>
                    <Patente>{v.tracto_patente}</Patente>
                  </TableCell>
                  <TableCell className="cifra text-right text-[16px] font-semibold">
                    {formatCLP(v.valor_flete_neto)}
                  </TableCell>
                  <TableCell>
                    <StatusBadge tono={ESTADO_VIAJE_TONO[v.estado]}>{ESTADO_VIAJE_LABEL[v.estado]}</StatusBadge>
                  </TableCell>
                  <TableCell>
                    <ChevronRight className="size-4 text-tinta-3 transition-transform group-hover:translate-x-0.5 group-hover:text-marca" />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Panel>

      <Dialog open={dialogo} onOpenChange={setDialogo}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Nuevo viaje</DialogTitle>
            <DialogDescription>Defina la ruta, el cliente y los equipos asignados al flete.</DialogDescription>
          </DialogHeader>

          <div className="space-y-s4">
            <fieldset className="space-y-s3 border-0">
              <legend className="rotulo float-left mb-s2 w-full">Ruta</legend>
              <div className="grid gap-s3 sm:grid-cols-2">
                <Campo etiqueta="Origen" htmlFor="v-origen" requerido error={err("origen")}>
                  <Input
                    id="v-origen"
                    value={form.origen}
                    onChange={(e) => setForm({ ...form, origen: e.target.value })}
                    placeholder="Santiago"
                    aria-invalid={!!err("origen")}
                  />
                </Campo>
                <Campo etiqueta="Destino" htmlFor="v-destino" requerido error={err("destino")}>
                  <Input
                    id="v-destino"
                    value={form.destino}
                    onChange={(e) => setForm({ ...form, destino: e.target.value })}
                    placeholder="Antofagasta"
                    aria-invalid={!!err("destino")}
                  />
                </Campo>
              </div>
              <Campo etiqueta="Fecha de inicio" htmlFor="v-fecha" requerido error={err("fecha_inicio")} className="sm:max-w-[50%] sm:pr-1.5">
                <Input
                  id="v-fecha"
                  type="date"
                  value={form.fecha_inicio}
                  onChange={(e) => setForm({ ...form, fecha_inicio: e.target.value })}
                  aria-invalid={!!err("fecha_inicio")}
                />
              </Campo>
            </fieldset>

            <fieldset className="space-y-s3 border-0 border-t border-borde pt-s4">
              <legend className="rotulo float-left mb-s2 w-full">Asignación</legend>
              <div className="grid gap-s3 sm:grid-cols-2">
                <Campo etiqueta="Cliente" htmlFor="v-cliente" requerido error={err("cliente_id")}>
                  <SelectSimple
                    id="v-cliente"
                    valor={form.cliente_id}
                    onCambio={(v) => setForm({ ...form, cliente_id: v })}
                    placeholder="Seleccione cliente"
                    opciones={clientes.map((c) => ({ valor: c.id, etiqueta: c.razon_social }))}
                  />
                </Campo>
                <Campo etiqueta="Chofer" htmlFor="v-chofer" requerido error={err("chofer_id")}>
                  <SelectSimple
                    id="v-chofer"
                    valor={form.chofer_id}
                    onCambio={(v) => setForm({ ...form, chofer_id: v })}
                    placeholder="Seleccione chofer"
                    opciones={choferes.map((c) => ({
                      valor: c.id,
                      etiqueta: `${c.nombre} · ${Math.round(Number(c.porcentaje_produccion) * 100)} %`,
                    }))}
                  />
                </Campo>
                <Campo etiqueta="Tracto" htmlFor="v-tracto" requerido error={err("tracto_id")}>
                  <SelectSimple
                    id="v-tracto"
                    valor={form.tracto_id}
                    onCambio={(v) => setForm({ ...form, tracto_id: v })}
                    placeholder="Patente del tracto"
                    opciones={tractos.map((t) => ({
                      valor: t.id,
                      etiqueta: `${t.patente}${t.marca ? ` · ${t.marca}` : ""}`,
                    }))}
                  />
                </Campo>
                <Campo etiqueta="Rampla" htmlFor="v-rampla" requerido error={err("rampla_id")}>
                  <SelectSimple
                    id="v-rampla"
                    valor={form.rampla_id}
                    onCambio={(v) => setForm({ ...form, rampla_id: v })}
                    placeholder="Patente de la rampla"
                    opciones={ramplas.map((r) => ({ valor: r.id, etiqueta: `${r.patente} · ${r.tipo}` }))}
                  />
                </Campo>
              </div>
            </fieldset>

            <fieldset className="space-y-s3 border-0 border-t border-borde pt-s4">
              <legend className="rotulo float-left mb-s2 w-full">Valor</legend>
              <Campo
                etiqueta="Valor del flete (neto)"
                htmlFor="v-flete"
                requerido
                error={err("valor_flete_neto")}
                ayuda={!form.chofer_id ? "Seleccione el chofer para estimar la rentabilidad." : undefined}
              >
                <InputCLP
                  id="v-flete"
                  value={form.valor_flete_neto}
                  onChange={(v) => setForm({ ...form, valor_flete_neto: v })}
                  placeholder="$ 1.200.000"
                  className="cifra h-12 text-[19px] font-semibold"
                />
              </Campo>
              <div
                role="status"
                aria-live="polite"
                className={cn(
                  "flex items-center justify-between gap-s3 rounded-xl border px-s4 py-s3 transition-colors duration-300",
                  rentabilidad && !rentabilidad.error ? TONO_RENTA[tonoRenta] : "border-dashed border-borde-fuerte text-tinta-3",
                )}
              >
                <div>
                  <p className="text-[14px] font-medium opacity-80">Rentabilidad estimada</p>
                  <p className="text-[13px] opacity-70">Flete − comisión del chofer (sin gastos aún)</p>
                </div>
                <div className="text-right">
                  <p className="cifra text-[26px] leading-none font-semibold">
                    {rentabilidad && !rentabilidad.error ? formatValorKpi(rentabilidad.valor, rentabilidad.formato) : "—"}
                  </p>
                  {rentabilidad?.detalle?.margen_viaje !== undefined && (
                    <p className="mt-1 text-[13px] opacity-80">margen {formatCLP(rentabilidad.detalle.margen_viaje)}</p>
                  )}
                </div>
              </div>
            </fieldset>

            <Campo etiqueta="Notas" htmlFor="v-notas">
              <Input
                id="v-notas"
                value={form.notas}
                onChange={(e) => setForm({ ...form, notas: e.target.value })}
                placeholder="Opcional"
              />
            </Campo>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogo(false)}>
              Cancelar
            </Button>
            <Button onClick={guardar} disabled={guardando}>
              {guardando ? "Guardando…" : "Crear viaje"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function ViajesPage() {
  return (
    <Suspense fallback={null}>
      <ViajesContenido />
    </Suspense>
  );
}
