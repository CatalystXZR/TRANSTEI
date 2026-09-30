"use client";

import { useEffect, useState } from "react";
import { Download, FileCheck, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { descargarArchivo } from "@/lib/download";
import { formatCLP, formatFecha, formatRut } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputCLP } from "@/components/ui-inputs/input-clp";
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

export default function LiquidacionesPage() {
  const { usuario } = useAuth();
  const hoy = new Date();
  const [mes, setMes] = useState(`${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`);
  const [filas, setFilas] = useState<FilaLiquidacion[]>([]);
  const [cargando, setCargando] = useState(true);
  const [choferSel, setChoferSel] = useState<FilaLiquidacion | null>(null);

  const [dialogoAnticipo, setDialogoAnticipo] = useState(false);
  const [dialogoAjuste, setDialogoAjuste] = useState(false);
  const [formAnticipo, setFormAnticipo] = useState({ monto: 0, fecha: hoy.toISOString().slice(0, 10) });
  const [formAjuste, setFormAjuste] = useState({ tipo: "bono", concepto: "", monto: 0 });
  const [guardando, setGuardando] = useState(false);

  const [anticipos, setAnticipos] = useState<Anticipo[]>([]);
  const [ajustes, setAjustes] = useState<Ajuste[]>([]);

  const puedeEscribir = usuario && ["admin", "contabilidad"].includes(usuario.rol);

  function recargar() {
    Promise.all([
      api.get<{ mes: string; choferes: FilaLiquidacion[] }>(`/liquidaciones/resumen?mes=${mes}`),
    ])
      .then(([r]) => {
        setFilas(r?.choferes ?? []);
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar"))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    Promise.all([
      api.get<{ mes: string; choferes: FilaLiquidacion[] }>(`/liquidaciones/resumen?mes=${mes}`),
    ])
      .then(([r]) => {
        if (!activo) return;
        setFilas(r?.choferes ?? []);
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
  }, [mes]);

  async function cargarDetalle(choferId: string) {
    try {
      const [a, j] = await Promise.all([
        api.get<Anticipo[]>(`/anticipos?chofer_id=${choferId}&mes=${mes}`),
        api.get<Ajuste[]>(`/ajustes?chofer_id=${choferId}&mes=${mes}`),
      ]);
      setAnticipos(a ?? []);
      setAjustes(j ?? []);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al cargar detalle");
    }
  }

  function abrirDetalle(fila: FilaLiquidacion) {
    setChoferSel(fila);
    cargarDetalle(fila.chofer_id);
  }

  async function guardarAnticipo() {
    if (!choferSel || !formAnticipo.monto) return;
    setGuardando(true);
    try {
      await api.post(
        `/anticipos?chofer_id=${choferSel.chofer_id}&monto=${formAnticipo.monto}&fecha=${formAnticipo.fecha}&mes_liquidacion=${mes}`,
        {},
      );
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
    if (!choferSel || !formAjuste.concepto.trim() || !formAjuste.monto) return;
    setGuardando(true);
    try {
      await api.post(
        `/ajustes?chofer_id=${choferSel.chofer_id}&mes=${mes}&tipo=${formAjuste.tipo}&concepto=${encodeURIComponent(formAjuste.concepto)}&monto=${formAjuste.monto}`,
        {},
      );
      toast.success("Ajuste registrado");
      setDialogoAjuste(false);
      cargarDetalle(choferSel.chofer_id);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    } finally {
      setGuardando(false);
    }
  }

  async function eliminarAnticipo(a: Anticipo) {
    try {
      await api.del(`/anticipos/${a.id}`);
      toast.success("Anticipo eliminado");
      if (choferSel) cargarDetalle(choferSel.chofer_id);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function eliminarAjuste(a: Ajuste) {
    try {
      await api.del(`/ajustes/${a.id}`);
      toast.success("Ajuste eliminado");
      if (choferSel) cargarDetalle(choferSel.chofer_id);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function calcularYGuardar(fila: FilaLiquidacion) {
    try {
      await api.post(`/liquidaciones/calcular?chofer_id=${fila.chofer_id}&mes=${mes}`, {});
      toast.success("Liquidación calculada y guardada");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function emitir(fila: FilaLiquidacion) {
    if (!fila.liquidacion_id) {
      await calcularYGuardar(fila);
      return;
    }
    try {
      await api.post(`/liquidaciones/${fila.liquidacion_id}/emitir`, {});
      toast.success("Liquidación emitida");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function descargarPdf(fila: FilaLiquidacion) {
    if (!fila.liquidacion_id) {
      toast.error("Primero calcule y guarde la liquidación");
      return;
    }
    const supabase = await import("@/lib/supabase/client");
    const { data } = await supabase.createClient().auth.getSession();
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"}/liquidaciones/${fila.liquidacion_id}/pdf`,
      { headers: { Authorization: `Bearer ${data.session?.access_token}` } },
    );
    if (!res.ok) {
      toast.error("No se pudo generar el PDF");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `liquidacion_${fila.rut.replace(/[^\dKk]/g, "")}_${mes}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-[#2A237A]">Liquidaciones de Sueldo</h1>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            onClick={() =>
              descargarArchivo(`/export/liquidaciones?mes=${mes}`, `liquidaciones_${mes}.csv`).catch(
                (e) => toast.error(e instanceof Error ? e.message : "Error al exportar"),
              )
            }
            className="text-base"
          >
            <Download className="h-5 w-5" />
            Exportar CSV
          </Button>
          <Label className="text-base">Mes</Label>
          <Input
            type="month"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
            className="w-44 text-base"
          />
        </div>
      </div>

      <p className="rounded-lg bg-blue-50 p-3 text-base text-blue-800">
        Sueldo = Base + (Σ fletes finalizados del mes × % comisión) + Bonos − Descuentos −
        Anticipos.
      </p>

      <div className="overflow-x-auto rounded-lg border bg-white">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-base">Chofer</TableHead>
              <TableHead className="text-base">Base</TableHead>
              <TableHead className="text-base">Comisión</TableHead>
              <TableHead className="text-base">Anticipos</TableHead>
              <TableHead className="text-base">Ajustes</TableHead>
              <TableHead className="text-base">Total Líquido</TableHead>
              <TableHead className="text-base">Estado</TableHead>
              <TableHead className="w-24 text-base"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-gray-500">
                  Cargando…
                </TableCell>
              </TableRow>
            ) : filas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-gray-500">
                  No hay choferes registrados
                </TableCell>
              </TableRow>
            ) : (
              filas.map((fila) => (
                <TableRow key={fila.chofer_id} className="cursor-pointer" onClick={() => abrirDetalle(fila)}>
                  <TableCell className="text-base">
                    <p className="font-medium">{fila.nombre}</p>
                    <p className="text-sm text-gray-500">{formatRut(fila.rut)}</p>
                  </TableCell>
                  <TableCell className="text-base">{formatCLP(fila.sueldo_base)}</TableCell>
                  <TableCell className="text-base">{formatCLP(fila.comision)}</TableCell>
                  <TableCell className="text-base text-red-600">
                    -{formatCLP(fila.anticipos)}
                  </TableCell>
                  <TableCell className="text-base">
                    {Number(fila.bonos) - Number(fila.descuentos) >= 0 ? "+" : "-"}
                    {formatCLP(Math.abs(Number(fila.bonos) - Number(fila.descuentos)))}
                  </TableCell>
                  <TableCell className="text-base font-bold text-[#2A237A]">
                    {formatCLP(fila.total)}
                  </TableCell>
                  <TableCell>
                    {fila.estado === "emitida" ? (
                      <Badge className="bg-green-600 text-white">Emitida</Badge>
                    ) : fila.liquidacion_id ? (
                      <Badge className="bg-yellow-500 text-black">Borrador</Badge>
                    ) : (
                      <Badge className="bg-gray-100 text-gray-600">Sin calcular</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                      <Button
                        size="icon"
                        variant="outline"
                        onClick={() => descargarPdf(fila)}
                        aria-label="Descargar PDF"
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                      {puedeEscribir && fila.estado !== "emitida" && (
                        <Button
                          size="icon"
                          variant="outline"
                          className="border-green-200 text-green-700 hover:bg-green-50"
                          onClick={() => emitir(fila)}
                          aria-label="Emitir liquidación"
                        >
                          <FileCheck className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!choferSel} onOpenChange={(o) => !o && setChoferSel(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl">
              {choferSel?.nombre} — {mes}
            </DialogTitle>
            <DialogDescription className="text-base">
              Anticipos y ajustes del mes. Estos modifican la liquidación al calcularla.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-base font-semibold">Anticipos</p>
              {puedeEscribir && (
                <Button
                  size="sm"
                  onClick={() => {
                    setFormAnticipo({ monto: 0, fecha: hoy.toISOString().slice(0, 10) });
                    setDialogoAnticipo(true);
                  }}
                >
                  <Plus className="h-4 w-4" />
                  Anticipo
                </Button>
              )}
            </div>
            {anticipos.length === 0 ? (
              <p className="text-sm text-gray-500">Sin anticipos este mes</p>
            ) : (
              anticipos.map((a) => (
                <div key={a.id} className="flex items-center justify-between rounded-md border p-2 text-base">
                  <span>
                    {formatFecha(a.fecha)} — {formatCLP(a.monto)}
                  </span>
                  {puedeEscribir && (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="text-red-600"
                      onClick={() => eliminarAnticipo(a)}
                      aria-label="Eliminar anticipo"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))
            )}

            <div className="flex items-center justify-between pt-2">
              <p className="text-base font-semibold">Ajustes (bonos / descuentos)</p>
              {puedeEscribir && (
                <Button
                  size="sm"
                  onClick={() => {
                    setFormAjuste({ tipo: "bono", concepto: "", monto: 0 });
                    setDialogoAjuste(true);
                  }}
                >
                  <Plus className="h-4 w-4" />
                  Ajuste
                </Button>
              )}
            </div>
            {ajustes.length === 0 ? (
              <p className="text-sm text-gray-500">Sin ajustes este mes</p>
            ) : (
              ajustes.map((a) => (
                <div key={a.id} className="flex items-center justify-between rounded-md border p-2 text-base">
                  <span>
                    <Badge className={`mr-2 text-sm ${a.tipo === "bono" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-700"}`}>
                      {a.tipo === "bono" ? "Bono" : "Desc."}
                    </Badge>
                    {a.concepto} — {formatCLP(a.monto)}
                  </span>
                  {puedeEscribir && (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="text-red-600"
                      onClick={() => eliminarAjuste(a)}
                      aria-label="Eliminar ajuste"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))
            )}
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setChoferSel(null)} className="text-base">
              Cerrar
            </Button>
            {puedeEscribir && (
              <Button
                onClick={() => {
                  if (choferSel) calcularYGuardar(choferSel);
                  setChoferSel(null);
                }}
                className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
              >
                Calcular y Guardar
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoAnticipo} onOpenChange={setDialogoAnticipo}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-xl">Registrar Anticipo</DialogTitle>
            <DialogDescription className="text-base">
              El anticipo se descontará de la liquidación de {mes}.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Monto ($)</Label>
              <InputCLP
                value={formAnticipo.monto}
                onChange={(v) => setFormAnticipo({ ...formAnticipo, monto: v })}
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base">Fecha</Label>
              <Input
                type="date"
                value={formAnticipo.fecha}
                onChange={(e) => setFormAnticipo({ ...formAnticipo, fecha: e.target.value })}
                className="text-base"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogoAnticipo(false)} className="text-base">
              Cancelar
            </Button>
            <Button
              onClick={guardarAnticipo}
              disabled={guardando}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoAjuste} onOpenChange={setDialogoAjuste}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-xl">Registrar Ajuste</DialogTitle>
            <DialogDescription className="text-base">
              Bono (suma) o descuento (resta) en la liquidación de {mes}.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Tipo</Label>
              <Select
                value={formAjuste.tipo}
                onValueChange={(v) => setFormAjuste({ ...formAjuste, tipo: (v ?? "bono") as "bono" | "descuento" })}
              >
                <SelectTrigger className="text-base">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="bono" className="text-base">
                    Bono (+)
                  </SelectItem>
                  <SelectItem value="descuento" className="text-base">
                    Descuento (−)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Concepto</Label>
              <Input
                value={formAjuste.concepto}
                onChange={(e) => setFormAjuste({ ...formAjuste, concepto: e.target.value })}
                className="text-base"
                placeholder="Bono puntualidad"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base">Monto ($)</Label>
              <InputCLP
                value={formAjuste.monto}
                onChange={(v) => setFormAjuste({ ...formAjuste, monto: v })}
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogoAjuste(false)} className="text-base">
              Cancelar
            </Button>
            <Button
              onClick={guardarAjuste}
              disabled={guardando}
              className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
            >
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
