"use client";

import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2, Wrench } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { Tracto } from "@/types";
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

interface Pauta {
  id: string;
  item: string;
  intervalo_km: number;
  orden: number;
  activo: boolean;
}

interface ItemEstado {
  pauta_id: string;
  item: string;
  intervalo_km: number;
  ultimo_km: number | null;
  ultima_fecha: string | null;
  proximo_km: number | null;
  km_restante: number | null;
  estado: "ok" | "por_vencer" | "pendiente" | "sin_registro";
}

interface EstadoTracto {
  tracto_id: string;
  patente: string;
  km_actual: number;
  items: ItemEstado[];
}

const ESTADO_MANT_COLOR: Record<string, string> = {
  ok: "bg-green-100 text-green-800",
  por_vencer: "bg-yellow-500 text-black",
  pendiente: "bg-red-600 text-white",
  sin_registro: "bg-gray-100 text-gray-600",
};

const ESTADO_MANT_LABEL: Record<string, string> = {
  ok: "Al día",
  por_vencer: "Por vencer",
  pendiente: "¡Pendiente!",
  sin_registro: "Sin registro",
};

export default function MantenimientoPage() {
  const { usuario } = useAuth();
  const [pestana, setPestana] = useState<"estado" | "pauta" | "registros">("estado");
  const [estados, setEstados] = useState<EstadoTracto[]>([]);
  const [pautas, setPautas] = useState<Pauta[]>([]);
  const [tractos, setTractos] = useState<Tracto[]>([]);
  const [cargando, setCargando] = useState(true);

  const [dialogoPauta, setDialogoPauta] = useState(false);
  const [editandoPauta, setEditandoPauta] = useState<Pauta | null>(null);
  const [formPauta, setFormPauta] = useState({ item: "", intervalo_km: "20000" });

  const [dialogoMant, setDialogoMant] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [formMant, setFormMant] = useState({
    tracto_id: "",
    pauta_id: "",
    km: "",
    fecha: new Date().toISOString().slice(0, 10),
    costo: "",
  });

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  function recargar() {
    Promise.all([
      api.get<EstadoTracto[]>("/mantenimiento/estado"),
      api.get<Pauta[]>("/pautas"),
      api.get<Tracto[]>("/tractos?activo=true"),
    ])
      .then(([e, p, t]) => {
        setEstados(e ?? []);
        setPautas(p ?? []);
        setTractos(t ?? []);
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : "Error al cargar"))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    Promise.all([
      api.get<EstadoTracto[]>("/mantenimiento/estado"),
      api.get<Pauta[]>("/pautas"),
      api.get<Tracto[]>("/tractos?activo=true"),
    ])
      .then(([e, p, t]) => {
        if (!activo) return;
        setEstados(e ?? []);
        setPautas(p ?? []);
        setTractos(t ?? []);
      })
      .catch((err) => {
        if (activo) toast.error(err instanceof Error ? err.message : "Error al cargar");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  async function guardarPauta() {
    if (!formPauta.item.trim() || !Number(formPauta.intervalo_km)) {
      toast.error("Complete item e intervalo en km");
      return;
    }
    try {
      if (editandoPauta) {
        await api.put(`/pautas/${editandoPauta.id}`, {
          item: formPauta.item.trim(),
          intervalo_km: Number(formPauta.intervalo_km),
          orden: editandoPauta.orden,
        });
        toast.success("Ítem actualizado");
      } else {
        await api.post("/pautas", {
          item: formPauta.item.trim(),
          intervalo_km: Number(formPauta.intervalo_km),
          orden: pautas.length + 1,
        });
        toast.success("Ítem agregado a la pauta");
      }
      setDialogoPauta(false);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    }
  }

  async function eliminarPauta(p: Pauta) {
    if (!confirm(`¿Quitar "${p.item}" de la pauta de mantenimiento?`)) return;
    try {
      await api.del(`/pautas/${p.id}`);
      toast.success("Ítem eliminado");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function guardarMantencion() {
    if (!formMant.tracto_id || !formMant.pauta_id || !formMant.km) {
      toast.error("Seleccione camión, ítem e ingrese el kilometraje");
      return;
    }
    setGuardando(true);
    try {
      await api.post(
        `/mantenimientos?tracto_id=${formMant.tracto_id}&pauta_id=${formMant.pauta_id}&km=${Number(formMant.km)}&fecha=${formMant.fecha}&costo=${Number(formMant.costo) || 0}`,
        {},
      );
      toast.success("Mantención registrada");
      setDialogoMant(false);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al registrar");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-[#2A237A]">Mantenimiento</h1>
        {puedeEscribir && (
          <Button
            onClick={() => setDialogoMant(true)}
            className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
          >
            <Wrench className="h-5 w-5" />
            Registrar Mantención
          </Button>
        )}
      </div>

      <div className="flex rounded-lg border bg-white p-1 sm:w-fit">
        {(
          [
            ["estado", "Estado de Flota"],
            ["pauta", "Pauta de Mantenimiento"],
            ["registros", "Registros"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setPestana(key)}
            className={`rounded-md px-4 py-2 text-base font-medium ${
              pestana === key ? "bg-[#2A237A] text-white" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {pestana === "estado" && (
        <div className="space-y-4">
          <p className="rounded-lg bg-yellow-50 p-3 text-base text-yellow-800">
            Alerta amarilla a 5.000 km antes del vencimiento. Al superar el km de cambio, la
            alerta roja queda <strong>permanente</strong> hasta registrar la mantención.
          </p>
          {cargando ? (
            <p className="py-8 text-center text-gray-500">Cargando…</p>
          ) : (
            <div className="space-y-4">
              {estados.map((t) => (
                <div key={t.tracto_id} className="rounded-lg border bg-white p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-lg font-bold text-[#2A237A]">
                      {t.patente}
                      <span className="ml-3 text-sm font-normal text-gray-500">
                        KM actual: {new Intl.NumberFormat("es-CL").format(t.km_actual)}
                      </span>
                    </p>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {t.items.map((item) => (
                      <div
                        key={item.pauta_id}
                        className={`rounded-lg border p-3 ${
                          item.estado === "pendiente"
                            ? "border-red-300 bg-red-50"
                            : item.estado === "por_vencer"
                              ? "border-yellow-300 bg-yellow-50"
                              : "border-gray-200"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <p className="text-base font-medium">{item.item}</p>
                          <Badge className={`${ESTADO_MANT_COLOR[item.estado]} text-sm`}>
                            {ESTADO_MANT_LABEL[item.estado]}
                          </Badge>
                        </div>
                        <p className="mt-1 text-sm text-gray-600">
                          {item.ultimo_km !== null ? (
                            <>
                              Último: {item.ultimo_km.toLocaleString("es-CL")} km (
                              {formatFecha(item.ultima_fecha)}) · Próximo:{" "}
                              {item.proximo_km?.toLocaleString("es-CL")} km
                            </>
                          ) : (
                            <>Cada {item.intervalo_km.toLocaleString("es-CL")} km</>
                          )}
                        </p>
                        {item.estado === "pendiente" && (
                          <p className="mt-1 text-sm font-bold text-red-700">
                            Superado en {(item.km_restante ?? 0) * -1} km — requiere mantención
                          </p>
                        )}
                        {item.estado === "por_vencer" && (
                          <p className="mt-1 text-sm font-medium text-yellow-700">
                            Faltan {item.km_restante} km
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {pestana === "pauta" && (
        <div className="space-y-4">
          {puedeEscribir && (
            <Button
              onClick={() => {
                setEditandoPauta(null);
                setFormPauta({ item: "", intervalo_km: "20000" });
                setDialogoPauta(true);
              }}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              <Plus className="h-5 w-5" />
              Agregar Ítem
            </Button>
          )}
          <div className="overflow-x-auto rounded-lg border bg-white">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-base">Ítem</TableHead>
                  <TableHead className="text-base">Cada (km)</TableHead>
                  {puedeEscribir && <TableHead className="w-28 text-base">Acciones</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {pautas.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="text-base font-medium">{p.item}</TableCell>
                    <TableCell className="text-base">
                      {p.intervalo_km.toLocaleString("es-CL")} km
                    </TableCell>
                    {puedeEscribir && (
                      <TableCell>
                        <div className="flex gap-2">
                          <Button
                            size="icon"
                            variant="outline"
                            onClick={() => {
                              setEditandoPauta(p);
                              setFormPauta({
                                item: p.item,
                                intervalo_km: String(p.intervalo_km),
                              });
                              setDialogoPauta(true);
                            }}
                            aria-label="Editar ítem"
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="outline"
                            className="border-red-200 text-red-600 hover:bg-red-50"
                            onClick={() => eliminarPauta(p)}
                            aria-label="Eliminar ítem"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {pestana === "registros" && (
        <p className="rounded-lg border bg-white p-6 text-center text-base text-gray-500">
          Los registros históricos se muestran en la Ficha de Equipos (Fase 4b). Cada mantención
          registrada actualiza automáticamente el estado y el kilometraje del camión.
        </p>
      )}

      <Dialog open={dialogoPauta} onOpenChange={setDialogoPauta}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-xl">
              {editandoPauta ? "Editar Ítem" : "Nuevo Ítem de Pauta"}
            </DialogTitle>
            <DialogDescription className="text-base">
              Ej: Cambio de aceite cada 20.000 km, Engrase cada 5.000 km.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Ítem</Label>
              <Input
                value={formPauta.item}
                onChange={(e) => setFormPauta({ ...formPauta, item: e.target.value })}
                className="text-base"
                placeholder="Cambio de aceite"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base">Intervalo (km)</Label>
              <Input
                type="number"
                min={1000}
                value={formPauta.intervalo_km}
                onChange={(e) => setFormPauta({ ...formPauta, intervalo_km: e.target.value })}
                className="text-base"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogoPauta(false)} className="text-base">
              Cancelar
            </Button>
            <Button onClick={guardarPauta} className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90">
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoMant} onOpenChange={setDialogoMant}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-xl">Registrar Mantención</DialogTitle>
            <DialogDescription className="text-base">
              El kilometraje registrado actualizará el estado del camión.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Camión *</Label>
              <Select
                value={formMant.tracto_id}
                onValueChange={(v) => setFormMant({ ...formMant, tracto_id: v ?? "" })}
              >
                <SelectTrigger className="text-base">
                  <SelectValue placeholder="Seleccione camión" />
                </SelectTrigger>
                <SelectContent>
                  {tractos.map((t) => (
                    <SelectItem key={t.id} value={t.id} className="text-base">
                      {t.patente} ({t.km_actual.toLocaleString("es-CL")} km)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Ítem de mantención *</Label>
              <Select
                value={formMant.pauta_id}
                onValueChange={(v) => setFormMant({ ...formMant, pauta_id: v ?? "" })}
              >
                <SelectTrigger className="text-base">
                  <SelectValue placeholder="Seleccione ítem" />
                </SelectTrigger>
                <SelectContent>
                  {pautas.map((p) => (
                    <SelectItem key={p.id} value={p.id} className="text-base">
                      {p.item} (cada {p.intervalo_km.toLocaleString("es-CL")} km)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Kilometraje *</Label>
                <Input
                  type="number"
                  value={formMant.km}
                  onChange={(e) => setFormMant({ ...formMant, km: e.target.value })}
                  className="text-base"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-base">Fecha</Label>
                <Input
                  type="date"
                  value={formMant.fecha}
                  onChange={(e) => setFormMant({ ...formMant, fecha: e.target.value })}
                  className="text-base"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Costo ($)</Label>
              <Input
                type="number"
                value={formMant.costo}
                onChange={(e) => setFormMant({ ...formMant, costo: e.target.value })}
                className="text-base"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogoMant(false)} className="text-base">
              Cancelar
            </Button>
            <Button
              onClick={guardarMantencion}
              disabled={guardando}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              {guardando ? "Guardando…" : "Registrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
