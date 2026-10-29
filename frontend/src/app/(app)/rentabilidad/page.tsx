"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Calculator, RefreshCw, Save, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import type {
  ConfiguracionCostosNucleo,
  EmpresaNucleo,
  ResultadoRentabilidadNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Aviso,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/sistema";
import { Campo, SelectSimple } from "@/components/formulario";
import { ResultadoRentabilidad } from "@/components/rentabilidad/resultado";

const RETORNOS = [
  { valor: "cargado_completo", etiqueta: "Retorno cargado completo" },
  { valor: "parcial", etiqueta: "Retorno parcial" },
  { valor: "vacio_cercano", etiqueta: "Vacío, hay carga cercana" },
  { valor: "vacio_sin_alternativa", etiqueta: "Vacío sin alternativa" },
  { valor: "no_aplica", etiqueta: "No aplica" },
];

type ConfigForm = {
  costo_fijo_mensual: string;
  viajes_estimados_mes: string;
  margen_objetivo: string;
  benchmark_margen_km: string;
  contribucion_minima: string;
  costo_variable_km_estandar: string;
  rendimiento_km_l: string;
  precio_diesel: string;
};

function configForm(config: ConfiguracionCostosNucleo | null): ConfigForm {
  return {
    costo_fijo_mensual: config?.costo_fijo_mensual ?? "0",
    viajes_estimados_mes: String(config?.viajes_estimados_mes ?? 60),
    margen_objetivo: String(Number(config?.margen_objetivo ?? 0.25) * 100),
    benchmark_margen_km: config?.benchmark_margen_km ?? "1200",
    contribucion_minima: config?.contribucion_minima ?? "100000",
    costo_variable_km_estandar: config?.costo_variable_km_estandar ?? "900",
    rendimiento_km_l: config?.rendimiento_km_l ?? "2.5",
    precio_diesel: config?.precio_diesel ?? "1000",
  };
}

