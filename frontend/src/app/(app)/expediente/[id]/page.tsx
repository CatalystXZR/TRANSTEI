"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Download,
  FileText,
  MapPin,
  Plus,
  QrCode,
  RefreshCw,
  ShieldAlert,
  Upload,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { nucleo, NucleoError, nucleoUpload } from "@/lib/nucleo";
import { formatCLP, formatFecha, formatFechaHora } from "@/lib/format";
import type {
  ChecklistItemNucleo,
  EmpresaNucleo,
  IncidenteNucleo,
  ParadaNucleo,
  ViajeExpedienteNucleo,
} from "@/types/nucleo";
import { getEmpresas } from "@/lib/nucleo";
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
  PageHeader,
  Panel,
  Patente,
  StatTile,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import { Campo, SelectSimple } from "@/components/formulario";
import { PODPanel } from "@/components/expediente/pod-panel";
import { GastosPanel } from "@/components/expediente/gastos-panel";
import { RentabilidadViajePanel } from "@/components/rentabilidad/rentabilidad-viaje-panel";
import { cn } from "cn";

type Tab =
  | "resumen"
  | "paradas"
  | "checklist"
  | "eventos"
  | "incidentes"
  | "documentos"
  | "pod"
  | "gastos"
  | "rentabilidad"
  | "auditoria";

const TABS: { valor: Tab; etiqueta: string }[] = [
  { valor: "resumen", etiqueta: "Resumen" },
  { valor: "paradas", etiqueta: "Paradas" },
  { valor: "checklist", etiqueta: "Checklist" },
  { valor: "eventos", etiqueta: "Eventos" },
  { valor: "incidentes", etiqueta: "Incidentes" },
  { valor: "documentos", etiqueta: "Documentos" },
  { valor: "pod", etiqueta: "POD" },
  { valor: "gastos", etiqueta: "Gastos y costos" },
  { valor: "rentabilidad", etiqueta: "Rentabilidad" },
  { valor: "auditoria", etiqueta: "Auditoría" },
];

const TIPOS_PARADA = [
  { valor: "origen", etiqueta: "Origen" },
  { valor: "carga", etiqueta: "Carga" },
  { valor: "descarga", etiqueta: "Descarga" },
  { valor: "intermedia", etiqueta: "Intermedia" },
  { valor: "devolucion", etiqueta: "Devolución" },
];

const ESTADOS_PARADA = [
  { valor: "pendiente", etiqueta: "Pendiente" },
  { valor: "en_curso", etiqueta: "En curso" },
  { valor: "completada", etiqueta: "Completada" },
  { valor: "omitida", etiqueta: "Omitida" },
];

const SEVERIDADES = [
  { valor: "baja", etiqueta: "Baja" },
  { valor: "media", etiqueta: "Media" },
  { valor: "alta", etiqueta: "Alta" },
  { valor: "critica", etiqueta: "Crítica" },
];

function tonoEstado(estado: string): Tono {
  if (estado === "anulado") return "neutro";
  if (["cerrado", "facturado", "cobrado"].includes(estado)) return "ok";
  if (["descargado", "pod_pendiente"].includes(estado)) return "atencion";
  return "info";
}

function tonoIncidente(severidad: string): Tono {
  if (severidad === "critica" || severidad === "alta") return "critico";
  if (severidad === "media") return "atencion";
  return "neutro";
}

