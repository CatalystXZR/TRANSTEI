"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Banknote,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Receipt,
  RefreshCw,
  ShieldAlert,
  ShoppingCart,
  TrendingDown,
  Truck,
  Wrench,
} from "lucide-react";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import { formatCLP, formatFechaHora } from "@/lib/format";
import type { TableroNucleo } from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import {
  Aviso,
  PageHeader,
  Panel,
  StatTile,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import { SelectSimple } from "@/components/formulario";

const CATEGORIAS = [
  { valor: "", etiqueta: "Todas las categorías" },
  { valor: "documentos", etiqueta: "Documentos" },
  { valor: "mantencion", etiqueta: "Mantención" },
  { valor: "pod", etiqueta: "POD" },
  { valor: "facturacion", etiqueta: "Sin facturar" },
  { valor: "oc", etiqueta: "OC" },
  { valor: "cxc", etiqueta: "CxC" },
  { valor: "margen", etiqueta: "Margen" },
  { valor: "incidente", etiqueta: "Incidentes" },
  { valor: "caja", etiqueta: "Caja" },
];

const ICONO: Record<string, typeof FileText> = {
  documentos: FileText,
  mantencion: Wrench,
  pod: ClipboardCheck,
  facturacion: Receipt,
  oc: ShoppingCart,
  cxc: Banknote,
  margen: TrendingDown,
  incidente: ShieldAlert,
  caja: Banknote,
};

function tonoSeveridad(severidad: string): Tono {
  if (severidad === "critica") return "critico";
  if (severidad === "alta") return "atencion";
  if (severidad === "media") return "info";
  return "neutro";
}

function etiquetaCategoria(categoria: string): string {
  const encontrada = CATEGORIAS.find((c) => c.valor === categoria);
  return encontrada?.etiqueta ?? categoria;
}

export default function TableroPage() {
  const [empresaId, setEmpresaId] = useState("");
  const [data, setData] = useState<TableroNucleo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [severidad, setSeveridad] = useState("");
  const [categoria, setCategoria] = useState("");

  useEffect(() => {
    let activo = true;
    getEmpresas()
      .then((empresas) => {
        if (!activo) return;
        if (empresas[0]) {
          setEmpresaId(empresas[0].id);
        } else {
          setError("El usuario no tiene una empresa activa.");
          setCargando(false);
        }
      })
      .catch((e) => {
        if (!activo) return;
        setError(e instanceof Error ? e.message : "No se pudieron cargar las empresas");
        setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!empresaId) return;
      if (silencioso) setActualizando(true);
      else setCargando(true);
      setError(null);
      try {
        const tablero = await nucleo.get<TableroNucleo>(
          "/nucleo/alertas/tablero",
          empresaId,
        );
        setData(tablero);
      } catch (e) {
        setError(e instanceof Error ? e.message : "No se pudo cargar el tablero");
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  const alertas = useMemo(
    () =>
      (data?.alertas ?? []).filter(
        (a) =>
          (!severidad || a.severidad === severidad) &&
          (!categoria || a.categoria === categoria),
      ),
    [data, severidad, categoria],
  );

  const kpis = data?.kpis;

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Dirección"
        titulo="Tablero del dueño"
        descripcion="Briefing diario y alertas accionables: documentos, mantención, POD, facturación, OC, margen, caja y CxC."
        acciones={
          <Button
            variant="outline"
            onClick={() => void cargar(true)}
            disabled={!empresaId || actualizando}
          >
            <RefreshCw className={actualizando ? "animate-spin" : undefined} />
            Actualizar
          </Button>
        }
      />

      {error && <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>}

      {data && data.salud.critica > 0 && (
        <Aviso tono="critico" icono={AlertTriangle}>
          Hay {data.salud.critica} alerta(s) crítica(s). Resuélvalas antes de tomar
          decisiones de precio o capacidad.
        </Aviso>
      )}

      <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          etiqueta="Alertas críticas"
          valor={data?.salud.critica ?? 0}
          detalle={`${data?.salud.alta ?? 0} altas · ${data?.salud.media ?? 0} medias`}
          tono={(data?.salud.critica ?? 0) > 0 ? "critico" : "ok"}
          icono={ShieldAlert}
          destacado
        />
        <StatTile
          etiqueta="CxC vencida"
          valor={formatCLP(kpis?.cxc_vencido ?? 0)}
          detalle={`CxC total ${formatCLP(kpis?.cxc_total ?? 0)}`}
          tono={Number(kpis?.cxc_vencido ?? 0) > 0 ? "critico" : "ok"}
          icono={Banknote}
        />
        <StatTile
          etiqueta="Caja operativa 30 días"
          valor={formatCLP(kpis?.caja_operativa ?? 0)}
          detalle="Cobros − gastos aprobados"
          tono={Number(kpis?.caja_operativa ?? 0) < 0 ? "critico" : "ok"}
          icono={Banknote}
        />
        <StatTile
          etiqueta="Freight Score promedio"
          valor={kpis?.freight_score_promedio ? Number(kpis.freight_score_promedio).toFixed(1) : "—"}
          detalle="Viajes con score calculado"
          tono={
            !kpis?.freight_score_promedio
              ? "neutro"
              : Number(kpis.freight_score_promedio) >= 80
                ? "ok"
                : Number(kpis.freight_score_promedio) >= 60
                  ? "atencion"
                  : "critico"
          }
          icono={TrendingDown}
        />
        <StatTile
          etiqueta="Viajes activos"
          valor={kpis?.viajes_activos ?? 0}
          detalle={`${kpis?.tractos_disponibles ?? 0}/${kpis?.tractos_activos ?? 0} tractos disponibles`}
          tono="info"
          icono={Truck}
        />
        <StatTile
          etiqueta="Sin POD"
          valor={kpis?.viajes_sin_pod ?? 0}
          detalle="Entregados sin evidencia"
          tono={(kpis?.viajes_sin_pod ?? 0) > 0 ? "atencion" : "ok"}
          icono={ClipboardCheck}
        />
        <StatTile
          etiqueta="Sin facturar"
          valor={kpis?.viajes_sin_facturar ?? 0}
          detalle="Viajes cerrados sin factura"
          tono={(kpis?.viajes_sin_facturar ?? 0) > 0 ? "atencion" : "ok"}
          icono={FileText}
        />
        <StatTile
          etiqueta="OC con alerta"
          valor={kpis?.oc_con_alerta ?? 0}
          detalle={`${kpis?.documentos_por_vencer ?? 0} docs · ${kpis?.mantenciones_proximas ?? 0} mantenciones`}
          tono={(kpis?.oc_con_alerta ?? 0) > 0 ? "atencion" : "ok"}
          icono={ShoppingCart}
        />
      </div>

      <div className="grid gap-s4 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel
          titulo="Briefing diario"
          descripcion={data ? `Generado ${formatFechaHora(data.generado_en)}` : undefined}
          acciones={
            <StatusBadge tono={data?.salud.critica ? "critico" : "ok"}>
              {data?.salud.critica ? "Requiere acción" : "Al día"}
            </StatusBadge>
          }
        >
          {cargando && !data ? (
            <div className="space-y-s3 p-s4">
              <div className="h-16 animate-pulse rounded-xl bg-superficie-hundida" />
              <div className="h-16 animate-pulse rounded-xl bg-superficie-hundida" />
            </div>
          ) : (
            <div className="space-y-s2 p-s4">
              {(data?.briefing ?? []).map((linea) => (
                <div key={linea} className="flex items-start gap-s2 text-[15px]">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-marca" />
                  <span>{linea}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel titulo="Acciones sugeridas">
          <div className="divide-y divide-borde">
            {(data?.acciones ?? []).map((accion) => (
              <Link
                key={accion.titulo}
                href={accion.link}
                className="flex items-start justify-between gap-s3 p-s4 hover:bg-superficie-hundida/40"
              >
                <div>
                  <p className="text-[15px] font-medium">{accion.titulo}</p>
                  <p className="text-[13px] text-tinta-3">{accion.descripcion}</p>
                </div>
                <StatusBadge
                  tono={
                    accion.prioridad === "critica"
                      ? "critico"
                      : accion.prioridad === "alta"
                        ? "atencion"
                        : "info"
                  }
                >
                  {accion.prioridad}
                </StatusBadge>
              </Link>
            ))}
          </div>
        </Panel>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-s3">
        <div className="flex flex-wrap gap-s2">
          {[
            { valor: "", etiqueta: "Todas" },
            { valor: "critica", etiqueta: "Críticas" },
            { valor: "alta", etiqueta: "Altas" },
            { valor: "media", etiqueta: "Medias" },
          ].map((opcion) => (
            <button
              key={opcion.valor}
              type="button"
              onClick={() => setSeveridad(opcion.valor)}
              className={
                severidad === opcion.valor
                  ? "rounded-lg border border-marca bg-marca px-3 py-2 text-[14px] font-medium text-white"
                  : "rounded-lg border border-borde bg-superficie px-3 py-2 text-[14px] font-medium text-tinta-2 hover:border-borde-fuerte"
              }
            >
              {opcion.etiqueta}
            </button>
          ))}
        </div>
        <div className="w-full sm:w-[280px]">
          <SelectSimple
            valor={categoria}
            onCambio={setCategoria}
            opciones={CATEGORIAS}
            placeholder="Categoría"
            ariaLabel="Filtrar alertas por categoría"
          />
        </div>
      </div>

      <Panel
        titulo={`Centro de alertas · ${alertas.length}`}
        descripcion="Cada alerta enlaza a la pantalla donde se resuelve."
      >
        <div className="divide-y divide-borde">
          {cargando && !data ? (
            <div className="space-y-s3 p-s4">
              <div className="h-20 animate-pulse rounded-xl bg-superficie-hundida" />
              <div className="h-20 animate-pulse rounded-xl bg-superficie-hundida" />
            </div>
          ) : alertas.length === 0 ? (
            <div className="flex flex-col items-center gap-s2 p-s6 text-center">
              <CheckCircle2 className="size-8 text-ok" />
              <p className="text-[16px] font-semibold">Sin alertas en este filtro</p>
              <p className="text-[14px] text-tinta-3">La operación está al día.</p>
            </div>
          ) : (
            alertas.map((alerta) => (
              <div key={alerta.id} className="flex flex-wrap items-start justify-between gap-s3 p-s4">
                <div className="flex min-w-0 items-start gap-s3">
                  <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-superficie-hundida text-tinta-3">
                    {(() => {
                      const Icono = ICONO[alerta.categoria] ?? AlertTriangle;
                      return <Icono className="size-4" />;
                    })()}
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-s2">
                      <StatusBadge tono={tonoSeveridad(alerta.severidad)}>
                        {alerta.severidad}
                      </StatusBadge>
                      <span className="text-[12px] font-medium tracking-wide text-tinta-3 uppercase">
                        {etiquetaCategoria(alerta.categoria)}
                      </span>
                    </div>
                    <p className="mt-s1 text-[15px] font-semibold">{alerta.titulo}</p>
                    <p className="text-[14px] text-tinta-2">{alerta.detalle}</p>
                  </div>
                </div>
                <Link href={alerta.link}>
                  <Button size="sm" variant="outline">
                    {alerta.accion}
                  </Button>
                </Link>
              </div>
            ))
          )}
        </div>
      </Panel>
    </div>
  );
}
