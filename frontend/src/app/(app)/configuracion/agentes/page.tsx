"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Info, RefreshCw, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { NucleoError, nucleo } from "@/lib/nucleo";
import { useNucleoEmpresa } from "@/lib/use-nucleo-empresa";
import type {
  ActualizarConfiguracionAgenteNucleo,
  AgenteConfigClave,
  AgenteConfigNucleo,
  ConfiguracionAgentesNucleo,
  RestablecerConfiguracionAgenteNucleo,
} from "@/types/agente-config";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Aviso, EstadoVacio, PageHeader, Panel } from "@/components/sistema";
import { ErrorNucleo } from "@/components/nucleo/estado-error";
import { PanelConfiguracionAgente } from "@/components/agente/panel-configuracion-agente";

const RUTA_CONFIGURACION = "/nucleo/agente/configuracion";
const RUTA_RESTABLECER = "/nucleo/agente/configuracion/restablecer";
const ID_SIN_PERMISO = "sin-permiso-agente-configurar";

function mensajeAccion(error: unknown): string {
  if (error instanceof NucleoError) {
    if (error.status === 401) {
      return "Su sesión expiró. Vuelva a iniciar sesión.";
    }
    if (error.status === 403) {
      return "Sin permiso para configurar los agentes (agente:configurar).";
    }
    if (error.status === 409) {
      return "La configuración cambió en el servidor. Actualice e intente nuevamente.";
    }
    return error.message;
  }
  if (error instanceof TypeError) {
    return "No se pudo conectar con el servidor. Revise su conexión e intente nuevamente.";
  }
  return error instanceof Error
    ? error.message
    : "Ocurrió un error inesperado.";
}

function CargandoPanel({ mensaje }: { mensaje: string }) {
  return (
    <Panel titulo="Capacidades de los agentes" descripcion={mensaje}>
      <div className="space-y-s4 p-s4" aria-busy="true">
        <span className="sr-only">{mensaje}</span>
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
    </Panel>
  );
}

