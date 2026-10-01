"use client";

import { useEffect, useState } from "react";
import { Bell, Check, HandCoins, Percent, Wrench } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader, Panel } from "@/components/sistema";

const CLAVES: { clave: string; titulo: string; descripcion: string; sufijo: string; icono: LucideIcon; min: number; max: number }[] = [
  { clave: "iva_porcentaje", titulo: "Tasa de IVA", descripcion: "Se aplica a las facturas afectas.", sufijo: "%", icono: Percent, min: 0, max: 100 },
  { clave: "alerta_km_mantenimiento", titulo: "Aviso de mantención", descripcion: "Kilómetros antes del cambio para marcar un ítem como próximo.", sufijo: "km", icono: Wrench, min: 0, max: 100000 },
  { clave: "dias_alerta_vencimientos", titulo: "Aviso de vencimientos", descripcion: "Días de anticipación para revisión técnica, seguros y licencias.", sufijo: "días", icono: Bell, min: 0, max: 365 },
  { clave: "dias_alerta_cobranza", titulo: "Aviso de cobranza", descripcion: "Facturas que vencen dentro de este plazo se marcan como “por vencer”.", sufijo: "días", icono: HandCoins, min: 0, max: 90 },
];

export default function ConfiguracionPage() {
  const [valores, setValores] = useState<Record<string, string>>({});
  const [originales, setOriginales] = useState<Record<string, string>>({});
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    api
      .get<Record<string, string>>("/configuracion")
      .then((d) => {
        if (!activo) return;
        setValores(d ?? {});
        setOriginales(d ?? {});
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

  async function guardar(clave: string, min: number, max: number) {
    const v = Number(valores[clave]);
    if (valores[clave] === "" || Number.isNaN(v) || v < min || v > max) {
      toast.error(`Ingrese un valor entre ${min} y ${max}`);
      return;
    }
    setGuardando(clave);
    try {
      await api.put(`/configuracion/${clave}?valor=${encodeURIComponent(String(v))}`, {});
      setOriginales((o) => ({ ...o, [clave]: String(v) }));
      toast.success("Configuración guardada");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setGuardando(null);
    }
  }

  return (
    <div className="space-y-s5">
      <PageHeader rotulo="Sistema" titulo="Configuración" descripcion="Parámetros que usan los cálculos y alertas del sistema." />
      <Panel>
        <ul className="divide-y divide-borde">
          {CLAVES.map((c) => {
            const cambiado = valores[c.clave] !== originales[c.clave];
            return (
              <li key={c.clave} className="flex flex-wrap items-center gap-s4 px-s4 py-s4">
                <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-marca-tenue text-marca">
                  <c.icono className="size-5" />
                </span>
                <div className="min-w-[220px] flex-1">
                  <label htmlFor={`cfg-${c.clave}`} className="text-[17px] font-semibold">
                    {c.titulo}
                  </label>
                  <p className="text-[15px] text-tinta-3">{c.descripcion}</p>
                </div>
                <div className="flex items-center gap-s2">
                  {cargando ? (
                    <Skeleton className="h-11 w-40" />
                  ) : (
                    <div className="relative">
                      <Input
                        id={`cfg-${c.clave}`}
                        type="number"
                        min={c.min}
                        max={c.max}
                        value={valores[c.clave] ?? ""}
                        onChange={(e) => setValores({ ...valores, [c.clave]: e.target.value })}
                        onKeyDown={(e) => e.key === "Enter" && guardar(c.clave, c.min, c.max)}
                        className="cifra w-40 pr-14 text-right text-[17px]"
                      />
                      <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[14px] text-tinta-3">{c.sufijo}</span>
                    </div>
                  )}
                  <Button onClick={() => guardar(c.clave, c.min, c.max)} disabled={!cambiado || guardando === c.clave} variant={cambiado ? "default" : "outline"}>
                    {guardando === c.clave ? "Guardando…" : cambiado ? "Guardar" : <><Check /> Guardado</>}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </Panel>
    </div>
  );
}
