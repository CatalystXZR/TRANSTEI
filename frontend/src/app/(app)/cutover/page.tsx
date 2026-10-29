"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRightLeft,
  CheckCircle2,
  Lock,
  RefreshCw,
  Unlock,
} from "lucide-react";
import { toast } from "sonner";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import { formatFechaHora } from "@/lib/format";
import type { CutoverEstadoNucleo } from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import {
  Aviso,
  PageHeader,
  Panel,
  StatTile,
  StatusBadge,
} from "@/components/sistema";

export default function CutoverPage() {
  const [empresaId, setEmpresaId] = useState("");
  const [estado, setEstado] = useState<CutoverEstadoNucleo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [procesando, setProcesando] = useState(false);
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

  const cargar = useCallback(async () => {
    if (!empresaId) return;
    setCargando(true);
    setError(null);
    try {
      const data = await nucleo.get<CutoverEstadoNucleo>(
        "/nucleo/cutover/estado",
        empresaId,
      );
      setEstado(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el estado de cutover");
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

  async function congelar() {
    const motivo = window.prompt("Motivo para congelar la escritura legacy:");
    if (!motivo || motivo.trim().length < 5) return;
    setProcesando(true);
    try {
      const data = await nucleo.post<CutoverEstadoNucleo>(
        "/nucleo/cutover/congelar",
        empresaId,
        { motivo: motivo.trim() },
      );
      setEstado(data);
      toast.success("Escritura legacy congelada");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo congelar");
    } finally {
      setProcesando(false);
    }
  }

  async function descongelar() {
    const motivo = window.prompt("Motivo para descongelar la escritura legacy:");
    if (!motivo || motivo.trim().length < 5) return;
    setProcesando(true);
    try {
      const data = await nucleo.post<CutoverEstadoNucleo>(
        "/nucleo/cutover/descongelar",
        empresaId,
        { motivo: motivo.trim() },
      );
      setEstado(data);
      toast.success("Escritura legacy descongelada");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo descongelar");
    } finally {
      setProcesando(false);
    }
  }

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Sistema"
        titulo="Cutover legacy → núcleo"
        descripcion="Congele la escritura del sistema anterior cuando `nucleo` sea la única fuente de verdad. Las lecturas legacy siguen disponibles para contingencia."
        acciones={
          <Button variant="outline" onClick={() => void cargar()} disabled={cargando}>
            <RefreshCw className={cargando ? "animate-spin" : undefined} /> Actualizar
          </Button>
        }
      />

      {error && <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>}

      <div className="grid gap-s3 sm:grid-cols-3">
        <StatTile
          etiqueta="Escritura legacy"
          valor={estado?.legacy_escritura_congelada ? "Congelada" : "Abierta"}
          detalle={estado?.mensaje}
          tono={estado?.legacy_escritura_congelada ? "ok" : "atencion"}
          icono={estado?.legacy_escritura_congelada ? Lock : Unlock}
          destacado
        />
        <StatTile
          etiqueta="Viajes legacy abiertos"
          valor={estado?.legacy_viajes_abiertos ?? "—"}
          detalle="Pendientes de migrar"
          tono={(estado?.legacy_viajes_abiertos ?? 0) > 0 ? "atencion" : "ok"}
          icono={ArrowRightLeft}
        />
        <StatTile
          etiqueta="Viajes en núcleo"
          valor={estado?.nucleo_viajes ?? "—"}
          detalle="Fuente de verdad nueva"
          tono="info"
          icono={CheckCircle2}
        />
      </div>

      <Panel titulo="Estado del control" descripcion={estado?.updated_at ? `Actualizado ${formatFechaHora(estado.updated_at)}` : undefined}>
        <div className="space-y-s3 p-s4 text-[14px]">
          <p className="flex flex-wrap items-center gap-s2">
            <StatusBadge tono={estado?.legacy_escritura_congelada ? "ok" : "atencion"}>
              {estado?.legacy_escritura_congelada ? "Congelada" : "Abierta"}
            </StatusBadge>
            <span>{estado?.mensaje ?? "Cargando…"}</span>
          </p>
          {estado?.congelada_en && (
            <p className="text-tinta-3">
              Congelada el {formatFechaHora(estado.congelada_en)} por{" "}
              {estado.congelada_por ?? "sistema"}. Motivo: {estado.motivo ?? "—"}.
            </p>
          )}
          <div className="flex flex-wrap gap-s2 pt-s2">
            <Button
              onClick={() => void congelar()}
              disabled={procesando || !estado || estado.legacy_escritura_congelada}
            >
              <Lock /> Congelar legacy
            </Button>
            <Button
              variant="outline"
              onClick={() => void descongelar()}
              disabled={procesando || !estado || !estado.legacy_escritura_congelada}
            >
              <Unlock /> Descongelar
            </Button>
          </div>
          <p className="text-[13px] text-tinta-3">
            Antes de congelar ejecute el backup/restore drill y la UAT. Después de
            congelar, cualquier POST/PUT/PATCH/DELETE a los routers legacy devuelve
            409; el schema `nucleo` sigue operando.
          </p>
        </div>
      </Panel>

      <Panel titulo="Runbook rápido">
        <ol className="list-inside list-decimal space-y-s2 p-s4 text-[14px]">
          <li>Backup y restore drill: <code>scripts/restore_drill.sh</code>.</li>
          <li>Dry-run de migración: <code>scripts/cutover_legacy.py --dry-run</code>.</li>
          <li>Cutover y congelamiento: <code>scripts/cutover_legacy.py --freeze</code>.</li>
          <li>Validar 409 en legacy y operación normal en `/despacho`, `/expediente`, `/cobranza`.</li>
          <li>Registrar evidencia en <code>docs/operacion/cutover.md</code> y <code>docs/qa/uat-piloto.md</code>.</li>
        </ol>
      </Panel>
    </div>
  );
}
