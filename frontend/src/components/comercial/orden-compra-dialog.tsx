"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { nucleo } from "@/lib/nucleo";
import { formatCLP } from "@/lib/format";
import type {
  CentroCostoNucleo,
  ClienteNucleo,
  OrdenCompraNucleo,
  TarifaNucleo,
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

type LineaForm = {
  descripcion: string;
  cantidad_estimada: string;
  unidad: string;
  precio_unitario: string;
  tarifa_id: string;
  centro_costo_id: string;
};

function lineaVacia(): LineaForm {
  return {
    descripcion: "",
    cantidad_estimada: "1",
    unidad: "viaje",
    precio_unitario: "",
    tarifa_id: "",
    centro_costo_id: "",
  };
}

function fechaFuturaISO(dias: number): string {
  return new Date(Date.now() + dias * 86400000).toISOString().slice(0, 10);
}

function hoyISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function OrdenCompraDialog({
  empresaId,
  moneda,
  oc,
  puedeSobregiro,
  onClose,
  onGuardado,
}: {
  empresaId: string;
  moneda: string;
  oc: OrdenCompraNucleo | null;
  puedeSobregiro: boolean;
  onClose: () => void;
  onGuardado: () => void;
}) {
  const editando = Boolean(oc);
  const [clientes, setClientes] = useState<ClienteNucleo[]>([]);
  const [centros, setCentros] = useState<CentroCostoNucleo[]>([]);
  const [tarifas, setTarifas] = useState<TarifaNucleo[]>([]);
  const [clienteId, setClienteId] = useState(oc?.cliente_id ?? "");
  const [numeroOc, setNumeroOc] = useState(oc?.numero_oc ?? "");
  const [referencia, setReferencia] = useState(oc?.referencia_interna ?? "");
  const [fechaEmision, setFechaEmision] = useState(oc?.fecha_emision ?? hoyISO());
  const [vigenciaDesde, setVigenciaDesde] = useState(oc?.vigencia_desde ?? hoyISO());
  const [vigenciaHasta, setVigenciaHasta] = useState(
    () => oc?.vigencia_hasta ?? fechaFuturaISO(180),
  );
  const [montoAutorizado, setMontoAutorizado] = useState(oc?.monto_autorizado ?? "");
  const [sobregiro, setSobregiro] = useState(oc?.sobregiro_autorizado ?? "0");
  const [centroId, setCentroId] = useState(oc?.centro_costo_id ?? "");
  const [proyecto, setProyecto] = useState(oc?.proyecto ?? "");
  const [faena, setFaena] = useState(oc?.faena ?? "");
  const [condicionesPago, setCondicionesPago] = useState(
    oc?.condiciones_pago_dias != null ? String(oc.condiciones_pago_dias) : "",
  );
  const [observaciones, setObservaciones] = useState(oc?.observaciones ?? "");
  const [lineas, setLineas] = useState<LineaForm[]>([lineaVacia()]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    Promise.all([
      nucleo.get<ClienteNucleo[]>("/nucleo/clientes?activo=true", empresaId),
      nucleo.get<CentroCostoNucleo[]>("/nucleo/centros-costo?activo=true", empresaId),
    ])
      .then(([c, cc]) => {
        if (!activo) return;
        setClientes(c);
        setCentros(cc);
      })
      .catch(() => {
        if (activo) setError("No se pudieron cargar clientes o centros de costo.");
      });
    return () => {
      activo = false;
    };
  }, [empresaId]);

  useEffect(() => {
    if (!clienteId) {
      return;
    }
    let activo = true;
    nucleo
      .get<TarifaNucleo[]>(`/nucleo/tarifas?cliente_id=${clienteId}&activo=true`, empresaId)
      .then((data) => {
        if (activo) setTarifas(data);
      })
      .catch(() => {
        if (activo) setTarifas([]);
      });
    return () => {
      activo = false;
    };
  }, [clienteId, empresaId]);

  const totalLineas = useMemo(
    () =>
      lineas.reduce(
        (acc, l) =>
          acc + Number(l.cantidad_estimada || 0) * Number(l.precio_unitario || 0),
        0,
      ),
    [lineas],
  );
  const excede = totalLineas > Number(montoAutorizado || 0);

  function setLinea(indice: number, campo: keyof LineaForm, valor: string) {
    setLineas((actuales) =>
      actuales.map((linea, i) => (i === indice ? { ...linea, [campo]: valor } : linea)),
    );
  }

  async function guardar() {
    if (!clienteId && !editando) {
      setError("Seleccione el cliente.");
      return;
    }
    if (!numeroOc.trim()) {
      setError("El número de OC es obligatorio.");
      return;
    }
    if (!montoAutorizado || Number(montoAutorizado) <= 0) {
      setError("El monto autorizado debe ser mayor que cero.");
      return;
    }
    if (excede) {
      setError("La suma de las líneas supera el monto autorizado.");
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      if (editando) {
        await nucleo.put(`/nucleo/ordenes-compra/${oc?.id}`, empresaId, {
          referencia_interna: referencia.trim() || null,
          fecha_emision: fechaEmision,
          vigencia_desde: vigenciaDesde,
          vigencia_hasta: vigenciaHasta,
          monto_autorizado: Number(montoAutorizado),
          moneda,
          centro_costo_id: centroId || null,
          proyecto: proyecto.trim() || null,
          faena: faena.trim() || null,
          condiciones_pago_dias: condicionesPago ? Number(condicionesPago) : null,
          observaciones: observaciones.trim() || null,
          version: oc?.version,
        });
        toast.success("OC actualizada");
      } else {
        await nucleo.post("/nucleo/ordenes-compra", empresaId, {
          cliente_id: clienteId,
          numero_oc: numeroOc.trim(),
          referencia_interna: referencia.trim() || null,
          fecha_emision: fechaEmision,
          vigencia_desde: vigenciaDesde,
          vigencia_hasta: vigenciaHasta,
          monto_autorizado: Number(montoAutorizado),
          sobregiro_autorizado: puedeSobregiro ? Number(sobregiro || 0) : 0,
          moneda,
          centro_costo_id: centroId || null,
          proyecto: proyecto.trim() || null,
          faena: faena.trim() || null,
          condiciones_pago_dias: condicionesPago ? Number(condicionesPago) : null,
          observaciones: observaciones.trim() || null,
          lineas: lineas
            .filter((l) => l.descripcion.trim() && Number(l.precio_unitario) > 0)
            .map((l) => ({
              descripcion: l.descripcion.trim(),
              cantidad_estimada: Number(l.cantidad_estimada),
              unidad: l.unidad,
              precio_unitario: Number(l.precio_unitario),
              tarifa_id: l.tarifa_id || null,
              centro_costo_id: l.centro_costo_id || null,
            })),
        });
        toast.success("OC creada");
      }
      onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar la OC");
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
          <DialogTitle>{editando ? `Editar OC ${oc?.numero_oc}` : "Nueva orden de compra"}</DialogTitle>
          <DialogDescription>
            El consumo se calcula automáticamente desde los viajes. Las líneas son
            referenciales y no reemplazan el saldo autorizado.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Aviso tono="critico" icono={AlertTriangle}>
            {error}
          </Aviso>
        )}

        <div className="grid gap-s3 sm:grid-cols-2">
          <Campo etiqueta="Cliente" requerido>
            <SelectSimple
              valor={clienteId}
              onCambio={(v) => {
                setClienteId(v);
                setLineas([lineaVacia()]);
                setTarifas([]);
              }}
              placeholder="Seleccione cliente"
              opciones={clientes.map((c) => ({
                valor: c.id,
                etiqueta: `${c.razon_social} · ${c.rut}`,
              }))}
            />
          </Campo>
          <Campo etiqueta="Número de OC" requerido ayuda={editando ? "No se puede cambiar" : "Único por cliente"}>
            <Input
              value={numeroOc}
              onChange={(e) => setNumeroOc(e.target.value)}
              disabled={editando}
              placeholder="OC-2026-001"
            />
          </Campo>
          <Campo etiqueta="Referencia interna">
            <Input value={referencia} onChange={(e) => setReferencia(e.target.value)} />
          </Campo>
          <Campo etiqueta="Centro de costo">
            <SelectSimple
              valor={centroId}
              onCambio={setCentroId}
              placeholder="Sin centro"
              opciones={centros.map((c) => ({
                valor: c.id,
                etiqueta: `${c.codigo} · ${c.nombre}`,
              }))}
            />
          </Campo>
          <Campo etiqueta="Fecha de emisión" requerido>
            <Input
              type="date"
              value={fechaEmision}
              onChange={(e) => setFechaEmision(e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Condiciones de pago (días)">
            <Input
              type="number"
              min={0}
              max={365}
              value={condicionesPago}
              onChange={(e) => setCondicionesPago(e.target.value)}
              placeholder="30"
            />
          </Campo>
          <Campo etiqueta="Vigente desde" requerido>
            <Input
              type="date"
              value={vigenciaDesde}
              onChange={(e) => setVigenciaDesde(e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Vigente hasta" requerido>
            <Input
              type="date"
              value={vigenciaHasta}
              onChange={(e) => setVigenciaHasta(e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Monto autorizado" requerido>
            <Input
              type="number"
              min={0}
              step="0.01"
              value={montoAutorizado}
              onChange={(e) => setMontoAutorizado(e.target.value)}
            />
          </Campo>
          <Campo
            etiqueta="Sobregiro autorizado"
            ayuda={
              puedeSobregiro
                ? "Solo gerencia/admin puede fijarlo al crear"
                : "Solicite aprobación de gerencia"
            }
          >
            <Input
              type="number"
              min={0}
              step="0.01"
              value={sobregiro}
              onChange={(e) => setSobregiro(e.target.value)}
              disabled={!puedeSobregiro || editando}
            />
          </Campo>
          <Campo etiqueta="Proyecto">
            <Input value={proyecto} onChange={(e) => setProyecto(e.target.value)} />
          </Campo>
          <Campo etiqueta="Faena">
            <Input value={faena} onChange={(e) => setFaena(e.target.value)} />
          </Campo>
          <Campo etiqueta="Observaciones" className="sm:col-span-2">
            <AreaTexto
              rows={2}
              value={observaciones}
              onChange={(e) => setObservaciones(e.target.value)}
            />
          </Campo>
        </div>

        {!editando && (
          <section className="space-y-s3 rounded-xl border border-borde p-s3">
            <div className="flex flex-wrap items-center justify-between gap-s2">
              <div>
                <h3 className="text-[17px] font-semibold">Líneas de la OC</h3>
                <p className="text-[14px] text-tinta-3">
                  Total líneas: {formatCLP(totalLineas)} · Autorizado: {formatCLP(Number(montoAutorizado || 0))}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setLineas((l) => [...l, lineaVacia()])}
              >
                <Plus /> Agregar línea
              </Button>
            </div>
            {excede && (
              <p className="text-[14px] text-critico">
                Las líneas superan el monto autorizado. Ajuste cantidades o precios.
              </p>
            )}
            <div className="space-y-s3">
              {lineas.map((linea, indice) => (
                <div
                  key={indice}
                  className="grid gap-s2 rounded-lg border border-borde bg-superficie-hundida/40 p-s3 sm:grid-cols-12"
                >
                  <Campo etiqueta="Descripción" className="sm:col-span-5">
                    <Input
                      value={linea.descripcion}
                      onChange={(e) => setLinea(indice, "descripcion", e.target.value)}
                      placeholder="Flete ruta"
                    />
                  </Campo>
                  <Campo etiqueta="Cantidad" className="sm:col-span-2">
                    <Input
                      type="number"
                      min={0}
                      step="0.001"
                      value={linea.cantidad_estimada}
                      onChange={(e) =>
                        setLinea(indice, "cantidad_estimada", e.target.value)
                      }
                    />
                  </Campo>
                  <Campo etiqueta="Unidad" className="sm:col-span-2">
                    <SelectSimple
                      valor={linea.unidad}
                      onCambio={(v) => setLinea(indice, "unidad", v)}
                      opciones={[
                        { valor: "viaje", etiqueta: "viaje" },
                        { valor: "km", etiqueta: "km" },
                        { valor: "ton", etiqueta: "ton" },
                        { valor: "hora", etiqueta: "hora" },
                      ]}
                    />
                  </Campo>
                  <Campo etiqueta="Precio unitario" className="sm:col-span-3">
                    <Input
                      type="number"
                      min={0}
                      step="0.0001"
                      value={linea.precio_unitario}
                      onChange={(e) =>
                        setLinea(indice, "precio_unitario", e.target.value)
                      }
                    />
                  </Campo>
                  <Campo etiqueta="Tarifa" className="sm:col-span-5">
                    <SelectSimple
                      valor={linea.tarifa_id}
                      onCambio={(v) => setLinea(indice, "tarifa_id", v)}
                      placeholder="Sin tarifa"
                      opciones={tarifas.map((t) => ({
                        valor: t.id,
                        etiqueta: `${t.codigo} · ${t.nombre}`,
                      }))}
                    />
                  </Campo>
                  <div className="flex items-end justify-end sm:col-span-7">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setLineas((actuales) =>
                          actuales.length === 1
                            ? [lineaVacia()]
                            : actuales.filter((_, i) => i !== indice),
                        )
                      }
                    >
                      <Trash2 /> Quitar
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

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
              "Guardar OC"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
