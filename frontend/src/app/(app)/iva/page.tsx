"use client";

import { useEffect, useState } from "react";
import { CalendarDays, Info, Receipt, ReceiptText } from "lucide-react";
import { nucleo } from "@/lib/nucleo";
import { useNucleoEmpresa } from "@/lib/use-nucleo-empresa";
import { formatCLP, formatFecha } from "@/lib/format";
import type { IvaResumenNucleo } from "@/types/nucleo";
import { Input } from "@/components/ui/input";
import {
  Aviso,
  PageHeader,
  Panel,
  StatTile,
  StatTileSkeleton,
} from "@/components/sistema";
import { ErrorNucleo } from "@/components/nucleo/estado-error";

function dosDigitos(n: number) {
  return String(n).padStart(2, "0");
}

function rangoMesActual() {
  const hoy = new Date();
  const anio = hoy.getFullYear();
  const mes = hoy.getMonth() + 1;
  const ultimoDia = new Date(anio, mes, 0).getDate();
  return {
    desde: `${anio}-${dosDigitos(mes)}-01`,
    hasta: `${anio}-${dosDigitos(mes)}-${dosDigitos(ultimoDia)}`,
  };
}

function numero(valor: string | null | undefined) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = Number(valor);
  if (Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 2 }).format(n);
}

export default function IvaPage() {
  const {
    empresa,
    empresaId,
    cargando: cargandoSesion,
    error: errorSesion,
  } = useNucleoEmpresa();

  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [resumen, setResumen] = useState<IvaResumenNucleo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [errorDatos, setErrorDatos] = useState<unknown>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      const rango = rangoMesActual();
      setDesde(rango.desde);
      setHasta(rango.hasta);
    }, 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!empresaId || !desde || !hasta || desde > hasta) return;
    let activo = true;
    const t = setTimeout(() => {
      setCargando(true);
      setErrorDatos(null);
      const params = new URLSearchParams({ desde, hasta });
      nucleo
        .get<IvaResumenNucleo>(
          `/nucleo/iva/resumen?${params.toString()}`,
          empresaId,
        )
        .then((data) => {
          if (activo) setResumen(data);
        })
        .catch((e) => {
          if (activo) setErrorDatos(e);
        })
        .finally(() => {
          if (activo) setCargando(false);
        });
    }, 200);
    return () => {
      activo = false;
      clearTimeout(t);
    };
  }, [empresaId, desde, hasta]);

  const rangoInvalido = !!desde && !!hasta && desde > hasta;
  const resumenVisible = rangoInvalido ? null : resumen;
  const cargandoVista =
    cargandoSesion ||
    !desde ||
    !hasta ||
    (!rangoInvalido && cargando);
  const bloqueado = Boolean(errorSesion || errorDatos);

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Finanzas"
        titulo="IVA mensual"
        descripcion="Resumen de IVA débito del núcleo sobre facturas no anuladas. El crédito fiscal, el monto a pagar y el remanente dependen de P-09 y no están implementados."
        acciones={
          <div className="flex flex-wrap items-end gap-s2">
            <label className="flex items-center gap-s2 text-tinta-3">
              <CalendarDays className="size-[18px]" aria-hidden="true" />
              <span className="sr-only">Desde</span>
              <Input
                type="date"
                value={desde}
                onChange={(e) => setDesde(e.target.value)}
                className="w-44"
                aria-label="Fecha desde"
              />
            </label>
            <label className="flex items-center gap-s2 text-tinta-3">
              <span className="sr-only">Hasta</span>
              <Input
                type="date"
                value={hasta}
                onChange={(e) => setHasta(e.target.value)}
                className="w-44"
                aria-label="Fecha hasta"
              />
            </label>
          </div>
        }
      />

      <ErrorNucleo error={errorSesion ?? errorDatos} />

      {rangoInvalido && (
        <Aviso tono="critico" icono={CalendarDays}>
          La fecha desde no puede ser posterior a la fecha hasta.
        </Aviso>
      )}

      {!bloqueado && (
        <>
      {empresa && (
        <p className="text-[14px] text-tinta-3">
          Empresa: <span className="font-medium text-tinta-2">{empresa.razon_social}</span>
        </p>
      )}

      {resumenVisible && (
        <Aviso tono="info" icono={CalendarDays}>
          Período consultado: <strong>{formatFecha(resumenVisible.desde)}</strong> al{" "}
          <strong>{formatFecha(resumenVisible.hasta)}</strong>. Tasa vigente:{" "}
          <strong>
            {resumenVisible.tasa_iva === null
              ? "no configurada"
              : `${numero(resumenVisible.tasa_iva)} %`}
          </strong>
          .
        </Aviso>
      )}

      {cargandoVista ? (
        <div className="grid gap-s3 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <StatTileSkeleton key={i} />
          ))}
        </div>
      ) : resumenVisible ? (
        <div className="grid gap-s3 md:grid-cols-3">
          <StatTile
            etiqueta="IVA débito"
            valor={formatCLP(resumenVisible.iva_debito)}
            detalle={`${resumenVisible.facturas} factura(s) no anulada(s)`}
            tono="info"
            icono={ReceiptText}
            destacado
          />
          <StatTile
            etiqueta="Base neta"
            valor={formatCLP(resumenVisible.base_neta)}
            detalle="Suma de netos de las facturas del rango"
            tono="ok"
            icono={Receipt}
          />
          <StatTile
            etiqueta="Tasa de IVA"
            valor={
              resumenVisible.tasa_iva === null
                ? "—"
                : `${numero(resumenVisible.tasa_iva)} %`
            }
            detalle={
              resumenVisible.tasa_iva === null
                ? "La empresa no tiene iva_porcentaje configurado"
                : "Valor vigente en configuración"
            }
            tono={resumenVisible.tasa_iva === null ? "atencion" : "neutro"}
            icono={Info}
          />
        </div>
      ) : (
        !errorDatos &&
        !rangoInvalido && (
          <Panel>
            <p className="p-s5 text-[15px] text-tinta-3">
              Seleccione un rango de fechas para consultar el resumen.
            </p>
          </Panel>
        )
      )}

      {resumenVisible && resumenVisible.facturas === 0 && (
        <Aviso tono="neutro" icono={ReceiptText}>
          No hay facturas no anuladas emitidas en el rango. El resumen se calcula igual,
          con débito cero.
        </Aviso>
      )}

      {resumenVisible?.advertencia && (
        <Aviso tono="atencion" icono={Info}>
          {resumenVisible.advertencia}
        </Aviso>
      )}

      <Panel
        titulo="Crédito fiscal pendiente"
        descripcion="Alcance declarado del núcleo, no un error de carga"
      >
        <div className="space-y-s3 p-s4">
          <Aviso tono="neutro" icono={Info}>
            Esta pantalla muestra <strong>solo IVA débito</strong>. El crédito fiscal de
            gastos, el monto a pagar, el remanente y el descuento de notas de crédito no
            están implementados porque dependen de la definición <strong>P-09</strong>.
            No se muestra un total que el servidor no entrega.
          </Aviso>
          <p className="text-[14px] text-tinta-3">
            Las facturas se agregan por fecha de emisión inclusiva y sólo se excluyen las
            anuladas. La tasa sale de <code>nucleo.config_vigente</code>; si no está
            configurada, el resumen la devuelve nula en lugar de asumir 19 %.
          </p>
        </div>
      </Panel>
        </>
      )}
    </div>
  );
}
