"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, FileWarning } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import type { AlertasDashboard, ResumenDashboard } from "@/types";
import { ESTADO_VIAJE_COLOR, ESTADO_VIAJE_LABEL } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function DashboardPage() {
  const [resumen, setResumen] = useState<ResumenDashboard | null>(null);
  const [alertas, setAlertas] = useState<AlertasDashboard | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let activo = true;
    Promise.all([
      api.get<ResumenDashboard>("/dashboard/resumen"),
      api.get<AlertasDashboard>("/dashboard/alertas"),
    ])
      .then(([r, a]) => {
        if (!activo) return;
        setResumen(r ?? null);
        setAlertas(a ?? null);
      })
      .catch((e) => {
        if (activo) toast.error(e instanceof Error ? e.message : "Error al cargar dashboard");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  if (cargando) {
    return <p className="py-10 text-center text-gray-500">Cargando panel de control…</p>;
  }

  const vencimientos = alertas?.vencimientos ?? [];
  const facturasVencidas = alertas?.facturas_vencidas ?? [];
  const hayAlertas = vencimientos.length > 0 || facturasVencidas.length > 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-[#2A237A]">Panel de Control</h1>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-gray-500">
              Ingresos del Mes ({resumen?.mes ?? "-"})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-green-700">
              {formatCLP(resumen?.ingresos_mes)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-gray-500">Cuentas por Cobrar</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-[#2A237A]">
              {formatCLP(resumen?.cuentas_por_cobrar)}
            </p>
            {Number(resumen?.cuentas_atrasadas ?? 0) > 0 && (
              <p className="mt-1 text-sm font-medium text-red-600">
                Atrasadas: {formatCLP(resumen?.cuentas_atrasadas)}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-gray-500">Gastos del Mes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-red-600">{formatCLP(resumen?.gastos_mes)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-gray-500">Viajes Activos</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-[#2A237A]">
              {resumen?.viajes_activos.length ?? 0}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg text-[#2A237A]">
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
              Centro de Alertas
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {!hayAlertas ? (
              <p className="text-base text-gray-500">Sin alertas pendientes. Todo al día ✓</p>
            ) : (
              <>
                {vencimientos.map((v, i) => (
                  <div
                    key={`v-${i}`}
                    className={`flex items-center justify-between rounded-lg border p-3 ${
                      v.dias_restantes < 0
                        ? "border-red-200 bg-red-50"
                        : "border-yellow-200 bg-yellow-50"
                    }`}
                  >
                    <div>
                      <p className="text-base font-medium">
                        {v.equipo} — {v.concepto}
                      </p>
                      <p className="text-sm text-gray-600">
                        Vence {formatFecha(v.fecha)} ·{" "}
                        {v.dias_restantes < 0
                          ? `vencido hace ${Math.abs(v.dias_restantes)} días`
                          : `en ${v.dias_restantes} días`}
                      </p>
                    </div>
                    <Badge
                      className={
                        v.dias_restantes < 0
                          ? "bg-red-600 text-white"
                          : "bg-yellow-500 text-black"
                      }
                    >
                      {v.dias_restantes < 0 ? "Vencido" : "Por vencer"}
                    </Badge>
                  </div>
                ))}
                {facturasVencidas.map((f) => (
                  <div
                    key={f.id}
                    className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 p-3"
                  >
                    <div className="flex items-center gap-2">
                      <FileWarning className="h-5 w-5 text-red-600" />
                      <div>
                        <p className="text-base font-medium">
                          Factura {f.numero_sii} — {f.cliente}
                        </p>
                        <p className="text-sm text-gray-600">
                          {formatCLP(f.total)} · atrasada {f.dias_atraso} días
                        </p>
                      </div>
                    </div>
                    <Link href="/cobranzas">
                      <Badge className="bg-red-600 text-white">Cobrar</Badge>
                    </Link>
                  </div>
                ))}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-lg text-[#2A237A]">
              Viajes Activos Hoy
              <Link href="/viajes" className="text-sm font-normal text-gray-500 hover:underline">
                Ver todos
              </Link>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-base">Ruta</TableHead>
                  <TableHead className="text-base">Camión</TableHead>
                  <TableHead className="text-base">Estado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(resumen?.viajes_activos ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3} className="py-6 text-center text-gray-500">
                      No hay camiones en ruta
                    </TableCell>
                  </TableRow>
                ) : (
                  (resumen?.viajes_activos ?? []).map((v) => (
                    <TableRow key={v.id}>
                      <TableCell className="text-base">
                        <Link href={`/viajes/${v.id}`} className="flex items-center gap-1 hover:underline">
                          {v.origen} <ArrowRight className="h-4 w-4" /> {v.destino}
                        </Link>
                      </TableCell>
                      <TableCell className="text-base font-medium">{v.tracto_patente}</TableCell>
                      <TableCell>
                        <Badge className={`${ESTADO_VIAJE_COLOR[v.estado]} text-sm`}>
                          {ESTADO_VIAJE_LABEL[v.estado]}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
