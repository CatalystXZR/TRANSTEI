"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { nucleo, NucleoError } from "@/lib/nucleo";
import { formatCLP, formatFecha, formatFechaHora } from "@/lib/format";
import type {
  HistorialCambioNucleo,
  OrdenCompraNucleo,
} from "@/types/nucleo";
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
import { AreaTexto, Campo } from "@/components/formulario";
import {
  Aviso,
  Panel,
  StatusBadge,
  type Tono,
} from "@/components/sistema";

function tonoAlerta(alerta: string): Tono {
  if (alerta === "sobregiro" || alerta === "100") return "critico";
  if (alerta === "90" || alerta === "80") return "atencion";
  return "ok";
}

function etiquetaAlerta(alerta: string): string {
  if (alerta === "normal") return "Normal";
  if (alerta === "80") return "80 % consumido";
  if (alerta === "90") return "90 % consumido";
  if (alerta === "100") return "Consumida";
  return "Sobregiro";
}

export function OrdenCompraDetalleDialog({
  empresaId,
  ocId,
  rol,
  onClose,
  onEditar,
  onCambio,
}: {
  empresaId: string;
  ocId: string;
  rol: string;
  onClose: () => void;
  onEditar: (oc: OrdenCompraNucleo) => void;
  onCambio: () => void;
}) {
  const [oc, setOc] = useState<OrdenCompraNucleo | null>(null);
  const [historial, setHistorial] = useState<HistorialCambioNucleo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [procesando, setProcesando] = useState(false);

  const [montoSobregiro, setMontoSobregiro] = useState("");
  const [motivoSobregiro, setMotivoSobregiro] = useState("");
  const [motivoRechazo, setMotivoRechazo] = useState("");

  const [lineaDescripcion, setLineaDescripcion] = useState("");
  const [lineaCantidad, setLineaCantidad] = useState("1");
  const [lineaUnidad, setLineaUnidad] = useState("viaje");
  const [lineaPrecio, setLineaPrecio] = useState("");

  const puedeAprobar = rol === "admin" || rol === "gerente";

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [detalle, hist] = await Promise.all([
        nucleo.get<OrdenCompraNucleo>(`/nucleo/ordenes-compra/${ocId}`, empresaId),
        nucleo.get<HistorialCambioNucleo[]>(
          `/nucleo/ordenes-compra/${ocId}/historial`,
          empresaId,
        ),
      ]);
      setOc(detalle);
      setHistorial(hist);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la OC");
    } finally {
      setCargando(false);
    }
  }, [empresaId, ocId]);

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  async function ejecutar(accion: () => Promise<unknown>, mensaje: string) {
    setProcesando(true);
    setError(null);
    try {
      await accion();
      toast.success(mensaje);
      setMontoSobregiro("");
      setMotivoSobregiro("");
      setMotivoRechazo("");
      await cargar();
      onCambio();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo completar la operación");
      if (e instanceof NucleoError && e.errores.length > 0) {
        setError(e.errores.map((i) => i.mensaje).join(" "));
      }
    } finally {
      setProcesando(false);
    }
  }

  function solicitar() {
    if (!oc) return;
    void ejecutar(
      () =>
        nucleo.post(`/nucleo/ordenes-compra/${oc.id}/sobregiro/solicitar`, empresaId, {
          monto: Number(montoSobregiro),
          motivo: motivoSobregiro.trim(),
        }),
      "Sobregiro solicitado",
    );
  }

  function aprobar() {
    if (!oc) return;
    void ejecutar(
      () =>
        nucleo.post(`/nucleo/ordenes-compra/${oc.id}/sobregiro/aprobar`, empresaId, {
          monto: montoSobregiro ? Number(montoSobregiro) : null,
        }),
      "Sobregiro aprobado",
    );
  }

  function rechazar() {
    if (!oc) return;
    void ejecutar(
      () =>
        nucleo.post(`/nucleo/ordenes-compra/${oc.id}/sobregiro/rechazar`, empresaId, {
          motivo: motivoRechazo.trim(),
        }),
      "Sobregiro rechazado",
    );
  }

  async function agregarLinea() {
    if (!oc) return;
    if (!lineaDescripcion.trim() || Number(lineaPrecio) <= 0) {
      toast.error("Complete descripción y precio de la línea");
      return;
    }
    await ejecutar(
      () =>
        nucleo.post(`/nucleo/ordenes-compra/${oc.id}/lineas`, empresaId, {
          descripcion: lineaDescripcion.trim(),
          cantidad_estimada: Number(lineaCantidad || 0),
          unidad: lineaUnidad,
          precio_unitario: Number(lineaPrecio),
        }),
      "Línea agregada",
    );
    setLineaDescripcion("");
    setLineaCantidad("1");
    setLineaPrecio("");
  }

  function desactivarLinea(lineaId: string) {
    if (!oc) return;
    void ejecutar(
      () =>
        nucleo.del(
          `/nucleo/ordenes-compra/${oc.id}/lineas/${lineaId}`,
          empresaId,
        ),
      "Línea desactivada",
    );
  }

  const pct = Math.min(100, Number(oc?.porcentaje_consumo ?? 0));

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>
            OC {oc?.numero_oc ?? "…"}{" "}
            {oc && (
              <StatusBadge tono={tonoAlerta(oc.alerta)}>
                {etiquetaAlerta(oc.alerta)}
              </StatusBadge>
            )}
          </DialogTitle>
          <DialogDescription>
            {oc
              ? `${oc.cliente_nombre} · ${oc.centro_costo_nombre ?? "Sin centro de costo"}`
              : "Cargando orden de compra…"}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Aviso tono="critico" icono={AlertTriangle}>
            {error}
          </Aviso>
        )}

        {cargando && !oc ? (
          <div className="flex items-center gap-2 py-s5 text-tinta-3">
            <Loader2 className="animate-spin" /> Cargando OC…
          </div>
        ) : oc ? (
          <div className="space-y-s4">
            <div className="grid gap-s3 rounded-xl border border-borde bg-superficie-hundida/50 p-s4 sm:grid-cols-4">
              <div>
                <p className="rotulo">Autorizado</p>
                <p className="cifra text-[22px] font-semibold">
                  {formatCLP(oc.monto_autorizado)}
                </p>
                <p className="text-[13px] text-tinta-3">
                  + sobregiro {formatCLP(oc.sobregiro_autorizado)}
                </p>
              </div>
              <div>
                <p className="rotulo">Consumido</p>
                <p className="cifra text-[22px] font-semibold">
                  {formatCLP(oc.monto_consumido)}
                </p>
                <p className="text-[13px] text-tinta-3">
                  {oc.porcentaje_consumo}% del total
                </p>
              </div>
              <div>
                <p className="rotulo">Saldo</p>
                <p
                  className={`cifra text-[22px] font-semibold ${Number(oc.saldo_disponible) < 0 ? "text-critico" : ""}`}
                >
                  {formatCLP(oc.saldo_disponible)}
                </p>
                <p className="text-[13px] text-tinta-3">{oc.viajes_count} viaje(s)</p>
              </div>
              <div>
                <p className="rotulo">Vigencia</p>
                <p className="text-[15px] font-medium">
                  {formatFecha(oc.vigencia_desde)} → {formatFecha(oc.vigencia_hasta)}
                </p>
                <p className="text-[13px] text-tinta-3">
                  {oc.vencida ? "Vencida" : "Vigente"} · {oc.estado}
                </p>
              </div>
            </div>

            <div>
              <div className="h-3 overflow-hidden rounded-full bg-superficie-hundida">
                <div
                  className={`h-full rounded-full transition-[width] ${
                    oc.alerta === "normal"
                      ? "bg-ok"
                      : oc.alerta === "80" || oc.alerta === "90"
                        ? "bg-atencion"
                        : "bg-critico"
                  }`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="mt-s1 flex justify-between text-[13px] text-tinta-3">
                <span>0%</span>
                <span>80% · 90% · 100%</span>
              </div>
            </div>

            <Panel
              titulo="Líneas de la OC"
              descripcion="Referenciales; el consumo real se calcula desde los viajes."
              acciones={
                <Button size="sm" variant="outline" onClick={() => onEditar(oc)}>
                  Editar cabecera
                </Button>
              }
            >
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>#</TableHead>
                      <TableHead>Descripción</TableHead>
                      <TableHead>Cantidad</TableHead>
                      <TableHead>Precio</TableHead>
                      <TableHead>Monto</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {oc.lineas.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-s4 text-center text-tinta-3">
                          Sin líneas registradas.
                        </TableCell>
                      </TableRow>
                    ) : (
                      oc.lineas.map((linea) => (
                        <TableRow key={linea.id}>
                          <TableCell>{linea.numero_linea}</TableCell>
                          <TableCell>{linea.descripcion}</TableCell>
                          <TableCell>
                            {Number(linea.cantidad_estimada).toLocaleString("es-CL")}{" "}
                            {linea.unidad}
                          </TableCell>
                          <TableCell>{formatCLP(linea.precio_unitario)}</TableCell>
                          <TableCell>{formatCLP(linea.monto_linea)}</TableCell>
                          <TableCell>
                            <StatusBadge tono={linea.activa ? "ok" : "neutro"}>
                              {linea.activa ? "Activa" : "Inactiva"}
                            </StatusBadge>
                          </TableCell>
                          <TableCell className="text-right">
                            {linea.activa && (
                              <Button
                                size="xs"
                                variant="ghost"
                                onClick={() => desactivarLinea(linea.id)}
                                disabled={procesando}
                              >
                                Desactivar
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
              <div className="grid gap-s2 border-t border-borde p-s3 sm:grid-cols-12">
                <Campo etiqueta="Descripción" className="sm:col-span-5">
                  <Input
                    value={lineaDescripcion}
                    onChange={(e) => setLineaDescripcion(e.target.value)}
                    placeholder="Nueva línea"
                  />
                </Campo>
                <Campo etiqueta="Cantidad" className="sm:col-span-2">
                  <Input
                    type="number"
                    min={0}
                    step="0.001"
                    value={lineaCantidad}
                    onChange={(e) => setLineaCantidad(e.target.value)}
                  />
                </Campo>
                <Campo etiqueta="Unidad" className="sm:col-span-2">
                  <select
                    className="h-10 w-full rounded-lg border border-borde-fuerte bg-superficie px-3 text-[15px]"
                    value={lineaUnidad}
                    onChange={(e) => setLineaUnidad(e.target.value)}
                  >
                    <option value="viaje">viaje</option>
                    <option value="km">km</option>
                    <option value="ton">ton</option>
                    <option value="hora">hora</option>
                  </select>
                </Campo>
                <Campo etiqueta="Precio" className="sm:col-span-2">
                  <Input
                    type="number"
                    min={0}
                    step="0.0001"
                    value={lineaPrecio}
                    onChange={(e) => setLineaPrecio(e.target.value)}
                  />
                </Campo>
                <div className="flex items-end sm:col-span-1">
                  <Button size="sm" onClick={() => void agregarLinea()} disabled={procesando}>
                    <Plus />
                  </Button>
                </div>
              </div>
            </Panel>

            <Panel titulo="Consumo por viaje" descripcion="Solo viajes confirmados o posteriores.">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Viaje</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead>Inicio</TableHead>
                      <TableHead className="text-right">Monto</TableHead>
                      <TableHead className="text-right">% OC</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {oc.viajes.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="py-s4 text-center text-tinta-3">
                          La OC aún no tiene consumo.
                        </TableCell>
                      </TableRow>
                    ) : (
                      oc.viajes.map((viaje) => (
                        <TableRow key={viaje.id}>
                          <TableCell className="font-mono text-[13px]">
                            {viaje.numero_viaje}
                          </TableCell>
                          <TableCell>{viaje.estado.replaceAll("_", " ")}</TableCell>
                          <TableCell>{formatFechaHora(viaje.inicio_planificado)}</TableCell>
                          <TableCell className="text-right">{formatCLP(viaje.monto)}</TableCell>
                          <TableCell className="text-right">
                            {Number(viaje.porcentaje_oc).toFixed(1)}%
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </Panel>

            <Panel
              titulo="Sobregiro"
              descripcion="Solicitud y aprobación de consumo sobre el monto autorizado."
            >
              <div className="space-y-s3 p-s4">
                <div className="flex flex-wrap items-center gap-s3 text-[14px]">
                  <StatusBadge
                    tono={
                      oc.sobregiro_estado === "pendiente"
                        ? "atencion"
                        : oc.sobregiro_estado === "aprobado"
                          ? "ok"
                          : oc.sobregiro_estado === "rechazado"
                            ? "critico"
                            : "neutro"
                    }
                  >
                    {oc.sobregiro_estado.replaceAll("_", " ")}
                  </StatusBadge>
                  <span>Autorizado acumulado: {formatCLP(oc.sobregiro_autorizado)}</span>
                  {oc.sobregiro_estado === "pendiente" && (
                    <span>
                      Solicitado: {formatCLP(oc.sobregiro_solicitado)} ·{" "}
                      {oc.sobregiro_motivo}
                    </span>
                  )}
                  {oc.sobregiro_resolucion && <span>{oc.sobregiro_resolucion}</span>}
                </div>

                {oc.sobregiro_estado === "pendiente" ? (
                  puedeAprobar ? (
                    <div className="grid gap-s3 sm:grid-cols-2">
                      <Campo
                        etiqueta="Monto a aprobar"
                        ayuda={`Máximo solicitado: ${formatCLP(oc.sobregiro_solicitado)}`}
                      >
                        <Input
                          type="number"
                          min={0}
                          step="0.01"
                          value={montoSobregiro}
                          onChange={(e) => setMontoSobregiro(e.target.value)}
                          placeholder={oc.sobregiro_solicitado}
                        />
                      </Campo>
                      <div className="flex items-end gap-s2">
                        <Button onClick={aprobar} disabled={procesando}>
                          Aprobar
                        </Button>
                      </div>
                      <Campo etiqueta="Motivo de rechazo" className="sm:col-span-2">
                        <AreaTexto
                          rows={2}
                          value={motivoRechazo}
                          onChange={(e) => setMotivoRechazo(e.target.value)}
                        />
                      </Campo>
                      <div>
                        <Button
                          variant="destructive"
                          onClick={rechazar}
                          disabled={procesando || motivoRechazo.trim().length < 5}
                        >
                          Rechazar
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-[14px] text-tinta-3">
                      La solicitud está pendiente de aprobación por gerencia.
                    </p>
                  )
                ) : (
                  <div className="grid gap-s3 sm:grid-cols-2">
                    <Campo etiqueta="Monto solicitado">
                      <Input
                        type="number"
                        min={0}
                        step="0.01"
                        value={montoSobregiro}
                        onChange={(e) => setMontoSobregiro(e.target.value)}
                      />
                    </Campo>
                    <Campo etiqueta="Motivo" className="sm:col-span-2">
                      <AreaTexto
                        rows={2}
                        value={motivoSobregiro}
                        onChange={(e) => setMotivoSobregiro(e.target.value)}
                        placeholder="Carga adicional, reajuste de combustible…"
                      />
                    </Campo>
                    <div>
                      <Button
                        onClick={solicitar}
                        disabled={
                          procesando ||
                          Number(montoSobregiro) <= 0 ||
                          motivoSobregiro.trim().length < 5
                        }
                      >
                        Solicitar sobregiro
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </Panel>

            <Panel
              titulo="Historial de cambios"
              descripcion="Auditoría inmutable de cabecera y líneas."
              acciones={
                <Button size="sm" variant="outline" onClick={() => void cargar()}>
                  <RefreshCw /> Actualizar
                </Button>
              }
            >
              <div className="divide-y divide-borde">
                {historial.length === 0 ? (
                  <p className="p-s4 text-[14px] text-tinta-3">Sin cambios registrados.</p>
                ) : (
                  historial.slice(0, 30).map((h) => (
                    <div key={h.id} className="flex flex-wrap justify-between gap-s2 p-s3">
                      <div>
                        <p className="text-[14px] font-medium">
                          {h.operacion} · {h.tabla.replace("nucleo.", "")}
                        </p>
                        <p className="text-[13px] text-tinta-3">
                          {h.auth_id ? `Usuario ${h.auth_id.slice(0, 8)}…` : "Sistema"}
                        </p>
                      </div>
                      <p className="text-[13px] text-tinta-3">
                        {formatFechaHora(h.ocurrido_en)}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </Panel>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
