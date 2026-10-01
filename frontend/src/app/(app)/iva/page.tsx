"use client";

import { useEffect, useState } from "react";
import { CalendarDays, Minus, Receipt, ReceiptText, Equal } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import { CATEGORIA_GASTO_LABEL } from "@/types";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Aviso, FilaVacia, FilasCargando, PageHeader, Panel, StatTileSkeleton } from "@/components/sistema";

interface IvaResumen {
  mes: string;
  tasa: string;
  debito: string;
  credito: string;
  a_pagar: string;
  facturas: { numero_sii: string; cliente: string; neto: string; iva: string }[];
  gastos: { id: string; categoria: string; monto: string; iva_credito: string; fecha: string }[];
}

function mesActual() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function nombreMes(mes: string) {
  const [a, m] = mes.split("-").map(Number);
  if (!a || !m) return mes;
  return new Intl.DateTimeFormat("es-CL", { month: "long", year: "numeric" }).format(new Date(a, m - 1, 1));
}

function fechaPago(mes: string) {
  const [a, m] = mes.split("-").map(Number);
  if (!a || !m) return "";
  return new Intl.DateTimeFormat("es-CL", { day: "numeric", month: "long", year: "numeric" }).format(new Date(a, m, 20));
}

export default function IvaPage() {
  const [mes, setMes] = useState("");
  const [data, setData] = useState<IvaResumen | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setMes(mesActual()), 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!mes) return;
    let activo = true;
    const t = setTimeout(() => setCargando(true), 0);
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
      clearTimeout(t);
    };
  }, [mes]);

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Finanzas"
        titulo="IVA mensual"
        descripcion="Débito fiscal de las facturas afectas menos el crédito de los gastos con IVA recuperable."
        acciones={
          <label className="flex items-center gap-s2 text-[15px] text-tinta-3">
            <CalendarDays className="size-[18px]" />
            <span className="sr-only">Mes</span>
            <Input type="month" value={mes} onChange={(e) => e.target.value && setMes(e.target.value)} className="w-48" aria-label="Mes a declarar" />
          </label>
        }
      />

      {cargando || !data ? (
        <div className="grid gap-s3 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <StatTileSkeleton key={i} />
          ))}
        </div>
      ) : (
        <section aria-label="Cuadratura" className="grid items-stretch gap-s3 md:grid-cols-[1fr_auto_1fr_auto_1.15fr]">
          <div className="rounded-xl border border-borde bg-superficie p-s4 shadow-elev-1">
            <p className="text-[15px] font-medium text-tinta-3">IVA débito</p>
            <p className="cifra mt-s3 text-[32px] leading-none font-semibold">{formatCLP(data.debito)}</p>
            <p className="mt-s2 text-[14px] text-tinta-3">{data.facturas.length} facturas afectas</p>
          </div>
          <div className="hidden items-center justify-center text-tinta-3 md:flex" aria-hidden="true">
            <Minus className="size-5" />
          </div>
          <div className="rounded-xl border border-borde bg-superficie p-s4 shadow-elev-1">
            <p className="text-[15px] font-medium text-tinta-3">IVA crédito</p>
            <p className="cifra mt-s3 text-[32px] leading-none font-semibold text-ok">{formatCLP(data.credito)}</p>
            <p className="mt-s2 text-[14px] text-tinta-3">{data.gastos.length} gastos con IVA recuperable</p>
          </div>
          <div className="hidden items-center justify-center text-tinta-3 md:flex" aria-hidden="true">
            <Equal className="size-5" />
          </div>
          <div className="relative overflow-hidden rounded-xl border border-marca bg-marca p-s4 text-white shadow-elev-2">
            <p className="text-[15px] font-medium text-white/75">A pagar</p>
            <p className="cifra mt-s3 text-[38px] leading-none font-semibold">{formatCLP(data.a_pagar)}</p>
            <p className="mt-s2 text-[14px] text-white/70">Plazo: {fechaPago(data.mes)}</p>
            <span className="absolute inset-x-0 bottom-0 h-[3px] bg-senal" aria-hidden="true" />
          </div>
        </section>
      )}

      {mes && (
        <Aviso icono={CalendarDays}>
          Período <strong className="capitalize">{nombreMes(mes)}</strong> · tasa {data?.tasa ?? "19"} %. El IVA se declara
          y paga hasta el día 20 del mes siguiente.
        </Aviso>
      )}

      <div className="grid gap-s4 xl:grid-cols-2">
        <Panel titulo="Facturas afectas" descripcion="Generan IVA débito">
          <div className="max-h-[420px] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>N°</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead className="text-right">Neto</TableHead>
                  <TableHead className="text-right">IVA</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cargando ? (
                  <FilasCargando columnas={4} filas={3} />
                ) : !data?.facturas.length ? (
                  <FilaVacia columnas={4} icono={ReceiptText} titulo="Sin facturas afectas este mes" />
                ) : (
                  data.facturas.map((f, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-mono">{f.numero_sii}</TableCell>
                      <TableCell>{f.cliente}</TableCell>
                      <TableCell className="cifra text-right text-tinta-2">{formatCLP(f.neto)}</TableCell>
                      <TableCell className="cifra text-right font-semibold">{formatCLP(f.iva)}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </Panel>
        <Panel titulo="Gastos con IVA recuperable" descripcion="Generan IVA crédito">
          <div className="max-h-[420px] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fecha</TableHead>
                  <TableHead>Categoría</TableHead>
                  <TableHead className="text-right">Monto</TableHead>
                  <TableHead className="text-right">Crédito</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cargando ? (
                  <FilasCargando columnas={4} filas={3} />
                ) : !data?.gastos.length ? (
                  <FilaVacia columnas={4} icono={Receipt} titulo="Sin gastos con IVA recuperable" />
                ) : (
                  data.gastos.map((g) => (
                    <TableRow key={g.id}>
                      <TableCell className="text-tinta-2">{formatFecha(g.fecha)}</TableCell>
                      <TableCell>{CATEGORIA_GASTO_LABEL[g.categoria as keyof typeof CATEGORIA_GASTO_LABEL] ?? g.categoria}</TableCell>
                      <TableCell className="cifra text-right text-tinta-2">{formatCLP(g.monto)}</TableCell>
                      <TableCell className="cifra text-right font-semibold text-ok">{formatCLP(g.iva_credito)}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
