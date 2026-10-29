"use client";

import { BarChart3, Calculator, Gauge, Route, Truck } from "lucide-react";
import { formatCLP } from "@/lib/format";
import type {
  ComponenteFreightScoreNucleo,
  ResultadoRentabilidadNucleo,
} from "@/types/nucleo";
import {
  Panel,
  StatTile,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function tonoSemaforo(semaforo: string): Tono {
  if (semaforo === "verde") return "ok";
  if (semaforo === "amarillo") return "atencion";
  return "critico";
}

function etiquetaSemaforo(semaforo: string): string {
  if (semaforo === "verde") return "Verde · aceptar";
  if (semaforo === "amarillo") return "Amarillo · negociar";
  return "Rojo · rechazar o aprobar el dueño";
}

function BarraComponente({ componente }: { componente: ComponenteFreightScoreNucleo }) {
  const score = Math.min(1, Math.max(0, Number(componente.score)));
  const color = score >= 0.8 ? "bg-ok" : score >= 0.5 ? "bg-atencion" : "bg-critico";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2.5 w-28 overflow-hidden rounded-full bg-superficie-hundida">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score * 100}%` }} />
      </div>
      <span className="w-12 text-right text-[13px] tabular-nums">
        {(score * 100).toFixed(0)}
      </span>
    </div>
  );
}

export function ResultadoRentabilidad({
  resultado,
  titulo = "Resultado",
  descripcion,
  fuente,
  numeroViaje,
}: {
  resultado: ResultadoRentabilidadNucleo;
  titulo?: string;
  descripcion?: string;
  fuente?: string;
  numeroViaje?: string;
}) {
  return (
    <div className="space-y-s4">
      <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          etiqueta="Freight Score"
          valor={Number(resultado.score).toFixed(1)}
          detalle={etiquetaSemaforo(resultado.semaforo)}
          tono={tonoSemaforo(resultado.semaforo)}
          icono={Gauge}
          destacado
        />
        <StatTile
          etiqueta="Margen de contribución"
          valor={`${(Number(resultado.margen_pct) * 100).toFixed(1)}%`}
          detalle={formatCLP(resultado.margen)}
          tono={Number(resultado.margen) >= 0 ? "ok" : "critico"}
          icono={BarChart3}
        />
        <StatTile
          etiqueta="Tarifa piso estratégica"
          valor={formatCLP(resultado.tarifa_piso_estrategica)}
          detalle={`Costo total ${formatCLP(resultado.costo_total)}`}
          tono="info"
          icono={Calculator}
        />
        <StatTile
          etiqueta="Tarifa piso táctica"
          valor={formatCLP(resultado.tarifa_piso_tactica)}
          detalle={`Variable ${formatCLP(resultado.costo_variable)}`}
          tono="neutro"
          icono={Route}
        />
      </div>

      <div className="grid gap-s4 xl:grid-cols-[1.1fr_0.9fr]">
        <Panel
          titulo={titulo}
          descripcion={descripcion}
          acciones={
            <StatusBadge tono={tonoSemaforo(resultado.semaforo)}>
              {resultado.semaforo}
            </StatusBadge>
          }
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Componente</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Peso</TableHead>
                  <TableHead className="text-right">Aporte</TableHead>
                  <TableHead>Detalle</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resultado.componentes.map((componente) => (
                  <TableRow key={componente.codigo}>
                    <TableCell className="font-medium">{componente.nombre}</TableCell>
                    <TableCell>
                      <BarraComponente componente={componente} />
                    </TableCell>
                    <TableCell>{(Number(componente.peso) * 100).toFixed(0)}%</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Number(componente.aporte).toFixed(1)}
                    </TableCell>
                    <TableCell className="max-w-[260px] text-[13px] text-tinta-3">
                      {componente.detalle}
                    </TableCell>
                  </TableRow>
                ))}
                <TableRow className="bg-superficie-hundida/60 font-semibold">
                  <TableCell colSpan={3}>Total ponderado</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {Number(resultado.score).toFixed(1)}
                  </TableCell>
                  <TableCell>{etiquetaSemaforo(resultado.semaforo)}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </Panel>

        <Panel titulo="Explicación del cálculo" descripcion={fuente ? `Fuente de costos: ${fuente}` : undefined}>
          <div className="space-y-s3 p-s4 text-[14px]">
            {numeroViaje && (
              <p className="flex items-center gap-2 font-medium">
                <Truck className="size-4 text-marca" /> Viaje {numeroViaje}
              </p>
            )}
            <div className="grid grid-cols-2 gap-s3 rounded-xl border border-borde bg-superficie-hundida/40 p-s3">
              <p><span className="block text-[12px] text-tinta-3">Ingreso</span> {formatCLP(resultado.ingreso_total)}</p>
              <p><span className="block text-[12px] text-tinta-3">Costo variable</span> {formatCLP(resultado.costo_variable)}</p>
              <p><span className="block text-[12px] text-tinta-3">Costo fijo asignado</span> {formatCLP(resultado.costo_fijo_asignado)}</p>
              <p><span className="block text-[12px] text-tinta-3">Costo total</span> {formatCLP(resultado.costo_total)}</p>
              <p><span className="block text-[12px] text-tinta-3">Margen/km</span> {resultado.margen_km ? `${formatCLP(resultado.margen_km)}/km` : "—"}</p>
              <p><span className="block text-[12px] text-tinta-3">Km totales</span> {Number(resultado.km_totales).toLocaleString("es-CL")}</p>
            </div>
            <ul className="list-inside list-disc space-y-s1 text-tinta-2">
              {resultado.explicacion.map((linea) => (
                <li key={linea}>{linea}</li>
              ))}
            </ul>
            {!resultado.configurado && (
              <p className="rounded-lg bg-atencion-tenue p-s2 text-[13px] text-atencion">
                Configure los costos de la empresa para que el piso y el score usen
                los parámetros reales.
              </p>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
