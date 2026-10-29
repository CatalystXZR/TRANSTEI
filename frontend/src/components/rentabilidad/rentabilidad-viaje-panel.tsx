"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { nucleo } from "@/lib/nucleo";
import type { RentabilidadViajeNucleo } from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Aviso } from "@/components/sistema";
import { ResultadoRentabilidad } from "@/components/rentabilidad/resultado";

export function RentabilidadViajePanel({
  empresaId,
  viajeId,
}: {
  empresaId: string;
  viajeId: string;
}) {
  const [data, setData] = useState<RentabilidadViajeNucleo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    if (!empresaId) return;
    setCargando(true);
    setError(null);
    try {
      const resultado = await nucleo.get<RentabilidadViajeNucleo>(
        `/nucleo/expediente/viajes/${viajeId}/rentabilidad`,
        empresaId,
      );
      setData(resultado);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo calcular la rentabilidad");
    } finally {
      setCargando(false);
    }
  }, [empresaId, viajeId]);

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  if (cargando && !data) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-borde bg-superficie p-s4 text-tinta-3">
        <Loader2 className="animate-spin" /> Calculando margen y Freight Score…
      </div>
    );
  }

  return (
    <div className="space-y-s4">
      {error && (
        <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>
      )}
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => void cargar()} disabled={cargando}>
          <RefreshCw className={cargando ? "animate-spin" : undefined} /> Recalcular
        </Button>
      </div>
      {data && (
        <ResultadoRentabilidad
          resultado={data}
          titulo={`Viaje ${data.numero_viaje}`}
          descripcion={`${data.cliente_nombre} · fuente de costos: ${data.fuente_costos}`}
          fuente={data.fuente_costos}
          numeroViaje={data.numero_viaje}
        />
      )}
    </div>
  );
}
