"use client";

import { useCallback, useEffect, useState } from "react";
import { Gauge, Lock, Pencil, Plus, Power, Trash2, Wand2, X } from "lucide-react";
import { cn } from "cn";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/auth-context";
import type {
  AmbitoKpi,
  CatalogoKpis,
  Chofer,
  FormatoKpi,
  Kpi,
  KpiValor,
  PreviewKpi,
  ReglaColor,
  UsoKpi,
} from "@/types";
import { TONO_KPI, formatValorKpi } from "@/types";
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
import { EstadoVacio, FilaVacia, FilasCargando, PageHeader, Panel, StatusBadge } from "@/components/sistema";
import { AreaTexto, Campo, SelectSimple } from "@/components/formulario";


const COLORES = ["rojo", "amarillo", "verde", "azul", "gris"] as const;
const OPERADORES = ["<", "<=", ">", ">=", "="] as const;

interface FormKpi {
  nombre: string;
  descripcion: string;
  ambito: AmbitoKpi;
  formato: FormatoKpi;
  periodo: string;
  uso: UsoKpi;
  formula: string;
  reglas_color: ReglaColor[];
  activo: boolean;
}

const VACIO: FormKpi = {
  nombre: "",
  descripcion: "",
  ambito: "global",
  formato: "numero",
  periodo: "mes",
  uso: "dashboard",
  formula: "",
  reglas_color: [],
  activo: true,
};

