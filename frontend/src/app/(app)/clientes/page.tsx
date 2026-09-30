"use client";

import { useEffect, useState } from "react";
import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatRut } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { Cliente } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputRut } from "@/components/ui-inputs/input-rut";
import { ImportarCsv } from "@/components/importar-csv";
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

interface FormCliente {
  razon_social: string;
  rut: string;
  giro: string;
  dias_pago: string;
  telefono: string;
  email: string;
}

const FORM_VACIO: FormCliente = {
  razon_social: "",
  rut: "",
  giro: "",
  dias_pago: "30",
  telefono: "",
  email: "",
};

export default function ClientesPage() {
  const { usuario } = useAuth();
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [dialogo, setDialogo] = useState(false);
  const [editando, setEditando] = useState<Cliente | null>(null);
  const [form, setForm] = useState<FormCliente>(FORM_VACIO);
  const [rutValido, setRutValido] = useState(true);
  const [eliminando, setEliminando] = useState<Cliente | null>(null);
  const [guardando, setGuardando] = useState(false);

  const puedeEscribir =
    usuario?.rol === "admin" || usuario?.rol === "operacion";

  function recargar() {
    api
      .get<Cliente[]>("/clientes")
      .then((data) => setClientes(data ?? []))
      .catch((e) =>
        toast.error(e instanceof Error ? e.message : "Error al cargar clientes"),
      )
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    api
      .get<Cliente[]>("/clientes")
      .then((data) => {
        if (activo) setClientes(data ?? []);
      })
      .catch((e) => {
        if (activo) toast.error(e instanceof Error ? e.message : "Error al cargar clientes");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  const filtrados = clientes.filter(
    (c) =>
      c.razon_social.toLowerCase().includes(busqueda.toLowerCase()) ||
      c.rut.includes(busqueda),
  );

  function abrirNuevo() {
    setEditando(null);
    setForm(FORM_VACIO);
    setDialogo(true);
  }

  function abrirEditar(cliente: Cliente) {
    setEditando(cliente);
    setForm({
      razon_social: cliente.razon_social,
      rut: cliente.rut,
      giro: cliente.giro ?? "",
      dias_pago: String(cliente.dias_pago),
      telefono: cliente.telefono ?? "",
      email: cliente.email ?? "",
    });
    setDialogo(true);
  }

  async function guardar() {
    if (!form.razon_social.trim() || !form.rut || !rutValido) {
      toast.error("Revise los datos: razón social y RUT son obligatorios");
      return;
    }
    setGuardando(true);
    const body = {
      razon_social: form.razon_social.trim(),
      rut: form.rut,
      giro: form.giro.trim() || null,
      dias_pago: Number(form.dias_pago) || 30,
      telefono: form.telefono.trim() || null,
      email: form.email.trim() || null,
    };
    try {
      if (editando) {
        await api.put(`/clientes/${editando.id}`, body);
        toast.success("Cliente actualizado");
      } else {
        await api.post("/clientes", body);
        toast.success("Cliente creado");
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
      await api.del(`/clientes/${eliminando.id}`);
      toast.success("Cliente eliminado");
      setEliminando(null);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al eliminar");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-[#2A237A]">Clientes</h1>
        <div className="flex flex-wrap gap-2">
          {puedeEscribir && (
            <>
              <ImportarCsv endpoint="/export/import/clientes" onImportado={recargar} />
              <Button
                onClick={abrirNuevo}
                className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
              >
                <Plus className="h-5 w-5" />
                Nuevo Cliente
              </Button>
            </>
          )}
        </div>
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
              <TableHead className="text-base">Razón Social</TableHead>
              <TableHead className="text-base">RUT</TableHead>
              <TableHead className="text-base">Días Pago</TableHead>
              <TableHead className="text-base">Teléfono</TableHead>
              {puedeEscribir && <TableHead className="w-28 text-base">Acciones</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-gray-500">
                  Cargando…
                </TableCell>
              </TableRow>
            ) : filtrados.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-gray-500">
                  No hay clientes registrados
                </TableCell>
              </TableRow>
            ) : (
              filtrados.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="text-base font-medium">{c.razon_social}</TableCell>
                  <TableCell className="text-base">{formatRut(c.rut)}</TableCell>
                  <TableCell className="text-base">{c.dias_pago} días</TableCell>
                  <TableCell className="text-base">{c.telefono ?? "-"}</TableCell>
                  {puedeEscribir && (
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          size="icon"
                          variant="outline"
                          onClick={() => abrirEditar(c)}
                          aria-label="Editar cliente"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="outline"
                          className="border-red-200 text-red-600 hover:bg-red-50"
                          onClick={() => setEliminando(c)}
                          aria-label="Eliminar cliente"
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
              {editando ? "Editar Cliente" : "Nuevo Cliente"}
            </DialogTitle>
            <DialogDescription className="text-base">
              Complete los datos del cliente. El RUT se valida automáticamente.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Razón Social *</Label>
              <Input
                value={form.razon_social}
                onChange={(e) => setForm({ ...form, razon_social: e.target.value })}
                className="text-base"
                placeholder="Empresa de Transportes SpA"
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
                <Label className="text-base">Días de Pago</Label>
                <Input
                  type="number"
                  min={0}
                  value={form.dias_pago}
                  onChange={(e) => setForm({ ...form, dias_pago: e.target.value })}
                  className="text-base"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-base">Teléfono</Label>
                <Input
                  value={form.telefono}
                  onChange={(e) => setForm({ ...form, telefono: e.target.value })}
                  className="text-base"
                  placeholder="+56 9 ..."
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Giro</Label>
              <Input
                value={form.giro}
                onChange={(e) => setForm({ ...form, giro: e.target.value })}
                className="text-base"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base">Email</Label>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="text-base"
                placeholder="contacto@empresa.cl"
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
            <DialogTitle className="text-xl">Eliminar Cliente</DialogTitle>
            <DialogDescription className="text-base">
              ¿Seguro que desea eliminar a <strong>{eliminando?.razon_social}</strong>?
              Podrá reactivarlo desde el sistema si lo necesita.
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