export default function ExpedienteDetallePage() {
  const params = useParams<{ id: string }>();
  const viajeId = params.id;
  const [empresaId, setEmpresaId] = useState("");
  const [empresa, setEmpresa] = useState<EmpresaNucleo | null>(null);
  const [viaje, setViaje] = useState<ViajeExpedienteNucleo | null>(null);
  const [tab, setTab] = useState<Tab>("resumen");
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [procesando, setProcesando] = useState(false);

  const [nuevaParada, setNuevaParada] = useState({
    tipo: "carga",
    nombre: "",
    ciudad: "",
    direccion: "",
    ventana_desde: "",
    ventana_hasta: "",
  });
  const [nuevoEvento, setNuevoEvento] = useState({
    tipo: "nota",
    descripcion: "",
  });
  const [nuevoIncidente, setNuevoIncidente] = useState({
    tipo: "averia",
    severidad: "media",
    descripcion: "",
  });

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

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!empresaId || !viajeId) return;
      if (silencioso) setActualizando(true);
      else setCargando(true);
      setError(null);
      try {
        const data = await nucleo.get<ViajeExpedienteNucleo>(
          `/nucleo/expediente/viajes/${viajeId}`,
          empresaId,
        );
        setViaje(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "No se pudo cargar el expediente");
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId, viajeId],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  async function ejecutar(accion: () => Promise<unknown>, mensaje: string) {
    setProcesando(true);
    setError(null);
    try {
      await accion();
      toast.success(mensaje);
      await cargar(true);
    } catch (e) {
      const texto = e instanceof Error ? e.message : "No se pudo completar la operación";
      setError(texto);
      if (e instanceof NucleoError && e.errores.length > 0) {
        setError([texto, ...e.errores.map((i) => i.mensaje)].join(" "));
      }
    } finally {
      setProcesando(false);
    }
  }

  function toggleChecklist(item: ChecklistItemNucleo) {
    if (!viaje) return;
    void ejecutar(
      () =>
        nucleo.put(
          `/nucleo/expediente/viajes/${viaje.id}/checklist/${item.id}`,
          empresaId,
          {
            completado: !item.completado,
            notas: item.notas,
            evidencia_url: item.evidencia_url,
            version: item.version,
          },
        ),
      item.completado ? "Ítem reabierto" : "Ítem completado",
    );
  }

  function crearParada() {
    if (!viaje) return;
    if (!nuevaParada.nombre.trim()) {
      toast.error("Ingrese el nombre de la parada");
      return;
    }
    void ejecutar(
      () =>
        nucleo.post(`/nucleo/expediente/viajes/${viaje.id}/paradas`, empresaId, {
          tipo: nuevaParada.tipo,
          nombre: nuevaParada.nombre.trim(),
          ciudad: nuevaParada.ciudad.trim() || null,
          direccion: nuevaParada.direccion.trim() || null,
          ventana_desde: nuevaParada.ventana_desde
            ? new Date(nuevaParada.ventana_desde).toISOString()
            : null,
          ventana_hasta: nuevaParada.ventana_hasta
            ? new Date(nuevaParada.ventana_hasta).toISOString()
            : null,
        }),
      "Parada agregada",
    ).then(() =>
      setNuevaParada({
        tipo: "carga",
        nombre: "",
        ciudad: "",
        direccion: "",
        ventana_desde: "",
        ventana_hasta: "",
      }),
    );
  }

  function cambiarEstadoParada(parada: ParadaNucleo, estado: string) {
    if (!viaje) return;
    void ejecutar(
      () =>
        nucleo.put(
          `/nucleo/expediente/viajes/${viaje.id}/paradas/${parada.id}`,
          empresaId,
          {
            orden: parada.orden,
            tipo: parada.tipo,
            nombre: parada.nombre,
            direccion: parada.direccion,
            comuna: parada.comuna,
            ciudad: parada.ciudad,
            contacto_nombre: parada.contacto_nombre,
            contacto_telefono: parada.contacto_telefono,
            ventana_desde: parada.ventana_desde,
            ventana_hasta: parada.ventana_hasta,
            estado,
            notas: parada.notas,
            activo: parada.activo,
            version: parada.version,
          },
        ),
      "Parada actualizada",
    );
  }

  function crearEvento() {
    if (!viaje || !nuevoEvento.descripcion.trim()) return;
    void ejecutar(
      () =>
        nucleo.post(`/nucleo/expediente/viajes/${viaje.id}/eventos`, empresaId, {
          tipo: nuevoEvento.tipo,
          descripcion: nuevoEvento.descripcion.trim(),
        }),
      "Evento registrado",
    ).then(() => setNuevoEvento({ tipo: "nota", descripcion: "" }));
  }

  function crearIncidente() {
    if (!viaje || !nuevoIncidente.descripcion.trim()) return;
    void ejecutar(
      () =>
        nucleo.post(`/nucleo/expediente/viajes/${viaje.id}/incidentes`, empresaId, {
          tipo: nuevoIncidente.tipo,
          severidad: nuevoIncidente.severidad,
          descripcion: nuevoIncidente.descripcion.trim(),
        }),
      "Incidente reportado",
    ).then(() =>
      setNuevoIncidente({ tipo: "averia", severidad: "media", descripcion: "" }),
    );
  }

  function resolverIncidente(incidente: IncidenteNucleo) {
    if (!viaje) return;
    const resolucion = window.prompt("Resolución del incidente:");
    if (!resolucion || resolucion.trim().length < 5) return;
    void ejecutar(
      () =>
        nucleo.put(
          `/nucleo/expediente/viajes/${viaje.id}/incidentes/${incidente.id}`,
          empresaId,
          {
            estado: "resuelto",
            resolucion: resolucion.trim(),
            version: incidente.version,
          },
        ),
      "Incidente resuelto",
    );
  }

  async function subirDocumento(file: File) {
    if (!viaje) return;
    const formData = new FormData();
    formData.set("tipo", "otro");
    formData.set("archivo", file);
    await ejecutar(
      () =>
        nucleoUpload(
          `/nucleo/expediente/viajes/${viaje.id}/documentos`,
          empresaId,
          formData,
        ),
      "Documento adjuntado",
    );
  }

  function cerrarViaje() {
    if (!viaje) return;
    if (!window.confirm("¿Cerrar el viaje? Esta acción no se puede revertir.")) return;
    void ejecutar(
      () =>
        nucleo.post(`/nucleo/expediente/viajes/${viaje.id}/cerrar`, empresaId, {
          observaciones: "Cierre desde expediente",
        }),
      "Viaje cerrado",
    );
  }

  const progreso = viaje ? Math.min(100, Number(viaje.resumen.progreso_pct)) : 0;

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Expediente"
        titulo={
          <span className="flex flex-wrap items-center gap-s3">
            {viaje?.numero_viaje ?? "Cargando viaje…"}
            {viaje && (
              <StatusBadge tono={tonoEstado(viaje.estado)}>
                {viaje.estado.replaceAll("_", " ")}
              </StatusBadge>
            )}
          </span>
        }
        descripcion={
          viaje
            ? `${viaje.cliente_nombre} · ${viaje.origen_nombre} → ${viaje.destino_nombre}`
            : "Detalle operativo del viaje"
        }
        acciones={
          <>
            <Link href="/expediente">
              <Button variant="outline">
                <ArrowLeft /> Volver
              </Button>
            </Link>
            <Button
              variant="outline"
              onClick={() => void cargar(true)}
              disabled={actualizando}
            >
              <RefreshCw className={actualizando ? "animate-spin" : undefined} />
              Actualizar
            </Button>
            {viaje?.resumen.puede_cerrar && (
              <Button onClick={cerrarViaje} disabled={procesando}>
                <CheckCircle2 /> Cerrar viaje
              </Button>
            )}
          </>
        }
      />

      {error && (
        <Aviso tono="critico" icono={AlertTriangle}>
          {error}
        </Aviso>
      )}

      {cargando && !viaje ? (
        <div className="space-y-s3">
          <div className="h-28 animate-pulse rounded-xl bg-superficie-hundida" />
          <div className="h-64 animate-pulse rounded-xl bg-superficie-hundida" />
        </div>
      ) : viaje ? (
        <>
          <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile
              etiqueta="Checklist"
              valor={`${progreso.toFixed(0)}%`}
              detalle={`${viaje.resumen.checklist_completados}/${viaje.resumen.checklist_total} ítems`}
              tono={viaje.resumen.checklist_requeridos_pendientes === 0 ? "ok" : "atencion"}
              icono={ClipboardCheck}
              destacado
            />
            <StatTile
              etiqueta="Paradas"
              valor={`${viaje.resumen.paradas_completadas}/${viaje.resumen.paradas_total}`}
              detalle="Completadas / total"
              tono="info"
              icono={MapPin}
            />
            <StatTile
              etiqueta="Incidentes abiertos"
              valor={viaje.resumen.incidentes_abiertos}
              detalle={viaje.resumen.incidentes_abiertos ? "Requieren atención" : "Sin incidentes"}
              tono={viaje.resumen.incidentes_abiertos ? "critico" : "ok"}
              icono={ShieldAlert}
            />
            <StatTile
              etiqueta="Documentos"
              valor={viaje.resumen.documentos_count}
              detalle="Adjuntos al expediente"
              tono="neutro"
              icono={FileText}
            />
          </div>

          <div className="flex flex-wrap gap-s2 overflow-x-auto">
            {TABS.map((t) => (
              <button
                key={t.valor}
                type="button"
                onClick={() => setTab(t.valor)}
                className={cn(
                  "rounded-lg border px-s3 py-2 text-[14px] font-medium transition-colors",
                  tab === t.valor
                    ? "border-marca bg-marca text-white"
                    : "border-borde bg-superficie text-tinta-2 hover:border-borde-fuerte",
                )}
              >
                {t.etiqueta}
              </button>
            ))}
          </div>

          {tab === "resumen" && <ResumenTab viaje={viaje} />}
          {tab === "paradas" && (
            <Panel titulo="Paradas del viaje" descripcion="Origen, carga, descarga e intermedias.">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>#</TableHead>
                      <TableHead>Tipo</TableHead>
                      <TableHead>Lugar</TableHead>
                      <TableHead>Ventana</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead className="text-right">Acción</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {viaje.paradas.map((parada) => (
                      <TableRow key={parada.id}>
                        <TableCell>{parada.orden}</TableCell>
                        <TableCell className="capitalize">{parada.tipo}</TableCell>
                        <TableCell>
                          <p className="font-medium">{parada.nombre}</p>
                          <p className="text-[13px] text-tinta-3">
                            {[parada.direccion, parada.ciudad].filter(Boolean).join(" · ") || "—"}
                          </p>
                        </TableCell>
                        <TableCell className="text-[13px]">
                          {parada.ventana_desde ? formatFechaHora(parada.ventana_desde) : "—"}
                          <br />
                          <span className="text-tinta-3">
                            {parada.ventana_hasta ? formatFechaHora(parada.ventana_hasta) : "—"}
                          </span>
                        </TableCell>
                        <TableCell>
                          <StatusBadge
                            tono={
                              parada.estado === "completada"
                                ? "ok"
                                : parada.estado === "omitida"
                                  ? "neutro"
                                  : parada.estado === "en_curso"
                                    ? "atencion"
                                    : "info"
                            }
                          >
                            {parada.estado.replaceAll("_", " ")}
                          </StatusBadge>
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-end">
                            <SelectSimple
                              valor={parada.estado}
                              onCambio={(v) => cambiarEstadoParada(parada, v)}
                              opciones={ESTADOS_PARADA}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="grid gap-s3 border-t border-borde p-s4 sm:grid-cols-6">
                <Campo etiqueta="Tipo" className="sm:col-span-1">
                  <SelectSimple
                    valor={nuevaParada.tipo}
                    onCambio={(v) => setNuevaParada((p) => ({ ...p, tipo: v }))}
                    opciones={TIPOS_PARADA}
                  />
                </Campo>
                <Campo etiqueta="Nombre" className="sm:col-span-2">
                  <Input
                    value={nuevaParada.nombre}
                    onChange={(e) => setNuevaParada((p) => ({ ...p, nombre: e.target.value }))}
                    placeholder="Bodega, cliente, predio…"
                  />
                </Campo>
                <Campo etiqueta="Ciudad" className="sm:col-span-1">
                  <Input
                    value={nuevaParada.ciudad}
                    onChange={(e) => setNuevaParada((p) => ({ ...p, ciudad: e.target.value }))}
                  />
                </Campo>
                <Campo etiqueta="Desde" className="sm:col-span-1">
                  <Input
                    type="datetime-local"
                    value={nuevaParada.ventana_desde}
                    onChange={(e) =>
                      setNuevaParada((p) => ({ ...p, ventana_desde: e.target.value }))
                    }
                  />
                </Campo>
                <div className="flex items-end">
                  <Button onClick={crearParada} disabled={procesando}>
                    <Plus /> Agregar
                  </Button>
                </div>
              </div>
            </Panel>
          )}

          {tab === "checklist" && (
            <Panel
              titulo="Checklist del viaje"
              descripcion="Los ítems obligatorios bloquean el cierre. Cada cambio queda auditado."
              acciones={
                <StatusBadge tono={viaje.resumen.checklist_requeridos_pendientes ? "atencion" : "ok"}>
                  {viaje.resumen.checklist_requeridos_pendientes} pendiente(s)
                </StatusBadge>
              }
            >
              <div className="divide-y divide-borde">
                {viaje.checklist.map((item) => (
                  <label
                    key={item.id}
                    className="flex cursor-pointer items-start gap-s3 p-s4 hover:bg-superficie-hundida/40"
                  >
                    <input
                      type="checkbox"
                      className="mt-1 size-4 accent-marca"
                      checked={item.completado}
                      onChange={() => toggleChecklist(item)}
                      disabled={procesando}
                    />
                    <span className="min-w-0 flex-1">
                      <span className={cn("block text-[15px] font-medium", item.completado && "text-tinta-3 line-through")}>
                        {item.item}
                      </span>
                      <span className="mt-0.5 block text-[13px] text-tinta-3">
                        {item.categoria} · {item.requerido ? "obligatorio" : "opcional"}
                        {item.completado_en ? ` · completado ${formatFechaHora(item.completado_en)}` : ""}
                      </span>
                    </span>
                    {item.completado ? (
                      <Check className="size-5 shrink-0 text-ok" />
                    ) : (
                      <XCircle className="size-5 shrink-0 text-tinta-3/40" />
                    )}
                  </label>
                ))}
              </div>
              {viaje.resumen.motivos_cierre.length > 0 && (
                <div className="border-t border-borde bg-atencion-tenue p-s4 text-[14px] text-atencion">
                  <p className="font-semibold">Para cerrar el viaje:</p>
                  <ul className="mt-1 list-inside list-disc">
                    {viaje.resumen.motivos_cierre.map((motivo) => (
                      <li key={motivo}>{motivo}</li>
                    ))}
                  </ul>
                </div>
              )}
            </Panel>
          )}

          {tab === "eventos" && (
            <Panel titulo="Bitácora de eventos" descripcion="Append-only: no se edita ni se borra.">
              <div className="grid gap-s3 border-b border-borde p-s4 sm:grid-cols-6">
                <Campo etiqueta="Tipo" className="sm:col-span-1">
                  <SelectSimple
                    valor={nuevoEvento.tipo}
                    onCambio={(v) => setNuevoEvento((e) => ({ ...e, tipo: v }))}
                    opciones={[
                      { valor: "nota", etiqueta: "Nota" },
                      { valor: "contacto", etiqueta: "Contacto" },
                      { valor: "checkpoint", etiqueta: "Checkpoint" },
                      { valor: "incidente", etiqueta: "Incidente" },
                      { valor: "otro", etiqueta: "Otro" },
                    ]}
                  />
                </Campo>
                <Campo etiqueta="Descripción" className="sm:col-span-4">
                  <Input
                    value={nuevoEvento.descripcion}
                    onChange={(e) =>
                      setNuevoEvento((ev) => ({ ...ev, descripcion: e.target.value }))
                    }
                    placeholder="Ej: llegada a origen, espera en planta…"
                  />
                </Campo>
                <div className="flex items-end">
                  <Button onClick={crearEvento} disabled={procesando}>
                    <Plus /> Registrar
                  </Button>
                </div>
              </div>
              <div className="divide-y divide-borde">
                {viaje.eventos.length === 0 ? (
                  <p className="p-s4 text-[14px] text-tinta-3">Sin eventos.</p>
                ) : (
                  viaje.eventos.map((evento) => (
                    <div key={evento.id} className="flex flex-wrap justify-between gap-s2 p-s4">
                      <div>
                        <p className="text-[15px] font-medium">{evento.descripcion}</p>
                        <p className="text-[13px] text-tinta-3">
                          {evento.tipo} · {evento.auth_id ? `usuario ${evento.auth_id.slice(0, 8)}…` : "sistema"}
                        </p>
                      </div>
                      <p className="text-[13px] text-tinta-3">{formatFechaHora(evento.ocurrido_en)}</p>
                    </div>
                  ))
                )}
              </div>
            </Panel>
          )}

          {tab === "incidentes" && (
            <Panel titulo="Incidentes" descripcion="Los incidentes alta/crítica abiertos bloquean el cierre.">
              <div className="grid gap-s3 border-b border-borde p-s4 sm:grid-cols-6">
                <Campo etiqueta="Tipo" className="sm:col-span-1">
                  <Input
                    value={nuevoIncidente.tipo}
                    onChange={(e) => setNuevoIncidente((i) => ({ ...i, tipo: e.target.value }))}
                  />
                </Campo>
                <Campo etiqueta="Severidad" className="sm:col-span-1">
                  <SelectSimple
                    valor={nuevoIncidente.severidad}
                    onCambio={(v) => setNuevoIncidente((i) => ({ ...i, severidad: v }))}
                    opciones={SEVERIDADES}
                  />
                </Campo>
                <Campo etiqueta="Descripción" className="sm:col-span-3">
                  <Input
                    value={nuevoIncidente.descripcion}
                    onChange={(e) =>
                      setNuevoIncidente((i) => ({ ...i, descripcion: e.target.value }))
                    }
                  />
                </Campo>
                <div className="flex items-end">
                  <Button onClick={crearIncidente} disabled={procesando}>
                    <Plus /> Reportar
                  </Button>
                </div>
              </div>
              <div className="divide-y divide-borde">
                {viaje.incidentes.length === 0 ? (
                  <p className="p-s4 text-[14px] text-tinta-3">Sin incidentes registrados.</p>
                ) : (
                  viaje.incidentes.map((incidente) => (
                    <div key={incidente.id} className="flex flex-wrap items-start justify-between gap-s3 p-s4">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-s2">
                          <StatusBadge tono={tonoIncidente(incidente.severidad)}>
                            {incidente.severidad}
                          </StatusBadge>
                          <span className="text-[15px] font-medium">{incidente.tipo}</span>
                          <StatusBadge tono={incidente.estado === "resuelto" ? "ok" : "atencion"}>
                            {incidente.estado.replaceAll("_", " ")}
                          </StatusBadge>
                        </div>
                        <p className="mt-s1 text-[14px] text-tinta-2">{incidente.descripcion}</p>
                        {incidente.resolucion && (
                          <p className="mt-s1 text-[13px] text-ok">Resolución: {incidente.resolucion}</p>
                        )}
                        <p className="text-[12px] text-tinta-3">{formatFechaHora(incidente.ocurrido_en)}</p>
                      </div>
                      {["abierto", "en_revision"].includes(incidente.estado) && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => resolverIncidente(incidente)}
                          disabled={procesando}
                        >
                          <Check /> Resolver
                        </Button>
                      )}
                    </div>
                  ))
                )}
              </div>
            </Panel>
          )}

          {tab === "documentos" && (
            <Panel
              titulo="Documentos del viaje"
              descripcion="PDF, JPG, PNG, WEBP o HEIC; máximo 10 MB."
              acciones={
                <label className="cursor-pointer">
                  <input
                    type="file"
                    className="hidden"
                    accept=".pdf,.jpg,.jpeg,.png,.webp,.heic"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void subirDocumento(file);
                      e.target.value = "";
                    }}
                  />
                  <span className="inline-flex items-center gap-2 rounded-lg border border-borde-fuerte bg-superficie px-3 py-2 text-[14px] font-medium hover:border-tinta-3/50">
                    <Upload className="size-4" /> Subir documento
                  </span>
                </label>
              }
            >
              <div className="divide-y divide-borde">
                {viaje.documentos.length === 0 ? (
                  <p className="p-s4 text-[14px] text-tinta-3">Sin documentos adjuntos.</p>
                ) : (
                  viaje.documentos.map((doc) => (
                    <div key={doc.id} className="flex flex-wrap items-center justify-between gap-s3 p-s4">
                      <div className="flex min-w-0 items-center gap-s3">
                        <span className="grid size-9 place-items-center rounded-lg bg-superficie-hundida text-tinta-3">
                          <FileText className="size-4" />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-[15px] font-medium">{doc.nombre}</p>
                          <p className="text-[13px] text-tinta-3">
                            {doc.tipo} · {doc.tamano_bytes ? `${(doc.tamano_bytes / 1024).toFixed(0)} KB` : "—"} ·{" "}
                            {formatFechaHora(doc.created_at)}
                          </p>
                        </div>
                      </div>
                      {doc.url_firmada && (
                        <a
                          href={doc.url_firmada}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-2 text-[14px] font-medium text-marca hover:underline"
                        >
                          <Download className="size-4" /> Abrir
                        </a>
                      )}
                    </div>
                  ))
                )}
              </div>
            </Panel>
          )}

          {tab === "pod" && (
            <PODPanel
              empresaId={empresaId}
              viaje={viaje}
              onCambio={() => void cargar(true)}
            />
          )}

          {tab === "gastos" && (
            <GastosPanel
              empresaId={empresaId}
              viaje={viaje}
              rol={empresa?.rol ?? ""}
              onCambio={() => void cargar(true)}
            />
          )}

          {tab === "rentabilidad" && (
            <RentabilidadViajePanel empresaId={empresaId} viajeId={viaje.id} />
          )}

          {tab === "auditoria" && (
            <Panel titulo="Auditoría" descripcion="Cambios del viaje, paradas, checklist, incidentes y documentos.">
              <div className="divide-y divide-borde">
                {viaje.historial.length === 0 ? (
                  <p className="p-s4 text-[14px] text-tinta-3">Sin registros.</p>
                ) : (
                  viaje.historial.map((h) => (
                    <div key={h.id} className="flex flex-wrap justify-between gap-s2 p-s3">
                      <div>
                        <p className="text-[14px] font-medium">
                          {h.operacion} · {h.tabla.replace("nucleo.", "")}
                        </p>
                        <p className="text-[13px] text-tinta-3">
                          {h.auth_id ? `usuario ${h.auth_id.slice(0, 8)}…` : "sistema"}
                        </p>
                      </div>
                      <p className="text-[13px] text-tinta-3">{formatFechaHora(h.ocurrido_en)}</p>
                    </div>
                  ))
                )}
              </div>
            </Panel>
          )}
        </>
      ) : null}
    </div>
  );
}

