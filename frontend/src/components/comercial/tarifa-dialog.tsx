"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { nucleo, NucleoError } from "@/lib/nucleo";
import type {
  ClienteNucleo,
  ModalidadTarifaNucleo,
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

const MODALIDADES: { valor: ModalidadTarifaNucleo; etiqueta: string }[] = [
  { valor: "viaje", etiqueta: "Por viaje" },
  { valor: "km", etiqueta: "Por km" },
  { valor: "tonelada", etiqueta: "Por tonelada" },
  { valor: "tonelada_km", etiqueta: "Por tonelada-km" },
  { valor: "hora", etiqueta: "Por hora" },
  { valor: "contenedor", etiqueta: "Por contenedor" },
  { valor: "estadia", etiqueta: "Estadía" },
  { valor: "mixta", etiqueta: "Mixta" },
];

const TIPOS_CARGA = [
  "general",
  "granel",
  "pallets",
  "contenedor",
  "maquinaria",
  "refrigerada",
  "peligrosa",
  "sobredimensionada",
  "ganado",
  "otra",
].map((v) => ({ valor: v, etiqueta: v.replaceAll("_", " ") }));

const TIPOS_RAMPLA = [
  "plana",
  "sider",
  "refrigerada",
  "portacontenedor",
  "cisterna",
  "cama_baja",
  "granelera",
  "otra",
].map((v) => ({ valor: v, etiqueta: v.replaceAll("_", " ") }));

type Form = {
  cliente_id: string;
  codigo: string;
  nombre: string;
  descripcion: string;
  modalidad: string;
  origen: string;
  destino: string;
  tipo_rampla: string;
  tipo_carga: string;
  vigencia_desde: string;
  vigencia_hasta: string;
  precio_unitario: string;
  minimo_cobro: string;
  incluye_peajes: boolean;
  incluye_combustible: boolean;
  precio_diesel_base: string;
  rendimiento_km_l: string;
  participacion_combustible: string;
  activo: boolean;
};

function hoyISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function formDesde(tarifa: TarifaNucleo | null): Form {
  if (!tarifa) {
    return {
      cliente_id: "",
      codigo: "",
      nombre: "",
      descripcion: "",
      modalidad: "viaje",
      origen: "",
      destino: "",
      tipo_rampla: "",
      tipo_carga: "",
      vigencia_desde: hoyISO(),
      vigencia_hasta: "",
      precio_unitario: "",
      minimo_cobro: "0",
      incluye_peajes: false,
      incluye_combustible: false,
      precio_diesel_base: "",
      rendimiento_km_l: "",
      participacion_combustible: "",
      activo: true,
    };
  }
  return {
    cliente_id: tarifa.cliente_id,
    codigo: tarifa.codigo,
    nombre: tarifa.nombre,
    descripcion: tarifa.descripcion ?? "",
    modalidad: tarifa.modalidad,
    origen: tarifa.origen ?? "",
    destino: tarifa.destino ?? "",
    tipo_rampla: tarifa.tipo_rampla ?? "",
    tipo_carga: tarifa.tipo_carga ?? "",
    vigencia_desde: tarifa.vigencia_desde,
    vigencia_hasta: tarifa.vigencia_hasta ?? "",
    precio_unitario: tarifa.precio_unitario,
    minimo_cobro: tarifa.minimo_cobro,
    incluye_peajes: tarifa.incluye_peajes,
    incluye_combustible: tarifa.incluye_combustible,
    precio_diesel_base: tarifa.precio_diesel_base ?? "",
    rendimiento_km_l: tarifa.rendimiento_km_l ?? "",
    participacion_combustible: tarifa.participacion_combustible ?? "",
    activo: tarifa.activo,
  };
}

export function TarifaDialog({
  empresaId,
  moneda,
  tarifa,
  onClose,
  onGuardado,
}: {
  empresaId: string;
  moneda: string;
  tarifa: TarifaNucleo | null;
  onClose: () => void;
  onGuardado: () => void;
}) {
  const editando = Boolean(tarifa);
  const [form, setForm] = useState<Form>(() => formDesde(tarifa));
  const [clientes, setClientes] = useState<ClienteNucleo[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    nucleo
      .get<ClienteNucleo[]>("/nucleo/clientes?activo=true", empresaId)
      .then((data) => {
        if (activo) setClientes(data);
      })
      .catch(() => {
        if (activo) setClientes([]);
      });
    return () => {
      activo = false;
    };
  }, [empresaId]);

  function set<K extends keyof Form>(campo: K, valor: Form[K]) {
    setForm((f) => ({ ...f, [campo]: valor }));
  }

  const faltan = [
    !form.cliente_id && "cliente",
    !form.codigo.trim() && "código",
    !form.nombre.trim() && "nombre",
    !form.vigencia_desde && "vigencia desde",
    !form.precio_unitario && "precio unitario",
  ].filter(Boolean);

  async function guardar() {
    if (faltan.length > 0) {
      setError(`Complete: ${faltan.join(", ")}.`);
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const body = {
        cliente_id: form.cliente_id,
        codigo: form.codigo.trim(),
        nombre: form.nombre.trim(),
        descripcion: form.descripcion.trim() || null,
        modalidad: form.modalidad,
        origen: form.origen.trim() || null,
        destino: form.destino.trim() || null,
        tipo_rampla: form.tipo_rampla || null,
        tipo_carga: form.tipo_carga || null,
        vigencia_desde: form.vigencia_desde,
        vigencia_hasta: form.vigencia_hasta || null,
        moneda,
        precio_unitario: Number(form.precio_unitario || 0),
        minimo_cobro: Number(form.minimo_cobro || 0),
        incluye_peajes: form.incluye_peajes,
        incluye_combustible: form.incluye_combustible,
        precio_diesel_base: form.precio_diesel_base
          ? Number(form.precio_diesel_base)
          : null,
        rendimiento_km_l: form.rendimiento_km_l
          ? Number(form.rendimiento_km_l)
          : null,
        participacion_combustible: form.participacion_combustible
          ? Number(form.participacion_combustible)
          : null,
        activo: form.activo,
        ...(editando ? { version: tarifa?.version } : {}),
      };
      if (editando) {
        await nucleo.put(`/nucleo/tarifas/${tarifa?.id}`, empresaId, body);
        toast.success("Tarifa actualizada");
      } else {
        await nucleo.post("/nucleo/tarifas", empresaId, body);
        toast.success("Tarifa creada");
      }
      onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar la tarifa");
      if (e instanceof NucleoError && e.errores.length > 0) {
        setError(e.errores.map((i) => i.mensaje).join(" "));
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
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{editando ? "Editar tarifa" : "Nueva tarifa"}</DialogTitle>
          <DialogDescription>
            El precio y la vigencia quedan congelados en el snapshot de cada viaje.
            Los cambios quedan en auditoría.
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
              valor={form.cliente_id}
              onCambio={(v) => set("cliente_id", v)}
              placeholder="Seleccione cliente"
              opciones={clientes.map((c) => ({
                valor: c.id,
                etiqueta: `${c.razon_social} · ${c.rut}`,
              }))}
            />
          </Campo>
          <Campo etiqueta="Código" requerido ayuda="Único por cliente">
            <Input
              value={form.codigo}
              onChange={(e) => set("codigo", e.target.value)}
              placeholder="T-SCL-CCP"
            />
          </Campo>
          <Campo etiqueta="Nombre" requerido className="sm:col-span-2">
            <Input
              value={form.nombre}
              onChange={(e) => set("nombre", e.target.value)}
              placeholder="Santiago - Concepción"
            />
          </Campo>
          <Campo etiqueta="Modalidad" requerido>
            <SelectSimple
              valor={form.modalidad}
              onCambio={(v) => set("modalidad", v)}
              opciones={MODALIDADES}
            />
          </Campo>
          <Campo etiqueta="Moneda">
            <Input value={moneda} disabled />
          </Campo>
          <Campo etiqueta="Origen">
            <Input
              value={form.origen}
              onChange={(e) => set("origen", e.target.value)}
              placeholder="Santiago"
            />
          </Campo>
          <Campo etiqueta="Destino">
            <Input
              value={form.destino}
              onChange={(e) => set("destino", e.target.value)}
              placeholder="Concepción"
            />
          </Campo>
          <Campo etiqueta="Tipo de rampla">
            <SelectSimple
              valor={form.tipo_rampla}
              onCambio={(v) => set("tipo_rampla", v)}
              placeholder="Cualquiera"
              opciones={TIPOS_RAMPLA}
            />
          </Campo>
          <Campo etiqueta="Tipo de carga">
            <SelectSimple
              valor={form.tipo_carga}
              onCambio={(v) => set("tipo_carga", v)}
              placeholder="Cualquiera"
              opciones={TIPOS_CARGA}
            />
          </Campo>
          <Campo etiqueta="Vigente desde" requerido>
            <Input
              type="date"
              value={form.vigencia_desde}
              onChange={(e) => set("vigencia_desde", e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Vigente hasta" ayuda="Vacío = sin vencimiento">
            <Input
              type="date"
              value={form.vigencia_hasta}
              onChange={(e) => set("vigencia_hasta", e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Precio unitario" requerido>
            <Input
              type="number"
              min={0}
              step="0.0001"
              value={form.precio_unitario}
              onChange={(e) => set("precio_unitario", e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Mínimo de cobro">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.minimo_cobro}
              onChange={(e) => set("minimo_cobro", e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Diésel base $/L" ayuda="Para reajuste de combustible">
            <Input
              type="number"
              min={0}
              step="0.0001"
              value={form.precio_diesel_base}
              onChange={(e) => set("precio_diesel_base", e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Rendimiento km/L">
            <Input
              type="number"
              min={0}
              step="0.001"
              value={form.rendimiento_km_l}
              onChange={(e) => set("rendimiento_km_l", e.target.value)}
            />
          </Campo>
          <Campo etiqueta="Descripción" className="sm:col-span-2">
            <AreaTexto
              rows={2}
              value={form.descripcion}
              onChange={(e) => set("descripcion", e.target.value)}
            />
          </Campo>
          <div className="flex flex-wrap gap-s4 sm:col-span-2">
            <label className="flex items-center gap-s2 text-[15px]">
              <input
                type="checkbox"
                className="size-4 accent-marca"
                checked={form.incluye_peajes}
                onChange={(e) => set("incluye_peajes", e.target.checked)}
              />
              Incluye peajes
            </label>
            <label className="flex items-center gap-s2 text-[15px]">
              <input
                type="checkbox"
                className="size-4 accent-marca"
                checked={form.incluye_combustible}
                onChange={(e) => set("incluye_combustible", e.target.checked)}
              />
              Incluye combustible
            </label>
            <label className="flex items-center gap-s2 text-[15px]">
              <input
                type="checkbox"
                className="size-4 accent-marca"
                checked={form.activo}
                onChange={(e) => set("activo", e.target.checked)}
              />
              Activa
            </label>
          </div>
        </div>

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
              "Guardar tarifa"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
