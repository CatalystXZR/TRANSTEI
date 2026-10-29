"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { nucleo, NucleoError } from "@/lib/nucleo";
import { formatCLP, formatFecha, toDatetimeLocal } from "@/lib/format";
import type {
  ClienteOpcionNucleo,
  OrdenCompraOpcionNucleo,
  TarifaOpcionNucleo,
  ViajeNucleo,
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
import { Campo, SelectSimple } from "@/components/formulario";
import { Aviso } from "@/components/sistema";

const TIPOS_CARGA = [
  { valor: "general", etiqueta: "General" },
  { valor: "granel", etiqueta: "Granel" },
  { valor: "pallets", etiqueta: "Pallets" },
  { valor: "contenedor", etiqueta: "Contenedor" },
  { valor: "maquinaria", etiqueta: "Maquinaria" },
  { valor: "refrigerada", etiqueta: "Refrigerada" },
  { valor: "peligrosa", etiqueta: "Carga peligrosa" },
  { valor: "sobredimensionada", etiqueta: "Sobredimensionada" },
  { valor: "ganado", etiqueta: "Ganado" },
  { valor: "otra", etiqueta: "Otra" },
];

type FormNuevoViaje = {
  cliente_id: string;
  orden_compra_id: string;
  tarifa_id: string;
  origen_nombre: string;
  destino_nombre: string;
  inicio_planificado: string;
  fin_planificado: string;
  distancia_km: string;
  tiempo_estimado_h: string;
  peso_bruto_kg: string;
  tipo_carga: string;
  descripcion_carga: string;
  valor_declarado: string;
  carga_peligrosa: boolean;
  numero_un: string;
  refrigerada: boolean;
  temperatura_min_c: string;
  temperatura_max_c: string;
  requiere_grua: boolean;
  requiere_montacargas: boolean;
  instrucciones_especiales: string;
};

function formInicial(): FormNuevoViaje {
  const inicio = new Date();
  inicio.setDate(inicio.getDate() + 1);
  inicio.setHours(8, 0, 0, 0);
  const fin = new Date(inicio);
  fin.setHours(12, 0, 0, 0);
  return {
    cliente_id: "",
    orden_compra_id: "",
    tarifa_id: "",
    origen_nombre: "Santiago",
    destino_nombre: "",
    inicio_planificado: toDatetimeLocal(inicio),
    fin_planificado: toDatetimeLocal(fin),
    distancia_km: "",
    tiempo_estimado_h: "",
    peso_bruto_kg: "25000",
    tipo_carga: "general",
    descripcion_carga: "",
    valor_declarado: "",
    carga_peligrosa: false,
    numero_un: "",
    refrigerada: false,
    temperatura_min_c: "",
    temperatura_max_c: "",
    requiere_grua: false,
    requiere_montacargas: false,
    instrucciones_especiales: "",
  };
}

export function NuevoViajeDialog({
  empresaId,
  onClose,
  onCreado,
}: {
  empresaId: string;
  onClose: () => void;
  onCreado: (viaje: ViajeNucleo) => void;
}) {
  const [form, setForm] = useState<FormNuevoViaje>(formInicial);
  const [clientes, setClientes] = useState<ClienteOpcionNucleo[]>([]);
  const [tarifas, setTarifas] = useState<TarifaOpcionNucleo[]>([]);
  const [ocs, setOcs] = useState<OrdenCompraOpcionNucleo[]>([]);
  const [cargandoClientes, setCargandoClientes] = useState(true);
  const [cargandoCatalogos, setCargandoCatalogos] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errores, setErrores] = useState<string[]>([]);

  useEffect(() => {
    let activo = true;
    nucleo
      .get<ClienteOpcionNucleo[]>("/nucleo/clientes", empresaId)
      .then((data) => {
        if (!activo) return;
        setClientes(data);
        if (data[0]) {
          void cargarCatalogos(data[0].id);
        }
      })
      .catch((e) => {
        if (!activo) return;
        setError(e instanceof Error ? e.message : "No se pudieron cargar los clientes");
      })
      .finally(() => {
        if (activo) setCargandoClientes(false);
      });
    return () => {
      activo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empresaId]);

  async function cargarCatalogos(clienteId: string) {
    setCargandoCatalogos(true);
    setError(null);
    try {
      const [listaTarifas, listaOcs] = await Promise.all([
        nucleo.get<TarifaOpcionNucleo[]>(
          `/nucleo/tarifas/opciones?cliente_id=${encodeURIComponent(clienteId)}`,
          empresaId,
        ),
        nucleo.get<OrdenCompraOpcionNucleo[]>(
          `/nucleo/ordenes-compra/opciones?cliente_id=${encodeURIComponent(clienteId)}`,
          empresaId,
        ),
      ]);
      setTarifas(listaTarifas);
      setOcs(listaOcs);
      setForm((f) => ({
        ...f,
        cliente_id: clienteId,
        tarifa_id: listaTarifas[0]?.id ?? "",
        orden_compra_id: listaOcs[0]?.id ?? "",
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar tarifas y OC");
      setTarifas([]);
      setOcs([]);
    } finally {
      setCargandoCatalogos(false);
    }
  }

  function cambiarCliente(clienteId: string) {
    setForm((f) => ({
      ...f,
      cliente_id: clienteId,
      tarifa_id: "",
      orden_compra_id: "",
    }));
    setErrores([]);
    void cargarCatalogos(clienteId);
  }

  const cliente = clientes.find((c) => c.id === form.cliente_id);
  const tarifa = tarifas.find((t) => t.id === form.tarifa_id);
  const oc = ocs.find((o) => o.id === form.orden_compra_id);
  const saldoOc = oc
    ? Number(oc.monto_autorizado) +
      Number(oc.sobregiro_autorizado) -
      Number(oc.monto_consumido)
    : 0;

  const puedeGuardar =
    !!form.cliente_id &&
    !!form.tarifa_id &&
    form.origen_nombre.trim().length > 0 &&
    form.destino_nombre.trim().length > 0 &&
    Number(form.peso_bruto_kg) > 0 &&
    !guardando &&
    !cargandoCatalogos;

  async function guardar() {
    if (!puedeGuardar) {
      setError("Complete cliente, tarifa, origen, destino y peso.");
      return;
    }
    setGuardando(true);
    setError(null);
    setErrores([]);
    try {
      const body = {
        cliente_id: form.cliente_id,
        orden_compra_id: form.orden_compra_id || null,
        tarifa_id: form.tarifa_id,
        inicio_planificado: new Date(form.inicio_planificado).toISOString(),
        fin_planificado: new Date(form.fin_planificado).toISOString(),
        origen_nombre: form.origen_nombre.trim(),
        destino_nombre: form.destino_nombre.trim(),
        distancia_km: form.distancia_km || null,
        tiempo_estimado_h: form.tiempo_estimado_h || null,
        peso_bruto_kg: form.peso_bruto_kg,
        tipo_carga: form.tipo_carga,
        descripcion_carga: form.descripcion_carga.trim() || null,
        valor_declarado: form.valor_declarado || null,
        carga_peligrosa: form.carga_peligrosa,
        numero_un: form.carga_peligrosa ? form.numero_un.trim() : null,
        refrigerada: form.refrigerada,
        temperatura_min_c: form.refrigerada ? form.temperatura_min_c : null,
        temperatura_max_c: form.refrigerada ? form.temperatura_max_c : null,
        requiere_grua: form.requiere_grua,
        requiere_montacargas: form.requiere_montacargas,
        instrucciones_especiales: form.instrucciones_especiales.trim() || null,
      };
      const viaje = await nucleo.post<ViajeNucleo>(
        "/nucleo/viajes",
        empresaId,
        body,
      );
      toast.success(`Viaje ${viaje.numero_viaje} creado y confirmado`);
      onCreado(viaje);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo crear el viaje");
      if (e instanceof NucleoError) {
        setErrores(e.errores.map((i) => i.mensaje));
      }
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
      <DialogContent
        showCloseButton={!guardando}
        className="max-h-[92vh] overflow-y-auto sm:max-w-3xl"
      >
        <DialogHeader>
          <DialogTitle>Nuevo viaje</DialogTitle>
          <DialogDescription>
            Cree el viaje con su OC, tarifa y carga. Al guardar queda confirmado y
            disponible en la mesa de despacho.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Aviso tono="critico" icono={AlertTriangle}>
            {error}
          </Aviso>
        )}
        {errores.length > 0 && (
          <ul className="list-inside list-disc space-y-s1 rounded-xl border border-critico/20 bg-critico-tenue p-s3 text-[14px] text-critico">
            {errores.map((e, idx) => (
              <li key={idx}>{e}</li>
            ))}
          </ul>
        )}

        <fieldset className="space-y-s3 border-0">
          <legend className="rotulo float-left mb-s2 w-full">Cliente y documentos comerciales</legend>
          <div className="grid gap-s3 sm:grid-cols-3">
            <Campo
              etiqueta="Cliente"
              htmlFor="nv-cliente"
              requerido
              ayuda={cliente ? `${cliente.rut} · ${cliente.dias_pago} días de pago` : undefined}
            >
              {cargandoClientes ? (
                <p className="flex h-11 items-center gap-2 text-[14px] text-tinta-3">
                  <Loader2 className="size-4 animate-spin" /> Cargando…
                </p>
              ) : (
                <SelectSimple
                  id="nv-cliente"
                  valor={form.cliente_id}
                  onCambio={cambiarCliente}
                  placeholder="Seleccione cliente"
                  opciones={clientes.map((c) => ({
                    valor: c.id,
                    etiqueta: c.razon_social,
                  }))}
                />
              )}
            </Campo>

            <Campo
              etiqueta="Orden de compra"
              htmlFor="nv-oc"
              ayuda={
                oc
                  ? `Saldo ${formatCLP(saldoOc)} · ${oc.estado}`
                  : "Sin OC: se puede despachar, pero no facturar"
              }
            >
              <SelectSimple
                id="nv-oc"
                valor={form.orden_compra_id}
                onCambio={(v) => setForm((f) => ({ ...f, orden_compra_id: v }))}
                placeholder={cargandoCatalogos ? "Cargando…" : "Sin OC"}
                opciones={[
                  { valor: "", etiqueta: "Sin OC (no facturable)" },
                  ...ocs.map((o) => ({
                    valor: o.id,
                    etiqueta: `${o.numero_oc} · ${o.estado} · saldo ${formatCLP(
                      Number(o.monto_autorizado) +
                        Number(o.sobregiro_autorizado) -
                        Number(o.monto_consumido),
                    )}`,
                  })),
                ]}
              />
            </Campo>

            <Campo
              etiqueta="Tarifa"
              htmlFor="nv-tarifa"
              requerido
              ayuda={
                tarifa
                  ? `${tarifa.modalidad} · ${tarifa.moneda} · vigente ${formatFecha(
                      tarifa.vigencia_desde,
                    )}${tarifa.vigencia_hasta ? ` a ${formatFecha(tarifa.vigencia_hasta)}` : ""}`
                  : "Seleccione una tarifa del cliente"
              }
            >
              <SelectSimple
                id="nv-tarifa"
                valor={form.tarifa_id}
                onCambio={(v) => setForm((f) => ({ ...f, tarifa_id: v }))}
                placeholder={cargandoCatalogos ? "Cargando…" : "Seleccione tarifa"}
                opciones={tarifas.map((t) => ({
                  valor: t.id,
                  etiqueta: `${t.codigo} · ${t.modalidad} · ${formatCLP(t.precio_unitario)}`,
                }))}
              />
            </Campo>
          </div>
          {tarifa && (
            <p className="text-[14px] text-tinta-3">
              {tarifa.modalidad === "viaje" || tarifa.modalidad === "contenedor"
                ? `Flete estimado: ${formatCLP(tarifa.precio_unitario)}`
                : "El flete se calcula al guardar con la distancia, peso o tiempo ingresados."}
            </p>
          )}
          {!form.orden_compra_id && (
            <Aviso tono="atencion" icono={AlertTriangle}>
              Sin OC el viaje puede operar, pero no se podrá facturar hasta cargarla.
            </Aviso>
          )}
        </fieldset>

        <fieldset className="space-y-s3 border-0">
          <legend className="rotulo float-left mb-s2 w-full">Ruta y ventana</legend>
          <div className="grid gap-s3 sm:grid-cols-2">
            <Campo etiqueta="Origen" htmlFor="nv-origen" requerido>
              <Input
                id="nv-origen"
                value={form.origen_nombre}
                onChange={(e) => setForm((f) => ({ ...f, origen_nombre: e.target.value }))}
                placeholder="Santiago"
              />
            </Campo>
            <Campo etiqueta="Destino" htmlFor="nv-destino" requerido>
              <Input
                id="nv-destino"
                value={form.destino_nombre}
                onChange={(e) => setForm((f) => ({ ...f, destino_nombre: e.target.value }))}
                placeholder="Concepción"
              />
            </Campo>
            <Campo etiqueta="Inicio" htmlFor="nv-inicio" requerido>
              <Input
                id="nv-inicio"
                type="datetime-local"
                value={form.inicio_planificado}
                onChange={(e) =>
                  setForm((f) => ({ ...f, inicio_planificado: e.target.value }))
                }
              />
            </Campo>
            <Campo etiqueta="Fin" htmlFor="nv-fin" requerido>
              <Input
                id="nv-fin"
                type="datetime-local"
                value={form.fin_planificado}
                onChange={(e) =>
                  setForm((f) => ({ ...f, fin_planificado: e.target.value }))
                }
              />
            </Campo>
            <Campo etiqueta="Distancia (km)" htmlFor="nv-distancia">
              <Input
                id="nv-distancia"
                type="number"
                min={0}
                step="0.1"
                value={form.distancia_km}
                onChange={(e) => setForm((f) => ({ ...f, distancia_km: e.target.value }))}
                placeholder="500"
              />
            </Campo>
            <Campo etiqueta="Tiempo estimado (h)" htmlFor="nv-tiempo">
              <Input
                id="nv-tiempo"
                type="number"
                min={0}
                step="0.1"
                value={form.tiempo_estimado_h}
                onChange={(e) =>
                  setForm((f) => ({ ...f, tiempo_estimado_h: e.target.value }))
                }
                placeholder="5"
              />
            </Campo>
          </div>
        </fieldset>

        <fieldset className="space-y-s3 border-0">
          <legend className="rotulo float-left mb-s2 w-full">Carga</legend>
          <div className="grid gap-s3 sm:grid-cols-3">
            <Campo etiqueta="Peso bruto (kg)" htmlFor="nv-peso" requerido>
              <Input
                id="nv-peso"
                type="number"
                min={1}
                step="1"
                value={form.peso_bruto_kg}
                onChange={(e) => setForm((f) => ({ ...f, peso_bruto_kg: e.target.value }))}
              />
            </Campo>
            <Campo etiqueta="Tipo de carga" htmlFor="nv-tipo">
              <SelectSimple
                id="nv-tipo"
                valor={form.tipo_carga}
                onCambio={(v) => setForm((f) => ({ ...f, tipo_carga: v }))}
                opciones={TIPOS_CARGA}
              />
            </Campo>
            <Campo etiqueta="Valor declarado (CLP)" htmlFor="nv-valor">
              <Input
                id="nv-valor"
                type="number"
                min={0}
                step="1"
                value={form.valor_declarado}
                onChange={(e) =>
                  setForm((f) => ({ ...f, valor_declarado: e.target.value }))
                }
                placeholder="Opcional"
              />
            </Campo>
          </div>
          <Campo etiqueta="Descripción de la carga" htmlFor="nv-descripcion">
            <Input
              id="nv-descripcion"
              value={form.descripcion_carga}
              onChange={(e) =>
                setForm((f) => ({ ...f, descripcion_carga: e.target.value }))
              }
              placeholder="Ej: 20 pallets de alimentos"
            />
          </Campo>
          <div className="flex flex-wrap gap-s4">
            <label className="flex items-center gap-s2 text-[15px]">
              <input
                type="checkbox"
                className="size-4 accent-marca"
                checked={form.carga_peligrosa}
                onChange={(e) =>
                  setForm((f) => ({ ...f, carga_peligrosa: e.target.checked }))
                }
              />
              Carga peligrosa
            </label>
            <label className="flex items-center gap-s2 text-[15px]">
              <input
                type="checkbox"
                className="size-4 accent-marca"
                checked={form.refrigerada}
                onChange={(e) =>
                  setForm((f) => ({ ...f, refrigerada: e.target.checked }))
                }
              />
              Refrigerada
            </label>
            <label className="flex items-center gap-s2 text-[15px]">
              <input
                type="checkbox"
                className="size-4 accent-marca"
                checked={form.requiere_grua}
                onChange={(e) =>
                  setForm((f) => ({ ...f, requiere_grua: e.target.checked }))
                }
              />
              Requiere grúa
            </label>
            <label className="flex items-center gap-s2 text-[15px]">
              <input
                type="checkbox"
                className="size-4 accent-marca"
                checked={form.requiere_montacargas}
                onChange={(e) =>
                  setForm((f) => ({ ...f, requiere_montacargas: e.target.checked }))
                }
              />
              Requiere montacargas
            </label>
          </div>
          {form.carga_peligrosa && (
            <Campo etiqueta="Número UN" htmlFor="nv-un" requerido>
              <Input
                id="nv-un"
                value={form.numero_un}
                onChange={(e) => setForm((f) => ({ ...f, numero_un: e.target.value }))}
                placeholder="Ej: UN 1263"
              />
            </Campo>
          )}
          {form.refrigerada && (
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Temperatura mínima (°C)" htmlFor="nv-tmin" requerido>
                <Input
                  id="nv-tmin"
                  type="number"
                  step="0.1"
                  value={form.temperatura_min_c}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, temperatura_min_c: e.target.value }))
                  }
                />
              </Campo>
              <Campo etiqueta="Temperatura máxima (°C)" htmlFor="nv-tmax" requerido>
                <Input
                  id="nv-tmax"
                  type="number"
                  step="0.1"
                  value={form.temperatura_max_c}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, temperatura_max_c: e.target.value }))
                  }
                />
              </Campo>
            </div>
          )}
          <Campo etiqueta="Instrucciones especiales" htmlFor="nv-instrucciones">
            <Input
              id="nv-instrucciones"
              value={form.instrucciones_especiales}
              onChange={(e) =>
                setForm((f) => ({ ...f, instrucciones_especiales: e.target.value }))
              }
              placeholder="Opcional"
            />
          </Campo>
        </fieldset>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={guardando}>
            Cancelar
          </Button>
          <Button onClick={() => void guardar()} disabled={!puedeGuardar}>
            {guardando ? (
              <>
                <Loader2 className="animate-spin" /> Guardando…
              </>
            ) : (
              <>
                Crear y confirmar <ArrowRight />
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