export default function KpisPage() {
  const { usuario } = useAuth();
  const [kpis, setKpis] = useState<Kpi[]>([]);
  const [valores, setValores] = useState<KpiValor[]>([]);
  const [choferes, setChoferes] = useState<Chofer[]>([]);
  const [cargando, setCargando] = useState(true);

  const [dialogo, setDialogo] = useState(false);
  const [editando, setEditando] = useState<Kpi | null>(null);
  const [form, setForm] = useState<FormKpi>(VACIO);
  const [catalogo, setCatalogo] = useState<CatalogoKpis | null>(null);
  const [preview, setPreview] = useState<PreviewKpi | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [mesPrueba, setMesPrueba] = useState(
    new Date().toISOString().slice(0, 7),
  );
  const [fletePrueba, setFletePrueba] = useState(1000000);
  const [gastosPrueba, setGastosPrueba] = useState(0);
  const [choferPrueba, setChoferPrueba] = useState("");

  const esAdmin = usuario?.rol === "admin";

  const recargar = useCallback(() => {
    api
      .get<Kpi[]>("/kpis")
      .then((d) => setKpis(d ?? []))
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar"));
    api
      .get<KpiValor[]>("/kpis/valores")
      .then((d) => setValores(d ?? []))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let activo = true;
    Promise.all([api.get<Kpi[]>("/kpis"), api.get<KpiValor[]>("/kpis/valores")])
      .then(([k, v]) => {
        if (!activo) return;
        setKpis(k ?? []);
        setValores(v ?? []);
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
  }, []);

  const cargarCatalogo = useCallback((ambito: AmbitoKpi) => {
    api
      .get<CatalogoKpis>(`/kpis/catalogo?ambito=${ambito}`)
      .then((d) => setCatalogo(d ?? null))
      .catch(() => setCatalogo(null));
  }, []);

  useEffect(() => {
    if (!dialogo) return;
    let activo = true;
    api
      .get<Chofer[]>("/choferes?activo=true")
      .then((d) => {
        if (activo) setChoferes(d ?? []);
      })
      .catch(() => undefined);
    return () => {
      activo = false;
    };
  }, [dialogo]);

  function abrirNuevo() {
    setEditando(null);
    setForm(VACIO);
    setPreview(null);
    cargarCatalogo("global");
    setDialogo(true);
  }

  function abrirEditar(kpi: Kpi) {
    setEditando(kpi);
    setForm({
      nombre: kpi.nombre,
      descripcion: kpi.descripcion ?? "",
      ambito: kpi.ambito,
      formato: kpi.formato,
      periodo: kpi.periodo,
      uso: kpi.uso,
      formula: kpi.formula,
      reglas_color: kpi.reglas_color ?? [],
      activo: kpi.activo,
    });
    setPreview(null);
    cargarCatalogo(kpi.ambito);
    setDialogo(true);
  }

  function cambiarAmbito(ambito: AmbitoKpi) {
    setForm((f) => ({ ...f, ambito }));
    setPreview(null);
    cargarCatalogo(ambito);
  }

  function insertarEnFormula(texto: string) {
    setForm((f) => ({
      ...f,
      formula: f.formula ? `${f.formula} ${texto}` : texto,
    }));
  }

  async function probar() {
    if (!form.formula.trim()) {
      toast.error("Escriba una fórmula para probar");
      return;
    }
    try {
      const body: Record<string, unknown> = {
        formula: form.formula,
        ambito: form.ambito,
      };
      if (form.ambito === "global") {
        body.periodo = mesPrueba;
      } else {
        body.flete_viaje = fletePrueba;
        body.gastos_viaje = gastosPrueba;
        body.chofer_id = choferPrueba || null;
      }
      const res = await api.post<PreviewKpi>("/kpis/preview", body);
      setPreview(res);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al probar");
    }
  }

  async function guardar() {
    if (!form.nombre.trim() || !form.formula.trim()) {
      toast.error("Complete nombre y fórmula");
      return;
    }
    setGuardando(true);
    const body = {
      nombre: form.nombre.trim(),
      descripcion: form.descripcion.trim() || null,
      ambito: form.ambito,
      formato: form.formato,
      periodo: form.periodo,
      uso: form.uso,
      formula: form.formula.trim(),
      reglas_color: form.reglas_color,
      activo: form.activo,
      orden: editando?.orden ?? kpis.length + 1,
    };
    try {
      if (editando) {
        await api.put(`/kpis/${editando.id}`, body);
        toast.success("KPI actualizado");
      } else {
        await api.post("/kpis", body);
        toast.success("KPI creado");
      }
      setDialogo(false);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setGuardando(false);
    }
  }

  async function desactivar(kpi: Kpi) {
    if (!confirm(`¿Desactivar el KPI "${kpi.nombre}"?`)) return;
    try {
      await api.del(`/kpis/${kpi.id}`);
      toast.success("KPI desactivado");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function reactivar(kpi: Kpi) {
    try {
      await api.put(`/kpis/${kpi.id}`, { activo: true });
      toast.success("KPI reactivado");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  function agregarRegla() {
    setForm((f) => ({
      ...f,
      reglas_color: [...f.reglas_color, { operador: "<", valor: 0, color: "rojo" }],
    }));
  }

  function actualizarRegla(i: number, parcial: Partial<ReglaColor>) {
    setForm((f) => ({
      ...f,
      reglas_color: f.reglas_color.map((r, idx) => (idx === i ? { ...r, ...parcial } : r)),
    }));
  }

  function quitarRegla(i: number) {
    setForm((f) => ({
      ...f,
      reglas_color: f.reglas_color.filter((_, idx) => idx !== i),
    }));
  }

  if (!esAdmin) {
    return (
      <Panel>
        <EstadoVacio icono={Lock} titulo="Acceso restringido" descripcion="Solo el administrador puede configurar indicadores." />
      </Panel>
    );
  }

  const valoresPorId = new Map(valores.map((v) => [v.id, v]));
  const USO_LABEL: Record<UsoKpi, string> = { dashboard: "Panel de control", rentabilidad_viaje: "Rentabilidad de viaje", interno: "Interno" };

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Sistema"
        titulo="Indicadores"
        descripcion="Defina los indicadores del panel con fórmulas sobre los datos del sistema. Se calculan en el servidor de forma segura."
        acciones={
          <Button onClick={abrirNuevo}>
            <Plus /> Nuevo indicador
          </Button>
        }
      />

      <Panel>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Indicador</TableHead>
              <TableHead>Fórmula</TableHead>
              <TableHead>Valor actual</TableHead>
              <TableHead>Uso</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="w-28 text-right">Acciones</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <FilasCargando columnas={6} />
            ) : kpis.length === 0 ? (
              <FilaVacia columnas={6} icono={Gauge} titulo="Sin indicadores" descripcion="Cree el primero para verlo en el panel de control." />
            ) : (
              kpis.map((k) => {
                const valor = valoresPorId.get(k.id);
                return (
                  <TableRow key={k.id} className={cn(!k.activo && "opacity-60")}>
                    <TableCell className="whitespace-normal">
                      <span className="font-medium">{k.nombre}</span>
                      {k.descripcion && <span className="block max-w-xs text-[13.5px] text-tinta-3">{k.descripcion}</span>}
                    </TableCell>
                    <TableCell>
                      <code className="block max-w-[320px] truncate rounded-md bg-superficie-hundida px-2 py-1 font-mono text-[13px] text-tinta-2" title={k.formula}>
                        {k.formula}
                      </code>
                    </TableCell>
                    <TableCell>
                      {valor ? (
                        valor.error ? (
                          <StatusBadge tono="critico">Error</StatusBadge>
                        ) : (
                          <StatusBadge tono={TONO_KPI[valor.color] ?? "neutro"}>{formatValorKpi(valor.valor, valor.formato)}</StatusBadge>
                        )
                      ) : (
                        <span className="text-[14px] text-tinta-3">{k.ambito === "viaje" ? "Por viaje" : "—"}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-tinta-2">{USO_LABEL[k.uso]}</TableCell>
                    <TableCell>{k.activo ? <StatusBadge tono="ok">Activo</StatusBadge> : <StatusBadge tono="neutro">Inactivo</StatusBadge>}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon-sm" onClick={() => abrirEditar(k)} aria-label={`Editar ${k.nombre}`}>
                          <Pencil />
                        </Button>
                        {k.activo ? (
                          <Button variant="ghost" size="icon-sm" className="text-tinta-3 hover:bg-critico-tenue hover:text-critico" onClick={() => desactivar(k)} aria-label={`Desactivar ${k.nombre}`}>
                            <Trash2 />
                          </Button>
                        ) : (
                          <Button variant="ghost" size="icon-sm" className="text-tinta-3 hover:bg-ok-tenue hover:text-ok" onClick={() => reactivar(k)} aria-label={`Reactivar ${k.nombre}`}>
                            <Power />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </Panel>

      <Dialog open={dialogo} onOpenChange={setDialogo}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{editando ? "Editar indicador" : "Nuevo indicador"}</DialogTitle>
            <DialogDescription>Escriba la fórmula con las métricas del catálogo y pruébela antes de guardar.</DialogDescription>
          </DialogHeader>

          <div className="space-y-s4">
            <div className="grid gap-s3 md:grid-cols-2">
              <Campo etiqueta="Nombre" htmlFor="k-nombre" requerido className="md:col-span-2">
                <Input id="k-nombre" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} placeholder="Margen del mes (%)" />
              </Campo>
              <Campo etiqueta="Descripción" htmlFor="k-desc" className="md:col-span-2">
                <Input id="k-desc" value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} placeholder="Opcional" />
              </Campo>
              <Campo etiqueta="Ámbito" htmlFor="k-ambito">
                <SelectSimple
                  id="k-ambito"
                  valor={form.ambito}
                  onCambio={(v) => cambiarAmbito((v || "global") as AmbitoKpi)}
                  opciones={[
                    { valor: "global", etiqueta: "Global (por período)" },
                    { valor: "viaje", etiqueta: "Por viaje" },
                  ]}
                />
              </Campo>
              <Campo etiqueta="Formato" htmlFor="k-formato">
                <SelectSimple
                  id="k-formato"
                  valor={form.formato}
                  onCambio={(v) => setForm({ ...form, formato: (v || "numero") as FormatoKpi })}
                  opciones={[
                    { valor: "clp", etiqueta: "Pesos ($)" },
                    { valor: "numero", etiqueta: "Número" },
                    { valor: "porcentaje", etiqueta: "Porcentaje (%)" },
                  ]}
                />
              </Campo>
              <Campo etiqueta="Uso" htmlFor="k-uso">
                <SelectSimple
                  id="k-uso"
                  valor={form.uso}
                  onCambio={(v) => setForm({ ...form, uso: (v || "dashboard") as UsoKpi })}
                  opciones={[
                    { valor: "dashboard", etiqueta: "Panel de control" },
                    { valor: "rentabilidad_viaje", etiqueta: "Rentabilidad de viaje" },
                    { valor: "interno", etiqueta: "Interno" },
                  ]}
                />
              </Campo>
              <Campo etiqueta="Estado" htmlFor="k-activo">
                <SelectSimple
                  id="k-activo"
                  valor={form.activo ? "si" : "no"}
                  onCambio={(v) => setForm({ ...form, activo: v !== "no" })}
                  opciones={[
                    { valor: "si", etiqueta: "Activo" },
                    { valor: "no", etiqueta: "Inactivo" },
                  ]}
                />
              </Campo>
            </div>

            <Campo etiqueta="Fórmula" htmlFor="k-formula" requerido>
              <AreaTexto
                id="k-formula"
                value={form.formula}
                onChange={(e) => {
                  setForm({ ...form, formula: e.target.value });
                  setPreview(null);
                }}
                rows={3}
                spellCheck={false}
                className="font-mono text-[15px]"
                placeholder="SI(ingresos_mes = 0, 0, margen_bruto / ingresos_mes * 100)"
              />
            </Campo>

            {catalogo && (
              <div className="space-y-s2 rounded-xl border border-borde bg-superficie-hundida/60 p-s3">
                <p className="rotulo">Métricas · clic para insertar</p>
                <div className="flex flex-wrap gap-1.5">
                  {catalogo.metricas.map((m) => (
                    <button
                      key={m.nombre}
                      type="button"
                      title={m.descripcion}
                      onClick={() => insertarEnFormula(m.nombre)}
                      className="cursor-pointer rounded-md border border-borde-fuerte bg-superficie px-2 py-1 font-mono text-[13px] text-tinta-2 transition-[background-color,color,border-color,transform] duration-150 hover:-translate-y-px hover:border-marca/40 hover:bg-marca-tenue hover:text-marca"
                    >
                      {m.nombre}
                    </button>
                  ))}
                </div>
                <p className="rotulo pt-s2">Funciones</p>
                <div className="flex flex-wrap gap-1.5">
                  {catalogo.funciones.map((f) => (
                    <span key={f.nombre} title={f.descripcion} className="rounded-md bg-superficie px-2 py-1 font-mono text-[13px] text-tinta-3">
                      {f.nombre}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-s3 rounded-xl border border-borde p-s3">
              <p className="rotulo">Probar con</p>
              {form.ambito === "global" ? (
                <Campo etiqueta="Mes" htmlFor="k-mes" className="max-w-[220px]">
                  <Input id="k-mes" type="month" value={mesPrueba} onChange={(e) => setMesPrueba(e.target.value)} />
                </Campo>
              ) : (
                <div className="grid gap-s3 sm:grid-cols-3">
                  <Campo etiqueta="Flete ($)" htmlFor="k-flete">
                    <Input id="k-flete" type="number" value={fletePrueba} onChange={(e) => setFletePrueba(Number(e.target.value) || 0)} />
                  </Campo>
                  <Campo etiqueta="Gastos ($)" htmlFor="k-gastos">
                    <Input id="k-gastos" type="number" value={gastosPrueba} onChange={(e) => setGastosPrueba(Number(e.target.value) || 0)} />
                  </Campo>
                  <Campo etiqueta="Chofer" htmlFor="k-chofer">
                    <SelectSimple
                      id="k-chofer"
                      valor={choferPrueba}
                      onCambio={setChoferPrueba}
                      placeholder="Sin chofer"
                      opciones={choferes.map((c) => ({ valor: c.id, etiqueta: `${c.nombre} (${Math.round(Number(c.porcentaje_produccion) * 100)} %)` }))}
                    />
                  </Campo>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-s3">
                <Button variant="outline" onClick={probar}>
                  <Wand2 /> Probar fórmula
                </Button>
                {preview && (
                  <p role="status" className={cn("text-[15.5px]", preview.error ? "text-critico" : "text-ok")}>
                    {preview.error ? `Error: ${preview.error}` : <>Resultado: <strong className="cifra text-[18px]">{formatValorKpi(preview.valor, form.formato)}</strong></>}
                  </p>
                )}
              </div>
              {preview && !preview.error && Object.keys(preview.metricas).length > 0 && (
                <details className="text-[14px] text-tinta-3">
                  <summary className="cursor-pointer select-none hover:text-tinta">Ver valores de las métricas</summary>
                  <ul className="mt-s2 grid gap-x-s4 gap-y-1 sm:grid-cols-2">
                    {Object.entries(preview.metricas).map(([k, v]) => (
                      <li key={k} className="flex justify-between gap-s2 border-b border-borde/60 py-0.5">
                        <span className="font-mono">{k}</span>
                        <span className="tabular-nums">{new Intl.NumberFormat("es-CL", { maximumFractionDigits: 2 }).format(v)}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>

            <div className="space-y-s3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[15px] font-medium text-tinta-2">Reglas de color</p>
                  <p className="text-[13.5px] text-tinta-3">Se aplica la primera que se cumpla, de arriba hacia abajo.</p>
                </div>
                <Button size="xs" variant="outline" onClick={agregarRegla}>
                  <Plus /> Regla
                </Button>
              </div>
              {form.reglas_color.length === 0 ? (
                <p className="rounded-lg border border-dashed border-borde-fuerte px-s3 py-s3 text-[14px] text-tinta-3">Sin reglas: el indicador se mostrará en tono neutro.</p>
              ) : (
                <ul className="space-y-s2">
                  {form.reglas_color.map((r, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-s2">
                      <span className="w-16 text-[14px] text-tinta-3">Si valor</span>
                      <SelectSimple
                        className="w-24"
                        ariaLabel="Operador"
                        valor={r.operador}
                        onCambio={(v) => actualizarRegla(i, { operador: (v || "<") as ReglaColor["operador"] })}
                        opciones={OPERADORES.map((op) => ({ valor: op, etiqueta: op }))}
                      />
                      <Input type="number" value={r.valor} onChange={(e) => actualizarRegla(i, { valor: Number(e.target.value) || 0 })} className="w-32" aria-label="Valor límite" />
                      <span className="text-[14px] text-tinta-3">→</span>
                      <SelectSimple
                        className="w-36"
                        ariaLabel="Color"
                        valor={r.color}
                        onCambio={(v) => actualizarRegla(i, { color: (v || "gris") as ReglaColor["color"] })}
                        opciones={COLORES.map((c) => ({ valor: c, etiqueta: { rojo: "Crítico (rojo)", amarillo: "Atención", verde: "Bien (verde)", azul: "Informativo", gris: "Neutro" }[c] }))}
                      />
                      <StatusBadge tono={TONO_KPI[r.color] ?? "neutro"}>Vista</StatusBadge>
                      <Button variant="ghost" size="icon-sm" className="text-tinta-3 hover:bg-critico-tenue hover:text-critico" onClick={() => quitarRegla(i)} aria-label="Quitar regla">
                        <X />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogo(false)}>
              Cancelar
            </Button>
            <Button onClick={guardar} disabled={guardando}>
              {guardando ? "Guardando…" : "Guardar indicador"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
