"use client";

import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CLAVES = [
  {
    clave: "iva_porcentaje",
    titulo: "Porcentaje de IVA",
    descripcion: "Tasa aplicada a facturas afectas (ej: 19)",
  },
  {
    clave: "alerta_km_mantenimiento",
    titulo: "Alerta de mantención (km)",
    descripcion: "Cuántos km antes del cambio se avisa (ej: 5000)",
  },
  {
    clave: "dias_alerta_vencimientos",
    titulo: "Alerta de vencimientos (días)",
    descripcion: "Anticipación para rev. técnica, seguros y licencias (ej: 30)",
  },
  {
    clave: "dias_alerta_cobranza",
    titulo: "Alerta de cobranza (días)",
    descripcion: "Facturas por vencer en N días se muestran en amarillo (ej: 5)",
  },
];

export default function ConfiguracionPage() {
  const [valores, setValores] = useState<Record<string, string>>({});
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    let activo = true;
    api
      .get<Record<string, string>>("/configuracion")
      .then((d) => {
        if (activo) setValores(d ?? {});
      })
      .catch((e) => {
        if (activo) toast.error(e instanceof Error ? e.message : "Error al cargar");
      });
    return () => {
      activo = false;
    };
  }, []);

  async function guardar(clave: string) {
    setGuardando(true);
    try {
      await api.put(`/configuracion/${clave}?valor=${encodeURIComponent(valores[clave] ?? "")}`, {});
      toast.success("Configuración guardada");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-[#2A237A]">Configuración del Sistema</h1>
      <div className="grid gap-4 md:grid-cols-2">
        {CLAVES.map((c) => (
          <Card key={c.clave}>
            <CardHeader>
              <CardTitle className="text-lg">{c.titulo}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-gray-500">{c.descripcion}</p>
              <div className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  <Label className="text-sm">Valor</Label>
                  <Input
                    type="number"
                    value={valores[c.clave] ?? ""}
                    onChange={(e) => setValores({ ...valores, [c.clave]: e.target.value })}
                    className="text-base"
                  />
                </div>
                <Button
                  onClick={() => guardar(c.clave)}
                  disabled={guardando}
                  className="bg-[#2A237A] hover:bg-[#2A237A]/90"
                >
                  <Save className="h-4 w-4" />
                  Guardar
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
