"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Download, FileCheck2, FileDown, Lock, Plus, Trash2, Wallet } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { api } from "@/lib/api";
import { descargarArchivo } from "@/lib/download";
import { formatCLP, formatFecha, formatRut } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputCLP } from "@/components/ui-inputs/input-clp";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Aviso, FilaVacia, FilasCargando, PageHeader, Panel, StatusBadge } from "@/components/sistema";
import { Campo, SelectSimple } from "@/components/formulario";

interface FilaLiquidacion {
  chofer_id: string;
  nombre: string;
  rut: string;
  sueldo_base: string;
  comision: string;
  anticipos: string;
  bonos: string;
  descuentos: string;
  total: string;
  liquidacion_id: string | null;
  estado: string | null;
}

interface Anticipo {
  id: string;
  chofer_id: string;
  fecha: string;
  monto: string;
  mes_liquidacion: string;
  notas: string | null;
}

interface Ajuste {
  id: string;
  chofer_id: string;
  mes: string;
  tipo: "bono" | "descuento";
  concepto: string;
  monto: string;
}

function mesActual() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function hoyISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function LiquidacionesPage() {
  const { usuario } = useAuth();
  const [mes, setMes] = useState("");
  const [filas, setFilas] = useState<FilaLiquidacion[]>([]);
  const [cargando, setCargando] = useState(true);
  const [choferSel, setChoferSel] = useState<FilaLiquidacion | null>(null);
  const [anticipos, setAnticipos] = useState<Anticipo[]>([]);
  const [ajustes, setAjustes] = useState<Ajuste[]>([]);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);

  const [dialogoAnticipo, setDialogoAnticipo] = useState(false);
  const [dialogoAjuste, setDialogoAjuste] = useState(false);
  const [formAnticipo, setFormAnticipo] = useState({ monto: 0, fecha: "" });
  const [formAjuste, setFormAjuste] = useState<{ tipo: "bono" | "descuento"; concepto: string; monto: number }>({ tipo: "bono", concepto: "", monto: 0 });
  const [guardando, setGuardando] = useState(false);
  const [emitiendo, setEmitiendo] = useState<FilaLiquidacion | null>(null);

  const puedeEscribir = !!usuario && ["admin", "contabilidad"].includes(usuario.rol);
  const bloqueada = choferSel?.estado === "emitida";

  useEffect(() => {
    const t = setTimeout(() => setMes(mesActual()), 0);
    return () => clearTimeout(t);
  }, []);

  function recargar() {
    if (!mes) return;
    api
      .get<{ mes: string; choferes: FilaLiquidacion[] }>(`/liquidaciones/resumen?mes=${mes}`)
      .then((r) => {
        const nuevas = r?.choferes ?? [];
        setFilas(nuevas);
        setChoferSel((sel) => (sel ? (nuevas.find((f) => f.chofer_id === sel.chofer_id) ?? sel) : sel));
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar"))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    if (!mes) return;
    let activo = true;
    const t = setTimeout(() => setCargando(true), 0);
    api
      .get<{ mes: string; choferes: FilaLiquidacion[] }>(`/liquidaciones/resumen?mes=${mes}`)
      .then((r) => {
        if (activo) setFilas(r?.choferes ?? []);
      })
      .catch((e) => {
        if (activo) toast.error(e instanceof Error ? e.message : "Error al cargar");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
      clearTimeout(t);
    };
  }, [mes]);

  const totales = useMemo(
    () => ({
      liquido: filas.reduce((a, f) => a + Number(f.total), 0),
      comision: filas.reduce((a, f) => a + Number(f.comision), 0),
      emitidas: filas.filter((f) => f.estado === "emitida").length,
    }),
    [filas],
  );

  async function cargarDetalle(choferId: string) {
    setCargandoDetalle(true);
    try {
      const [a, j] = await Promise.all([
        api.get<Anticipo[]>(`/anticipos?chofer_id=${choferId}&mes=${mes}`),
        api.get<Ajuste[]>(`/ajustes?chofer_id=${choferId}&mes=${mes}`),
      ]);
      setAnticipos(a ?? []);
      setAjustes(j ?? []);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al cargar detalle");
    } finally {
      setCargandoDetalle(false);
    }
  }

  function abrirDetalle(fila: FilaLiquidacion) {
    setChoferSel(fila);
    setAnticipos([]);
    setAjustes([]);
    cargarDetalle(fila.chofer_id);
  }

  async function guardarAnticipo() {
    if (!choferSel || !formAnticipo.monto) {
      toast.error("Ingrese el monto del anticipo");
      return;
    }
    setGuardando(true);
    try {
      const qs = new URLSearchParams({ chofer_id: choferSel.chofer_id, monto: String(formAnticipo.monto), fecha: formAnticipo.fecha || hoyISO(), mes_liquidacion: mes });
      await api.post(`/anticipos?${qs.toString()}`, {});
      toast.success("Anticipo registrado");
      setDialogoAnticipo(false);
      cargarDetalle(choferSel.chofer_id);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    } finally {
      setGuardando(false);
    }
  }

  async function guardarAjuste() {
    if (!choferSel || !formAjuste.concepto.trim() || !formAjuste.monto) {
      toast.error("Complete concepto y monto");
      return;
    }
    setGuardando(true);
    try {
      const qs = new URLSearchParams({ chofer_id: choferSel.chofer_id, mes, tipo: formAjuste.tipo, concepto: formAjuste.concepto.trim(), monto: String(formAjuste.monto) });
      await api.post(`/ajustes?${qs.toString()}`, {});
      toast.success(formAjuste.tipo === "bono" ? "Bono registrado" : "Descuento registrado");
      setDialogoAjuste(false);
      cargarDetalle(choferSel.chofer_id);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    } finally {
      setGuardando(false);
    }
  }

  async function eliminar(tipo: "anticipos" | "ajustes", id: string) {
    try {
      await api.del(`/${tipo}/${id}`);
      toast.success("Registro eliminado");
      if (choferSel) cargarDetalle(choferSel.chofer_id);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function guardarBorrador(fila: FilaLiquidacion) {
    try {
      await api.post(`/liquidaciones/calcular?chofer_id=${fila.chofer_id}&mes=${mes}`, {});
      toast.success("Liquidación guardada como borrador");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function confirmarEmitir() {
    if (!emitiendo) return;
    try {
      const liq = await api.post<{ id: string }>(`/liquidaciones/calcular?chofer_id=${emitiendo.chofer_id}&mes=${mes}`, {});
      const id = liq?.id ?? emitiendo.liquidacion_id;
      if (!id) throw new Error("No se pudo calcular la liquidación");
      await api.post(`/liquidaciones/${id}/emitir`, {});
      toast.success(`Liquidación de ${emitiendo.nombre} emitida`);
      setEmitiendo(null);
      setChoferSel(null);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function descargarPdf(fila: FilaLiquidacion) {
    if (!fila.liquidacion_id) {
      toast.error("Guarde o emita la liquidación antes de descargar el PDF");
      return;
    }
    try {
      await descargarArchivo(`/liquidaciones/${fila.liquidacion_id}/pdf`, `liquidacion_${fila.rut.replace(/[^\dKk]/g, "")}_${mes}.pdf`);
    } catch {
      toast.error("No se pudo generar el PDF");
    }
  }

  const estadoBadge = (f: FilaLiquidacion) =>
    f.estado === "emitida" ? (
      <StatusBadge tono="ok">Emitida</StatusBadge>
    ) : f.liquidacion_id ? (
      <StatusBadge tono="atencion">Borrador</StatusBadge>
    ) : (
      <StatusBadge tono="neutro">Sin calcular</StatusBadge>
    );

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Finanzas"
        titulo="Liquidaciones de sueldo"
        descripcion="Sueldo = base + comisión de los fletes finalizados del mes + bonos − descuentos − anticipos."
        acciones={
          <>
            <label className="flex items-center gap-s2 text-tinta-3">
              <CalendarDays className="size-[18px]" />
              <Input type="month" value={mes} onChange={(e) => e.target.value && setMes(e.target.value)} className="w-48" aria-label="Mes de liquidación" />
            </label>
            <Button
              variant="outline"
              onClick={() =>
                descargarArchivo(`/export/liquidaciones?mes=${mes}`, `liquidaciones_${mes}.csv`).catch((e) =>
                  toast.error(e instanceof Error ? e.message : "Error al exportar"),
                )
              }
            >
              <Download /> Exportar
            </Button>
          </>
        }
      />

      {!cargando && filas.length > 0 && (
        <div className="grid gap-s3 sm:grid-cols-3">
          <div className="rounded-xl border border-borde bg-superficie px-s4 py-s3 shadow-elev-1">
            <p className="text-[14px] text-tinta-3">Total líquido del mes</p>
            <p className="cifra text-[26px] font-semibold">{formatCLP(totales.liquido)}</p>
          </div>
          <div className="rounded-xl border border-borde bg-superficie px-s4 py-s3 shadow-elev-1">
            <p className="text-[14px] text-tinta-3">Comisiones</p>
            <p className="cifra text-[26px] font-semibold">{formatCLP(totales.comision)}</p>
          </div>
          <div className="rounded-xl border border-borde bg-superficie px-s4 py-s3 shadow-elev-1">
            <p className="text-[14px] text-tinta-3">Emitidas</p>
            <p className="cifra text-[26px] font-semibold">
              {totales.emitidas} <span className="text-[16px] font-normal text-tinta-3">de {filas.length}</span>
            </p>
          </div>
        </div>
      )}

      <Panel>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Chofer</TableHead>
              <TableHead className="text-right">Base</TableHead>
              <TableHead className="text-right">Comisión</TableHead>
              <TableHead className="text-right">Ajustes</TableHead>
              <TableHead className="text-right">Anticipos</TableHead>
              <TableHead className="text-right">Líquido</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="text-right">
                <span className="sr-only">Acciones</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <FilasCargando columnas={8} />
            ) : filas.length === 0 ? (
              <FilaVacia columnas={8} icono={Wallet} titulo="No hay choferes activos" descripcion="Registre choferes para calcular sus liquidaciones." />
            ) : (
              filas.map((f) => {
                const ajuste = Number(f.bonos) - Number(f.descuentos);
                return (
                  <TableRow key={f.chofer_id} className="cursor-pointer" onClick={() => abrirDetalle(f)}>
                    <TableCell>
                      <span className="font-medium">{f.nombre}</span>
                      <span className="block font-mono text-[13px] text-tinta-3">{formatRut(f.rut)}</span>
                    </TableCell>
                    <TableCell className="cifra text-right text-tinta-2">{formatCLP(f.sueldo_base)}</TableCell>
                    <TableCell className="cifra text-right text-tinta-2">{formatCLP(f.comision)}</TableCell>
                    <TableCell className={cn("cifra text-right", ajuste > 0 ? "text-ok" : ajuste < 0 ? "text-critico" : "text-tinta-3")}>
                      {ajuste === 0 ? "—" : `${ajuste > 0 ? "+" : "−"}${formatCLP(Math.abs(ajuste))}`}
                    </TableCell>
                    <TableCell className="cifra text-right text-critico">{Number(f.anticipos) ? `−${formatCLP(f.anticipos)}` : <span className="text-tinta-3">—</span>}</TableCell>
                    <TableCell className="cifra text-right text-[17px] font-semibold">{formatCLP(f.total)}</TableCell>
                    <TableCell>{estadoBadge(f)}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon-sm" onClick={() => descargarPdf(f)} disabled={!f.liquidacion_id} aria-label={`Descargar PDF de ${f.nombre}`} title="Descargar PDF">
                          <FileDown />
                        </Button>
                        {puedeEscribir && f.estado !== "emitida" && (
                          <Button variant="outline" size="xs" onClick={() => setEmitiendo(f)}>
                            <FileCheck2 /> Emitir
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

      {/* Detalle del chofer */}
      <Dialog open={!!choferSel} onOpenChange={(o) => !o && setChoferSel(null)}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{choferSel?.nombre}</DialogTitle>
            <DialogDescription>
              Liquidación de <span className="capitalize">{mes && new Intl.DateTimeFormat("es-CL", { month: "long", year: "numeric" }).format(new Date(Number(mes.slice(0, 4)), Number(mes.slice(5)) - 1, 1))}</span>
            </DialogDescription>
          </DialogHeader>

          {choferSel && (
            <dl className="space-y-s2 rounded-xl bg-superficie-hundida px-s4 py-s3 text-[15.5px]">
              {[
                ["Sueldo base", formatCLP(choferSel.sueldo_base), ""],
                ["Comisión por fletes", formatCLP(choferSel.comision), ""],
                ["Bonos", `+${formatCLP(choferSel.bonos)}`, "text-ok"],
                ["Descuentos", `−${formatCLP(choferSel.descuentos)}`, "text-critico"],
                ["Anticipos", `−${formatCLP(choferSel.anticipos)}`, "text-critico"],
              ].map(([k, v, c]) => (
                <div key={k} className="flex justify-between">
                  <dt className="text-tinta-3">{k}</dt>
                  <dd className={cn("cifra", c)}>{v}</dd>
                </div>
              ))}
              <div className="flex items-baseline justify-between border-t border-borde-fuerte pt-s2">
                <dt className="font-medium">Total líquido</dt>
                <dd className="cifra text-[24px] font-semibold text-marca">{formatCLP(choferSel.total)}</dd>
              </div>
            </dl>
          )}

          {bloqueada && (
            <Aviso tono="neutro" icono={Lock}>
              Esta liquidación ya fue emitida. Anticipos y ajustes del mes quedan bloqueados en el documento.
            </Aviso>
          )}

          <section className="space-y-s2">
            <div className="flex items-center justify-between">
              <h3 className="text-[16px] font-semibold">Anticipos</h3>
              {puedeEscribir && !bloqueada && (
                <Button
                  size="xs"
                  variant="outline"
                  onClick={() => {
                    setFormAnticipo({ monto: 0, fecha: hoyISO() });
                    setDialogoAnticipo(true);
                  }}
                >
                  <Plus /> Anticipo
                </Button>
              )}
            </div>
            {cargandoDetalle ? (
              <p className="text-[14px] text-tinta-3">Cargando…</p>
            ) : anticipos.length === 0 ? (
              <p className="text-[14px] text-tinta-3">Sin anticipos este mes.</p>
            ) : (
              <ul className="divide-y divide-borde rounded-xl border border-borde">
                {anticipos.map((a) => (
                  <li key={a.id} className="flex items-center justify-between px-s3 py-s2 text-[15px]">
                    <span>
                      {formatFecha(a.fecha)} · <span className="cifra font-medium">{formatCLP(a.monto)}</span>
                    </span>
                    {puedeEscribir && !bloqueada && (
                      <Button variant="ghost" size="icon-xs" className="text-tinta-3 hover:bg-critico-tenue hover:text-critico" onClick={() => eliminar("anticipos", a.id)} aria-label="Eliminar anticipo">
                        <Trash2 />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-s2">
            <div className="flex items-center justify-between">
              <h3 className="text-[16px] font-semibold">Bonos y descuentos</h3>
              {puedeEscribir && !bloqueada && (
                <Button
                  size="xs"
                  variant="outline"
                  onClick={() => {
                    setFormAjuste({ tipo: "bono", concepto: "", monto: 0 });
                    setDialogoAjuste(true);
                  }}
                >
                  <Plus /> Ajuste
                </Button>
              )}
            </div>
            {cargandoDetalle ? (
              <p className="text-[14px] text-tinta-3">Cargando…</p>
            ) : ajustes.length === 0 ? (
              <p className="text-[14px] text-tinta-3">Sin ajustes este mes.</p>
            ) : (
              <ul className="divide-y divide-borde rounded-xl border border-borde">
                {ajustes.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-s2 px-s3 py-s2 text-[15px]">
                    <span className="flex items-center gap-s2">
                      <StatusBadge tono={a.tipo === "bono" ? "ok" : "critico"}>{a.tipo === "bono" ? "Bono" : "Descuento"}</StatusBadge>
                      {a.concepto}
                    </span>
                    <span className="flex items-center gap-s2">
                      <span className="cifra font-medium">{formatCLP(a.monto)}</span>
                      {puedeEscribir && !bloqueada && (
                        <Button variant="ghost" size="icon-xs" className="text-tinta-3 hover:bg-critico-tenue hover:text-critico" onClick={() => eliminar("ajustes", a.id)} aria-label="Eliminar ajuste">
                          <Trash2 />
                        </Button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <DialogFooter>
            <Button variant="outline" onClick={() => setChoferSel(null)}>
              Cerrar
            </Button>
            {puedeEscribir && choferSel && !bloqueada && (
              <>
                <Button variant="secondary" onClick={() => guardarBorrador(choferSel)}>
                  Guardar borrador
                </Button>
                <Button onClick={() => setEmitiendo(choferSel)}>
                  <FileCheck2 /> Emitir
                </Button>
              </>
            )}
            {choferSel?.liquidacion_id && (
              <Button variant={bloqueada ? "default" : "ghost"} onClick={() => descargarPdf(choferSel)}>
                <FileDown /> PDF
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmar emisión */}
      <Dialog open={!!emitiendo} onOpenChange={(o) => !o && setEmitiendo(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Emitir liquidación</DialogTitle>
            <DialogDescription>
              Se emitirá la liquidación de <strong>{emitiendo?.nombre}</strong> por{" "}
              <strong>{emitiendo ? formatCLP(emitiendo.total) : ""}</strong>. Una vez emitida no se puede recalcular.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmitiendo(null)}>
              Cancelar
            </Button>
            <Button onClick={confirmarEmitir}>
              <FileCheck2 /> Emitir
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoAnticipo} onOpenChange={setDialogoAnticipo}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar anticipo</DialogTitle>
            <DialogDescription>Se descontará de la liquidación del mes seleccionado.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-s3 sm:grid-cols-2">
            <Campo etiqueta="Monto" htmlFor="a-monto" requerido>
              <InputCLP key={dialogoAnticipo ? "a1" : "a0"} id="a-monto" value={formAnticipo.monto} onChange={(v) => setFormAnticipo({ ...formAnticipo, monto: v })} className="cifra" />
            </Campo>
            <Campo etiqueta="Fecha" htmlFor="a-fecha">
              <Input id="a-fecha" type="date" value={formAnticipo.fecha} onChange={(e) => setFormAnticipo({ ...formAnticipo, fecha: e.target.value })} />
            </Campo>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoAnticipo(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarAnticipo} disabled={guardando}>
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoAjuste} onOpenChange={setDialogoAjuste}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar ajuste</DialogTitle>
            <DialogDescription>Un bono suma y un descuento resta en la liquidación del mes.</DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Tipo" htmlFor="j-tipo">
                <SelectSimple
                  id="j-tipo"
                  valor={formAjuste.tipo}
                  onCambio={(v) => setFormAjuste({ ...formAjuste, tipo: (v || "bono") as "bono" | "descuento" })}
                  opciones={[
                    { valor: "bono", etiqueta: "Bono (suma)" },
                    { valor: "descuento", etiqueta: "Descuento (resta)" },
                  ]}
                />
              </Campo>
              <Campo etiqueta="Monto" htmlFor="j-monto" requerido>
                <InputCLP key={dialogoAjuste ? "j1" : "j0"} id="j-monto" value={formAjuste.monto} onChange={(v) => setFormAjuste({ ...formAjuste, monto: v })} className="cifra" />
              </Campo>
            </div>
            <Campo etiqueta="Concepto" htmlFor="j-concepto" requerido>
              <Input id="j-concepto" value={formAjuste.concepto} onChange={(e) => setFormAjuste({ ...formAjuste, concepto: e.target.value })} placeholder="Bono de puntualidad" />
            </Campo>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoAjuste(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarAjuste} disabled={guardando}>
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