export default function ConfiguracionAgentesPage() {
  const {
    empresa,
    empresaId,
    permisos,
    cargando: cargandoSesion,
    error: errorSesion,
  } = useNucleoEmpresa();

  const [agentes, setAgentes] = useState<AgenteConfigNucleo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [errorCarga, setErrorCarga] = useState<unknown>(null);
  const [guardando, setGuardando] = useState<Record<string, boolean>>({});
  const [restableciendo, setRestableciendo] =
    useState<AgenteConfigClave | null>(null);

  const enVueloAgente = useRef(new Set<AgenteConfigClave>());
  const restableciendoRef = useRef(false);
  const solicitudRef = useRef(0);

  const puedeConfigurar = permisos.includes("agente:configurar");

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!empresaId) return;
      const solicitud = ++solicitudRef.current;
      if (silencioso) {
        setActualizando(true);
      } else {
        setCargando(true);
        setAgentes([]);
      }
      setErrorCarga(null);
      try {
        const data = await nucleo.get<ConfiguracionAgentesNucleo>(
          RUTA_CONFIGURACION,
          empresaId,
        );
        if (solicitud !== solicitudRef.current) return;
        setAgentes(data.agentes);
      } catch (e) {
        if (solicitud !== solicitudRef.current) return;
        setErrorCarga(e);
      } finally {
        if (solicitud === solicitudRef.current) {
          setCargando(false);
          setActualizando(false);
        }
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

  const cambiarCapacidad = useCallback(
    async (
      agenteClave: AgenteConfigClave,
      capacidadClave: string,
      habilitada: boolean,
    ) => {
      if (!empresaId || !puedeConfigurar) return;
      if (enVueloAgente.current.has(agenteClave)) return;

      const agenteActual = agentes.find((a) => a.clave === agenteClave);
      const capacidadActual = agenteActual?.capacidades.find(
        (c) => c.clave === capacidadClave,
      );
      if (!capacidadActual || capacidadActual.habilitada === habilitada) return;

      const anterior = capacidadActual.habilitada;
      const claveGuardado = `${agenteClave}:${capacidadClave}`;
      enVueloAgente.current.add(agenteClave);
      setGuardando((prev) => ({ ...prev, [claveGuardado]: true }));

      // Actualización optimista: el interruptor responde de inmediato y se
      // revierte si el servidor rechaza el cambio.
      setAgentes((prev) =>
        prev.map((a) =>
          a.clave === agenteClave
            ? {
                ...a,
                capacidades: a.capacidades.map((c) =>
                  c.clave === capacidadClave ? { ...c, habilitada } : c,
                ),
              }
            : a,
        ),
      );

      try {
        const body: ActualizarConfiguracionAgenteNucleo = {
          agente: agenteClave,
          cambios: [{ capacidad: capacidadClave, habilitada }],
        };
        const actualizado = await nucleo.put<AgenteConfigNucleo>(
          RUTA_CONFIGURACION,
          empresaId,
          body,
        );
        setAgentes((prev) =>
          prev.map((a) => (a.clave === actualizado.clave ? actualizado : a)),
        );
        toast.success(
          habilitada ? "Capacidad habilitada" : "Capacidad deshabilitada",
        );
      } catch (e) {
        setAgentes((prev) =>
          prev.map((a) =>
            a.clave === agenteClave
              ? {
                  ...a,
                  capacidades: a.capacidades.map((c) =>
                    c.clave === capacidadClave
                      ? { ...c, habilitada: anterior }
                      : c,
                  ),
                }
              : a,
          ),
        );
        toast.error(mensajeAccion(e));
      } finally {
        enVueloAgente.current.delete(agenteClave);
        setGuardando((prev) => {
          const siguiente = { ...prev };
          delete siguiente[claveGuardado];
          return siguiente;
        });
      }
    },
    [agentes, empresaId, puedeConfigurar],
  );

  const restablecer = useCallback(
    async (agenteClave: AgenteConfigClave) => {
      if (!empresaId) {
        throw new Error("No hay una empresa activa.");
      }
      if (!puedeConfigurar) {
        throw new Error("Su rol no tiene el permiso agente:configurar.");
      }
      if (restableciendoRef.current) {
        throw new Error("Ya hay un restablecimiento en curso.");
      }
      if (enVueloAgente.current.has(agenteClave)) {
        throw new Error(
          "Hay un cambio de capacidad en curso. Espere a que termine.",
        );
      }

      restableciendoRef.current = true;
      setRestableciendo(agenteClave);
      try {
        const body: RestablecerConfiguracionAgenteNucleo = {
          agente: agenteClave,
        };
        const actualizado = await nucleo.post<AgenteConfigNucleo>(
          RUTA_RESTABLECER,
          empresaId,
          body,
        );
        setAgentes((prev) =>
          prev.map((a) => (a.clave === actualizado.clave ? actualizado : a)),
        );
        toast.success(`Configuración de ${actualizado.nombre} restablecida`);
      } catch (e) {
        const mensaje = mensajeAccion(e);
        toast.error(mensaje);
        throw new Error(mensaje);
      } finally {
        restableciendoRef.current = false;
        setRestableciendo(null);
      }
    },
    [empresaId, puedeConfigurar],
  );

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Sistema"
        titulo="Capacidades de los agentes"
        descripcion="Define qué puede hacer cada agente en esta empresa. Los límites de seguridad no se pueden cambiar."
        acciones={
          <Button
            variant="outline"
            onClick={() => void cargar(true)}
            disabled={!empresaId || cargando || actualizando}
          >
            <RefreshCw className={actualizando ? "animate-spin" : undefined} />
            Actualizar
          </Button>
        }
      />

      {cargandoSesion ? (
        <CargandoPanel mensaje="Resolviendo la empresa activa y sus permisos…" />
      ) : errorSesion ? (
        <ErrorNucleo error={errorSesion} />
      ) : !empresaId ? (
        <div role="alert">
          <Aviso tono="atencion" icono={ShieldAlert}>
            El usuario no tiene una empresa activa asignada.
          </Aviso>
        </div>
      ) : cargando && agentes.length === 0 ? (
        <CargandoPanel mensaje="Cargando la configuración de los agentes…" />
      ) : errorCarga && agentes.length === 0 ? (
        <div className="space-y-s3">
          <ErrorNucleo error={errorCarga} />
          <Button variant="outline" onClick={() => void cargar()}>
            <RefreshCw /> Reintentar
          </Button>
        </div>
      ) : (
        <>
          {empresa && (
            <p className="text-[14px] text-tinta-3">
              Empresa:{" "}
              <span className="font-medium text-tinta-2">
                {empresa.razon_social}
              </span>{" "}
              · Rol:{" "}
              <span className="font-medium text-tinta-2">{empresa.rol}</span>
            </p>
          )}

          {errorCarga && agentes.length > 0 && (
            <div className="flex flex-wrap items-start justify-between gap-s3">
              <div className="min-w-[240px] flex-1">
                <ErrorNucleo error={errorCarga} />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void cargar(true)}
                disabled={actualizando}
              >
                <RefreshCw
                  className={actualizando ? "animate-spin" : undefined}
                />
                Reintentar
              </Button>
            </div>
          )}

          {!puedeConfigurar && (
            <div id={ID_SIN_PERMISO}>
              <Aviso tono="atencion" icono={ShieldAlert}>
                Su rol puede consultar esta configuración, pero no modificarla.
                El servidor volverá a verificar el permiso{" "}
                <code>agente:configurar</code>.
              </Aviso>
            </div>
          )}

          {agentes.length === 0 ? (
            <Panel
              titulo="Agentes"
              descripcion="Configuración de capacidades por empresa."
            >
              <EstadoVacio
                icono={Bot}
                titulo="Sin agentes configurados"
                descripcion="El servidor no devolvió agentes para esta empresa."
                accion={
                  <Button
                    variant="outline"
                    onClick={() => void cargar()}
                    disabled={cargando}
                  >
                    <RefreshCw /> Actualizar
                  </Button>
                }
              />
            </Panel>
          ) : (
            agentes.map((agente) => (
              <PanelConfiguracionAgente
                key={`${empresaId}:${agente.clave}`}
                agente={agente}
                puedeConfigurar={puedeConfigurar}
                idPermiso={ID_SIN_PERMISO}
                guardando={guardando}
                restableciendo={restableciendo === agente.clave}
                onCambio={(capacidad, habilitada) => {
                  void cambiarCapacidad(
                    agente.clave,
                    capacidad,
                    habilitada,
                  );
                }}
                onRestablecer={() => restablecer(agente.clave)}
              />
            ))
          )}

          <Aviso tono="neutro" icono={Info}>
            El servidor valida el permiso <code>agente:configurar</code> y la
            empresa en cada cambio. Esta pantalla no puede ampliar los permisos
            de su rol ni activar módulos por sí sola.
          </Aviso>
        </>
      )}
    </div>
  );
}