function ResumenTab({ viaje }: { viaje: ViajeExpedienteNucleo }) {
  return (
    <div className="grid gap-s4 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-s4">
        <Panel titulo="Ruta y ventana" descripcion={`Buffer ${viaje.buffer_minutos} min`}>
          <div className="grid gap-s4 p-s4 sm:grid-cols-2">
            <div className="space-y-s1">
              <p className="rotulo">Origen</p>
              <p className="flex items-center gap-2 text-[17px] font-semibold">
                <MapPin className="size-4 text-marca" /> {viaje.origen_nombre}
              </p>
              <p className="text-[14px] text-tinta-3">
                {[viaje.origen_direccion, viaje.origen_comuna, viaje.origen_ciudad]
                  .filter(Boolean)
                  .join(" · ") || "Sin dirección"}
              </p>
              <p className="text-[13px] text-tinta-3">
                {formatFechaHora(viaje.inicio_planificado)} → {formatFechaHora(viaje.fin_planificado)}
              </p>
            </div>
            <div className="space-y-s1">
              <p className="rotulo">Destino</p>
              <p className="flex items-center gap-2 text-[17px] font-semibold">
                <MapPin className="size-4 text-critico" /> {viaje.destino_nombre}
              </p>
              <p className="text-[14px] text-tinta-3">
                {[viaje.destino_direccion, viaje.destino_comuna, viaje.destino_ciudad]
                  .filter(Boolean)
                  .join(" · ") || "Sin dirección"}
              </p>
              <p className="text-[13px] text-tinta-3">
                {viaje.distancia_km ? `${Number(viaje.distancia_km).toLocaleString("es-CL")} km` : "Distancia no informada"}
              </p>
            </div>
          </div>
        </Panel>

        <Panel titulo="Carga">
          <div className="grid gap-s3 p-s4 text-[14px] sm:grid-cols-2">
            <p><span className="text-tinta-3">Tipo:</span> {viaje.tipo_carga.replaceAll("_", " ")}</p>
            <p><span className="text-tinta-3">Peso bruto:</span> {viaje.peso_bruto_kg ? `${Number(viaje.peso_bruto_kg).toLocaleString("es-CL")} kg` : "—"}</p>
            <p><span className="text-tinta-3">Volumen:</span> {viaje.volumen_m3 ? `${Number(viaje.volumen_m3).toLocaleString("es-CL")} m³` : "—"}</p>
            <p><span className="text-tinta-3">Valor declarado:</span> {viaje.valor_declarado ? formatCLP(viaje.valor_declarado) : "—"}</p>
            <p><span className="text-tinta-3">Peligrosa:</span> {viaje.carga_peligrosa ? `Sí (UN ${viaje.numero_un ?? "—"})` : "No"}</p>
            <p><span className="text-tinta-3">Refrigerada:</span> {viaje.refrigerada ? `${viaje.temperatura_min_c ?? "—"} a ${viaje.temperatura_max_c ?? "—"} °C` : "No"}</p>
            {viaje.descripcion_carga && (
              <p className="sm:col-span-2"><span className="text-tinta-3">Descripción:</span> {viaje.descripcion_carga}</p>
            )}
            {viaje.instrucciones_especiales && (
              <p className="sm:col-span-2"><span className="text-tinta-3">Instrucciones:</span> {viaje.instrucciones_especiales}</p>
            )}
          </div>
        </Panel>

        <Panel titulo="Documentos y evidencia" descripcion="Adjuntos y código QR del expediente.">
          <div className="flex flex-wrap items-center gap-s5 p-s4">
            <div className="rounded-xl border border-borde bg-white p-s2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={viaje.qr_url} alt={`QR ${viaje.numero_viaje}`} className="size-36" />
            </div>
            <div className="space-y-s1 text-[14px] text-tinta-2">
              <p className="flex items-center gap-2 font-medium"><QrCode className="size-4" /> Escanee para abrir el expediente</p>
              <p className="text-tinta-3">El QR contiene el folio y el enlace al detalle del viaje.</p>
              <p className="text-tinta-3">{viaje.documentos.length} documento(s) adjunto(s).</p>
            </div>
          </div>
        </Panel>
      </div>

      <div className="space-y-s4">
        <Panel titulo="Recursos y finanzas">
          <div className="space-y-s3 p-s4 text-[14px]">
            <div className="flex flex-wrap items-center gap-s2">
              {viaje.tracto_patente ? <Patente>{viaje.tracto_patente}</Patente> : <span>Sin tracto</span>}
              {viaje.rampla_patente ? <Patente>{viaje.rampla_patente}</Patente> : null}
            </div>
            <p><span className="text-tinta-3">Chofer:</span> {viaje.chofer_nombre ?? "Sin asignar"}</p>
            <p><span className="text-tinta-3">Cliente:</span> {viaje.cliente_nombre} · {viaje.cliente_rut ?? "—"}</p>
            <p><span className="text-tinta-3">OC:</span> {viaje.oc_numero ?? "Sin OC"}</p>
            <p><span className="text-tinta-3">Tarifa:</span> {viaje.tarifa_codigo ?? "—"}</p>
            <div className="rounded-lg border border-borde bg-superficie-hundida/50 p-s3">
              <p className="flex justify-between"><span className="text-tinta-3">Flete neto</span> <span className="cifra">{formatCLP(viaje.valor_flete_neto)}</span></p>
              <p className="flex justify-between"><span className="text-tinta-3">Recargos</span> <span className="cifra">{formatCLP(viaje.monto_recargos)}</span></p>
              <p className="mt-s1 flex justify-between border-t border-borde pt-s1 font-semibold"><span>Total</span> <span className="cifra">{formatCLP(viaje.monto_total_neto ?? viaje.valor_flete_neto)}</span></p>
            </div>
            <p><span className="text-tinta-3">Pago:</span> {viaje.condiciones_pago_dias ?? "—"} días</p>
            <p><span className="text-tinta-3">Creado:</span> {formatFecha(viaje.created_at.slice(0, 10))}</p>
          </div>
        </Panel>

        {viaje.factura && (
          <Panel titulo="Factura" descripcion={viaje.factura.numero_factura}>
            <div className="space-y-s2 p-s4 text-[14px]">
              <p className="flex justify-between"><span className="text-tinta-3">Estado</span> <StatusBadge tono={viaje.factura.estado === "pagada" ? "ok" : viaje.factura.estado === "parcial" ? "atencion" : "info"}>{viaje.factura.estado}</StatusBadge></p>
              <p className="flex justify-between"><span className="text-tinta-3">Total</span> <span className="cifra">{formatCLP(viaje.factura.total)}</span></p>
              <p className="flex justify-between"><span className="text-tinta-3">Pagado</span> <span className="cifra">{formatCLP(viaje.factura.pagado)}</span></p>
              <p className="flex justify-between font-semibold"><span>Saldo</span> <span className="cifra">{formatCLP(viaje.factura.saldo)}</span></p>
              <p className="text-[13px] text-tinta-3">Vence {formatFecha(viaje.factura.fecha_vencimiento)}</p>
            </div>
          </Panel>
        )}

        <Panel titulo="Cierre" descripcion="Checklist completo y sin incidentes críticos.">
          <div className="space-y-s3 p-s4 text-[14px]">
            <p className="flex items-center gap-2">
              {viaje.resumen.puede_cerrar ? (
                <><CheckCircle2 className="size-5 text-ok" /> Listo para cerrar</>
              ) : (
                <><AlertTriangle className="size-5 text-atencion" /> Aún no se puede cerrar</>
              )}
            </p>
            {viaje.resumen.motivos_cierre.length > 0 && (
              <ul className="list-inside list-disc space-y-s1 text-tinta-3">
                {viaje.resumen.motivos_cierre.map((m) => <li key={m}>{m}</li>)}
              </ul>
            )}
            <p className="text-tinta-3">
              {viaje.resumen.checklist_completados}/{viaje.resumen.checklist_total} ítems completados.
            </p>
          </div>
        </Panel>
      </div>
    </div>
  );
}
