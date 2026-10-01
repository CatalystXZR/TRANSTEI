"use client";

import { useEffect, useMemo, useState } from "react";
import { IdCard, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatCLP, formatRut } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { Chofer } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputCLP } from "@/components/ui-inputs/input-clp";
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
import { FilaVacia, FilasCargando, PageHeader, Panel, Vencimiento } from "@/components/sistema";
import { Campo } from "@/components/formulario";

interface FormChofer {
  nombre: string;
  rut: string;
  sueldo_base: number;
  porcentaje_produccion: string;
  vencimiento_licencia: string;
}

const FORM_VACIO: FormChofer = { nombre: "", rut: "", sueldo_base: 0, porcentaje_produccion: "15", vencimiento_licencia: "" };

export default function ChoferesPage() {
  const { usuario } = useAuth();
  const [choferes, setChoferes] = useState<Chofer[]>([]);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [dialogo, setDialogo] = useState(false);
  const [editando, setEditando] = useState<Chofer | null>(null);
  const [form, setForm] = useState<FormChofer>(FORM_VACIO);
  const [rutValido, setRutValido] = useState(true);
  const [intento, setIntento] = useState(false);
  const [eliminando, setEliminando] = useState<Chofer | null>(null);
  const [guardando, setGuardando] = useState(false);

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  function recargar() {
    api
      .get<Chofer[]>("/choferes?activo=true")
      .then((data) => setChoferes(data ?? []))
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar choferes"))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    api
      .get<Chofer[]>("/choferes?activo=true")
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

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    const qRut = q.replace(/[^0-9k]/g, "");
    return choferes.filter(
      (c) => !q || c.nombre.toLowerCase().includes(q) || (qRut && c.rut.toLowerCase().replace(/[^0-9k]/g, "").includes(qRut)),
    );
  }, [choferes, busqueda]);

  function abrirNuevo() {
    setEditando(null);
    setForm(FORM_VACIO);
    setRutValido(true);
    setIntento(false);
    setDialogo(true);
  }

  function abrirEditar(c: Chofer) {
    setEditando(c);
    setForm({
      nombre: c.nombre,
      rut: c.rut,
      sueldo_base: Number(c.sueldo_base),
      porcentaje_produccion: String(Math.round(Number(c.porcentaje_produccion) * 1000) / 10),
      vencimiento_licencia: c.vencimiento_licencia ?? "",
    });
    setRutValido(true);
    setIntento(false);
    setDialogo(true);
  }

  const pct = Number(form.porcentaje_produccion);
  const pctInvalido = form.porcentaje_produccion !== "" && (Number.isNaN(pct) || pct < 0 || pct > 100);

  async function guardar() {
    setIntento(true);
    if (!form.nombre.trim() || !form.rut || !rutValido || pctInvalido) {
      toast.error("Revise los datos marcados");
      return;
    }
    setGuardando(true);
    const body = {
      nombre: form.nombre.trim(),
      rut: form.rut,
      sueldo_base: form.sueldo_base,
      porcentaje_produccion: (Number(form.porcentaje_produccion) || 0) / 100,
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
      toast.success("Chofer desactivado");
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
        titulo="Choferes"
        descripcion="Conductores, su remuneración y el vencimiento de su licencia."
        acciones={
          puedeEscribir && (
            <>
              <ImportarCsv endpoint="/export/import/choferes" onImportado={recargar} />
              <Button onClick={abrirNuevo}>
                <Plus /> Nuevo chofer
              </Button>
            </>
          )
        }
      />

      <Panel
        titulo={`${choferes.length} ${choferes.length === 1 ? "chofer" : "choferes"}`}
        acciones={
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-[18px] -translate-y-1/2 text-tinta-3" />
            <Input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar por nombre o RUT"
              className="h-10 pl-10"
              aria-label="Buscar choferes"
            />
          </div>
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nombre</TableHead>
              <TableHead>RUT</TableHead>
              <TableHead className="text-right">Sueldo base</TableHead>
              <TableHead className="text-right">Comisión</TableHead>
              <TableHead>Licencia</TableHead>
              {puedeEscribir && <TableHead className="w-28 text-right">Acciones</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <FilasCargando columnas={columnas} />
            ) : filtrados.length === 0 ? (
              <FilaVacia
                columnas={columnas}
                icono={IdCard}
                titulo={choferes.length === 0 ? "Aún no hay choferes" : "Sin resultados"}
                descripcion={choferes.length === 0 ? "Agregue choferes para asignarlos a los viajes." : "Pruebe con otro nombre o RUT."}
              />
            ) : (
              filtrados.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-medium">{c.nombre}</TableCell>
                  <TableCell className="font-mono text-[14.5px] text-tinta-2">{formatRut(c.rut)}</TableCell>
                  <TableCell className="cifra text-right">{formatCLP(c.sueldo_base)}</TableCell>
                  <TableCell className="cifra text-right">
                    {Math.round(Number(c.porcentaje_produccion) * 1000) / 10} %
                  </TableCell>
                  <TableCell>
                    <Vencimiento fecha={c.vencimiento_licencia} />
                  </TableCell>
                  {puedeEscribir && (
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon-sm" onClick={() => abrirEditar(c)} aria-label={`Editar ${c.nombre}`}>
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-tinta-3 hover:bg-critico-tenue hover:text-critico"
                          onClick={() => setEliminando(c)}
                          aria-label={`Desactivar ${c.nombre}`}
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
            <DialogTitle>{editando ? "Editar chofer" : "Nuevo chofer"}</DialogTitle>
            <DialogDescription>Sueldo mensual = sueldo base + (% comisión × fletes finalizados del mes).</DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <Campo etiqueta="Nombre completo" htmlFor="ch-nombre" requerido error={intento && !form.nombre.trim() ? "Ingrese el nombre" : null}>
              <Input id="ch-nombre" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
            </Campo>
            <Campo
              etiqueta="RUT"
              htmlFor="ch-rut"
              requerido
              error={!rutValido ? "El RUT no es válido" : intento && !form.rut ? "Ingrese el RUT" : null}
            >
              <InputRut
                key={editando?.id ?? "nuevo"}
                id="ch-rut"
                value={form.rut}
                onChange={(rut) => setForm({ ...form, rut })}
                onValidez={setRutValido}
                placeholder="12.345.678-9"
              />
            </Campo>
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Sueldo base" htmlFor="ch-sueldo">
                <InputCLP
                  key={editando?.id ?? "nuevo"}
                  id="ch-sueldo"
                  value={form.sueldo_base}
                  onChange={(v) => setForm({ ...form, sueldo_base: v })}
                  placeholder="$ 500.000"
                  className="cifra"
                />
              </Campo>
              <Campo etiqueta="Comisión (%)" htmlFor="ch-pct" error={pctInvalido ? "Entre 0 y 100" : null}>
                <Input
                  id="ch-pct"
                  type="number"
                  min={0}
                  max={100}
                  step={0.5}
                  value={form.porcentaje_produccion}
                  onChange={(e) => setForm({ ...form, porcentaje_produccion: e.target.value })}
                  aria-invalid={pctInvalido}
                />
              </Campo>
            </div>
            <Campo etiqueta="Vencimiento de licencia" htmlFor="ch-lic" ayuda="Se alertará 30 días antes">
              <Input
                id="ch-lic"
                type="date"
                value={form.vencimiento_licencia}
                onChange={(e) => setForm({ ...form, vencimiento_licencia: e.target.value })}
              />
            </Campo>
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
            <DialogTitle>Desactivar chofer</DialogTitle>
            <DialogDescription>
              <strong>{eliminando?.nombre}</strong> dejará de estar disponible para nuevos viajes. Su historial se conserva.
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
