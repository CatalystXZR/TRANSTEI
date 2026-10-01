"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, FileWarning } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import type { AlertasDashboard, KpiValor, ResumenDashboard } from "@/types";
import { ESTADO_VIAJE_COLOR, ESTADO_VIAJE_LABEL, formatValorKpi } from "@/types";
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
  const [kpis, setKpis] = useState<KpiValor[]>([]);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let activo = true;
    Promise.all([
      api.get<ResumenDashboard>("/dashboard/resumen"),
      api.get<AlertasDashboard>("/dashboard/alertas"),
      api.get<KpiValor[]>("/kpis/valores"),
    ])
      .then(([r, a, k]) => {
        if (!activo) return;
        setResumen(r ?? null);
        setAlertas(a ?? null);
        setKpis(k ?? []);
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

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {kpis.length === 0 ? (
          <Card className="sm:col-span-2 lg:col-span-3 xl:col-span-4">
            <CardContent className="pt-6 text-base text-gray-500">
              No hay indicadores configurados. Un administrador puede crearlos en
              “Indicadores (KPIs)”.
            </CardContent>
          </Card>
        ) : (
          kpis.map((k) => (
            <Card key={k.id}>
              <CardHeader>
                <CardTitle className="text-base text-gray-500">{k.nombre}</CardTitle>
              </CardHeader>
              <CardContent>
                {k.error ? (
                  <p className="text-sm text-red-600">Error en la fórmula</p>
                ) : (
                  <div className="flex items-center gap-2">
                    <span
                      className="h-3 w-3 shrink-0 rounded-full"
                      style={{
                        backgroundColor:
                          k.color === "rojo"
                            ? "#dc2626"
                            : k.color === "amarillo"
                              ? "#f59e0b"
                              : k.color === "verde"
                                ? "#16a34a"
                                : k.color === "azul"
                                  ? "#2A237A"
                                  : "#d1d5db",
                      }}
                    />
                    <p className="text-2xl font-bold text-[#2A237A]">
                      {formatValorKpi(k.valor, k.formato)}
                    </p>
                  </div>
                )}
                {k.descripcion && (
                  <p className="mt-1 text-xs text-gray-400">{k.descripcion}</p>
                )}
              </CardContent>
            </Card>
          ))
        )}
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
