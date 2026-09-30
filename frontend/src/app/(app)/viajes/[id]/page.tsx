"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Camera, ExternalLink, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiUpload } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { CategoriaGasto, Gasto, Viaje } from "@/types";
import {
  CATEGORIA_GASTO_LABEL,
  ESTADO_VIAJE_COLOR,
  ESTADO_VIAJE_LABEL,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputCLP } from "@/components/ui-inputs/input-clp";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

const CATEGORIAS = Object.keys(CATEGORIA_GASTO_LABEL) as CategoriaGasto[];

const ACCIONES_ESTADO: Record<string, { destino: string; etiqueta: string }[]> = {
  programado: [{ destino: "en_ruta", etiqueta: "Iniciar Viaje" }],
  en_ruta: [
    { destino: "finalizado", etiqueta: "Finalizar Viaje" },
    { destino: "programado", etiqueta: "Volver a Programado" },
  ],
  finalizado: [{ destino: "en_ruta", etiqueta: "Volver a En Ruta" }],
  facturado: [{ destino: "finalizado", etiqueta: "Quitar de Facturación" }],
};

export default function ViajeDetallePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { usuario } = useAuth();
  const [viaje, setViaje] = useState<Viaje | null>(null);
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [cargando, setCargando] = useState(true);

  const [dialogoGasto, setDialogoGasto] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [formGasto, setFormGasto] = useState({
    categoria: "combustible" as CategoriaGasto,
    monto: 0,
    iva_recuperable: false,
    fecha: new Date().toISOString().slice(0, 10),
    notas: "",
  });
  const [archivo, setArchivo] = useState<File | null>(null);

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  const cargar = useCallback(() => {
    Promise.all([
      api.get<Viaje>(`/viajes/${params.id}`),
      api.get<Gasto[]>(`/viajes/${params.id}/gastos`),
    ])
      .then(([v, g]) => {
        setViaje(v ?? null);
        setGastos(g ?? []);
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar"))
      .finally(() => setCargando(false));
  }, [params.id]);

  useEffect(() => {
    let activo = true;
    Promise.all([
      api.get<Viaje>(`/viajes/${params.id}`),
      api.get<Gasto[]>(`/viajes/${params.id}/gastos`),
    ])
      .then(([v, g]) => {
        if (!activo) return;
        setViaje(v ?? null);
        setGastos(g ?? []);
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

  async function cambiarEstado(destino: string) {
    try {
      await api.patch(`/viajes/${params.id}/estado`, { estado: destino });
      toast.success(`Viaje actualizado: ${ESTADO_VIAJE_LABEL[destino as keyof typeof ESTADO_VIAJE_LABEL]}`);
      cargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al cambiar estado");
    }
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
    fd.append("fecha", formGasto.fecha);
    if (formGasto.notas.trim()) fd.append("notas", formGasto.notas.trim());
    if (archivo) fd.append("archivo", archivo);
    try {
      await apiUpload(`/viajes/${params.id}/gastos`, fd);
      toast.success("Gasto registrado");
      setDialogoGasto(false);
      setArchivo(null);
      cargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar gasto");
    } finally {
      setGuardando(false);
    }
  }

  async function eliminarGasto(gasto: Gasto) {
    if (!confirm(`¿Eliminar este gasto de ${formatCLP(gasto.monto)}?`)) return;
    try {
      await api.del(`/gastos/${gasto.id}`);
      toast.success("Gasto eliminado");
      cargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al eliminar");
    }
  }

  async function verRespaldo(gasto: Gasto) {
    try {
      const res = await api.get<{ url: string }>(`/gastos/${gasto.id}/respaldo`);
      if (res?.url) window.open(res.url, "_blank");
    } catch {
      toast.error("No se pudo obtener el respaldo");
    }
  }

  if (cargando) {
    return <p className="py-10 text-center text-gray-500">Cargando viaje…</p>;
  }
  if (!viaje) {
    return (
      <div className="space-y-4 py-10 text-center">
        <p className="text-lg text-gray-500">Viaje no encontrado</p>
        <Button variant="outline" onClick={() => router.push("/viajes")}>
          Volver a Viajes
        </Button>
      </div>
    );
  }

  const totalGastos = gastos.reduce((acc, g) => acc + Number(g.monto), 0);
  const rentabilidad = Number(viaje.valor_flete_neto) - totalGastos;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/viajes")} aria-label="Volver">
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-[#2A237A]">
              {viaje.origen} → {viaje.destino}
            </h1>
            <p className="text-base text-gray-500">{formatFecha(viaje.fecha_inicio)}</p>
          </div>
          <Badge className={`${ESTADO_VIAJE_COLOR[viaje.estado]} text-sm`}>
            {ESTADO_VIAJE_LABEL[viaje.estado]}
          </Badge>
        </div>
        {puedeEscribir &&
          (ACCIONES_ESTADO[viaje.estado] ?? []).map((a) => (
            <Button
              key={a.destino}
              onClick={() => cambiarEstado(a.destino)}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              {a.etiqueta}
            </Button>
          ))}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-gray-500">Valor Flete</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-[#2A237A]">
              {formatCLP(viaje.valor_flete_neto)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-gray-500">Gastos de Ruta</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-red-600">{formatCLP(totalGastos)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-gray-500">Rentabilidad (Flete − Gastos)</CardTitle>
          </CardHeader>
          <CardContent>
            <p className={`text-3xl font-bold ${rentabilidad >= 0 ? "text-green-700" : "text-red-600"}`}>
              {formatCLP(rentabilidad)}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Datos del Viaje</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 text-base sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <p className="text-gray-500">Cliente</p>
            <p className="font-medium">{viaje.cliente_nombre}</p>
          </div>
          <div>
            <p className="text-gray-500">Chofer</p>
            <p className="font-medium">{viaje.chofer_nombre}</p>
          </div>
          <div>
            <p className="text-gray-500">Camión</p>
            <p className="font-medium">{viaje.tracto_patente}</p>
          </div>
          <div>
            <p className="text-gray-500">Rampla</p>
            <p className="font-medium">{viaje.rampla_patente}</p>
          </div>
          <div>
            <p className="text-gray-500">Fecha Fin</p>
            <p className="font-medium">{formatFecha(viaje.fecha_fin)}</p>
          </div>
          {viaje.notas && (
            <div>
              <p className="text-gray-500">Notas</p>
              <p className="font-medium">{viaje.notas}</p>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-[#2A237A]">Gastos del Viaje</h2>
          {puedeEscribir && viaje.estado !== "facturado" && (
            <Button onClick={() => setDialogoGasto(true)} className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90">
              <Plus className="h-5 w-5" />
              Registrar Gasto
            </Button>
          )}
        </div>
        <div className="overflow-x-auto rounded-lg border bg-white">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-base">Fecha</TableHead>
                <TableHead className="text-base">Categoría</TableHead>
                <TableHead className="text-base">Monto</TableHead>
                <TableHead className="text-base">IVA Rec.</TableHead>
                <TableHead className="text-base">Respaldo</TableHead>
                {puedeEscribir && <TableHead className="w-16 text-base"></TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {gastos.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-gray-500">
                    Sin gastos registrados
                  </TableCell>
                </TableRow>
              ) : (
                gastos.map((g) => (
                  <TableRow key={g.id}>
                    <TableCell className="text-base">{formatFecha(g.fecha)}</TableCell>
                    <TableCell className="text-base">
                      {CATEGORIA_GASTO_LABEL[g.categoria]}
                    </TableCell>
                    <TableCell className="text-base font-semibold">{formatCLP(g.monto)}</TableCell>
                    <TableCell className="text-base">
                      {g.iva_recuperable ? (
                        <Badge className="bg-green-100 text-green-800">Sí</Badge>
                      ) : (
                        <Badge className="bg-gray-100 text-gray-600">No</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {g.respaldo_url ? (
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => verRespaldo(g)}
                          aria-label="Ver respaldo"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      ) : (
                        <span className="text-sm text-gray-400">-</span>
                      )}
                    </TableCell>
                    {puedeEscribir && (
                      <TableCell>
                        <Button
                          size="icon"
                          variant="outline"
                          className="border-red-200 text-red-600 hover:bg-red-50"
                          onClick={() => eliminarGasto(g)}
                          aria-label="Eliminar gasto"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={dialogoGasto} onOpenChange={setDialogoGasto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-xl">Registrar Gasto</DialogTitle>
            <DialogDescription className="text-base">
              Adjunte una foto de la boleta si la tiene a mano.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Categoría</Label>
                <Select
                  value={formGasto.categoria}
                  onValueChange={(v) => setFormGasto({ ...formGasto, categoria: v as CategoriaGasto })}
                >
                  <SelectTrigger className="text-base">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIAS.map((c) => (
                      <SelectItem key={c} value={c} className="text-base">
                        {CATEGORIA_GASTO_LABEL[c]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-base">Monto ($) *</Label>
                <InputCLP
                  value={formGasto.monto}
                  onChange={(v) => setFormGasto({ ...formGasto, monto: v })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 items-end gap-4">
              <div className="space-y-2">
                <Label className="text-base">Fecha</Label>
                <Input
                  type="date"
                  value={formGasto.fecha}
                  onChange={(e) => setFormGasto({ ...formGasto, fecha: e.target.value })}
                  className="text-base"
                />
              </div>
              <label className="flex items-center gap-2 pb-2 text-base">
                <input
                  type="checkbox"
                  checked={formGasto.iva_recuperable}
                  onChange={(e) =>
                    setFormGasto({ ...formGasto, iva_recuperable: e.target.checked })
                  }
                  className="h-5 w-5 accent-[#2A237A]"
                />
                IVA recuperable
              </label>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Notas</Label>
              <Input
                value={formGasto.notas}
                onChange={(e) => setFormGasto({ ...formGasto, notas: e.target.value })}
                className="text-base"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base">Foto boleta / PDF</Label>
              <Input
                type="file"
                accept="image/*,.pdf"
                onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
                className="text-base"
              />
              {archivo && (
                <p className="flex items-center gap-1 text-sm text-green-700">
                  <Camera className="h-4 w-4" /> {archivo.name}
                </p>
              )}
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogoGasto(false)} className="text-base">
              Cancelar
            </Button>
            <Button
              onClick={guardarGasto}
              disabled={guardando}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              {guardando ? "Guardando…" : "Guardar Gasto"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

