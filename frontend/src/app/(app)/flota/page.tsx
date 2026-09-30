"use client";

import { useEffect, useState } from "react";
import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { Rampla, Tracto } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
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

type Pestana = "tractos" | "ramplas";

interface FormTracto {
  patente: string;
  marca: string;
  modelo: string;
  ano: string;
  km_actual: string;
  vencimiento_revision_tecnica: string;
  vencimiento_seguro: string;
}

interface FormRampla {
  patente: string;
  tipo: "plana" | "sider";
  vencimiento_revision_tecnica: string;
}

const TRACTO_VACIO: FormTracto = {
  patente: "",
  marca: "",
  modelo: "",
  ano: "",
  km_actual: "0",
  vencimiento_revision_tecnica: "",
  vencimiento_seguro: "",
};

const RAMPLA_VACIO: FormRampla = {
  patente: "",
  tipo: "plana",
  vencimiento_revision_tecnica: "",
};

function BadgeVencimiento({ fecha }: { fecha: string | null }) {
  if (!fecha) return <span>-</span>;
  const d = new Date(`${fecha}T00:00:00`);
  const hoy = new Date();
  const dias = Math.floor((d.getTime() - hoy.getTime()) / 86400000);
  if (dias < 0) return <Badge className="bg-red-600 text-white">{formatFecha(fecha)}</Badge>;
  if (dias <= 30) return <Badge className="bg-yellow-500 text-black">{formatFecha(fecha)}</Badge>;
  return <Badge className="bg-green-100 text-green-800">{formatFecha(fecha)}</Badge>;
}

