"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarClock,
  CircleCheck,
  FileWarning,
  Gauge,
  Plus,
  Truck,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { formatCLP, formatFecha } from "@/lib/format";
import { useAuth } from "@/context/auth-context";
import type { AlertasDashboard, KpiValor, ResumenDashboard } from "@/types";
import { ESTADO_VIAJE_LABEL, ESTADO_VIAJE_TONO, TONO_KPI, formatValorKpi } from "@/types";
import { buttonVariants } from "@/components/ui/button";
import {
  EstadoVacio,
  PageHeader,
  Panel,
  Patente,
  StatTile,
  StatTileSkeleton,
  StatusBadge,
} from "@/components/sistema";
import { Skeleton } from "@/components/ui/skeleton";

function saludo() {
  const h = new Date().getHours();
  if (h < 12) return "Buenos días";
  if (h < 20) return "Buenas tardes";
  return "Buenas noches";
}

export default function DashboardPage() {
  const { usuario } = useAuth();
  const [resumen, setResumen] = useState<ResumenDashboard | null>(null);
  const [alertas, setAlertas] = useState<AlertasDashboard | null>(null);
  const [kpis, setKpis] = useState<KpiValor[]>([]);
  const [cargando, setCargando] = useState(true);
  const [hola, setHola] = useState("Hola");

  useEffect(() => {
    let activo = true;
    const t = setTimeout(() => setHola(saludo()), 0);
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
        if (activo) toast.error(e instanceof Error ? e.message : "Error al cargar el panel");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
      clearTimeout(t);
    };
  }, []);

  const vencimientos = alertas?.vencimientos ?? [];
  const facturasVencidas = alertas?.facturas_vencidas ?? [];
  const totalAlertas = vencimientos.length + facturasVencidas.length;
  const viajesActivos = resumen?.viajes_activos ?? [];
  const puedeCrear = usuario?.rol === "admin" || usuario?.rol === "operacion";
  const primerNombre = usuario?.nombre?.split(/[\s.]/)[0] ?? "";

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Resumen del negocio"
        titulo={
          <>
            {hola}
            {primerNombre && <span className="capitalize">, {primerNombre}</span>}
          </>
        }
        descripcion={
          cargando ? (
            "Cargando la situación del día…"
          ) : (
            <>
              Hay <strong className="font-semibold text-tinta">{formatCLP(resumen?.cuentas_por_cobrar)}</strong> por
              cobrar
              {Number(resumen?.cuentas_atrasadas ?? 0) > 0 && (
                <>
                  , de los cuales{" "}
                  <strong className="font-semibold text-critico">{formatCLP(resumen?.cuentas_atrasadas)}</strong> están
                  vencidos
                </>
              )}
              . {viajesActivos.length} {viajesActivos.length === 1 ? "viaje activo" : "viajes activos"} y{" "}
              {totalAlertas} {totalAlertas === 1 ? "alerta pendiente" : "alertas pendientes"}.
            </>
          )
        }
        acciones={
          puedeCrear && (
            <Link href="/viajes?nuevo=1" className={buttonVariants({ size: "lg" })}>
              <Plus /> Nuevo viaje
            </Link>
          )
        }
      />

      {/* Indicadores */}
      <section aria-label="Indicadores" className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-[repeat(auto-fit,minmax(240px,1fr))]">
        {cargando ? (
          Array.from({ length: 4 }).map((_, i) => <StatTileSkeleton key={i} />)
        ) : kpis.length === 0 ? (
          <div className="rounded-xl border border-dashed border-borde-fuerte bg-superficie sm:col-span-2 xl:col-span-4">
            <EstadoVacio
              icono={Gauge}
              titulo="Sin indicadores configurados"
              descripcion="Un administrador puede crearlos en Sistema → Indicadores."
            />
          </div>
        ) : (
          kpis.map((k, i) => (
            <StatTile
              key={k.id}
              etiqueta={k.nombre}
              valor={k.error ? "—" : formatValorKpi(k.valor, k.formato)}
              detalle={k.error ? "Revise la fórmula del indicador" : (k.descripcion ?? undefined)}
              tono={k.error ? "critico" : (TONO_KPI[k.color] ?? "neutro")}
              destacado={i === 0 && !k.error}
            />
          ))
        )}
      </section>

      <div className="grid gap-s4 xl:grid-cols-[1.35fr_1fr]">
        {/* Viajes activos */}
        <Panel
          titulo="Viajes activos"
          descripcion="Programados y en ruta"
          acciones={
            <Link
              href="/viajes"
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[14px] font-medium text-marca transition-colors hover:bg-marca-tenue"
            >
              Ver todos <ArrowRight className="size-4" />
            </Link>
          }
        >
          {cargando ? (
            <div className="space-y-s3 p-s4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : viajesActivos.length === 0 ? (
            <EstadoVacio icono={Truck} titulo="No hay camiones en ruta" descripcion="Los viajes programados o en ruta aparecerán aquí." />
          ) : (
            <ul className="divide-y divide-borde">
              {viajesActivos.map((v) => (
                <li key={v.id}>
                  <Link
                    href={`/viajes/${v.id}`}
                    className="group flex items-center gap-s3 px-s4 py-s3 transition-colors hover:bg-marca-tenue/45"
                  >
                    <Patente>{v.tracto_patente}</Patente>
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-1.5 truncate text-[16px] font-medium text-tinta">
                        {v.origen}
                        <ArrowRight className="size-3.5 shrink-0 text-tinta-3" />
                        {v.destino}
                      </p>
                      <p className="truncate text-[14px] text-tinta-3">
                        {v.chofer_nombre} · {v.cliente_nombre} · {formatFecha(v.fecha_inicio)}
                      </p>
                    </div>
                    <StatusBadge tono={ESTADO_VIAJE_TONO[v.estado]}>{ESTADO_VIAJE_LABEL[v.estado]}</StatusBadge>
                    <ArrowUpRight className="hidden size-4 text-tinta-3 opacity-0 transition-[opacity,transform] group-hover:translate-x-0.5 group-hover:opacity-100 sm:block" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* Alertas */}
        <Panel
          titulo="Requiere atención"
          descripcion={cargando ? undefined : totalAlertas === 0 ? "Todo al día" : `${totalAlertas} pendientes`}
        >
          {cargando ? (
            <div className="space-y-s3 p-s4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : totalAlertas === 0 ? (
            <EstadoVacio icono={CircleCheck} titulo="Sin pendientes" descripcion="No hay documentos por vencer ni facturas atrasadas." />
          ) : (
            <ul className="divide-y divide-borde">
              {facturasVencidas.map((f) => (
                <li key={f.id} className="flex items-center gap-s3 px-s4 py-s3">
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-critico-tenue text-critico">
                    <FileWarning className="size-[18px]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[15.5px] font-medium">
                      Factura {f.numero_sii} · {f.cliente}
                    </p>
                    <p className="text-[14px] text-tinta-3">
                      {formatCLP(f.total)} · {f.dias_atraso} días de atraso
                    </p>
                  </div>
                  <Link href="/cobranzas" className={buttonVariants({ variant: "outline", size: "xs" })}>
                    Cobrar
                  </Link>
                </li>
              ))}
              {vencimientos.map((v, i) => {
                const vencido = v.dias_restantes < 0;
                return (
                  <li key={`v-${i}`} className="flex items-center gap-s3 px-s4 py-s3">
                    <span
                      className={`grid size-9 shrink-0 place-items-center rounded-lg ${
                        vencido ? "bg-critico-tenue text-critico" : "bg-atencion-tenue text-atencion"
                      }`}
                    >
                      <CalendarClock className="size-[18px]" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[15.5px] font-medium">
                        {v.equipo} · {v.concepto}
                      </p>
                      <p className="text-[14px] text-tinta-3">
                        {formatFecha(v.fecha)} ·{" "}
                        {vencido ? `vencido hace ${Math.abs(v.dias_restantes)} días` : `vence en ${v.dias_restantes} días`}
                      </p>
                    </div>
                    <StatusBadge tono={vencido ? "critico" : "atencion"}>{vencido ? "Vencido" : "Próximo"}</StatusBadge>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
