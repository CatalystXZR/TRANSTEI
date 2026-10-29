"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  Fuel,
  Loader2,
  Plus,
  Receipt,
  RefreshCw,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { nucleo, nucleoUpload } from "@/lib/nucleo";
import { formatCLP, formatFecha } from "@/lib/format";
import type {
  GastoNucleo,
  PrecioDieselNucleo,
  ViajeExpedienteNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AreaTexto, Campo, SelectSimple } from "@/components/formulario";
import { Aviso, Panel, StatTile, StatusBadge } from "@/components/sistema";

const TIPOS = [
  { valor: "combustible", etiqueta: "Combustible" },
  { valor: "peaje", etiqueta: "Peaje / TAG" },
  { valor: "estadia", etiqueta: "Estadía" },
  { valor: "viatico", etiqueta: "Viático" },
  { valor: "mantenimiento", etiqueta: "Mantenimiento" },
  { valor: "lavado", etiqueta: "Lavado" },
  { valor: "pesaje", etiqueta: "Pesaje" },
  { valor: "otro", etiqueta: "Otro" },
];

const ROLES_APRUEBAN = ["admin", "gerente", "contador", "tesoreria"];

function hoyISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function GastosPanel({
  empresaId,
  viaje,
  rol,
  onCambio,
}: {
  empresaId: string;
  viaje: ViajeExpedienteNucleo;
  rol: string;
  onCambio: () => void;
}) {
  const [gastos, setGastos] = useState<GastoNucleo[]>(viaje.gastos);
  const [precio, setPrecio] = useState<PrecioDieselNucleo | null>(null);
  const [precioNuevo, setPrecioNuevo] = useState("");
  const [cargando, setCargando] = useState(false);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mostrarForm, setMostrarForm] = useState(false);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [form, setForm] = useState({
    tipo: "combustible",
    fecha: hoyISO(),
    monto_total: "",
    iva: "0",
    litros: "",
    precio_litro: "",
    km_odometro: "",
    proveedor: "",
    numero_documento: "",
    estacion: "",
    tag: "",
    observaciones: "",
  });

  const puedeAprobar = ROLES_APRUEBAN.includes(rol);
  const puedeEditar = ["admin", "gerente", "despacho", "conductor"].includes(rol);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [lista, precioActual] = await Promise.all([
        nucleo.get<GastoNucleo[]>(
          `/nucleo/expediente/viajes/${viaje.id}/gastos`,
          empresaId,
        ),
        nucleo.get<PrecioDieselNucleo | null>(
          "/nucleo/combustible/precio-vigente",
          empresaId,
        ),
      ]);
      setGastos(lista);
      setPrecio(precioActual);
      if (precioActual) setPrecioNuevo(precioActual.precio_litro);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar los gastos");
    } finally {
      setCargando(false);
    }
  }, [empresaId, viaje.id]);

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  function set<K extends keyof typeof form>(campo: K, valor: string) {
    setForm((f) => ({ ...f, [campo]: valor }));
  }

  function totalCalculado(): number {
    if (form.tipo === "combustible" && form.litros && form.precio_litro) {
      return (
        Number(form.litros) * Number(form.precio_litro) + Number(form.iva || 0)
      );
    }
    return Number(form.monto_total || 0);
  }

  async function guardarPrecio() {
    if (!precioNuevo || Number(precioNuevo) <= 0) return;
    setProcesando(true);
    try {
      await nucleo.post("/nucleo/combustible/precios", empresaId, {
        fecha: hoyISO(),
        precio_litro: Number(precioNuevo),
        fuente: "Registro manual",
      });
      toast.success("Precio diésel actualizado");
      await cargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo guardar el precio");
    } finally {
      setProcesando(false);
    }
  }

  async function crearGasto() {
    const total = totalCalculado();
    if (total <= 0) {
      setError("El monto total debe ser mayor que cero.");
      return;
    }
    if (form.tipo === "combustible" && !form.litros) {
      setError("El gasto de combustible requiere litros.");
      return;
    }
    setProcesando(true);
    setError(null);
    try {
      const gasto = await nucleo.post<GastoNucleo>(
        `/nucleo/expediente/viajes/${viaje.id}/gastos`,
        empresaId,
        {
          tipo: form.tipo,
          fecha: form.fecha,
          monto_total: total,
          iva: Number(form.iva || 0),
          moneda: viaje.moneda,
          litros: form.litros ? Number(form.litros) : null,
          precio_litro: form.precio_litro ? Number(form.precio_litro) : null,
          km_odometro: form.km_odometro ? Number(form.km_odometro) : null,
          proveedor: form.proveedor.trim() || null,
          numero_documento: form.numero_documento.trim() || null,
          estacion: form.estacion.trim() || null,
          tag: form.tag.trim() || null,
          observaciones: form.observaciones.trim() || null,
        },
      );
      if (archivo) {
        const fd = new FormData();
        fd.set("archivo", archivo);
        await nucleoUpload(
          `/nucleo/expediente/gastos/${gasto.id}/comprobante`,
          empresaId,
          fd,
        );
      }
      toast.success("Gasto registrado; queda pendiente de aprobación");
      setMostrarForm(false);
      setArchivo(null);
      setForm({
        tipo: "combustible",
        fecha: hoyISO(),
        monto_total: "",
        iva: "0",
        litros: "",
        precio_litro: "",
        km_odometro: "",
        proveedor: "",
        numero_documento: "",
        estacion: "",
        tag: "",
        observaciones: "",
      });
      await cargar();
      onCambio();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo registrar el gasto");
    } finally {
      setProcesando(false);
    }
  }

  async function aprobar(gasto: GastoNucleo) {
    const observacion = window.prompt("Observación de aprobación (opcional):") ?? undefined;
    setProcesando(true);
    try {
      await nucleo.post(
        `/nucleo/expediente/gastos/${gasto.id}/aprobar`,
        empresaId,
        { observacion: observacion || null },
      );
      toast.success("Gasto aprobado");
      await cargar();
      onCambio();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo aprobar");
    } finally {
      setProcesando(false);
    }
  }

  async function rechazar(gasto: GastoNucleo) {
    const motivo = window.prompt("Motivo del rechazo:");
    if (!motivo || motivo.trim().length < 5) return;
    setProcesando(true);
    try {
      await nucleo.post(
        `/nucleo/expediente/gastos/${gasto.id}/rechazar`,
        empresaId,
        { motivo: motivo.trim() },
      );
      toast.success("Gasto rechazado");
      await cargar();
      onCambio();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo rechazar");
    } finally {
      setProcesando(false);
    }
  }

  const costos = viaje.costos;
  const pendientes = gastos.filter((g) => g.estado === "pendiente");

  return (
    <div className="space-y-s4">
      {error && (
        <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>
      )}

      <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          etiqueta="Gastos aprobados"
          valor={formatCLP(costos?.gastos_aprobados ?? 0)}
          detalle={`${gastos.filter((g) => g.estado === "aprobado").length} documento(s)`}
          tono="ok"
          icono={Receipt}
          destacado
        />
        <StatTile
          etiqueta="Pendientes de aprobación"
          valor={formatCLP(costos?.gastos_pendientes ?? 0)}
          detalle={`${pendientes.length} por revisar`}
          tono={pendientes.length ? "atencion" : "ok"}
          icono={Receipt}
        />
        <StatTile
          etiqueta="Costo variable"
          valor={formatCLP(costos?.costo_variable ?? 0)}
          detalle={`Comisión ${formatCLP(costos?.comision_estimada ?? 0)}`}
          tono="info"
          icono={Fuel}
        />
        <StatTile
          etiqueta="Margen del viaje"
          valor={`${Number(costos?.margen_pct ?? 0).toFixed(1)}%`}
          detalle={formatCLP(costos?.margen ?? 0)}
          tono={Number(costos?.margen ?? 0) >= 0 ? "ok" : "critico"}
          icono={Receipt}
        />
      </div>

      {costos && (
        <div className="grid gap-s3 rounded-xl border border-borde bg-superficie-hundida/50 p-s4 text-[14px] sm:grid-cols-4">
          <p><span className="text-tinta-3">Ingreso:</span> {formatCLP(costos.ingreso_total)}</p>
          <p><span className="text-tinta-3">Litros:</span> {Number(costos.litros).toLocaleString("es-CL")}</p>
          <p><span className="text-tinta-3">Rendimiento:</span> {costos.rendimiento_km_l ? `${Number(costos.rendimiento_km_l).toFixed(2)} km/L` : "—"}</p>
          <p><span className="text-tinta-3">Costo/km:</span> {costos.costo_por_km ? formatCLP(costos.costo_por_km) : "—"}</p>
        </div>
      )}

      <Panel
        titulo="Gastos del viaje"
        descripcion="Combustible, peajes, estadías y otros. El costo real usa solo gastos aprobados."
        acciones={
          <div className="flex flex-wrap gap-s2">
            <Button size="sm" variant="outline" onClick={() => void cargar()} disabled={cargando}>
              <RefreshCw className={cargando ? "animate-spin" : undefined} /> Actualizar
            </Button>
            {puedeEditar && (
              <Button size="sm" onClick={() => setMostrarForm((v) => !v)}>
                <Plus /> Registrar gasto
              </Button>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap items-end gap-s3 border-b border-borde p-s3">
          <Campo etiqueta="Precio diésel vigente" ayuda={precio ? `Desde ${formatFecha(precio.fecha)}` : "Sin precio registrado"}>
            <Input
              type="number"
              min={0}
              step="0.0001"
              value={precioNuevo}
              onChange={(e) => setPrecioNuevo(e.target.value)}
              className="w-[160px]"
              disabled={!puedeEditar}
            />
          </Campo>
          {puedeEditar && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => void guardarPrecio()}
              disabled={procesando || Number(precioNuevo) <= 0}
            >
              Guardar precio
            </Button>
          )}
          <p className="pb-2 text-[13px] text-tinta-3">
            Se usa para autocompletar el precio del combustible.
          </p>
        </div>

        {mostrarForm && puedeEditar && (
          <div className="grid gap-s3 border-b border-borde bg-superficie-hundida/30 p-s4 sm:grid-cols-4">
            <Campo etiqueta="Tipo" requerido>
              <SelectSimple
                valor={form.tipo}
                onCambio={(v) => set("tipo", v)}
                opciones={TIPOS}
              />
            </Campo>
            <Campo etiqueta="Fecha" requerido>
              <Input type="date" value={form.fecha} onChange={(e) => set("fecha", e.target.value)} />
            </Campo>
            <Campo etiqueta="Proveedor">
              <Input value={form.proveedor} onChange={(e) => set("proveedor", e.target.value)} />
            </Campo>
            <Campo etiqueta="Documento">
              <Input value={form.numero_documento} onChange={(e) => set("numero_documento", e.target.value)} />
            </Campo>
            {form.tipo === "combustible" ? (
              <>
                <Campo etiqueta="Litros" requerido>
                  <Input type="number" min={0} step="0.001" value={form.litros} onChange={(e) => set("litros", e.target.value)} />
                </Campo>
                <Campo etiqueta="Precio por litro">
                  <Input
                    type="number"
                    min={0}
                    step="0.0001"
                    value={form.precio_litro || precio?.precio_litro || ""}
                    onChange={(e) => set("precio_litro", e.target.value)}
                    placeholder={precio?.precio_litro ?? "0"}
                  />
                </Campo>
                <Campo etiqueta="Km odómetro">
                  <Input type="number" min={0} step="0.1" value={form.km_odometro} onChange={(e) => set("km_odometro", e.target.value)} />
                </Campo>
                <Campo etiqueta="Estación">
                  <Input value={form.estacion} onChange={(e) => set("estacion", e.target.value)} />
                </Campo>
              </>
            ) : (
              <>
                <Campo etiqueta="Monto total" requerido>
                  <Input type="number" min={0} step="0.01" value={form.monto_total} onChange={(e) => set("monto_total", e.target.value)} />
                </Campo>
                <Campo etiqueta="TAG / referencia">
                  <Input value={form.tag} onChange={(e) => set("tag", e.target.value)} />
                </Campo>
              </>
            )}
            <Campo etiqueta="IVA">
              <Input type="number" min={0} step="0.01" value={form.iva} onChange={(e) => set("iva", e.target.value)} />
            </Campo>
            <Campo etiqueta="Comprobante" className="sm:col-span-2">
              <input
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.webp,.heic"
                onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
                className="block w-full text-[14px]"
              />
            </Campo>
            <Campo etiqueta="Observaciones" className="sm:col-span-2">
              <AreaTexto rows={2} value={form.observaciones} onChange={(e) => set("observaciones", e.target.value)} />
            </Campo>
            <div className="flex items-end gap-s2 sm:col-span-2">
              <p className="pb-2 text-[14px] text-tinta-2">
                Total: <strong>{formatCLP(totalCalculado())}</strong>
              </p>
              <Button onClick={() => void crearGasto()} disabled={procesando}>
                {procesando ? <Loader2 className="animate-spin" /> : <Plus />} Guardar
              </Button>
            </div>
          </div>
        )}

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fecha</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Proveedor</TableHead>
                <TableHead>Litros</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="text-right">Neto</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {gastos.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-s5 text-center text-tinta-3">
                    Sin gastos registrados.
                  </TableCell>
                </TableRow>
              ) : (
                gastos.map((gasto) => (
                  <TableRow key={gasto.id}>
                    <TableCell>{formatFecha(gasto.fecha)}</TableCell>
                    <TableCell className="capitalize">{gasto.tipo}</TableCell>
                    <TableCell>{gasto.proveedor ?? gasto.estacion ?? "—"}</TableCell>
                    <TableCell>{gasto.litros ? Number(gasto.litros).toLocaleString("es-CL") : "—"}</TableCell>
                    <TableCell className="text-right">{formatCLP(gasto.monto_total)}</TableCell>
                    <TableCell className="text-right">{formatCLP(gasto.monto_neto)}</TableCell>
                    <TableCell>
                      <StatusBadge
                        tono={
                          gasto.estado === "aprobado"
                            ? "ok"
                            : gasto.estado === "rechazado"
                              ? "critico"
                              : "atencion"
                        }
                      >
                        {gasto.estado}
                      </StatusBadge>
                      {gasto.motivo_rechazo && (
                        <p className="mt-1 max-w-[180px] text-[12px] text-critico">
                          {gasto.motivo_rechazo}
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-s2">
                        {gasto.comprobante_url_firmada && (
                          <a
                            href={gasto.comprobante_url_firmada}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center text-[13px] font-medium text-marca hover:underline"
                          >
                            Ver
                          </a>
                        )}
                        {puedeAprobar && gasto.estado === "pendiente" && (
                          <>
                            <Button size="xs" onClick={() => void aprobar(gasto)} disabled={procesando}>
                              <Check /> Aprobar
                            </Button>
                            <Button
                              size="xs"
                              variant="destructive"
                              onClick={() => void rechazar(gasto)}
                              disabled={procesando}
                            >
                              <X /> Rechazar
                            </Button>
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </Panel>
    </div>
  );
}
