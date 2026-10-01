"use client";

import { useEffect, useMemo, useState } from "react";
import { Building2, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatRut } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { Cliente } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FilaVacia, FilasCargando, PageHeader, Panel } from "@/components/sistema";
import { Campo } from "@/components/formulario";

interface FormCliente {
  razon_social: string;
  rut: string;
  giro: string;
  dias_pago: string;
  telefono: string;
  email: string;
}

const FORM_VACIO: FormCliente = { razon_social: "", rut: "", giro: "", dias_pago: "30", telefono: "", email: "" };

export default function ClientesPage() {
  const { usuario } = useAuth();
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [dialogo, setDialogo] = useState(false);
  const [editando, setEditando] = useState<Cliente | null>(null);
  const [form, setForm] = useState<FormCliente>(FORM_VACIO);
  const [rutValido, setRutValido] = useState(true);
  const [intento, setIntento] = useState(false);
  const [eliminando, setEliminando] = useState<Cliente | null>(null);
  const [guardando, setGuardando] = useState(false);

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  function recargar() {
    api
      .get<Cliente[]>("/clientes?activo=true")
      .then((data) => setClientes(data ?? []))
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar clientes"))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    api
      .get<Cliente[]>("/clientes?activo=true")
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

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    const qRut = q.replace(/[^0-9k]/g, "");
    return clientes.filter(
      (c) => !q || c.razon_social.toLowerCase().includes(q) || (qRut && c.rut.toLowerCase().replace(/[^0-9k]/g, "").includes(qRut)),
    );
  }, [clientes, busqueda]);

  function abrirNuevo() {
    setEditando(null);
    setForm(FORM_VACIO);
    setRutValido(true);
    setIntento(false);
    setDialogo(true);
  }

  function abrirEditar(c: Cliente) {
    setEditando(c);
    setForm({
      razon_social: c.razon_social,
      rut: c.rut,
      giro: c.giro ?? "",
      dias_pago: String(c.dias_pago),
      telefono: c.telefono ?? "",
      email: c.email ?? "",
    });
    setRutValido(true);
    setIntento(false);
    setDialogo(true);
  }

  async function guardar() {
    setIntento(true);
    if (!form.razon_social.trim() || !form.rut || !rutValido) {
      toast.error("Revise los datos: razón social y RUT válido son obligatorios");
      return;
    }
    setGuardando(true);
    const body = {
      razon_social: form.razon_social.trim(),
      rut: form.rut,
      giro: form.giro.trim() || null,
      dias_pago: Math.max(0, Number(form.dias_pago) || 30),
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
      toast.success("Cliente desactivado");
      setEliminando(null);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al eliminar");
    }
  }

  const columnas = puedeEscribir ? 6 : 5;

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Maestros"
        titulo="Clientes"
        descripcion="Empresas a las que se presta servicio de transporte y sus condiciones de pago."
        acciones={
          puedeEscribir && (
            <>
              <ImportarCsv endpoint="/export/import/clientes" onImportado={recargar} />
              <Button onClick={abrirNuevo}>
                <Plus /> Nuevo cliente
              </Button>
            </>
          )
        }
      />

      <Panel
        titulo={`${clientes.length} ${clientes.length === 1 ? "cliente" : "clientes"}`}
        acciones={
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-[18px] -translate-y-1/2 text-tinta-3" />
            <Input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar por nombre o RUT"
              className="h-10 pl-10"
              aria-label="Buscar clientes"
            />
          </div>
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Razón social</TableHead>
              <TableHead>RUT</TableHead>
              <TableHead>Pago</TableHead>
              <TableHead>Teléfono</TableHead>
              <TableHead>Correo</TableHead>
              {puedeEscribir && <TableHead className="w-28 text-right">Acciones</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <FilasCargando columnas={columnas} />
            ) : filtrados.length === 0 ? (
              <FilaVacia
                columnas={columnas}
                icono={Building2}
                titulo={clientes.length === 0 ? "Aún no hay clientes" : "Sin resultados"}
                descripcion={clientes.length === 0 ? "Agregue clientes manualmente o importe una planilla CSV." : "Pruebe con otro nombre o RUT."}
              />
            ) : (
              filtrados.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <span className="font-medium">{c.razon_social}</span>
                    {c.giro && <span className="block text-[13.5px] text-tinta-3">{c.giro}</span>}
                  </TableCell>
                  <TableCell className="font-mono text-[14.5px] text-tinta-2">{formatRut(c.rut)}</TableCell>
                  <TableCell className="text-tinta-2">{c.dias_pago} días</TableCell>
                  <TableCell className="text-tinta-2">{c.telefono ?? "—"}</TableCell>
                  <TableCell className="text-tinta-2">{c.email ?? "—"}</TableCell>
                  {puedeEscribir && (
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon-sm" onClick={() => abrirEditar(c)} aria-label={`Editar ${c.razon_social}`}>
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-tinta-3 hover:bg-critico-tenue hover:text-critico"
                          onClick={() => setEliminando(c)}
                          aria-label={`Desactivar ${c.razon_social}`}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </TableCell>
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Panel>

      <Dialog open={dialogo} onOpenChange={setDialogo}>
        <DialogContent className="max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editando ? "Editar cliente" : "Nuevo cliente"}</DialogTitle>
            <DialogDescription>El RUT se valida automáticamente al escribirlo.</DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <Campo
              etiqueta="Razón social"
              htmlFor="c-razon"
              requerido
              error={intento && !form.razon_social.trim() ? "Ingrese la razón social" : null}
            >
              <Input
                id="c-razon"
                value={form.razon_social}
                onChange={(e) => setForm({ ...form, razon_social: e.target.value })}
                placeholder="Empresa de Transportes SpA"
              />
            </Campo>
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo
                etiqueta="RUT"
                htmlFor="c-rut"
                requerido
                error={!rutValido ? "El RUT no es válido" : intento && !form.rut ? "Ingrese el RUT" : null}
              >
                <InputRut
                  key={editando?.id ?? "nuevo"}
                  id="c-rut"
                  value={form.rut}
                  onChange={(rut) => setForm({ ...form, rut })}
                  onValidez={setRutValido}
                  placeholder="76.123.456-7"
                />
              </Campo>
              <Campo etiqueta="Días de pago" htmlFor="c-dias" ayuda="Plazo para calcular el vencimiento">
                <Input
                  id="c-dias"
                  type="number"
                  min={0}
                  value={form.dias_pago}
                  onChange={(e) => setForm({ ...form, dias_pago: e.target.value })}
                />
              </Campo>
            </div>
            <Campo etiqueta="Giro" htmlFor="c-giro">
              <Input id="c-giro" value={form.giro} onChange={(e) => setForm({ ...form, giro: e.target.value })} placeholder="Opcional" />
            </Campo>
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Teléfono" htmlFor="c-tel">
                <Input id="c-tel" value={form.telefono} onChange={(e) => setForm({ ...form, telefono: e.target.value })} placeholder="+56 9 …" />
              </Campo>
              <Campo etiqueta="Correo" htmlFor="c-email">
                <Input id="c-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="contacto@empresa.cl" />
              </Campo>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogo(false)}>
              Cancelar
            </Button>
            <Button onClick={guardar} disabled={guardando}>
              {guardando ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!eliminando} onOpenChange={(o) => !o && setEliminando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desactivar cliente</DialogTitle>
            <DialogDescription>
              <strong>{eliminando?.razon_social}</strong> dejará de aparecer en las listas. Su historial de viajes y
              facturas se conserva.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEliminando(null)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={eliminar}>
              <Trash2 /> Desactivar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