export default function RentabilidadPage() {
  const [empresaId, setEmpresaId] = useState("");
  const [empresa, setEmpresa] = useState<EmpresaNucleo | null>(null);
  const [config, setConfig] = useState<ConfiguracionCostosNucleo | null>(null);
  const [form, setForm] = useState<ConfigForm>(configForm(null));
  const [sim, setSim] = useState({
    distancia_km: "500",
    km_vacios: "0",
    peso_kg: "25000",
    capacidad_kg: "28000",
    flete_neto: "1200000",
    costos_variables: "",
    dias_pago: "45",
    retorno: "cargado_completo",
    riesgo_puntos: "1",
  });
  const [resultado, setResultado] = useState<ResultadoRentabilidadNucleo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [simulando, setSimulando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    getEmpresas()
      .then((empresas) => {
        if (!activo) return;
        if (empresas[0]) {
          setEmpresa(empresas[0]);
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

  const cargar = useCallback(async () => {
    if (!empresaId) return;
    setCargando(true);
    setError(null);
    try {
      const data = await nucleo.get<ConfiguracionCostosNucleo>(
        "/nucleo/rentabilidad/configuracion",
        empresaId,
      );
      setConfig(data);
      setForm(configForm(data));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la configuración");
    } finally {
      setCargando(false);
    }
  }, [empresaId]);

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  function setConfigField(campo: keyof ConfigForm, valor: string) {
    setForm((f) => ({ ...f, [campo]: valor }));
  }

  function setSimField(campo: keyof typeof sim, valor: string) {
    setSim((s) => ({ ...s, [campo]: valor }));
  }

  async function guardarConfig() {
    setGuardando(true);
    setError(null);
    try {
      const data = await nucleo.put<ConfiguracionCostosNucleo>(
        "/nucleo/rentabilidad/configuracion",
        empresaId,
        {
          costo_fijo_mensual: Number(form.costo_fijo_mensual || 0),
          viajes_estimados_mes: Number(form.viajes_estimados_mes || 1),
          margen_objetivo: Number(form.margen_objetivo || 0) / 100,
          benchmark_margen_km: Number(form.benchmark_margen_km || 1),
          contribucion_minima: Number(form.contribucion_minima || 0),
          costo_variable_km_estandar: Number(form.costo_variable_km_estandar || 0),
          rendimiento_km_l: Number(form.rendimiento_km_l || 1),
          precio_diesel: Number(form.precio_diesel || 0),
          version: config?.configurado ? config.version : undefined,
        },
      );
      setConfig(data);
      setForm(configForm(data));
      toast.success("Configuración de costos guardada");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar la configuración");
    } finally {
      setGuardando(false);
    }
  }

  async function simular() {
    setSimulando(true);
    setError(null);
    try {
      const data = await nucleo.post<ResultadoRentabilidadNucleo>(
        "/nucleo/rentabilidad/simulador",
        empresaId,
        {
          distancia_km: Number(sim.distancia_km || 0),
          km_vacios: Number(sim.km_vacios || 0),
          peso_kg: Number(sim.peso_kg || 0),
          capacidad_kg: Number(sim.capacidad_kg || 0),
          flete_neto: Number(sim.flete_neto || 0),
          costos_variables: sim.costos_variables
            ? Number(sim.costos_variables)
            : null,
          dias_pago: Number(sim.dias_pago || 0),
          retorno: sim.retorno,
          riesgo_puntos: Number(sim.riesgo_puntos || 0),
        },
      );
      setResultado(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo simular el flete");
    } finally {
      setSimulando(false);
    }
  }

  const puedeConfigurar = ["admin", "gerente"].includes(empresa?.rol ?? "");

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Rentabilidad"
        titulo="Margen, tarifa piso y Freight Score"
        descripcion="Decida si un flete conviene: costo total, piso estratégico/táctico, seis componentes del Freight Score y semáforo."
        acciones={
          <Button variant="outline" onClick={() => void cargar()} disabled={!empresaId || cargando}>
            <RefreshCw className={cargando ? "animate-spin" : undefined} /> Actualizar
          </Button>
        }
      />

      {error && (
        <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>
      )}

      <div className="grid gap-s4 xl:grid-cols-[0.95fr_1.05fr]">
        <Panel
          titulo="Parámetros de costo de la empresa"
          descripcion={
            config?.configurado
              ? "Estos valores alimentan el piso y el score."
              : "Sin configuración guardada; se usan valores por defecto."
          }
          acciones={
            <StatusBadge tono={config?.configurado ? "ok" : "atencion"}>
              {config?.configurado ? `v${config.version}` : "Default"}
            </StatusBadge>
          }
        >
          <div className="grid gap-s3 p-s4 sm:grid-cols-2">
            <Campo etiqueta="Costo fijo mensual" ayuda="Arriendo, seguros, sueldos base…">
              <Input
                type="number"
                min={0}
                value={form.costo_fijo_mensual}
                onChange={(e) => setConfigField("costo_fijo_mensual", e.target.value)}
                disabled={!puedeConfigurar}
              />
            </Campo>
            <Campo etiqueta="Viajes estimados/mes">
              <Input
                type="number"
                min={1}
                value={form.viajes_estimados_mes}
                onChange={(e) => setConfigField("viajes_estimados_mes", e.target.value)}
                disabled={!puedeConfigurar}
              />
            </Campo>
            <Campo etiqueta="Margen objetivo (%)">
              <Input
                type="number"
                min={0}
                max={95}
                step="0.1"
                value={form.margen_objetivo}
                onChange={(e) => setConfigField("margen_objetivo", e.target.value)}
                disabled={!puedeConfigurar}
              />
            </Campo>
            <Campo etiqueta="Benchmark margen/km">
              <Input
                type="number"
                min={1}
                value={form.benchmark_margen_km}
                onChange={(e) => setConfigField("benchmark_margen_km", e.target.value)}
                disabled={!puedeConfigurar}
              />
            </Campo>
            <Campo etiqueta="Contribución mínima $" ayuda="Para tarifa piso táctica">
              <Input
                type="number"
                min={0}
                value={form.contribucion_minima}
                onChange={(e) => setConfigField("contribucion_minima", e.target.value)}
                disabled={!puedeConfigurar}
              />
            </Campo>
            <Campo etiqueta="Costo variable/km estándar">
              <Input
                type="number"
                min={0}
                value={form.costo_variable_km_estandar}
                onChange={(e) =>
                  setConfigField("costo_variable_km_estandar", e.target.value)
                }
                disabled={!puedeConfigurar}
              />
            </Campo>
            <Campo etiqueta="Rendimiento km/L">
              <Input
                type="number"
                min={0.1}
                step="0.001"
                value={form.rendimiento_km_l}
                onChange={(e) => setConfigField("rendimiento_km_l", e.target.value)}
                disabled={!puedeConfigurar}
              />
            </Campo>
            <Campo etiqueta="Precio diésel referencia">
              <Input
                type="number"
                min={0}
                step="0.0001"
                value={form.precio_diesel}
                onChange={(e) => setConfigField("precio_diesel", e.target.value)}
                disabled={!puedeConfigurar}
              />
            </Campo>
          </div>
          {puedeConfigurar ? (
            <div className="flex justify-end border-t border-borde p-s4">
              <Button onClick={() => void guardarConfig()} disabled={guardando}>
                <Save /> {guardando ? "Guardando…" : "Guardar parámetros"}
              </Button>
            </div>
          ) : (
            <p className="border-t border-borde p-s4 text-[13px] text-tinta-3">
              Solo administración o gerencia puede modificar los parámetros.
            </p>
          )}
        </Panel>

        <Panel
          titulo="Simulador de flete"
          descripcion="Pruebe un flete antes de aceptarlo. No escribe en la base."
          acciones={
            <Button onClick={() => void simular()} disabled={simulando}>
              <Sparkles /> {simulando ? "Calculando…" : "Simular"}
            </Button>
          }
        >
          <div className="grid gap-s3 p-s4 sm:grid-cols-2">
            <Campo etiqueta="Distancia cargada (km)" requerido>
              <Input type="number" min={1} value={sim.distancia_km} onChange={(e) => setSimField("distancia_km", e.target.value)} />
            </Campo>
            <Campo etiqueta="Km vacíos">
              <Input type="number" min={0} value={sim.km_vacios} onChange={(e) => setSimField("km_vacios", e.target.value)} />
            </Campo>
            <Campo etiqueta="Peso (kg)">
              <Input type="number" min={0} value={sim.peso_kg} onChange={(e) => setSimField("peso_kg", e.target.value)} />
            </Campo>
            <Campo etiqueta="Capacidad (kg)">
              <Input type="number" min={0} value={sim.capacidad_kg} onChange={(e) => setSimField("capacidad_kg", e.target.value)} />
            </Campo>
            <Campo etiqueta="Flete neto" requerido>
              <Input type="number" min={1} value={sim.flete_neto} onChange={(e) => setSimField("flete_neto", e.target.value)} />
            </Campo>
            <Campo etiqueta="Costos variables" ayuda="Vacío = usar costo/km estándar">
              <Input type="number" min={0} value={sim.costos_variables} onChange={(e) => setSimField("costos_variables", e.target.value)} />
            </Campo>
            <Campo etiqueta="Días de pago">
              <Input type="number" min={0} max={365} value={sim.dias_pago} onChange={(e) => setSimField("dias_pago", e.target.value)} />
            </Campo>
            <Campo etiqueta="Retorno / backhaul">
              <SelectSimple
                valor={sim.retorno}
                onCambio={(v) => setSimField("retorno", v)}
                opciones={RETORNOS}
              />
            </Campo>
            <Campo etiqueta="Puntos de riesgo (0–10)" ayuda="Peligrosa +3, sobredimensión +2, refrigerada +1">
              <Input type="number" min={0} max={10} value={sim.riesgo_puntos} onChange={(e) => setSimField("riesgo_puntos", e.target.value)} />
            </Campo>
            <div className="flex items-end">
              <Button className="w-full" onClick={() => void simular()} disabled={simulando}>
                <Calculator /> Calcular flete
              </Button>
            </div>
          </div>
        </Panel>
      </div>

      {resultado && (
        <ResultadoRentabilidad
          resultado={resultado}
          titulo="Simulación de flete"
          descripcion="Resultado calculado con los parámetros vigentes."
        />
      )}
    </div>
  );
}
