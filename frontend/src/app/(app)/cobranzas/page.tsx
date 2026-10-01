"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, HandCoins } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { api } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import { Button } from "@/components/ui/button";
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
  FilaVacia,
  FilasCargando,
  PageHeader,
  Panel,
  Segmentado,
  StatTile,
  StatTileSkeleton,
  StatusBadge,
  type Tono,
} from "@/components/sistema";

interface CobranzaItem {
  id: string;
  numero_sii: string;
  cliente: string;
  total: string;
  fecha_emision: string;
  fecha_vencimiento: string | null;
  dias_restantes: number | null;
  semaforo: "vencida" | "por_vencer" | "al_dia";
}

interface Cobranzas {
  total_vencidas: string;
  total_por_vencer: string;
  total_al_dia: string;
  items: CobranzaItem[];
}

const SEMAFORO: Record<CobranzaItem["semaforo"], { tono: Tono; label: string }> = {
  vencida: { tono: "critico", label: "Vencida" },
  por_vencer: { tono: "atencion", label: "Por vencer" },
  al_dia: { tono: "ok", label: "Al día" },
};

type Filtro = "todas" | CobranzaItem["semaforo"];

export default function CobranzasPage() {
  const [data, setData] = useState<Cobranzas | null>(null);
  const [cargando, setCargando] = useState(true);
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [pagando, setPagando] = useState<CobranzaItem | null>(null);

  function recargar() {
    api
      .get<Cobranzas>("/cobranzas")
      .then((d) => setData(d ?? null))
      .catch((e) => toast.error(e instanceof Error ? e.message : "Error al cargar"))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    let activo = true;
    api
      .get<Cobranzas>("/cobranzas")
      .then((d) => {
        if (activo) setData(d ?? null);
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

  const items = useMemo(() => (data?.items ?? []).filter((i) => filtro === "todas" || i.semaforo === filtro), [data, filtro]);
  const cuenta = (s: CobranzaItem["semaforo"]) => (data?.items ?? []).filter((i) => i.semaforo === s).length;
  const total = Number(data?.total_vencidas ?? 0) + Number(data?.total_por_vencer ?? 0) + Number(data?.total_al_dia ?? 0);

  async function confirmarPago() {
    if (!pagando) return;
    try {
      await api.patch(`/facturas/${pagando.id}/estado`, { estado: "pagada" });
      toast.success(`Pago registrado: factura ${pagando.numero_sii}`);
      setPagando(null);
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Finanzas"
        titulo="Cuentas por cobrar"
        descripcion={cargando ? "Facturas pendientes de pago, ordenadas por vencimiento." : <>Total pendiente <strong className="font-semibold text-tinta">{formatCLP(total)}</strong>, ordenado por vencimiento.</>}
      />

      <section className="grid gap-s3 md:grid-cols-3" aria-label="Resumen de cobranzas">
        {cargando ? (
          Array.from({ length: 3 }).map((_, i) => <StatTileSkeleton key={i} />)
        ) : (
          <>
            <StatTile etiqueta="Vencidas" valor={formatCLP(data?.total_vencidas)} detalle={`${cuenta("vencida")} facturas — cobrar ya`} tono="critico" />
            <StatTile etiqueta="Por vencer" valor={formatCLP(data?.total_por_vencer)} detalle={`${cuenta("por_vencer")} facturas en los próximos días`} tono="atencion" />
            <StatTile etiqueta="Al día" valor={formatCLP(data?.total_al_dia)} detalle={`${cuenta("al_dia")} facturas dentro de plazo`} tono="ok" />
          </>
        )}
      </section>

      <Segmentado
        etiqueta="Filtrar por estado"
        valor={filtro}
        onCambio={setFiltro}
        opciones={[
          { valor: "todas", etiqueta: "Todas", contador: data?.items.length ?? 0 },
          { valor: "vencida", etiqueta: "Vencidas", contador: cuenta("vencida") },
          { valor: "por_vencer", etiqueta: "Por vencer", contador: cuenta("por_vencer") },
          { valor: "al_dia", etiqueta: "Al día", contador: cuenta("al_dia") },
        ]}
      />

      <Panel>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>N° SII</TableHead>
              <TableHead>Cliente</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead>Emisión</TableHead>
              <TableHead>Vencimiento</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="text-right">
                <span className="sr-only">Acciones</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <FilasCargando columnas={7} />
            ) : items.length === 0 ? (
              <FilaVacia
                columnas={7}
                icono={HandCoins}
                titulo={(data?.items.length ?? 0) === 0 ? "No hay facturas pendientes" : "Sin facturas en este estado"}
                descripcion={(data?.items.length ?? 0) === 0 ? "Todas las facturas emitidas están pagadas." : undefined}
              />
            ) : (
              items.map((i) => (
                <TableRow key={i.id}>
                  <TableCell className="font-mono font-semibold">{i.numero_sii}</TableCell>
                  <TableCell className="font-medium">{i.cliente}</TableCell>
                  <TableCell className="cifra text-right text-[16px] font-semibold">{formatCLP(i.total)}</TableCell>
                  <TableCell className="text-tinta-2">{formatFecha(i.fecha_emision)}</TableCell>
                  <TableCell>
                    <span className="text-tinta-2">{formatFecha(i.fecha_vencimiento)}</span>
                    {i.dias_restantes !== null && (
                      <span
                        className={cn(
                          "ml-2 text-[13px] font-medium",
                          i.dias_restantes < 0 ? "text-critico" : i.semaforo === "por_vencer" ? "text-atencion" : "text-tinta-3",
                        )}
                      >
                        {i.dias_restantes < 0 ? `${-i.dias_restantes} d de atraso` : i.dias_restantes === 0 ? "vence hoy" : `en ${i.dias_restantes} d`}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge tono={SEMAFORO[i.semaforo].tono}>{SEMAFORO[i.semaforo].label}</StatusBadge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="xs" onClick={() => setPagando(i)}>
                      <CheckCircle2 /> Registrar pago
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Panel>

      <Dialog open={!!pagando} onOpenChange={(o) => !o && setPagando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar pago</DialogTitle>
            <DialogDescription>
              Factura <strong>{pagando?.numero_sii}</strong> de {pagando?.cliente} por{" "}
              <strong>{pagando ? formatCLP(pagando.total) : ""}</strong>. Se registrará con fecha de hoy.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPagando(null)}>
              Cancelar
            </Button>
            <Button variant="success" onClick={confirmarPago}>
              <CheckCircle2 /> Confirmar pago
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
