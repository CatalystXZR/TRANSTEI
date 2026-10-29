"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  ClipboardCheck,
  FileText,
  RefreshCw,
  Search,
  Truck,
} from "lucide-react";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import { formatCLP, formatFechaHora } from "@/lib/format";
import type {
  EmpresaNucleo,
  EstadoViajeNucleo,
  ListaExpedienteNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Aviso,
  EstadoVacio,
  PageHeader,
  Panel,
  StatTile,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import { SelectSimple } from "@/components/formulario";

const ESTADOS: { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "confirmado", etiqueta: "Confirmado" },
  { valor: "asignado", etiqueta: "Asignado" },
  { valor: "en_carga", etiqueta: "En carga" },
  { valor: "cargado", etiqueta: "Cargado" },
  { valor: "en_ruta", etiqueta: "En ruta" },
  { valor: "en_descarga", etiqueta: "En descarga" },
  { valor: "descargado", etiqueta: "Descargado" },
  { valor: "pod_pendiente", etiqueta: "POD pendiente" },
  { valor: "cerrado", etiqueta: "Cerrado" },
  { valor: "facturado", etiqueta: "Facturado" },
  { valor: "cobrado", etiqueta: "Cobrado" },
  { valor: "anulado", etiqueta: "Anulado" },
];

function tonoEstado(estado: EstadoViajeNucleo): Tono {
  if (estado === "anulado") return "neutro";
  if (estado === "cerrado" || estado === "facturado" || estado === "cobrado") return "ok";
  if (estado === "pod_pendiente" || estado === "descargado") return "atencion";
  return "info";
}

