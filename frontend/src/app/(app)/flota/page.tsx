"use client";

import { useEffect, useMemo, useState } from "react";
import { Container, Pencil, Plus, Search, Trash2, Truck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/auth-context";
import type { Rampla, Tracto } from "@/types";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FilaVacia, FilasCargando, PageHeader, Panel, Patente, Segmentado, Vencimiento } from "@/components/sistema";
import { Campo, SelectSimple } from "@/components/formulario";

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
const RAMPLA_VACIO: FormRampla = { patente: "", tipo: "plana", vencimiento_revision_tecnica: "" };

const km = (n: number) => new Intl.NumberFormat("es-CL").format(n);

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

  const [intento, setIntento] = useState(false);
  const [eliminando, setEliminando] = useState<{ tipo: Pestana; id: string; patente: string } | null>(null);
  const [guardando, setGuardando] = useState(false);

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  function recargar() {
    Promise.all([api.get<Tracto[]>("/tractos?activo=true"), api.get<Rampla[]>("/ramplas?activo=true")])
      .then(([t, r]) => {
        setTractos(t ?? []);
        setRamplas(r ?? []);
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar la flota"))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    Promise.all([api.get<Tracto[]>("/tractos?activo=true"), api.get<Rampla[]>("/ramplas?activo=true")])
      .then(([t, r]) => {
        if (!activo) return;
        setTractos(t ?? []);
        setRamplas(r ?? []);
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

  const q = busqueda.trim().toLowerCase();
  const tractosFiltrados = useMemo(
    () => tractos.filter((t) => !q || t.patente.toLowerCase().includes(q) || (t.marca ?? "").toLowerCase().includes(q) || (t.modelo ?? "").toLowerCase().includes(q)),
    [tractos, q],
  );
  const ramplasFiltradas = useMemo(() => ramplas.filter((r) => !q || r.patente.toLowerCase().includes(q)), [ramplas, q]);

  function nuevoTracto() {
    setEditandoTracto(null);
    setFormTracto(TRACTO_VACIO);
    setIntento(false);
    setDialogoTracto(true);
  }
  function editarTracto(t: Tracto) {
    setEditandoTracto(t);
    setFormTracto({
      patente: t.patente,
      marca: t.marca ?? "",
      modelo: t.modelo ?? "",
      ano: t.ano ? String(t.ano) : "",
      km_actual: String(t.km_actual),
      vencimiento_revision_tecnica: t.vencimiento_revision_tecnica ?? "",
      vencimiento_seguro: t.vencimiento_seguro ?? "",
    });
    setIntento(false);
    setDialogoTracto(true);
  }
  function nuevaRampla() {
    setEditandoRampla(null);
    setFormRampla(RAMPLA_VACIO);
    setIntento(false);
    setDialogoRampla(true);
  }
  function editarRampla(r: Rampla) {
    setEditandoRampla(r);
    setFormRampla({ patente: r.patente, tipo: r.tipo, vencimiento_revision_tecnica: r.vencimiento_revision_tecnica ?? "" });
    setIntento(false);
    setDialogoRampla(true);
  }

  const kmInvalido = editandoTracto !== null && Number(formTracto.km_actual) < editandoTracto.km_actual;

  async function guardarTracto() {
    setIntento(true);
    if (!formTracto.patente.trim() || kmInvalido) {
      toast.error("Revise los datos marcados");
      return;
    }
    setGuardando(true);
    const body = {
      patente: formTracto.patente.trim().toUpperCase(),
      marca: formTracto.marca.trim() || null,
      modelo: formTracto.modelo.trim() || null,
      ano: formTracto.ano ? Number(formTracto.ano) : null,
      km_actual: Math.max(0, Number(formTracto.km_actual) || 0),
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
    setIntento(true);
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
      await api.del(`/${eliminando.tipo}/${eliminando.id}`);
      toast.success("Equipo desactivado");
      setEliminando(null);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al eliminar");
    }
  }

  const acciones = (onEditar: () => void, onEliminar: () => void, nombre: string) => (
    <div className="flex justify-end gap-1">
      <Button variant="ghost" size="icon-sm" onClick={onEditar} aria-label={`Editar ${nombre}`}>
        <Pencil />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        className="text-tinta-3 hover:bg-critico-tenue hover:text-critico"
        onClick={onEliminar}
        aria-label={`Desactivar ${nombre}`}
      >
        <Trash2 />
      </Button>
    </div>
  );

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Operación"
        titulo="Flota"
        descripcion="Tractocamiones y ramplas, con el estado de su documentación."
        acciones={
          puedeEscribir && (
            <>
              <Button variant="outline" onClick={nuevaRampla}>
                <Plus /> Rampla
              </Button>
              <Button onClick={nuevoTracto}>
                <Plus /> Tractocamión
              </Button>
            </>
          )
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-s3">
        <Segmentado
          etiqueta="Tipo de equipo"
          valor={pestana}
          onCambio={setPestana}
          opciones={[
            { valor: "tractos", etiqueta: "Tractocamiones", contador: tractos.length },
            { valor: "ramplas", etiqueta: "Ramplas", contador: ramplas.length },
          ]}
        />
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-[18px] -translate-y-1/2 text-tinta-3" />
          <Input value={busqueda} onChange={(e) => setBusqueda(e.target.value)} placeholder="Buscar por patente o marca" className="pl-10" aria-label="Buscar equipos" />
        </div>
      </div>

      <Panel>
        {pestana === "tractos" ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Patente</TableHead>
                <TableHead>Marca / modelo</TableHead>
                <TableHead>Año</TableHead>
                <TableHead className="text-right">Kilometraje</TableHead>
                <TableHead>Rev. técnica</TableHead>
                <TableHead>Seguro</TableHead>
                {puedeEscribir && <TableHead className="w-28 text-right">Acciones</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <FilasCargando columnas={puedeEscribir ? 7 : 6} />
              ) : tractosFiltrados.length === 0 ? (
                <FilaVacia columnas={puedeEscribir ? 7 : 6} icono={Truck} titulo={tractos.length ? "Sin resultados" : "Aún no hay tractocamiones"} descripcion={tractos.length ? "Pruebe con otra patente." : "Registre los tractocamiones de la flota."} />
              ) : (
                tractosFiltrados.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>
                      <Patente>{t.patente}</Patente>
                    </TableCell>
                    <TableCell>
                      <span className="font-medium">{t.marca ?? "—"}</span>
                      {t.modelo && <span className="text-tinta-3"> · {t.modelo}</span>}
                    </TableCell>
                    <TableCell className="text-tinta-2">{t.ano ?? "—"}</TableCell>
                    <TableCell className="cifra text-right">{km(t.km_actual)} km</TableCell>
                    <TableCell>
                      <Vencimiento fecha={t.vencimiento_revision_tecnica} />
                    </TableCell>
                    <TableCell>
                      <Vencimiento fecha={t.vencimiento_seguro} />
                    </TableCell>
                    {puedeEscribir && (
                      <TableCell>{acciones(() => editarTracto(t), () => setEliminando({ tipo: "tractos", id: t.id, patente: t.patente }), t.patente)}</TableCell>
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
                <TableHead>Patente</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Rev. técnica</TableHead>
                {puedeEscribir && <TableHead className="w-28 text-right">Acciones</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <FilasCargando columnas={puedeEscribir ? 4 : 3} />
              ) : ramplasFiltradas.length === 0 ? (
                <FilaVacia columnas={puedeEscribir ? 4 : 3} icono={Container} titulo={ramplas.length ? "Sin resultados" : "Aún no hay ramplas"} descripcion={ramplas.length ? "Pruebe con otra patente." : "Registre las ramplas de la flota."} />
              ) : (
                ramplasFiltradas.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>
                      <Patente>{r.patente}</Patente>
                    </TableCell>
                    <TableCell className="capitalize text-tinta-2">{r.tipo}</TableCell>
                    <TableCell>
                      <Vencimiento fecha={r.vencimiento_revision_tecnica} />
                    </TableCell>
                    {puedeEscribir && (
                      <TableCell>{acciones(() => editarRampla(r), () => setEliminando({ tipo: "ramplas", id: r.id, patente: r.patente }), r.patente)}</TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </Panel>

      <Dialog open={dialogoTracto} onOpenChange={setDialogoTracto}>
        <DialogContent className="max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editandoTracto ? "Editar tractocamión" : "Nuevo tractocamión"}</DialogTitle>
            <DialogDescription>Los vencimientos se alertan 30 días antes en el panel de control.</DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Patente" htmlFor="t-pat" requerido error={intento && !formTracto.patente.trim() ? "Ingrese la patente" : null}>
                <Input id="t-pat" value={formTracto.patente} onChange={(e) => setFormTracto({ ...formTracto, patente: e.target.value.toUpperCase() })} className="font-mono uppercase" placeholder="BBCT-34" />
              </Campo>
              <Campo etiqueta="Año" htmlFor="t-ano">
                <Input id="t-ano" type="number" min={1980} max={2100} value={formTracto.ano} onChange={(e) => setFormTracto({ ...formTracto, ano: e.target.value })} />
              </Campo>
              <Campo etiqueta="Marca" htmlFor="t-marca">
                <Input id="t-marca" value={formTracto.marca} onChange={(e) => setFormTracto({ ...formTracto, marca: e.target.value })} placeholder="Freightliner" />
              </Campo>
              <Campo etiqueta="Modelo" htmlFor="t-modelo">
                <Input id="t-modelo" value={formTracto.modelo} onChange={(e) => setFormTracto({ ...formTracto, modelo: e.target.value })} />
              </Campo>
            </div>
            <Campo
              etiqueta="Kilometraje actual"
              htmlFor="t-km"
              error={kmInvalido ? `No puede ser menor a ${km(editandoTracto!.km_actual)} km` : null}
              ayuda={editandoTracto ? "Solo puede aumentar. Se actualiza también al registrar mantenciones." : undefined}
            >
              <Input id="t-km" type="number" min={0} value={formTracto.km_actual} onChange={(e) => setFormTracto({ ...formTracto, km_actual: e.target.value })} aria-invalid={kmInvalido} />
            </Campo>
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Revisión técnica" htmlFor="t-rt">
                <Input id="t-rt" type="date" value={formTracto.vencimiento_revision_tecnica} onChange={(e) => setFormTracto({ ...formTracto, vencimiento_revision_tecnica: e.target.value })} />
              </Campo>
              <Campo etiqueta="Seguro" htmlFor="t-seg">
                <Input id="t-seg" type="date" value={formTracto.vencimiento_seguro} onChange={(e) => setFormTracto({ ...formTracto, vencimiento_seguro: e.target.value })} />
              </Campo>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoTracto(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarTracto} disabled={guardando}>
              {guardando ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoRampla} onOpenChange={setDialogoRampla}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editandoRampla ? "Editar rampla" : "Nueva rampla"}</DialogTitle>
            <DialogDescription>Registre la patente, el tipo y la revisión técnica.</DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Patente" htmlFor="r-pat" requerido error={intento && !formRampla.patente.trim() ? "Ingrese la patente" : null}>
                <Input id="r-pat" value={formRampla.patente} onChange={(e) => setFormRampla({ ...formRampla, patente: e.target.value.toUpperCase() })} className="font-mono uppercase" placeholder="JK-1234" />
              </Campo>
              <Campo etiqueta="Tipo" htmlFor="r-tipo">
                <SelectSimple
                  id="r-tipo"
                  valor={formRampla.tipo}
                  onCambio={(v) => setFormRampla({ ...formRampla, tipo: (v || "plana") as "plana" | "sider" })}
                  opciones={[
                    { valor: "plana", etiqueta: "Plana" },
                    { valor: "sider", etiqueta: "Sider" },
                  ]}
                />
              </Campo>
            </div>
            <Campo etiqueta="Revisión técnica" htmlFor="r-rt">
              <Input id="r-rt" type="date" value={formRampla.vencimiento_revision_tecnica} onChange={(e) => setFormRampla({ ...formRampla, vencimiento_revision_tecnica: e.target.value })} />
            </Campo>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoRampla(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarRampla} disabled={guardando}>
              {guardando ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!eliminando} onOpenChange={(o) => !o && setEliminando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desactivar equipo</DialogTitle>
            <DialogDescription>
              La patente <strong>{eliminando?.patente}</strong> dejará de estar disponible para nuevos viajes. Su historial
              se conserva.
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
