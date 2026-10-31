"use client";

import { useEffect, useState } from "react";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import type { EmpresaNucleo, MisPermisosNucleo } from "@/types/nucleo";

export interface SesionNucleo {
  empresa: EmpresaNucleo | null;
  empresaId: string;
  permisos: string[];
  cargando: boolean;
  error: unknown;
}

/**
 * Resuelve la empresa activa y los permisos efectivos del rol en esa empresa.
 * Los permisos son sólo una guía de UI: cada endpoint vuelve a autorizar.
 * La empresa se toma de `/nucleo/mis-empresas`, igual que el resto del núcleo.
 */
export function useNucleoEmpresa(): SesionNucleo {
  const [empresa, setEmpresa] = useState<EmpresaNucleo | null>(null);
  const [permisos, setPermisos] = useState<string[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let activo = true;

    async function cargar() {
      try {
        const empresas = await getEmpresas();
        if (!activo) return;
        const primera = empresas[0];
        if (!primera) {
          setError(new Error("El usuario no tiene una empresa activa asignada."));
          return;
        }
        setEmpresa(primera);
        const mios = await nucleo.get<MisPermisosNucleo>(
          "/nucleo/permisos/mios",
          primera.id,
        );
        if (!activo) return;
        setPermisos(mios.permisos);
      } catch (e) {
        if (activo) setError(e);
      } finally {
        if (activo) setCargando(false);
      }
    }

    void cargar();
    return () => {
      activo = false;
    };
  }, []);

  return {
    empresa,
    empresaId: empresa?.id ?? "",
    permisos,
    cargando,
    error,
  };
}
