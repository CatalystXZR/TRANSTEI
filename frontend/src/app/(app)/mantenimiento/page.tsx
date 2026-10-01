"use client";

import { useEffect, useMemo, useState } from "react";
import { History, ListChecks, Pencil, Plus, Trash2, Truck, Wrench } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { api } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { Tracto } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputCLP } from "@/components/ui-inputs/input-clp";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Aviso,
  EstadoVacio,
  FilaVacia,
  FilasCargando,
  PageHeader,
  Panel,
  Patente,
  Segmentado,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import { Campo, SelectSimple } from "@/components/formulario";

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

interface Registro {
  id: string;
  tracto_id: string;
  pauta_id: string;
  fecha: string;
  km: number;
  costo: string;
  notas: string | null;
}

const ESTADO_MANT: Record<ItemEstado["estado"], { tono: Tono; label: string }> = {
  pendiente: { tono: "critico", label: "Vencido" },
  por_vencer: { tono: "atencion", label: "Próximo" },
  ok: { tono: "ok", label: "Al día" },
  sin_registro: { tono: "neutro", label: "Sin registro" },
};

const km = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `${new Intl.NumberFormat("es-CL").format(n)} km`);

function hoyISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function MantenimientoPage() {
  const { usuario } = useAuth();
  const [pestana, setPestana] = useState<"estado" | "pauta" | "registros">("estado");
  const [estados, setEstados] = useState<EstadoTracto[]>([]);
  const [pautas, setPautas] = useState<Pauta[]>([]);
  const [tractos, setTractos] = useState<Tracto[]>([]);
  const [registros, setRegistros] = useState<Registro[]>([]);
  const [cargando, setCargando] = useState(true);

  const [dialogoPauta, setDialogoPauta] = useState(false);
  const [editandoPauta, setEditandoPauta] = useState<Pauta | null>(null);
  const [formPauta, setFormPauta] = useState({ item: "", intervalo_km: "20000" });
  const [quitandoPauta, setQuitandoPauta] = useState<Pauta | null>(null);

  const [dialogoMant, setDialogoMant] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [intento, setIntento] = useState(false);
  const [formMant, setFormMant] = useState({ tracto_id: "", pauta_id: "", km: "", fecha: "", costo: 0 });

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  function cargarTodo() {
    return Promise.all([
      api.get<EstadoTracto[]>("/mantenimiento/estado"),
      api.get<Pauta[]>("/pautas"),
      api.get<Tracto[]>("/tractos?activo=true"),
      api.get<Registro[]>("/mantenimientos"),
    ]);
  }

  function recargar() {
    cargarTodo()
      .then(([e, p, t, r]) => {
        setEstados(e ?? []);
        setPautas(p ?? []);
        setTractos(t ?? []);
        setRegistros(r ?? []);
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : "Error al cargar"))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    cargarTodo()
      .then(([e, p, t, r]) => {
        if (!activo) return;
        setEstados(e ?? []);
        setPautas(p ?? []);
        setTractos(t ?? []);
        setRegistros(r ?? []);
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

  const resumen = useMemo(() => {
    let vencidos = 0;
    let proximos = 0;
    estados.forEach((t) =>
      t.items.forEach((i) => {
        if (i.estado === "pendiente") vencidos++;
        if (i.estado === "por_vencer") proximos++;
      }),
    );
    return { vencidos, proximos };
  }, [estados]);

  const patentePorId = useMemo(() => new Map(tractos.map((t) => [t.id, t.patente])), [tractos]);
  const itemPorId = useMemo(() => new Map(pautas.map((p) => [p.id, p.item])), [pautas]);

  function abrirMantencion(tractoId = "", pautaId = "") {
    const t = tractos.find((x) => x.id === tractoId);
    setFormMant({ tracto_id: tractoId, pauta_id: pautaId, km: t ? String(t.km_actual) : "", fecha: hoyISO(), costo: 0 });
    setIntento(false);
    setDialogoMant(true);
  }

  async function guardarPauta() {
    if (!formPauta.item.trim() || !(Number(formPauta.intervalo_km) > 0)) {
      toast.error("Complete el ítem y un intervalo mayor a cero");
      return;
    }
    try {
      const body = { item: formPauta.item.trim(), intervalo_km: Number(formPauta.intervalo_km), orden: editandoPauta?.orden ?? pautas.length + 1 };
      if (editandoPauta) {
        await api.put(`/pautas/${editandoPauta.id}`, body);
        toast.success("Ítem actualizado");
      } else {
        await api.post("/pautas", body);
        toast.success("Ítem agregado a la pauta");
      }
      setDialogoPauta(false);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    }
  }

  async function confirmarQuitarPauta() {
    if (!quitandoPauta) return;
    try {
      await api.del(`/pautas/${quitandoPauta.id}`);
      toast.success("Ítem quitado de la pauta");
      setQuitandoPauta(null);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  const tractoSel = tractos.find((t) => t.id === formMant.tracto_id);

  async function guardarMantencion() {
    setIntento(true);
    if (!formMant.tracto_id || !formMant.pauta_id || !formMant.km) {
      toast.error("Seleccione camión, ítem e ingrese el kilometraje");
      return;
    }
    setGuardando(true);
    try {
      const qs = new URLSearchParams({
        tracto_id: formMant.tracto_id,
        pauta_id: formMant.pauta_id,
        km: String(Math.max(0, Number(formMant.km))),
        fecha: formMant.fecha || hoyISO(),
        costo: String(formMant.costo || 0),
      });
      await api.post(`/mantenimientos?${qs.toString()}`, {});
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
    <div className="space-y-s5">
      <PageHeader
        rotulo="Operación"
        titulo="Mantenimiento"
        descripcion="Pauta preventiva por kilometraje. Un ítem vencido permanece marcado hasta registrar su mantención."
        acciones={
          puedeEscribir && (
            <Button onClick={() => abrirMantencion()}>
              <Wrench /> Registrar mantención
            </Button>
          )
        }
      />

      {!cargando && (resumen.vencidos > 0 || resumen.proximos > 0) && (
        <Aviso tono={resumen.vencidos > 0 ? "critico" : "atencion"} icono={Wrench}>
          {resumen.vencidos > 0 && (
            <>
              <strong>{resumen.vencidos}</strong> {resumen.vencidos === 1 ? "ítem vencido" : "ítems vencidos"}
            </>
          )}
          {resumen.vencidos > 0 && resumen.proximos > 0 && " y "}
          {resumen.proximos > 0 && (
            <>
              <strong>{resumen.proximos}</strong> {resumen.proximos === 1 ? "próximo a vencer" : "próximos a vencer"}
            </>
          )}
          . Se alerta 5.000 km antes del cambio.
        </Aviso>
      )}

      <Segmentado
        etiqueta="Vista"
        valor={pestana}
        onCambio={setPestana}
        opciones={[
          { valor: "estado", etiqueta: "Estado de la flota", contador: estados.length },
          { valor: "pauta", etiqueta: "Pauta", contador: pautas.length },
          { valor: "registros", etiqueta: "Historial", contador: registros.length },
        ]}
      />

      {pestana === "estado" &&
        (cargando ? (
          <div className="space-y-s3">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-48 w-full rounded-xl" />
            ))}
          </div>
        ) : estados.length === 0 ? (
          <Panel>
            <EstadoVacio icono={Truck} titulo="No hay tractocamiones" descripcion="Registre la flota para comenzar a controlar su mantenimiento." />
          </Panel>
        ) : (
          <div className="space-y-s4">
            {estados.map((t) => {
              const peor = t.items.some((i) => i.estado === "pendiente") ? "critico" : t.items.some((i) => i.estado === "por_vencer") ? "atencion" : "ok";
              return (
                <Panel
                  key={t.tracto_id}
                  titulo={
                    <span className="flex items-center gap-s3">
                      <Patente>{t.patente}</Patente>
                      <span className="cifra text-[15px] font-normal text-tinta-3">{km(t.km_actual)}</span>
                    </span>
                  }
                  acciones={
                    <StatusBadge tono={peor}>{peor === "critico" ? "Requiere mantención" : peor === "atencion" ? "Próximo a mantención" : "Al día"}</StatusBadge>
                  }
                >
                  <div className="grid gap-px bg-borde sm:grid-cols-2 xl:grid-cols-3">
                    {t.items.map((i) => {
                      const e = ESTADO_MANT[i.estado];
                      const usado =
                        i.ultimo_km !== null && i.intervalo_km > 0 ? Math.min(100, Math.max(0, ((t.km_actual - i.ultimo_km) / i.intervalo_km) * 100)) : 0;
                      return (
                        <button
                          key={i.pauta_id}
                          type="button"
                          disabled={!puedeEscribir}
                          onClick={() => abrirMantencion(t.tracto_id, i.pauta_id)}
                          className="group bg-superficie p-s4 text-left transition-colors enabled:cursor-pointer enabled:hover:bg-marca-tenue/40 disabled:cursor-default"
                          aria-label={`${i.item}: ${e.label}. ${puedeEscribir ? "Registrar mantención" : ""}`}
                        >
                          <div className="flex items-start justify-between gap-s2">
                            <p className="text-[15.5px] font-medium">{i.item}</p>
                            <StatusBadge tono={e.tono}>{e.label}</StatusBadge>
                          </div>
                          <div className="mt-s3 h-1.5 overflow-hidden rounded-full bg-superficie-hundida">
                            <div
                              className={cn(
                                "h-full rounded-full transition-[width] duration-700",
                                i.estado === "pendiente" ? "bg-critico" : i.estado === "por_vencer" ? "bg-senal" : i.estado === "ok" ? "bg-ok" : "bg-borde-fuerte",
                              )}
                              style={{ width: `${i.estado === "sin_registro" ? 0 : usado}%` }}
                            />
                          </div>
                          <p className="mt-s2 text-[13.5px] text-tinta-3">
                            {i.estado === "sin_registro" ? (
                              <>Cada {km(i.intervalo_km)} · sin mantención registrada</>
                            ) : i.estado === "pendiente" ? (
                              <span className="font-medium text-critico">Excedido en {km(-(i.km_restante ?? 0))}</span>
                            ) : (
                              <>
                                Faltan <span className={cn("font-medium", i.estado === "por_vencer" ? "text-atencion" : "text-tinta-2")}>{km(i.km_restante)}</span> · próximo a los {km(i.proximo_km)}
                              </>
                            )}
                          </p>
                          {i.ultima_fecha && <p className="text-[13px] text-tinta-3">Último: {formatFecha(i.ultima_fecha)} a los {km(i.ultimo_km)}</p>}
                        </button>
                      );
                    })}
                  </div>
                </Panel>
              );
            })}
          </div>
        ))}

      {pestana === "pauta" && (
        <Panel
          titulo="Pauta de mantenimiento"
          descripcion="Aplica a toda la flota"
          acciones={
            puedeEscribir && (
              <Button
                size="sm"
                onClick={() => {
                  setEditandoPauta(null);
                  setFormPauta({ item: "", intervalo_km: "20000" });
                  setDialogoPauta(true);
                }}
              >
                <Plus /> Agregar ítem
              </Button>
            )
          }
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ítem</TableHead>
                <TableHead className="text-right">Intervalo</TableHead>
                {puedeEscribir && <TableHead className="w-28 text-right">Acciones</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <FilasCargando columnas={puedeEscribir ? 3 : 2} />
              ) : pautas.length === 0 ? (
                <FilaVacia columnas={puedeEscribir ? 3 : 2} icono={ListChecks} titulo="Pauta vacía" descripcion="Agregue ítems como cambio de aceite o engrase." />
              ) : (
                pautas.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.item}</TableCell>
                    <TableCell className="cifra text-right">cada {km(p.intervalo_km)}</TableCell>
                    {puedeEscribir && (
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => {
                              setEditandoPauta(p);
                              setFormPauta({ item: p.item, intervalo_km: String(p.intervalo_km) });
                              setDialogoPauta(true);
                            }}
                            aria-label={`Editar ${p.item}`}
                          >
                            <Pencil />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="text-tinta-3 hover:bg-critico-tenue hover:text-critico"
                            onClick={() => setQuitandoPauta(p)}
                            aria-label={`Quitar ${p.item}`}
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
      )}

      {pestana === "registros" && (
        <Panel titulo="Historial de mantenciones">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fecha</TableHead>
                <TableHead>Camión</TableHead>
                <TableHead>Ítem</TableHead>
                <TableHead className="text-right">Kilometraje</TableHead>
                <TableHead className="text-right">Costo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <FilasCargando columnas={5} />
              ) : registros.length === 0 ? (
                <FilaVacia columnas={5} icono={History} titulo="Sin mantenciones registradas" />
              ) : (
                registros.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="text-tinta-2">{formatFecha(r.fecha)}</TableCell>
                    <TableCell>
                      <Patente>{patentePorId.get(r.tracto_id) ?? "—"}</Patente>
                    </TableCell>
                    <TableCell className="font-medium">{itemPorId.get(r.pauta_id) ?? "Ítem eliminado"}</TableCell>
                    <TableCell className="cifra text-right">{km(r.km)}</TableCell>
                    <TableCell className="cifra text-right">{Number(r.costo) ? formatCLP(r.costo) : "—"}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Panel>
      )}

      <Dialog open={dialogoPauta} onOpenChange={setDialogoPauta}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editandoPauta ? "Editar ítem" : "Nuevo ítem de pauta"}</DialogTitle>
            <DialogDescription>Ej.: cambio de aceite cada 20.000 km, engrase cada 5.000 km.</DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <Campo etiqueta="Ítem" htmlFor="p-item" requerido>
              <Input id="p-item" value={formPauta.item} onChange={(e) => setFormPauta({ ...formPauta, item: e.target.value })} placeholder="Cambio de aceite" />
            </Campo>
            <Campo etiqueta="Intervalo (km)" htmlFor="p-int" requerido>
              <Input id="p-int" type="number" min={500} step={500} value={formPauta.intervalo_km} onChange={(e) => setFormPauta({ ...formPauta, intervalo_km: e.target.value })} />
            </Campo>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoPauta(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarPauta}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!quitandoPauta} onOpenChange={(o) => !o && setQuitandoPauta(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Quitar ítem de la pauta</DialogTitle>
            <DialogDescription>
              <strong>{quitandoPauta?.item}</strong> dejará de controlarse en la flota. El historial se conserva.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setQuitandoPauta(null)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={confirmarQuitarPauta}>
              <Trash2 /> Quitar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoMant} onOpenChange={setDialogoMant}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar mantención</DialogTitle>
            <DialogDescription>El kilometraje registrado actualiza el estado y el kilometraje del camión.</DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Camión" htmlFor="m-tracto" requerido error={intento && !formMant.tracto_id ? "Seleccione el camión" : null}>
                <SelectSimple
                  id="m-tracto"
                  valor={formMant.tracto_id}
                  onCambio={(v) => {
                    const t = tractos.find((x) => x.id === v);
                    setFormMant({ ...formMant, tracto_id: v, km: t ? String(t.km_actual) : formMant.km });
                  }}
                  placeholder="Seleccione camión"
                  opciones={tractos.map((t) => ({ valor: t.id, etiqueta: `${t.patente} · ${km(t.km_actual)}` }))}
                />
              </Campo>
              <Campo etiqueta="Ítem" htmlFor="m-item" requerido error={intento && !formMant.pauta_id ? "Seleccione el ítem" : null}>
                <SelectSimple
                  id="m-item"
                  valor={formMant.pauta_id}
                  onCambio={(v) => setFormMant({ ...formMant, pauta_id: v })}
                  placeholder="Seleccione ítem"
                  opciones={pautas.map((p) => ({ valor: p.id, etiqueta: p.item }))}
                />
              </Campo>
              <Campo
                etiqueta="Kilometraje"
                htmlFor="m-km"
                requerido
                error={intento && !formMant.km ? "Ingrese el kilometraje" : null}
                ayuda={tractoSel ? `Actual registrado: ${km(tractoSel.km_actual)}` : undefined}
              >
                <Input id="m-km" type="number" min={0} value={formMant.km} onChange={(e) => setFormMant({ ...formMant, km: e.target.value })} />
              </Campo>
              <Campo etiqueta="Fecha" htmlFor="m-fecha">
                <Input id="m-fecha" type="date" value={formMant.fecha} onChange={(e) => setFormMant({ ...formMant, fecha: e.target.value })} />
              </Campo>
            </div>
            <Campo etiqueta="Costo" htmlFor="m-costo">
              <InputCLP key={dialogoMant ? "abierto" : "cerrado"} id="m-costo" value={formMant.costo} onChange={(v) => setFormMant({ ...formMant, costo: v })} placeholder="$ 0" />
            </Campo>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoMant(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarMantencion} disabled={guardando}>
              {guardando ? "Guardando…" : "Registrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
