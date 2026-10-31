"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bell,
  Check,
  HandCoins,
  Info,
  Percent,
  RefreshCw,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { nucleo } from "@/lib/nucleo";
import { useNucleoEmpresa } from "@/lib/use-nucleo-empresa";
import { formatFechaHora } from "@/lib/format";
import type {
  ConfiguracionItemNucleo,
  ConfiguracionNucleo,
  ConfiguracionUpdateNucleo,
  JsonNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Aviso, PageHeader, Panel } from "@/components/sistema";
import { ErrorNucleo } from "@/components/nucleo/estado-error";

interface ClaveCatalogo {
  clave: string;
  titulo: string;
  descripcion: string;
  sufijo: string;
  icono: LucideIcon;
  tipo: "numero" | "entero";
  min: number;
  max?: number;
}

const CATALOGO: ClaveCatalogo[] = [
  {
    clave: "iva_porcentaje",
    titulo: "Tasa de IVA",
    descripcion: "Se aplica a las facturas afectas y al resumen de IVA débito.",
    sufijo: "%",
    icono: Percent,
    tipo: "numero",
    min: 0,
    max: 100,
  },
  {
    clave: "alerta_km_mantenimiento",
    titulo: "Aviso de mantención",
    descripcion:
      "Kilómetros antes del próximo cambio para marcar un ítem como próximo a vencer.",
    sufijo: "km",
    icono: Wrench,
    tipo: "entero",
    min: 0,
  },
  {
    clave: "dias_alerta_vencimientos",
    titulo: "Aviso de vencimientos",
    descripcion:
      "Días de anticipación para revisión técnica, seguros y licencias.",
    sufijo: "días",
    icono: Bell,
    tipo: "entero",
    min: 0,
  },
  {
    clave: "dias_alerta_cobranza",
    titulo: "Aviso de cobranza",
    descripcion:
      "Facturas que vencen dentro de este plazo se marcan como “por vencer”.",
    sufijo: "días",
    icono: HandCoins,
    tipo: "entero",
    min: 0,
  },
];

function valorTexto(valor: JsonNucleo | undefined): string {
  if (valor === undefined || valor === null) return "";
  if (typeof valor === "string") return valor;
  if (typeof valor === "number" || typeof valor === "boolean") return String(valor);
  return JSON.stringify(valor);
}

function mensajeDeError(error: unknown) {
  return error instanceof Error ? error.message : "Ocurrió un error inesperado.";
}

function tipoDeValor(valor: JsonNucleo | undefined): "numero" | "texto" {
  return typeof valor === "number" ? "numero" : "texto";
}