export default function ExpedientePage() {
  const [empresaId, setEmpresaId] = useState("");
  const [empresa, setEmpresa] = useState<EmpresaNucleo | null>(null);
  const [data, setData] = useState<ListaExpedienteNucleo | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [estado, setEstado] = useState("");
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
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
          setError("El usuario no tiene una empresa activa asignada.");
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
        const params = new URLSearchParams({
          limit: "100",
          ...(estado ? { estado } : {}),
          ...(busqueda.trim() ? { q: busqueda.trim() } : {}),
        });
        const lista = await nucleo.get<ListaExpedienteNucleo>(
          `/nucleo/expediente/viajes?${params.toString()}`,
          empresaId,
        );
        setData(lista);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar el expediente");
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId, estado, busqueda],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 250);
    return () => clearTimeout(t);
  }, [cargar]);

  const items = useMemo(() => data?.items ?? [], [data]);
  const stats = useMemo(() => {
    const pendientes = items.filter((i) => i.checklist_pendientes > 0).length;
    const incidentes = items.reduce((acc, i) => acc + i.incidentes_abiertos, 0);
    const documentos = items.reduce((acc, i) => acc + i.documentos_count, 0);
    return { pendientes, incidentes, documentos };
  }, [items]);

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Operación"
        titulo="Expediente del viaje"
        descripcion="Detalle operativo, paradas, checklist, eventos, incidentes y documentos. El cierre exige checklist completo y sin incidentes críticos abiertos."
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

      {error && (
        <Aviso tono="critico" icono={AlertTriangle}>
          {error}
        </Aviso>
      )}

      <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          etiqueta="Viajes en expediente"
          valor={data?.total ?? 0}
          detalle={empresa?.razon_social}
          tono="info"
          icono={Truck}
          destacado
        />
        <StatTile
          etiqueta="Con checklist pendiente"
          valor={stats.pendientes}
          detalle="Ítems obligatorios sin completar"
          tono={stats.pendientes > 0 ? "atencion" : "ok"}
          icono={ClipboardCheck}
        />
        <StatTile
          etiqueta="Incidentes abiertos"
          valor={stats.incidentes}
          detalle="En la lista consultada"
          tono={stats.incidentes > 0 ? "critico" : "ok"}
          icono={AlertTriangle}
        />
        <StatTile
          etiqueta="Documentos adjuntos"
          valor={stats.documentos}
          detalle="Guías, permisos y evidencias"
          tono="neutro"
          icono={FileText}
        />
      </div>

      <div className="flex flex-wrap items-end justify-between gap-s3">
        <div className="w-full sm:w-[240px]">
          <SelectSimple
            valor={estado}
            onCambio={setEstado}
            opciones={ESTADOS}
            placeholder="Estado"
            ariaLabel="Filtrar por estado"
          />
        </div>
        <label className="relative w-full sm:w-[360px]">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-tinta-3" />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar por folio, ruta u OC…"
            className="pl-9"
          />
        </label>
      </div>

      <Panel
        titulo={`Viajes · ${items.length}`}
        descripcion="Haga clic en un viaje para abrir su expediente completo."
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Viaje</TableHead>
                <TableHead>Cliente / ruta</TableHead>
                <TableHead>Ventana</TableHead>
                <TableHead>Recursos</TableHead>
                <TableHead>Checklist</TableHead>
                <TableHead>Incidentes</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Abrir</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-s6 text-center text-tinta-3">
                    Cargando expedientes…
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="p-0">
                    <EstadoVacio
                      icono={Truck}
                      titulo="Sin viajes"
                      descripcion="Cree un viaje en la Mesa de despacho para abrir su expediente."
                    />
                  </TableCell>
                </TableRow>
              ) : (
                items.map((viaje) => (
                  <TableRow key={viaje.id}>
                    <TableCell>
                      <Link
                        href={`/expediente/${viaje.id}`}
                        className="font-mono text-[13px] font-semibold text-marca hover:underline"
                      >
                        {viaje.numero_viaje}
                      </Link>
                      <p className="text-[12px] text-tinta-3">{viaje.oc_numero ?? "Sin OC"}</p>
                    </TableCell>
                    <TableCell>
                      <p className="font-medium">{viaje.cliente_nombre}</p>
                      <p className="text-[13px] text-tinta-3">
                        {viaje.origen} → {viaje.destino}
                      </p>
                    </TableCell>
                    <TableCell className="text-[14px]">
                      {formatFechaHora(viaje.inicio_planificado)}
                      <br />
                      <span className="text-tinta-3">{formatFechaHora(viaje.fin_planificado)}</span>
                    </TableCell>
                    <TableCell className="text-[13px]">
                      {viaje.tracto_patente ? (
                        <>
                          <p className="font-mono">{viaje.tracto_patente}</p>
                          <p className="text-tinta-3">
                            {viaje.rampla_patente ?? "sin rampla"} · {viaje.chofer_nombre ?? "sin chofer"}
                          </p>
                        </>
                      ) : (
                        <span className="text-tinta-3">Sin asignar</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-s2">
                        <div className="h-2 w-16 overflow-hidden rounded-full bg-superficie-hundida">
                          <div
                            className={`h-full rounded-full ${Number(viaje.checklist_pct) >= 100 ? "bg-ok" : "bg-atencion"}`}
                            style={{ width: `${Math.min(100, Number(viaje.checklist_pct))}%` }}
                          />
                        </div>
                        <span className="text-[13px] tabular-nums">
                          {Number(viaje.checklist_pct).toFixed(0)}%
                        </span>
                      </div>
                      {viaje.checklist_pendientes > 0 && (
                        <p className="text-[12px] text-atencion">
                          {viaje.checklist_pendientes} pendiente(s)
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      {viaje.incidentes_abiertos > 0 ? (
                        <StatusBadge tono="critico">{viaje.incidentes_abiertos}</StatusBadge>
                      ) : (
                        <span className="text-tinta-3">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge tono={tonoEstado(viaje.estado)}>
                        {viaje.estado.replaceAll("_", " ")}
                      </StatusBadge>
                      <p className="mt-1 text-[12px] text-tinta-3">{formatCLP(viaje.flete_total)}</p>
                    </TableCell>
                    <TableCell className="text-right">
                      <Link href={`/expediente/${viaje.id}`}>
                        <Button size="xs" variant="outline">
                          Abrir <ArrowRight />
                        </Button>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </Panel>
    </div>
  );
}
