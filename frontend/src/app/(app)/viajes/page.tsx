"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Eye, Plus } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type {
  Chofer,
  Cliente,
  EstadoViaje,
  Rampla,
  Tracto,
  Viaje,
} from "@/types";
import { ESTADO_VIAJE_COLOR, ESTADO_VIAJE_LABEL } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputCLP } from "@/components/ui-inputs/input-clp";
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

const ESTADOS: EstadoViaje[] = ["programado", "en_ruta", "finalizado", "facturado"];

export default function ViajesPage() {
  const { usuario } = useAuth();
  const [viajes, setViajes] = useState<Viaje[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [choferes, setChoferes] = useState<Chofer[]>([]);
  const [tractos, setTractos] = useState<Tracto[]>([]);
  const [ramplas, setRamplas] = useState<Rampla[]>([]);
  const [cargando, setCargando] = useState(true);
  const [filtroEstado, setFiltroEstado] = useState<string>("todos");

  const [dialogo, setDialogo] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [form, setForm] = useState({
    fecha_inicio: "",
    origen: "",
    destino: "",
    valor_flete_neto: 0,
    cliente_id: "",
    chofer_id: "",
    tracto_id: "",
    rampla_id: "",
    notas: "",
  });

  const puedeEscribir = usuario?.rol === "admin" || usuario?.rol === "operacion";

  useEffect(() => {
    let activo = true;
    Promise.all([
      api.get<Viaje[]>("/viajes"),
      api.get<Cliente[]>("/clientes?activo=true"),
      api.get<Chofer[]>("/choferes?activo=true"),
      api.get<Tracto[]>("/tractos?activo=true"),
      api.get<Rampla[]>("/ramplas?activo=true"),
    ])
      .then(([v, c, ch, t, r]) => {
        if (!activo) return;
        setViajes(v ?? []);
        setClientes(c ?? []);
        setChoferes(ch ?? []);
        setTractos(t ?? []);
        setRamplas(r ?? []);
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar"))
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  const filtrados =
    filtroEstado === "todos" ? viajes : viajes.filter((v) => v.estado === filtroEstado);

  async function guardar() {
    const obligatorios = ["fecha_inicio", "origen", "destino", "cliente_id", "chofer_id", "tracto_id", "rampla_id"];
    if (obligatorios.some((k) => !form[k as keyof typeof form])) {
      toast.error("Complete todos los campos obligatorios");
      return;
    }
    setGuardando(true);
    try {
      await api.post("/viajes", {
        fecha_inicio: form.fecha_inicio,
        origen: form.origen.trim(),
        destino: form.destino.trim(),
        valor_flete_neto: form.valor_flete_neto,
        cliente_id: form.cliente_id,
        chofer_id: form.chofer_id,
        tracto_id: form.tracto_id,
        rampla_id: form.rampla_id,
        notas: form.notas.trim() || null,
      });
      toast.success("Viaje creado");
      setDialogo(false);
      const v = await api.get<Viaje[]>("/viajes");
      setViajes(v ?? []);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-[#2A237A]">Viajes</h1>
        {puedeEscribir && (
          <Button
            onClick={() => setDialogo(true)}
            className="bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
          >
            <Plus className="h-5 w-5" />
            Nuevo Viaje
          </Button>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setFiltroEstado("todos")}
          className={`rounded-full px-4 py-1.5 text-base font-medium ${
            filtroEstado === "todos" ? "bg-[#2A237A] text-white" : "bg-white text-gray-600 border"
          }`}
        >
          Todos ({viajes.length})
        </button>
        {ESTADOS.map((e) => (
          <button
            key={e}
            onClick={() => setFiltroEstado(e)}
            className={`rounded-full px-4 py-1.5 text-base font-medium ${
              filtroEstado === e ? "bg-[#2A237A] text-white" : "bg-white text-gray-600 border"
            }`}
          >
            {ESTADO_VIAJE_LABEL[e]} ({viajes.filter((v) => v.estado === e).length})
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-lg border bg-white">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-base">Inicio</TableHead>
              <TableHead className="text-base">Ruta</TableHead>
              <TableHead className="text-base">Cliente</TableHead>
              <TableHead className="text-base">Chofer</TableHead>
              <TableHead className="text-base">Camión</TableHead>
              <TableHead className="text-base">Valor Flete</TableHead>
              <TableHead className="text-base">Estado</TableHead>
              <TableHead className="w-16 text-base"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-gray-500">
                  Cargando…
                </TableCell>
              </TableRow>
            ) : filtrados.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-gray-500">
                  No hay viajes registrados
                </TableCell>
              </TableRow>
            ) : (
              filtrados.map((v) => (
                <TableRow key={v.id}>
                  <TableCell className="text-base">{formatFecha(v.fecha_inicio)}</TableCell>
                  <TableCell className="text-base">
                    {v.origen} → {v.destino}
                  </TableCell>
                  <TableCell className="text-base">{v.cliente_nombre}</TableCell>
                  <TableCell className="text-base">{v.chofer_nombre}</TableCell>
                  <TableCell className="text-base font-medium">{v.tracto_patente}</TableCell>
                  <TableCell className="text-base font-semibold">
                    {formatCLP(v.valor_flete_neto)}
                  </TableCell>
                  <TableCell>
                    <Badge className={`${ESTADO_VIAJE_COLOR[v.estado]} text-sm`}>
                      {ESTADO_VIAJE_LABEL[v.estado]}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Link href={`/viajes/${v.id}`}>
                      <Button size="icon" variant="outline" aria-label="Ver viaje">
                        <Eye className="h-4 w-4" />
                      </Button>
                    </Link>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogo} onOpenChange={setDialogo}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl">Nuevo Viaje</DialogTitle>
            <DialogDescription className="text-base">
              Seleccione cliente, chofer y equipos para el flete.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Fecha Inicio *</Label>
                <Input
                  type="date"
                  value={form.fecha_inicio}
                  onChange={(e) => setForm({ ...form, fecha_inicio: e.target.value })}
                  className="text-base"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-base">Valor Flete ($) *</Label>
                <InputCLP
                  value={form.valor_flete_neto}
                  onChange={(v) => setForm({ ...form, valor_flete_neto: v })}
                  placeholder="$ 1.200.000"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Origen *</Label>
                <Input
                  value={form.origen}
                  onChange={(e) => setForm({ ...form, origen: e.target.value })}
                  className="text-base"
                  placeholder="Santiago"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-base">Destino *</Label>
                <Input
                  value={form.destino}
                  onChange={(e) => setForm({ ...form, destino: e.target.value })}
                  className="text-base"
                  placeholder="Antofagasta"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Cliente *</Label>
              <Select
                value={form.cliente_id}
                onValueChange={(v) => setForm({ ...form, cliente_id: v ?? "" })}
              >
                <SelectTrigger className="text-base">
                  <SelectValue placeholder="Seleccione cliente" />
                </SelectTrigger>
                <SelectContent>
                  {clientes.map((c) => (
                    <SelectItem key={c.id} value={c.id} className="text-base">
                      {c.razon_social}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Chofer *</Label>
              <Select
                value={form.chofer_id}
                onValueChange={(v) => setForm({ ...form, chofer_id: v ?? "" })}
              >
                <SelectTrigger className="text-base">
                  <SelectValue placeholder="Seleccione chofer" />
                </SelectTrigger>
                <SelectContent>
                  {choferes.map((c) => (
                    <SelectItem key={c.id} value={c.id} className="text-base">
                      {c.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-base">Tracto *</Label>
                <Select
                  value={form.tracto_id}
                  onValueChange={(v) => setForm({ ...form, tracto_id: v ?? "" })}
                >
                  <SelectTrigger className="text-base">
                    <SelectValue placeholder="Tracto" />
                  </SelectTrigger>
                  <SelectContent>
                    {tractos.map((t) => (
                      <SelectItem key={t.id} value={t.id} className="text-base">
                        {t.patente}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-base">Rampla *</Label>
                <Select
                  value={form.rampla_id}
                  onValueChange={(v) => setForm({ ...form, rampla_id: v ?? "" })}
                >
                  <SelectTrigger className="text-base">
                    <SelectValue placeholder="Rampla" />
                  </SelectTrigger>
                  <SelectContent>
                    {ramplas.map((r) => (
                      <SelectItem key={r.id} value={r.id} className="text-base">
                        {r.patente}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-base">Notas</Label>
              <Input
                value={form.notas}
                onChange={(e) => setForm({ ...form, notas: e.target.value })}
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
              {guardando ? "Guardando…" : "Crear Viaje"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