export default function ConfiguracionPage() {
  const {
    empresa,
    empresaId,
    permisos,
    cargando: cargandoSesion,
    error: errorSesion,
  } = useNucleoEmpresa();

  const puedeEscribir = permisos.includes("configuracion:escribir");

  const [items, setItems] = useState<ConfiguracionItemNucleo[]>([]);
  const [valores, setValores] = useState<Record<string, string>>({});
  const [originales, setOriginales] = useState<Record<string, string>>({});
  const [erroresCampo, setErroresCampo] = useState<Record<string, string | null>>({});
  const [mensajeServidor, setMensajeServidor] = useState("");
  const [cargandoConfig, setCargandoConfig] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [guardando, setGuardando] = useState<string | null>(null);
  const [errorCarga, setErrorCarga] = useState<unknown>(null);

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!empresaId) return;
      if (silencioso) setActualizando(true);
      else setCargandoConfig(true);
      setErrorCarga(null);
      try {
        const data = await nucleo.get<ConfiguracionNucleo>(
          "/nucleo/configuracion",
          empresaId,
        );
        setItems(data.items);
        setMensajeServidor(data.mensaje);
        const porClave = new Map(data.items.map((item) => [item.clave, item]));
        const siguientes: Record<string, string> = {};
        for (const clave of CATALOGO) {
          siguientes[clave.clave] = valorTexto(porClave.get(clave.clave)?.valor);
        }
        for (const item of data.items) {
          if (!(item.clave in siguientes)) {
            siguientes[item.clave] = valorTexto(item.valor);
          }
        }
        setValores(siguientes);
        setOriginales(siguientes);
      } catch (e) {
        setErrorCarga(e);
      } finally {
        setCargandoConfig(false);
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

  const cargando = cargandoSesion || cargandoConfig;
  const bloqueado = Boolean(errorSesion || errorCarga);

  const itemPorClave = useMemo(
    () => new Map(items.map((item) => [item.clave, item])),
    [items],
  );

  const filas = useMemo(() => {
    const conocidas = new Set(CATALOGO.map((c) => c.clave));
    const extras = items
      .filter((item) => !conocidas.has(item.clave))
      .map((item) => ({
        clave: item.clave,
        titulo: item.clave,
        descripcion: "Clave entregada por el servidor fuera del catálogo conocido.",
        sufijo: "",
        icono: Info,
        tipo: tipoDeValor(item.valor),
        min: 0,
        max: undefined,
      }));
    return [...CATALOGO, ...extras];
  }, [items]);

  async function guardar(clave: string, tipo: "numero" | "entero" | "texto", min: number, max?: number) {
    setErroresCampo((prev) => ({ ...prev, [clave]: null }));
    const texto = (valores[clave] ?? "").trim();
    if (!texto) {
      setErroresCampo((prev) => ({
        ...prev,
        [clave]: "Ingrese un valor.",
      }));
      return;
    }

    let valor: JsonNucleo;
    if (tipo === "texto") {
      valor = texto;
    } else {
      const numero = Number(texto.replace(",", "."));
      if (!Number.isFinite(numero)) {
        setErroresCampo((prev) => ({
          ...prev,
          [clave]: "Ingrese un número válido.",
        }));
        return;
      }
      if (tipo === "entero" && !Number.isInteger(numero)) {
        setErroresCampo((prev) => ({
          ...prev,
          [clave]: "Ingrese un número entero.",
        }));
        return;
      }
      if (numero < min || (max !== undefined && numero > max)) {
        setErroresCampo((prev) => ({
          ...prev,
          [clave]:
            max === undefined
              ? `Ingrese un valor mayor o igual a ${min}.`
              : `Ingrese un valor entre ${min} y ${max}.`,
        }));
        return;
      }
      valor = numero;
    }

    setGuardando(clave);
    try {
      const body: ConfiguracionUpdateNucleo = { valor };
      const actualizado = await nucleo.put<ConfiguracionItemNucleo>(
        `/nucleo/configuracion/${clave}`,
        empresaId,
        body,
      );
      setItems((prev) =>
        prev.some((item) => item.clave === clave)
          ? prev.map((item) => (item.clave === clave ? actualizado : item))
          : [...prev, actualizado],
      );
      const textoActualizado = valorTexto(actualizado.valor);
      setValores((prev) => ({ ...prev, [clave]: textoActualizado }));
      setOriginales((prev) => ({ ...prev, [clave]: textoActualizado }));
      toast.success("Configuración guardada");
    } catch (e) {
      const mensaje = mensajeDeError(e);
      setErroresCampo((prev) => ({ ...prev, [clave]: mensaje }));
      toast.error(mensaje);
    } finally {
      setGuardando(null);
    }
  }

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Sistema"
        titulo="Configuración por empresa"
        descripcion="Parámetros vigentes que usan los cálculos y alertas del núcleo. Cada cambio cierra la vigencia anterior y queda en historial append-only."
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

      <ErrorNucleo error={errorSesion ?? errorCarga} />

      {!bloqueado && (
        <>
      {empresa && (
        <p className="text-[14px] text-tinta-3">
          Empresa: <span className="font-medium text-tinta-2">{empresa.razon_social}</span>{" "}
          · Rol: <span className="font-medium text-tinta-2">{empresa.rol}</span>
        </p>
      )}

      {!puedeEscribir && !cargando && (
        <Aviso tono="neutro" icono={Info}>
          Su rol puede consultar la configuración, pero no modificarla. El servidor
          volverá a verificar el permiso <code>configuracion:escribir</code>.
        </Aviso>
      )}

      <Panel
        titulo="Valores vigentes"
        descripcion={
          mensajeServidor ||
          "Sólo se muestran las filas con vigencia abierta (vigente_hasta nulo)."
        }
      >
        <ul className="divide-y divide-borde">
          {filas.map((fila) => {
            const item = itemPorClave.get(fila.clave);
            const valor = valores[fila.clave] ?? "";
            const original = originales[fila.clave] ?? "";
            const cambiado = valor !== original;
            const error = erroresCampo[fila.clave];
            const Icono = fila.icono;
            const idCampo = `cfg-${fila.clave}`;
            const idError = `${idCampo}-error`;
            return (
              <li
                key={fila.clave}
                className="flex flex-wrap items-start gap-s4 px-s4 py-s4"
              >
                <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-marca-tenue text-marca">
                  <Icono className="size-5" aria-hidden="true" />
                </span>
                <div className="min-w-[240px] flex-1">
                  <label htmlFor={idCampo} className="text-[17px] font-semibold">
                    {fila.titulo}
                  </label>
                  <p className="text-[15px] text-tinta-3">{fila.descripcion}</p>
                  <p className="mt-s1 text-[13px] text-tinta-3">
                    {item
                      ? `Vigente desde ${formatFechaHora(item.vigente_desde)} · actualizado ${formatFechaHora(item.updated_at)} · versión ${item.version}`
                      : "Sin valor vigente para esta empresa; el servidor validará el catálogo al guardar."}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-s2">
                  <div className="flex items-center gap-s2">
                    {cargando ? (
                      <Skeleton className="h-11 w-40" />
                    ) : (
                      <div className="relative">
                        <Input
                          id={idCampo}
                          type={fila.tipo === "texto" ? "text" : "number"}
                          min={fila.tipo === "texto" ? undefined : fila.min}
                          max={fila.tipo === "texto" ? undefined : fila.max}
                          step={fila.tipo === "entero" ? 1 : "any"}
                          value={valor}
                          disabled={!puedeEscribir}
                          aria-invalid={!!error}
                          aria-describedby={error ? idError : undefined}
                          onChange={(e) =>
                            setValores({ ...valores, [fila.clave]: e.target.value })
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && puedeEscribir) {
                              void guardar(
                                fila.clave,
                                fila.tipo,
                                fila.min,
                                fila.max,
                              );
                            }
                          }}
                          className="cifra w-40 pr-14 text-right text-[17px]"
                        />
                        {fila.sufijo && (
                          <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[14px] text-tinta-3">
                            {fila.sufijo}
                          </span>
                        )}
                      </div>
                    )}
                    <Button
                      onClick={() =>
                        void guardar(fila.clave, fila.tipo, fila.min, fila.max)
                      }
                      disabled={
                        !puedeEscribir ||
                        !cambiado ||
                        guardando === fila.clave ||
                        cargando
                      }
                      variant={cambiado ? "default" : "outline"}
                    >
                      {guardando === fila.clave ? (
                        "Guardando…"
                      ) : cambiado ? (
                        "Guardar"
                      ) : (
                        <>
                          <Check /> Guardado
                        </>
                      )}
                    </Button>
                  </div>
                  {error && (
                    <p id={idError} className="max-w-[360px] text-[14px] text-critico" role="alert">
                      {error}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </Panel>

      <Panel
        titulo="Historial de cambios"
        descripcion="La base conserva todas las versiones; esta pantalla sólo muestra la vigente."
      >
        <div className="space-y-s3 p-s4">
          <Aviso tono="neutro" icono={Info}>
            Un cambio de valor no edita la fila anterior: la cierra con{" "}
            <code>vigente_hasta</code> y crea una versión nueva. No hay un endpoint de
            historial en esta ola; consulte <code>nucleo.configuracion_empresa</code> o la
            auditoría del núcleo.
          </Aviso>
          <p className="text-[14px] text-tinta-3">
            El servidor valida el catálogo y el rango. <code>iva_porcentaje</code> se
            valida también en el cliente entre 0 y 100, pero el backend es la autoridad.
          </p>
        </div>
      </Panel>
        </>
      )}
    </div>
  );
}
