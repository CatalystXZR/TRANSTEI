"use client";

import { useEffect, useState } from "react";
import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatCLP, formatFecha, formatRut } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { Chofer } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputCLP } from "@/components/ui-inputs/input-clp";
import { InputRut } from "@/components/ui-inputs/input-rut";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface FormChofer {
  nombre: string;
  rut: string;
  sueldo_base: number;
  porcentaje_produccion: string;
  vencimiento_licencia: string;
}

const FORM_VACIO: FormChofer = {
  nombre: "",
  rut: "",
  sueldo_base: 0,
  porcentaje_produccion: "15",
  vencimiento_licencia: "",
};

const LIMITE_ALERTA_LICENCIA = Date.now() + 30 * 86400000;

export default function ChoferesPage() {
  const { usuario } = useAuth();
  const [choferes, setChoferes] = useState<Chofer[]>([]);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [dialogo, setDialogo] = useState(false);
  const [editando, setEditando] = useState<Chofer | null>(null);
  const [form, setForm] = useState<FormChofer>(FORM_VACIO);
  const [rutValido, setRutValido] = useState(true);
  const [eliminando, setEliminando] = useState<Chofer | null>(null);
  const [guardando, setGuardando] = useState(false);

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  function recargar() {
    api
      .get<Chofer[]>("/choferes")
      .then((data) => setChoferes(data ?? []))
      .catch((e) =>
        toast.error(e instanceof Error ? e.message : "Error al cargar choferes"),
      )
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    api
      .get<Chofer[]>("/choferes")
      .then((data) => {
        if (activo) setChoferes(data ?? []);
      })
      .catch((e) => {
        if (activo) toast.error(e instanceof Error ? e.message : "Error al cargar choferes");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  const filtrados = choferes.filter(
    (c) =>
      c.nombre.toLowerCase().includes(busqueda.toLowerCase()) || c.rut.includes(busqueda),
  );

  function abrirNuevo() {
    setEditando(null);
    setForm(FORM_VACIO);
    setDialogo(true);
  }

  function abrirEditar(chofer: Chofer) {
    setEditando(chofer);
    setForm({
      nombre: chofer.nombre,
      rut: chofer.rut,
      sueldo_base: Number(chofer.sueldo_base),
      porcentaje_produccion: String(Math.round(Number(chofer.porcentaje_produccion) * 100)),
      vencimiento_licencia: chofer.vencimiento_licencia ?? "",
    });
    setDialogo(true);
  }

  async function guardar() {
    if (!form.nombre.trim() || !form.rut || !rutValido) {
      toast.error("Revise los datos: nombre y RUT son obligatorios");
      return;
    }
    setGuardando(true);
    const body = {
      nombre: form.nombre.trim(),
      rut: form.rut,
      sueldo_base: form.sueldo_base,
      porcentaje_produccion: Number(form.porcentaje_produccion || "0") / 100,
      vencimiento_licencia: form.vencimiento_licencia || null,
    };
    try {
      if (editando) {
        await api.put(`/choferes/${editando.id}`, body);
        toast.success("Chofer actualizado");
      } else {
        await api.post("/choferes", body);
        toast.success("Chofer creado");
      }
      setDialogo(false);
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
      await api.del(`/choferes/${eliminando.id}`);
      toast.success("Chofer eliminado");
      setEliminando(null);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al eliminar");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-[#2A237A]">Choferes</h1>
        {puedeEscribir && (
          <Button onClick={abrirNuevo} className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90">
            <Plus className="h-5 w-5" />
            Nuevo Chofer
          </Button>
        )}
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
        <Input
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          placeholder="Buscar por nombre o RUT"
          className="pl-10 text-base"
        />
      </div>

      <div className="overflow-x-auto rounded-lg border bg-white">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-base">Nombre</TableHead>
              <TableHead className="text-base">RUT</TableHead>
              <TableHead className="text-base">Sueldo Base</TableHead>
              <TableHead className="text-base">% Comisión</TableHead>
              <TableHead className="text-base">Venc. Licencia</TableHead>
              {puedeEscribir && <TableHead className="w-28 text-base">Acciones</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-gray-500">
                  Cargando…
                </TableCell>
              </TableRow>
            ) : filtrados.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-gray-500">
                  No hay choferes registrados
                </TableCell>
              </TableRow>
            ) : (
              filtrados.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="text-base font-medium">{c.nombre}</TableCell>
                  <TableCell className="text-base">{formatRut(c.rut)}</TableCell>
                  <TableCell className="text-base">{formatCLP(c.sueldo_base)}</TableCell>
                  <TableCell className="text-base">
                    {Math.round(Number(c.porcentaje_produccion) * 100)}%
                  </TableCell>
                  <TableCell className="text-base">
                    {c.vencimiento_licencia ? (
                      <Badge
                        className={
                          new Date(c.vencimiento_licencia).getTime() < LIMITE_ALERTA_LICENCIA
                            ? "bg-yellow-500 text-black"
                            : "bg-gray-100 text-gray-700"
                        }
                      >
                        {formatFecha(c.vencimiento_licencia)}
                      </Badge>
                    ) : (
                      "-"
                    )}
                  </TableCell>
                  {puedeEscribir && (
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          size="icon"
                          variant="outline"
                          onClick={() => abrirEditar(c)}
                          aria-label="Editar chofer"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="outline"
                          className="border-red-200 text-red-600 hover:bg-red-50"
                          onClick={() => setEliminando(c)}
                          aria-label="Eliminar chofer"
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
      </div>

      <Dialog open={dialogo} onOpenChange={setDialogo}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl">
              {editando ? "Editar Chofer" : "Nuevo Chofer"}
            </DialogTitle>
            <DialogDescription className="text-base">
              El sueldo mensual se calcula como Sueldo Base + (% Comisión × fletes del mes).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Nombre *</Label>
              <Input
                value={form.nombre}
                onChange={(e) => setForm({ ...form, nombre: e.target.value })}
                className="text-base"
                placeholder="Nombre completo"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base">RUT *</Label>
              <InputRut
                value={form.rut}
                onChange={(rut) => setForm({ ...form, rut })}
                onValidez={setRutValido}
                placeholder="12.345.678-9"
              />
              {!rutValido && (
                <p className="text-sm text-red-600">El RUT ingresado no es válido</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Sueldo Base ($)</Label>
                <InputCLP
                  value={form.sueldo_base}
                  onChange={(v) => setForm({ ...form, sueldo_base: v })}
                  placeholder="$ 500.000"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-base">% Comisión</Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={form.porcentaje_produccion}
                  onChange={(e) =>
                    setForm({ ...form, porcentaje_produccion: e.target.value })
                  }
                  className="text-base"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Vencimiento Licencia</Label>
              <Input
                type="date"
                value={form.vencimiento_licencia}
                onChange={(e) => setForm({ ...form, vencimiento_licencia: e.target.value })}
                className="text-base"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogo(false)} className="text-base">
              Cancelar
            </Button>
            <Button
              onClick={guardar}
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
            <DialogTitle className="text-xl">Eliminar Chofer</DialogTitle>
            <DialogDescription className="text-base">
              ¿Seguro que desea eliminar a <strong>{eliminando?.nombre}</strong>?
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
