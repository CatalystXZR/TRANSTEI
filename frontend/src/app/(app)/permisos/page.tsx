"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, KeyRound, RefreshCw, ShieldCheck } from "lucide-react";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import type {
  MatrizPermisosNucleo,
  MisPermisosNucleo,
  PermisoRolNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import {
  Aviso,
  PageHeader,
  Panel,
  StatTile,
  StatusBadge,
} from "@/components/sistema";

const ETIQUETA_ROL: Record<string, string> = {
  admin: "Administración",
  gerente: "Gerencia",
  despacho: "Despacho",
  contador: "Contabilidad",
  tesoreria: "Tesorería",
  taller: "Taller",
  conductor: "Conductor",
  auditor: "Auditoría",
};

const ETIQUETA_MODULO: Record<string, string> = {
  maestros: "Maestros",
  operacion: "Operación",
  comercial: "Comercial",
  agenda: "Agenda",
  expediente: "Expediente",
  pod: "POD",
  gastos: "Gastos",
  rentabilidad: "Rentabilidad",
  facturacion: "Facturación",
  cobranza: "Cobranza",
  alertas: "Alertas",
  auditoria: "Auditoría",
  conductor: "PWA conductor",
  configuracion: "Configuración",
  roles: "Roles",
  usuarios: "Usuarios",
};

function agrupar(permisos: string[]): Record<string, string[]> {
  const grupos: Record<string, string[]> = {};
  for (const permiso of permisos) {
    const [modulo, accion] = permiso.split(":");
    grupos[modulo] = grupos[modulo] ?? [];
    grupos[modulo].push(accion);
  }
  return grupos;
}

export default function PermisosPage() {
  const [empresaId, setEmpresaId] = useState("");
  const [mios, setMios] = useState<MisPermisosNucleo | null>(null);
  const [matriz, setMatriz] = useState<MatrizPermisosNucleo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    getEmpresas()
      .then((empresas) => {
        if (!activo) return;
        if (empresas[0]) setEmpresaId(empresas[0].id);
        else {
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
        const propios = await nucleo.get<MisPermisosNucleo>(
          "/nucleo/permisos/mios",
          empresaId,
        );
        setMios(propios);
        try {
          const m = await nucleo.get<MatrizPermisosNucleo>(
            "/nucleo/permisos/matriz",
            empresaId,
          );
          setMatriz(m);
        } catch {
          setMatriz(null);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "No se pudieron cargar los permisos");
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

  const roles: PermisoRolNucleo[] = matriz?.roles ?? [];

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Sistema"
        titulo="Roles y permisos"
        descripcion="Matriz de 8 roles por módulo y acción. El backend valida cada permiso; la UI solo refleja la política."
        acciones={
          <Button
            variant="outline"
            onClick={() => void cargar(true)}
            disabled={!empresaId || actualizando}
          >
            <RefreshCw className={actualizando ? "animate-spin" : undefined} /> Actualizar
          </Button>
        }
      />

      {error && <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>}

      <div className="grid gap-s3 sm:grid-cols-3">
        <StatTile
          etiqueta="Su rol"
          valor={mios ? ETIQUETA_ROL[mios.rol] ?? mios.rol : "—"}
          detalle={mios ? `${mios.permisos.length} permisos` : "Cargando…"}
          tono="info"
          icono={ShieldCheck}
          destacado
        />
        <StatTile
          etiqueta="Roles definidos"
          valor={roles.length || 8}
          detalle="Segregación de funciones"
          tono="neutro"
          icono={KeyRound}
        />
        <StatTile
          etiqueta="Permisos del catálogo"
          valor={matriz?.permisos.length ?? 28}
          detalle="Módulos y acciones"
          tono="neutro"
          icono={KeyRound}
        />
      </div>

      <Panel
        titulo="Sus permisos"
        descripcion={mios ? `Rol ${mios.rol}` : "Cargando…"}
      >
        {mios ? (
          <div className="space-y-s3 p-s4">
            {Object.entries(agrupar(mios.permisos)).map(([modulo, acciones]) => (
              <div key={modulo} className="flex flex-wrap items-center gap-s2">
                <span className="w-32 text-[14px] font-medium">
                  {ETIQUETA_MODULO[modulo] ?? modulo}
                </span>
                {acciones.sort().map((accion) => (
                  <StatusBadge key={accion} tono={accion === "aprobar" || accion === "emitir" || accion === "administrar" ? "atencion" : "ok"}>
                    {accion}
                  </StatusBadge>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <p className="p-s4 text-[14px] text-tinta-3">Cargando permisos…</p>
        )}
      </Panel>

      {cargando && roles.length === 0 ? (
        <div className="h-64 animate-pulse rounded-xl bg-superficie-hundida" />
      ) : roles.length === 0 ? (
        <Aviso tono="neutro">
          Su rol no puede ver la matriz completa. Sus permisos personales están arriba.
        </Aviso>
      ) : (
        <div className="grid gap-s4 xl:grid-cols-2">
          {roles.map((rol) => {
            const grupos = agrupar(rol.permisos);
            return (
              <Panel
                key={rol.rol}
                titulo={ETIQUETA_ROL[rol.rol] ?? rol.rol}
                descripcion={`${rol.permisos.length} permiso(s)`}
                acciones={<StatusBadge tono={rol.rol === "admin" ? "critico" : "info"}>{rol.rol}</StatusBadge>}
              >
                <div className="space-y-s2 p-s4">
                  {Object.entries(grupos).map(([modulo, acciones]) => (
                    <div key={modulo} className="flex flex-wrap items-center gap-s2 text-[13px]">
                      <span className="w-28 font-medium text-tinta-2">
                        {ETIQUETA_MODULO[modulo] ?? modulo}
                      </span>
                      {acciones.sort().map((accion) => (
                        <span
                          key={accion}
                          className="rounded-md bg-superficie-hundida px-2 py-0.5 text-tinta-3"
                        >
                          {accion}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              </Panel>
            );
          })}
        </div>
      )}
    </div>
  );
}
