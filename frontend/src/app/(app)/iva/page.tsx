"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import { CATEGORIA_GASTO_LABEL } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface IvaResumen {
  mes: string;
  tasa: string;
  debito: string;
  credito: string;
  a_pagar: string;
  facturas: { numero_sii: string; cliente: string; neto: string; iva: string }[];
  gastos: { id: string; categoria: string; monto: string; iva_credito: string; fecha: string }[];
}

export default function IvaPage() {
  const hoy = new Date();
  const [mes, setMes] = useState(`${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`);
  const [data, setData] = useState<IvaResumen | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let activo = true;
    api
      .get<IvaResumen>(`/iva/resumen?mes=${mes}`)
      .then((d) => {
        if (activo) setData(d ?? null);
      })
      .catch((e) => {
        if (activo) toast.error(e instanceof Error ? e.message : "Error al calcular IVA");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [mes]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-[#2A237A]">Cuadratura de IVA</h1>
        <div className="flex items-center gap-3">
          <Input
            type="month"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
            className="w-44 text-base"
          />
        </div>
      </div>

      <div className="rounded-lg bg-yellow-50 p-4 text-base text-yellow-800">
        El IVA se paga el día <strong>20</strong> del mes siguiente al declarado.
      </div>

      {cargando ? (
        <p className="py-8 text-center text-gray-500">Calculando…</p>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base text-gray-500">IVA Débito Fiscal</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold text-[#2A237A]">{formatCLP(data?.debito)}</p>
                <p className="text-sm text-gray-500">IVA de facturas afectas emitidas</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base text-gray-500">IVA Crédito Fiscal</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold text-green-700">{formatCLP(data?.credito)}</p>
                <p className="text-sm text-gray-500">IVA de gastos con boleta recuperable</p>
              </CardContent>
            </Card>
            <Card className={Number(data?.a_pagar ?? 0) > 0 ? "border-red-200" : ""}>
              <CardHeader>
                <CardTitle className="text-base text-gray-500">A Pagar (día 20)</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold text-red-600">{formatCLP(data?.a_pagar)}</p>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border bg-white">
              <p className="border-b p-4 text-base font-semibold">
                Facturas afectas del mes ({data?.facturas.length ?? 0})
              </p>
              <div className="max-h-80 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-base">N°</TableHead>
                      <TableHead className="text-base">Cliente</TableHead>
                      <TableHead className="text-base">Neto</TableHead>
                      <TableHead className="text-base">IVA</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(data?.facturas ?? []).map((f, i) => (
                      <TableRow key={i}>
                        <TableCell className="text-base">{f.numero_sii}</TableCell>
                        <TableCell className="text-base">{f.cliente}</TableCell>
                        <TableCell className="text-base">{formatCLP(f.neto)}</TableCell>
                        <TableCell className="text-base">{formatCLP(f.iva)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
            <div className="rounded-lg border bg-white">
              <p className="border-b p-4 text-base font-semibold">
                Gastos con IVA recuperable ({data?.gastos.length ?? 0})
              </p>
              <div className="max-h-80 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-base">Fecha</TableHead>
                      <TableHead className="text-base">Categoría</TableHead>
                      <TableHead className="text-base">Monto</TableHead>
                      <TableHead className="text-base">Crédito</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(data?.gastos ?? []).map((g) => (
                      <TableRow key={g.id}>
                        <TableCell className="text-base">{formatFecha(g.fecha)}</TableCell>
                        <TableCell className="text-base">
                          {CATEGORIA_GASTO_LABEL[g.categoria as keyof typeof CATEGORIA_GASTO_LABEL] ??
                            g.categoria}
                        </TableCell>
                        <TableCell className="text-base">{formatCLP(g.monto)}</TableCell>
                        <TableCell className="text-base text-green-700">
                          {formatCLP(g.iva_credito)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
