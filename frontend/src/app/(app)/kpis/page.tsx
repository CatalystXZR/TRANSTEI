"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Power, Trash2, Wand2, X } from "lucide-react";
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
import { COLOR_KPI_CLASES, formatValorKpi } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
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
      <Card className="mx-auto max-w-lg">
        <CardContent className="pt-6 text-center text-base text-gray-600">
          Solo el administrador puede configurar indicadores.
        </CardContent>
      </Card>
    );
  }

  const valoresPorId = new Map(valores.map((v) => [v.id, v]));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#2A237A]">Indicadores (KPIs)</h1>
          <p className="text-sm text-gray-500">
            Cree, edite y pruebe los indicadores del panel. Las fórmulas se calculan en el backend.
          </p>
        </div>
        <Button onClick={abrirNuevo} className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90">
          <Plus className="h-5 w-5" />
          Nuevo KPI
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border bg-white">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-base">Nombre</TableHead>
              <TableHead className="text-base">Ámbito</TableHead>
              <TableHead className="text-base">Fórmula</TableHead>
              <TableHead className="text-base">Valor actual</TableHead>
              <TableHead className="text-base">Uso</TableHead>
              <TableHead className="text-base">Estado</TableHead>
              <TableHead className="w-32 text-base">Acciones</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-gray-500">
                  Cargando…
                </TableCell>
              </TableRow>
            ) : kpis.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-gray-500">
                  No hay KPIs configurados
                </TableCell>
              </TableRow>
            ) : (
              kpis.map((k) => {
                const valor = valoresPorId.get(k.id);
                return (
                  <TableRow key={k.id}>
                    <TableCell className="text-base font-medium">
                      {k.nombre}
                      {k.descripcion && (
                        <p className="text-sm text-gray-500">{k.descripcion}</p>
                      )}
                    </TableCell>
                    <TableCell className="text-base capitalize">{k.ambito}</TableCell>
                    <TableCell className="max-w-xs truncate font-mono text-sm text-gray-600">
                      {k.formula}
                    </TableCell>
                    <TableCell>
                      {valor ? (
                        <Badge className={`${COLOR_KPI_CLASES[valor.color]} text-sm`}>
                          {valor.error ? "Error" : formatValorKpi(valor.valor, valor.formato)}
                        </Badge>
                      ) : k.uso === "rentabilidad_viaje" ? (
                        <span className="text-sm text-gray-500">Por viaje</span>
                      ) : (
                        <span className="text-sm text-gray-400">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-base capitalize">
                      {k.uso === "rentabilidad_viaje" ? "Rentabilidad" : k.uso}
                    </TableCell>
                    <TableCell>
                      {k.activo ? (
                        <Badge className="bg-green-100 text-green-800">Activo</Badge>
                      ) : (
                        <Badge className="bg-gray-100 text-gray-600">Inactivo</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          size="icon"
                          variant="outline"
                          onClick={() => abrirEditar(k)}
                          aria-label="Editar KPI"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        {k.activo ? (
                          <Button
                            size="icon"
                            variant="outline"
                            className="border-red-200 text-red-600 hover:bg-red-50"
                            onClick={() => desactivar(k)}
                            aria-label="Desactivar KPI"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        ) : (
                          <Button
                            size="icon"
                            variant="outline"
                            className="border-green-200 text-green-700 hover:bg-green-50"
                            onClick={() => reactivar(k)}
                            aria-label="Reactivar KPI"
                          >
                            <Power className="h-4 w-4" />
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
      </div>

      <Dialog open={dialogo} onOpenChange={setDialogo}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="text-xl">
              {editando ? "Editar KPI" : "Nuevo KPI"}
            </DialogTitle>
            <DialogDescription className="text-base">
              Escriba la fórmula usando las métricas del catálogo. Pruébela antes de guardar.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 md:col-span-2">
              <Label className="text-base">Nombre *</Label>
              <Input
                value={form.nombre}
                onChange={(e) => setForm({ ...form, nombre: e.target.value })}
                className="text-base"
                placeholder="Margen del mes (%)"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label className="text-base">Descripción</Label>
              <Input
                value={form.descripcion}
                onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
                className="text-base"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base">Ámbito</Label>
              <Select value={form.ambito} onValueChange={(v) => cambiarAmbito((v ?? "global") as AmbitoKpi)}>
                <SelectTrigger className="text-base">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global" className="text-base">
                    Global (por período)
                  </SelectItem>
                  <SelectItem value="viaje" className="text-base">
                    Por viaje
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Formato</Label>
              <Select
                value={form.formato}
                onValueChange={(v) => setForm({ ...form, formato: (v ?? "numero") as FormatoKpi })}
              >
                <SelectTrigger className="text-base">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="clp" className="text-base">
                    Pesos ($)
                  </SelectItem>
                  <SelectItem value="numero" className="text-base">
                    Número
                  </SelectItem>
                  <SelectItem value="porcentaje" className="text-base">
                    Porcentaje (%)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Uso</Label>
              <Select value={form.uso} onValueChange={(v) => setForm({ ...form, uso: (v ?? "dashboard") as UsoKpi })}>
                <SelectTrigger className="text-base">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="dashboard" className="text-base">
                    Panel de control
                  </SelectItem>
                  <SelectItem value="rentabilidad_viaje" className="text-base">
                    Semáforo de rentabilidad de viaje
                  </SelectItem>
                  <SelectItem value="interno" className="text-base">
                    Interno
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Activo</Label>
              <Select
                value={form.activo ? "si" : "no"}
                onValueChange={(v) => setForm({ ...form, activo: v === "si" })}
              >
                <SelectTrigger className="text-base">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="si" className="text-base">
                    Sí
                  </SelectItem>
                  <SelectItem value="no" className="text-base">
                    No
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2 md:col-span-2">
              <Label className="text-base">Fórmula *</Label>
              <textarea
                value={form.formula}
                onChange={(e) => setForm({ ...form, formula: e.target.value })}
                rows={3}
                className="w-full rounded-md border border-input bg-transparent p-3 font-mono text-base shadow-sm"
                placeholder="SI(ingresos_mes = 0, 0, margen_bruto / ingresos_mes * 100)"
              />
            </div>

            {catalogo && (
              <div className="space-y-2 md:col-span-2">
                <Label className="text-base">Métricas disponibles (clic para insertar)</Label>
                <div className="flex flex-wrap gap-2">
                  {catalogo.metricas.map((m) => (
                    <button
                      key={m.nombre}
                      type="button"
                      title={m.descripcion}
                      onClick={() => insertarEnFormula(m.nombre)}
                      className="rounded-full border border-[#2A237A]/30 bg-white px-3 py-1 font-mono text-sm text-[#2A237A] hover:bg-[#2A237A]/5"
                    >
                      {m.nombre}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  {catalogo.funciones.map((f) => (
                    <span
                      key={f.nombre}
                      title={f.descripcion}
                      className="rounded-full bg-gray-100 px-3 py-1 font-mono text-sm text-gray-700"
                    >
                      {f.nombre}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-3 md:col-span-2">
              <div className="flex items-center justify-between">
                <Label className="text-base">Parámetros de prueba</Label>
              </div>
              {form.ambito === "global" ? (
                <div className="flex items-center gap-3">
                  <span className="text-base text-gray-600">Mes:</span>
                  <Input
                    type="month"
                    value={mesPrueba}
                    onChange={(e) => setMesPrueba(e.target.value)}
                    className="w-44 text-base"
                  />
                </div>
              ) : (
                <div className="flex flex-wrap items-end gap-3">
                  <div className="space-y-1">
                    <span className="text-sm text-gray-600">Flete ($)</span>
                    <Input
                      type="number"
                      value={fletePrueba}
                      onChange={(e) => setFletePrueba(Number(e.target.value) || 0)}
                      className="w-40 text-base"
                    />
                  </div>
                  <div className="space-y-1">
                    <span className="text-sm text-gray-600">Gastos ($)</span>
                    <Input
                      type="number"
                      value={gastosPrueba}
                      onChange={(e) => setGastosPrueba(Number(e.target.value) || 0)}
                      className="w-40 text-base"
                    />
                  </div>
                  <div className="space-y-1">
                    <span className="text-sm text-gray-600">Chofer</span>
                    <Select value={choferPrueba} onValueChange={(v) => setChoferPrueba(v ?? "")}>
                      <SelectTrigger className="w-48 text-base">
                        <SelectValue placeholder="Sin chofer" />
                      </SelectTrigger>
                      <SelectContent>
                        {choferes.map((c) => (
                          <SelectItem key={c.id} value={c.id} className="text-base">
                            {c.nombre} ({Math.round(Number(c.porcentaje_produccion) * 100)}%)
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
              <Button onClick={probar} variant="outline" className="text-base">
                <Wand2 className="h-4 w-4" />
                Probar fórmula
              </Button>

              {preview && (
                <div
                  className={`rounded-lg border p-3 text-base ${
                    preview.error ? "border-red-200 bg-red-50" : "border-green-200 bg-green-50"
                  }`}
                >
                  {preview.error ? (
                    <p className="text-red-700">Error: {preview.error}</p>
                  ) : (
                    <p className="text-green-800">
                      Resultado:{" "}
                      <strong>{formatValorKpi(preview.valor, form.formato)}</strong>
                    </p>
                  )}
                  {!preview.error && Object.keys(preview.metricas).length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-sm text-gray-600">
                        Ver métricas usadas
                      </summary>
                      <ul className="mt-1 grid gap-1 text-sm text-gray-600 sm:grid-cols-2">
                        {Object.entries(preview.metricas).map(([k, v]) => (
                          <li key={k}>
                            <span className="font-mono">{k}</span>:{" "}
                            {new Intl.NumberFormat("es-CL").format(v)}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </div>

            <div className="space-y-3 md:col-span-2">
              <div className="flex items-center justify-between">
                <Label className="text-base">Reglas de color (semáforo)</Label>
                <Button size="sm" variant="outline" onClick={agregarRegla} className="text-base">
                  <Plus className="h-4 w-4" />
                  Agregar regla
                </Button>
              </div>
              {form.reglas_color.length === 0 ? (
                <p className="text-sm text-gray-500">
                  Sin reglas: el indicador se mostrará en gris.
                </p>
              ) : (
                <div className="space-y-2">
                  {form.reglas_color.map((r, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-2">
                      <Select
                        value={r.operador}
                        onValueChange={(v) =>
                          actualizarRegla(i, { operador: (v ?? "<") as ReglaColor["operador"] })
                        }
                      >
                        <SelectTrigger className="w-24 text-base">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {OPERADORES.map((op) => (
                            <SelectItem key={op} value={op} className="text-base">
                              {op}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Input
                        type="number"
                        value={r.valor}
                        onChange={(e) =>
                          actualizarRegla(i, { valor: Number(e.target.value) || 0 })
                        }
                        className="w-32 text-base"
                      />
                      <Select
                        value={r.color}
                        onValueChange={(v) =>
                          actualizarRegla(i, { color: (v ?? "gris") as ReglaColor["color"] })
                        }
                      >
                        <SelectTrigger className="w-32 text-base">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {COLORES.map((c) => (
                            <SelectItem key={c} value={c} className="text-base capitalize">
                              {c}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <span className="text-sm text-gray-500">
                        → color si valor {r.operador} {r.valor}
                      </span>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="text-red-600"
                        onClick={() => quitarRegla(i)}
                        aria-label="Quitar regla"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                  <p className="text-xs text-gray-500">
                    Se aplica la primera regla que se cumpla, de arriba hacia abajo.
                  </p>
                </div>
              )}
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
              {guardando ? "Guardando…" : "Guardar KPI"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
