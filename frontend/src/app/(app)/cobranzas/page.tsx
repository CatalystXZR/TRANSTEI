"use client";

import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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

const SEMAFORO_COLOR: Record<string, string> = {
  vencida: "bg-red-600 text-white",
  por_vencer: "bg-yellow-500 text-black",
  al_dia: "bg-green-100 text-green-800",
};

const SEMAFORO_LABEL: Record<string, string> = {
  vencida: "Vencida",
  por_vencer: "Por vencer",
  al_dia: "Al día",
};

export default function CobranzasPage() {
  const [data, setData] = useState<Cobranzas | null>(null);
  const [cargando, setCargando] = useState(true);

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

  async function marcarPagada(item: CobranzaItem) {
    try {
      await api.patch(`/facturas/${item.id}/estado`, { estado: "pagada" });
      toast.success("Factura marcada como pagada");
      recargar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-[#2A237A]">Cuentas por Cobrar</h1>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base text-red-700">
              <span className="h-3 w-3 rounded-full bg-red-600" /> Vencidas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-red-600">{formatCLP(data?.total_vencidas)}</p>
          </CardContent>
        </Card>
        <Card className="border-yellow-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base text-yellow-700">
              <span className="h-3 w-3 rounded-full bg-yellow-500" /> Por vencer (≤5 días)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-yellow-600">
              {formatCLP(data?.total_por_vencer)}
            </p>
          </CardContent>
        </Card>
        <Card className="border-green-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base text-green-700">
              <span className="h-3 w-3 rounded-full bg-green-600" /> Al día
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-green-700">{formatCLP(data?.total_al_dia)}</p>
          </CardContent>
        </Card>
      </div>

      <div className="overflow-x-auto rounded-lg border bg-white">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-base">N° SII</TableHead>
              <TableHead className="text-base">Cliente</TableHead>
              <TableHead className="text-base">Total</TableHead>
              <TableHead className="text-base">Emisión</TableHead>
              <TableHead className="text-base">Vencimiento</TableHead>
              <TableHead className="text-base">Semáforo</TableHead>
              <TableHead className="w-24 text-base"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cargando ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-gray-500">
                  Cargando…
                </TableCell>
              </TableRow>
            ) : (data?.items ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-gray-500">
                  No hay facturas pendientes ✓
                </TableCell>
              </TableRow>
            ) : (
              (data?.items ?? []).map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="text-base font-semibold">{item.numero_sii}</TableCell>
                  <TableCell className="text-base">{item.cliente}</TableCell>
                  <TableCell className="text-base font-semibold">{formatCLP(item.total)}</TableCell>
                  <TableCell className="text-base">{formatFecha(item.fecha_emision)}</TableCell>
                  <TableCell className="text-base">
                    {formatFecha(item.fecha_vencimiento)}
                    {item.dias_restantes !== null && item.dias_restantes >= 0 && (
                      <span className="ml-1 text-sm text-gray-500">
                        ({item.dias_restantes} d)
                      </span>
                    )}
                    {item.dias_restantes !== null && item.dias_restantes < 0 && (
                      <span className="ml-1 text-sm font-medium text-red-600">
                        (+{Math.abs(item.dias_restantes)} d atraso)
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge className={`${SEMAFORO_COLOR[item.semaforo]} text-sm`}>
                      {SEMAFORO_LABEL[item.semaforo]}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      className="bg-green-600 text-white hover:bg-green-700"
                      onClick={() => marcarPagada(item)}
                      aria-label="Marcar pagada"
                    >
                      <CheckCircle2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