export default function FlotaPage() {
  const { usuario } = useAuth();
  const [pestana, setPestana] = useState<Pestana>("tractos");
  const [tractos, setTractos] = useState<Tracto[]>([]);
  const [ramplas, setRamplas] = useState<Rampla[]>([]);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState("");

  const [dialogoTracto, setDialogoTracto] = useState(false);
  const [editandoTracto, setEditandoTracto] = useState<Tracto | null>(null);
  const [formTracto, setFormTracto] = useState<FormTracto>(TRACTO_VACIO);

  const [dialogoRampla, setDialogoRampla] = useState(false);
  const [editandoRampla, setEditandoRampla] = useState<Rampla | null>(null);
  const [formRampla, setFormRampla] = useState<FormRampla>(RAMPLA_VACIO);

  const [eliminando, setEliminando] = useState<{ tipo: Pestana; item: Tracto | Rampla } | null>(null);
  const [guardando, setGuardando] = useState(false);

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  function recargar() {
    Promise.all([api.get<Tracto[]>("/tractos"), api.get<Rampla[]>("/ramplas")])
      .then(([t, r]) => {
        setTractos(t ?? []);
        setRamplas(r ?? []);
      })
      .catch((e) =>
        toast.error(e instanceof Error ? e.message : "Error al cargar la flota"),
      )
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    Promise.all([api.get<Tracto[]>("/tractos"), api.get<Rampla[]>("/ramplas")])
      .then(([t, r]) => {
        if (activo) {
          setTractos(t ?? []);
          setRamplas(r ?? []);
        }
      })
      .catch((e) => {
        if (activo) toast.error(e instanceof Error ? e.message : "Error al cargar la flota");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  async function guardarTracto() {
    if (!formTracto.patente.trim()) {
      toast.error("La patente es obligatoria");
      return;
    }
    setGuardando(true);
    const body = {
      patente: formTracto.patente.trim().toUpperCase(),
      marca: formTracto.marca.trim() || null,
      modelo: formTracto.modelo.trim() || null,
      ano: formTracto.ano ? Number(formTracto.ano) : null,
      km_actual: Number(formTracto.km_actual) || 0,
      vencimiento_revision_tecnica: formTracto.vencimiento_revision_tecnica || null,
      vencimiento_seguro: formTracto.vencimiento_seguro || null,
    };
    try {
      if (editandoTracto) {
        await api.put(`/tractos/${editandoTracto.id}`, body);
        toast.success("Tracto actualizado");
      } else {
        await api.post("/tractos", body);
        toast.success("Tracto creado");
      }
      setDialogoTracto(false);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setGuardando(false);
    }
  }

  async function guardarRampla() {
    if (!formRampla.patente.trim()) {
      toast.error("La patente es obligatoria");
      return;
    }
    setGuardando(true);
    const body = {
      patente: formRampla.patente.trim().toUpperCase(),
      tipo: formRampla.tipo,
      vencimiento_revision_tecnica: formRampla.vencimiento_revision_tecnica || null,
    };
    try {
      if (editandoRampla) {
        await api.put(`/ramplas/${editandoRampla.id}`, body);
        toast.success("Rampla actualizada");
      } else {
        await api.post("/ramplas", body);
        toast.success("Rampla creada");
      }
      setDialogoRampla(false);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setGuardando(false);
    }
  }

  async function eliminar() {
    if (!eliminando) return;
    try {
      const path =
        eliminando.tipo === "tractos"
          ? `/tractos/${eliminando.item.id}`
          : `/ramplas/${eliminando.item.id}`;
      await api.del(path);
      toast.success("Eliminado correctamente");
      setEliminando(null);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al eliminar");
    }
  }

  const tractosFiltrados = tractos.filter(
    (t) =>
      t.patente.toLowerCase().includes(busqueda.toLowerCase()) ||
      (t.marca ?? "").toLowerCase().includes(busqueda.toLowerCase()),
  );
  const ramplasFiltradas = ramplas.filter((r) =>
    r.patente.toLowerCase().includes(busqueda.toLowerCase()),
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-[#2A237A]">Flota</h1>
        {puedeEscribir && (
          <div className="flex gap-2">
            <Button
              onClick={() => {
                setEditandoTracto(null);
                setFormTracto(TRACTO_VACIO);
                setDialogoTracto(true);
              }}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              <Plus className="h-5 w-5" />
              Nuevo Tracto
            </Button>
            <Button
              onClick={() => {
                setEditandoRampla(null);
                setFormRampla(RAMPLA_VACIO);
                setDialogoRampla(true);
              }}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              <Plus className="h-5 w-5" />
              Nueva Rampla
            </Button>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        <div className="flex rounded-lg border bg-white p-1">
          <button
            onClick={() => setPestana("tractos")}
            className={`rounded-md px-4 py-2 text-base font-medium transition-colors ${
              pestana === "tractos" ? "bg-[#2A237A] text-white" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            Tractocamiones ({tractos.length})
          </button>
          <button
            onClick={() => setPestana("ramplas")}
            className={`rounded-md px-4 py-2 text-base font-medium transition-colors ${
              pestana === "ramplas" ? "bg-[#2A237A] text-white" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            Ramplas ({ramplas.length})
          </button>
        </div>
        <div className="relative max-w-xs flex-1">
          <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar por patente"
            className="pl-10 text-base"
          />
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border bg-white">
        {pestana === "tractos" ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-base">Patente</TableHead>
                <TableHead className="text-base">Marca</TableHead>
                <TableHead className="text-base">Modelo</TableHead>
                <TableHead className="text-base">KM Actual</TableHead>
                <TableHead className="text-base">Rev. Técnica</TableHead>
                <TableHead className="text-base">Seguro</TableHead>
                {puedeEscribir && <TableHead className="w-28 text-base">Acciones</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-gray-500">
                    Cargando…
                  </TableCell>
                </TableRow>
              ) : tractosFiltrados.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-gray-500">
                    No hay tractos registrados
                  </TableCell>
                </TableRow>
              ) : (
                tractosFiltrados.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="text-base font-bold">{t.patente}</TableCell>
                    <TableCell className="text-base">{t.marca ?? "-"}</TableCell>
                    <TableCell className="text-base">{t.modelo ?? "-"}</TableCell>
                    <TableCell className="text-base">
                      {new Intl.NumberFormat("es-CL").format(t.km_actual)} km
                    </TableCell>
                    <TableCell className="text-base">
                      <BadgeVencimiento fecha={t.vencimiento_revision_tecnica} />
                    </TableCell>
                    <TableCell className="text-base">
                      <BadgeVencimiento fecha={t.vencimiento_seguro} />
                    </TableCell>
                    {puedeEscribir && (
                      <TableCell>
                        <div className="flex gap-2">
                          <Button
                            size="icon"
                            variant="outline"
                            onClick={() => {
                              setEditandoTracto(t);
                              setFormTracto({
                                patente: t.patente,
                                marca: t.marca ?? "",
                                modelo: t.modelo ?? "",
                                ano: t.ano ? String(t.ano) : "",
                                km_actual: String(t.km_actual),
                                vencimiento_revision_tecnica:
                                  t.vencimiento_revision_tecnica ?? "",
                                vencimiento_seguro: t.vencimiento_seguro ?? "",
                              });
                              setDialogoTracto(true);
                            }}
                            aria-label="Editar tracto"
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="outline"
                            className="border-red-200 text-red-600 hover:bg-red-50"
                            onClick={() => setEliminando({ tipo: "tractos", item: t })}
                            aria-label="Eliminar tracto"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-base">Patente</TableHead>
                <TableHead className="text-base">Tipo</TableHead>
                <TableHead className="text-base">Rev. Técnica</TableHead>
                {puedeEscribir && <TableHead className="w-28 text-base">Acciones</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-gray-500">
                    Cargando…
                  </TableCell>
                </TableRow>
              ) : ramplasFiltradas.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-gray-500">
                    No hay ramplas registradas
                  </TableCell>
                </TableRow>
              ) : (
                ramplasFiltradas.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="text-base font-bold">{r.patente}</TableCell>
                    <TableCell className="text-base capitalize">{r.tipo}</TableCell>
                    <TableCell className="text-base">
                      <BadgeVencimiento fecha={r.vencimiento_revision_tecnica} />
                    </TableCell>
                    {puedeEscribir && (
                      <TableCell>
                        <div className="flex gap-2">
                          <Button
                            size="icon"
                            variant="outline"
                            onClick={() => {
                              setEditandoRampla(r);
                              setFormRampla({
                                patente: r.patente,
                                tipo: r.tipo,
                                vencimiento_revision_tecnica:
                                  r.vencimiento_revision_tecnica ?? "",
                              });
                              setDialogoRampla(true);
                            }}
                            aria-label="Editar rampla"
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="outline"
                            className="border-red-200 text-red-600 hover:bg-red-50"
                            onClick={() => setEliminando({ tipo: "ramplas", item: r })}
                            aria-label="Eliminar rampla"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </div>

      <Dialog open={dialogoTracto} onOpenChange={setDialogoTracto}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl">
              {editandoTracto ? "Editar Tracto" : "Nuevo Tracto"}
            </DialogTitle>
            <DialogDescription className="text-base">
              Registre los datos del tractocamión.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Patente *</Label>
                <Input
                  value={formTracto.patente}
                  onChange={(e) => setFormTracto({ ...formTracto, patente: e.target.value })}
                  className="text-base uppercase"
                  placeholder="BBCT-34"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-base">Marca</Label>
                <Input
                  value={formTracto.marca}
                  onChange={(e) => setFormTracto({ ...formTracto, marca: e.target.value })}
                  className="text-base"
                  placeholder="Freightliner"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Modelo</Label>
                <Input
                  value={formTracto.modelo}
                  onChange={(e) => setFormTracto({ ...formTracto, modelo: e.target.value })}
                  className="text-base"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-base">Año</Label>
                <Input
                  type="number"
                  value={formTracto.ano}
                  onChange={(e) => setFormTracto({ ...formTracto, ano: e.target.value })}
                  className="text-base"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Kilometraje Actual</Label>
              <Input
                type="number"
                value={formTracto.km_actual}
                onChange={(e) => setFormTracto({ ...formTracto, km_actual: e.target.value })}
                className="text-base"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Rev. Técnica</Label>
                <Input
                  type="date"
                  value={formTracto.vencimiento_revision_tecnica}
                  onChange={(e) =>
                    setFormTracto({
                      ...formTracto,
                      vencimiento_revision_tecnica: e.target.value,
                    })
                  }
                  className="text-base"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-base">Seguro</Label>
                <Input
                  type="date"
                  value={formTracto.vencimiento_seguro}
                  onChange={(e) =>
                    setFormTracto({ ...formTracto, vencimiento_seguro: e.target.value })
                  }
                  className="text-base"
                />
              </div>
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogoTracto(false)} className="text-base">
              Cancelar
            </Button>
            <Button
              onClick={guardarTracto}
              disabled={guardando}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              {guardando ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoRampla} onOpenChange={setDialogoRampla}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl">
              {editandoRampla ? "Editar Rampla" : "Nueva Rampla"}
            </DialogTitle>
            <DialogDescription className="text-base">
              Registre los datos de la rampla.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Patente *</Label>
              <Input
                value={formRampla.patente}
                onChange={(e) => setFormRampla({ ...formRampla, patente: e.target.value })}
                className="text-base uppercase"
                placeholder="RAMPLA-1"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base">Tipo</Label>
              <Select
                value={formRampla.tipo}
                onValueChange={(v) =>
                  setFormRampla({ ...formRampla, tipo: v as "plana" | "sider" })
                }
              >
                <SelectTrigger className="text-base">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="plana" className="text-base">
                    Plana
                  </SelectItem>
                  <SelectItem value="sider" className="text-base">
                    Sider
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Rev. Técnica</Label>
              <Input
                type="date"
                value={formRampla.vencimiento_revision_tecnica}
                onChange={(e) =>
                  setFormRampla({ ...formRampla, vencimiento_revision_tecnica: e.target.value })
                }
                className="text-base"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogoRampla(false)} className="text-base">
              Cancelar
            </Button>
            <Button
              onClick={guardarRampla}
              disabled={guardando}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              {guardando ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!eliminando} onOpenChange={(o) => !o && setEliminando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-xl">Eliminar Equipo</DialogTitle>
            <DialogDescription className="text-base">
              ¿Seguro que desea eliminar la patente{" "}
              <strong>
                {(eliminando?.item as { patente?: string })?.patente}
              </strong>
              ?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setEliminando(null)} className="text-base">
              Cancelar
            </Button>
            <Button variant="destructive" onClick={eliminar} className="text-base">
              <Trash2 className="h-4 w-4" />
              Eliminar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
