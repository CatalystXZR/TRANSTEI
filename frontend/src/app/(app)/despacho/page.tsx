"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Container,
  MapPin,
  Plus,
  RefreshCw,
  Route,
  Truck,
  UserRound,
  Weight,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { getEmpresas, nucleo, NucleoError } from "@/lib/nucleo";
import { formatCLP, formatFechaHora, toDatetimeLocal } from "@/lib/format";
import type {
  EmpresaNucleo,
  IncidenciaNucleo,
  ListaRecursosNucleo,
  ListaViajesNucleo,
  RecursoNucleo,
  ResultadoNucleo,
  TipoRecurso,
  ViajeNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { NuevoViajeDialog } from "@/components/despacho/nuevo-viaje-dialog";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Campo, SelectSimple } from "@/components/formulario";
import {
  Aviso,
  EstadoVacio,
  PageHeader,
  Panel,
  Patente,
  Segmentado,
  StatTile,
  StatusBadge,
  type Tono,
} from "@/components/sistema";

const TIPOS: TipoRecurso[] = ["tracto", "rampla", "chofer"];

const TIPO_LABEL: Record<TipoRecurso, string> = {
  tracto: "Tractos",
  rampla: "Ramplas",
  chofer: "Choferes",
};

const TIPO_SINGULAR: Record<TipoRecurso, string> = {
  tracto: "tracto",
  rampla: "rampla",
  chofer: "chofer",
};

const ICONO_TIPO = {
  tracto: Truck,
  rampla: Container,
  chofer: UserRound,
} as const;

type FormAsignacion = {
  tracto_id: string;
  rampla_id: string;
  chofer_id: string;
  inicio: string;
  fin: string;
  minutos_traslado: string;
  motivo_reasignacion: string;
};

const FORM_VACIO: FormAsignacion = {
  tracto_id: "",
  rampla_id: "",
  chofer_id: "",
  inicio: "",
  fin: "",
  minutos_traslado: "0",
  motivo_reasignacion: "",
};

function tonoRecurso(recurso: RecursoNucleo): Tono {
  if (recurso.disponible) return "ok";
  if (recurso.incidencias.some((i) => i.bloqueante)) return "critico";
  return "atencion";
}

function tonoViaje(viaje: ViajeNucleo): Tono {
  if (viaje.estado === "asignado") return "info";
  if (viaje.estado === "confirmado") return "atencion";
  return "neutro";
}

function etiquetaViaje(viaje: ViajeNucleo): string {
  if (viaje.estado === "confirmado") return "Por asignar";
  if (viaje.estado === "asignado") return "Asignado";
  return viaje.estado.replaceAll("_", " ");
}

function resumenRecurso(recurso: RecursoNucleo | undefined): string {
  if (!recurso) return "Seleccione un recurso";
  const libre = recurso.libre_desde
    ? `Libre desde ${formatFechaHora(recurso.libre_desde)}`
    : "No asignable";
  const docs = recurso.documentos_ok ? "documentos al día" : "documentos con bloqueo";
  return `${libre} · ${docs}`;
}

export default function DespachoPage() {
  const [empresas, setEmpresas] = useState<EmpresaNucleo[]>([]);
  const [empresaId, setEmpresaId] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [viajes, setViajes] = useState<ViajeNucleo[]>([]);
  const [recursos, setRecursos] = useState<Record<TipoRecurso, RecursoNucleo[]>>({
    tracto: [],
    rampla: [],
    chofer: [],
  });
  const [tab, setTab] = useState<TipoRecurso>("tracto");
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [errorCarga, setErrorCarga] = useState<string | null>(null);

  const [nuevoAbierto, setNuevoAbierto] = useState(false);
  const [viajeSel, setViajeSel] = useState<ViajeNucleo | null>(null);
  const [form, setForm] = useState<FormAsignacion>(FORM_VACIO);
  const [validacion, setValidacion] = useState<ResultadoNucleo | null>(null);
  const [validando, setValidando] = useState(false);
  const [asignando, setAsignando] = useState(false);
  const [errorAsignacion, setErrorAsignacion] = useState<string | null>(null);
  const [erroresAsignacion, setErroresAsignacion] = useState<IncidenciaNucleo[]>([]);

  useEffect(() => {
    const inicializarFechas = setTimeout(() => {
      const ahora = new Date();
      const inicio = new Date(ahora);
      inicio.setHours(0, 0, 0, 0);
      const fin = new Date(inicio);
      fin.setDate(fin.getDate() + 7);
      fin.setHours(23, 59, 0, 0);
      setDesde(toDatetimeLocal(inicio));
      setHasta(toDatetimeLocal(fin));
    }, 0);

    let activo = true;
    getEmpresas()
      .then((data) => {
        if (!activo) return;
        setEmpresas(data);
        if (data[0]) {
          setEmpresaId(data[0].id);
        } else {
          setErrorCarga("El usuario no tiene una empresa activa asignada.");
          setCargando(false);
        }
      })
      .catch((e) => {
        if (!activo) return;
        setErrorCarga(e instanceof Error ? e.message : "No se pudieron cargar las empresas");
        setCargando(false);
      });
    return () => {
      activo = false;
      clearTimeout(inicializarFechas);
    };
  }, []);

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!empresaId || !desde || !hasta) return;
      if (silencioso) setActualizando(true);
      else setCargando(true);
      setErrorCarga(null);
      try {
        const desdeISO = new Date(desde).toISOString();
        const hastaISO = new Date(hasta).toISOString();
        const qs = `desde=${encodeURIComponent(desdeISO)}&hasta=${encodeURIComponent(hastaISO)}&solo_aptos=false&limit=50`;
        const [listaViajes, tractos, ramplas, choferes] = await Promise.all([
          nucleo.get<ListaViajesNucleo>(
            `/nucleo/viajes?desde=${encodeURIComponent(desdeISO)}&hasta=${encodeURIComponent(hastaISO)}&limit=100`,
            empresaId,
          ),
          nucleo.get<ListaRecursosNucleo>(`/nucleo/disponibilidad/recursos?tipo=tracto&${qs}`, empresaId),
          nucleo.get<ListaRecursosNucleo>(`/nucleo/disponibilidad/recursos?tipo=rampla&${qs}`, empresaId),
          nucleo.get<ListaRecursosNucleo>(`/nucleo/disponibilidad/recursos?tipo=chofer&${qs}`, empresaId),
        ]);
        setViajes(listaViajes.items);
        setRecursos({
          tracto: tractos.items,
          rampla: ramplas.items,
          chofer: choferes.items,
        });
      } catch (e) {
        setErrorCarga(e instanceof Error ? e.message : "Error al cargar la mesa de despacho");
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId, desde, hasta],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  const empresa = empresas.find((e) => e.id === empresaId);
  const porAsignar = viajes.filter((v) => v.estado === "confirmado").length;
  const disponibles = {
    tracto: recursos.tracto.filter((r) => r.disponible).length,
    rampla: recursos.rampla.filter((r) => r.disponible).length,
    chofer: recursos.chofer.filter((r) => r.disponible).length,
  };
  const totales = {
    tracto: recursos.tracto.length,
    rampla: recursos.rampla.length,
    chofer: recursos.chofer.length,
  };

  function setRecurso(tipo: TipoRecurso, valor: string) {
    if (tipo === "tracto") setForm((f) => ({ ...f, tracto_id: valor }));
    else if (tipo === "rampla") setForm((f) => ({ ...f, rampla_id: valor }));
    else setForm((f) => ({ ...f, chofer_id: valor }));
    setValidacion(null);
    setErrorAsignacion(null);
    setErroresAsignacion([]);
  }

  function abrirAsignacion(viaje: ViajeNucleo) {
    const primerDisponible = (tipo: TipoRecurso) =>
      recursos[tipo].find((r) => r.disponible)?.id ?? "";
    setViajeSel(viaje);
    setForm({
      tracto_id: viaje.tracto_id ?? primerDisponible("tracto"),
      rampla_id: viaje.rampla_id ?? primerDisponible("rampla"),
      chofer_id: viaje.chofer_id ?? primerDisponible("chofer"),
      inicio: toDatetimeLocal(viaje.inicio_planificado),
      fin: toDatetimeLocal(viaje.fin_planificado),
      minutos_traslado: "0",
      motivo_reasignacion: "",
    });
    setValidacion(null);
    setErrorAsignacion(null);
    setErroresAsignacion([]);
  }

  function cerrarDialogo(open: boolean) {
    if (!open && !asignando) setViajeSel(null);
  }

  function bodyAsignacion(incluirViaje: boolean) {
    if (!viajeSel) throw new Error("No hay viaje seleccionado");
    if (!form.tracto_id || !form.rampla_id || !form.chofer_id) {
      throw new Error("Seleccione tracto, rampla y chofer");
    }
    if (!form.inicio || !form.fin) {
      throw new Error("Defina la ventana del viaje");
    }
    return {
      ...(incluirViaje ? { viaje_id: viajeSel.id } : {}),
      tracto_id: form.tracto_id,
      rampla_id: form.rampla_id,
      chofer_id: form.chofer_id,
      inicio_planificado: new Date(form.inicio).toISOString(),
      fin_planificado: new Date(form.fin).toISOString(),
      minutos_traslado: Number(form.minutos_traslado) || 0,
      ...(form.motivo_reasignacion.trim()
        ? { motivo_reasignacion: form.motivo_reasignacion.trim() }
        : {}),
    };
  }

  async function validar() {
    if (!viajeSel) return;
    setValidando(true);
    setErrorAsignacion(null);
    setErroresAsignacion([]);
    try {
      const body = bodyAsignacion(true);
      const resultado = await nucleo.post<ResultadoNucleo>(
        "/nucleo/disponibilidad/validar-asignacion",
        empresaId,
        body,
      );
      setValidacion(resultado);
    } catch (e) {
      setValidacion(null);
      setErrorAsignacion(e instanceof Error ? e.message : "Error al validar");
      if (e instanceof NucleoError) setErroresAsignacion(e.errores);
    } finally {
      setValidando(false);
    }
  }

  async function confirmar() {
    if (!viajeSel) return;
    setAsignando(true);
    setErrorAsignacion(null);
    setErroresAsignacion([]);
    try {
      const body = bodyAsignacion(false);
      await nucleo.post(
        `/nucleo/viajes/${viajeSel.id}/asignar`,
        empresaId,
        body,
      );
      toast.success(`Viaje ${viajeSel.numero_viaje} asignado`);
      setViajeSel(null);
      setValidacion(null);
      await cargar(true);
    } catch (e) {
      setErrorAsignacion(e instanceof Error ? e.message : "Error al asignar");
      if (e instanceof NucleoError) setErroresAsignacion(e.errores);
    } finally {
      setAsignando(false);
    }
  }

  const seleccionados = {
    tracto: recursos.tracto.find((r) => r.id === form.tracto_id),
    rampla: recursos.rampla.find((r) => r.id === form.rampla_id),
    chofer: recursos.chofer.find((r) => r.id === form.chofer_id),
  };

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Operación"
        titulo="Mesa de despacho"
        descripcion="Vea qué tracto, rampla y chofer están libres, valide el cumplimiento y asigne el viaje sin dobles reservas."
        acciones={
          <>
            <Button
              variant="outline"
              onClick={() => void cargar(true)}
              disabled={!empresaId || actualizando}
            >
              <RefreshCw className={cn("size-4", actualizando && "animate-spin")} />
              Actualizar
            </Button>
            <Button onClick={() => setNuevoAbierto(true)} disabled={!empresaId}>
              <Plus /> Nuevo viaje
            </Button>
          </>
        }
      />

      {errorCarga && (
        <Aviso tono="critico" icono={AlertTriangle}>
          {errorCarga}
        </Aviso>
      )}

      <Panel
        titulo="Ventana de planificación"
        descripcion={empresa ? `${empresa.razon_social} · buffer ${empresa.buffer_operacional_min} min` : undefined}
        className="p-s3"
      >
        <div className="flex flex-wrap items-end gap-s3">
          <label className="space-y-s1 text-[14px] font-medium text-tinta-2">
            <span className="block">Desde</span>
            <Input
              type="datetime-local"
              value={desde}
              onChange={(e) => setDesde(e.target.value)}
              className="w-[230px]"
            />
          </label>
          <label className="space-y-s1 text-[14px] font-medium text-tinta-2">
            <span className="block">Hasta</span>
            <Input
              type="datetime-local"
              value={hasta}
              onChange={(e) => setHasta(e.target.value)}
              className="w-[230px]"
            />
          </label>
          <p className="pb-2 text-[14px] text-tinta-3">
            La disponibilidad se calcula en UTC y se muestra en hora de Chile.
          </p>
        </div>
      </Panel>

      <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          etiqueta="Tractos disponibles"
          valor={`${disponibles.tracto}/${totales.tracto}`}
          detalle="Con documentos y ventana libre"
          tono={disponibles.tracto > 0 ? "ok" : "critico"}
          icono={Truck}
          destacado
        />
        <StatTile
          etiqueta="Ramplas disponibles"
          valor={`${disponibles.rampla}/${totales.rampla}`}
          detalle="Compatibles con la ventana consultada"
          tono={disponibles.rampla > 0 ? "ok" : "critico"}
          icono={Container}
        />
        <StatTile
          etiqueta="Choferes disponibles"
          valor={`${disponibles.chofer}/${totales.chofer}`}
          detalle="Licencia y examen al día"
          tono={disponibles.chofer > 0 ? "ok" : "critico"}
          icono={UserRound}
        />
        <StatTile
          etiqueta="Viajes por asignar"
          valor={porAsignar}
          detalle={`${viajes.length} viaje(s) en la ventana`}
          tono={porAsignar === 0 ? "ok" : "atencion"}
          icono={CalendarClock}
        />
      </div>

      <div className="grid gap-s4 xl:grid-cols-[1.15fr_0.85fr]">
        <Panel
          titulo="Viajes"
          descripcion="Confirmados por asignar y asignados para reasignar"
          acciones={<StatusBadge tono="info">{viajes.length} en ventana</StatusBadge>}
        >
          {cargando ? (
            <div className="space-y-s3 p-s4">
              <div className="h-28 animate-pulse rounded-xl bg-superficie-hundida" />
              <div className="h-28 animate-pulse rounded-xl bg-superficie-hundida" />
            </div>
          ) : viajes.length === 0 ? (
            <EstadoVacio
              icono={CalendarClock}
              titulo="No hay viajes en la ventana"
              descripcion="Cree un viaje en el núcleo o amplíe el rango de fechas."
            />
          ) : (
            <div className="divide-y divide-borde">
              {viajes.map((viaje) => (
                <article key={viaje.id} className="space-y-s3 p-s4">
                  <div className="flex flex-wrap items-start justify-between gap-s3">
                    <div className="min-w-0">
                      <p className="font-mono text-[13px] font-semibold tracking-wide text-tinta-3">
                        {viaje.numero_viaje}
                      </p>
                      <h3 className="mt-s1 flex items-center gap-2 text-[20px] leading-tight font-semibold">
                        <MapPin className="size-4 text-marca" />
                        {viaje.origen}
                        <ArrowRight className="size-4 text-tinta-3" />
                        {viaje.destino}
                      </h3>
                      <p className="mt-s1 text-[15px] text-tinta-3">{viaje.cliente_nombre}</p>
                    </div>
                    <div className="flex flex-col items-end gap-s2">
                      <StatusBadge tono={tonoViaje(viaje)}>{etiquetaViaje(viaje)}</StatusBadge>
                      <p className="cifra text-[22px] font-semibold">{formatCLP(viaje.flete_total)}</p>
                    </div>
                  </div>

                  <div className="grid gap-s2 text-[14px] text-tinta-2 sm:grid-cols-2">
                    <p className="flex items-center gap-2">
                      <Clock3 className="size-4 text-tinta-3" />
                      {formatFechaHora(viaje.inicio_planificado)} → {formatFechaHora(viaje.fin_planificado)}
                    </p>
                    <p className="flex items-center gap-2">
                      <Route className="size-4 text-tinta-3" />
                      {viaje.oc_numero ?? "Sin OC"} · {viaje.tarifa_codigo ?? "Sin tarifa"}
                    </p>
                    <p className="flex items-center gap-2">
                      <Weight className="size-4 text-tinta-3" />
                      {viaje.peso_bruto_kg ? `${Number(viaje.peso_bruto_kg).toLocaleString("es-CL")} kg` : "Sin peso"}
                      {viaje.refrigerada ? " · Refrigerada" : ""}
                      {viaje.carga_peligrosa ? " · Peligrosa" : ""}
                    </p>
                    <p className="flex items-center gap-2">
                      <Truck className="size-4 text-tinta-3" />
                      {viaje.tracto_patente ? (
                        <>
                          <Patente>{viaje.tracto_patente}</Patente>
                          <span>·</span>
                          <Patente>{viaje.rampla_patente}</Patente>
                        </>
                      ) : (
                        "Sin recursos asignados"
                      )}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-s2">
                    <p className="text-[14px] text-tinta-3">
                      {viaje.chofer_nombre ?? "Sin chofer asignado"}
                    </p>
                    <Button size="sm" onClick={() => abrirAsignacion(viaje)}>
                      {viaje.estado === "asignado" ? "Reasignar" : "Asignar"}
                      <ArrowRight />
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          titulo="Disponibilidad"
          descripcion="Documentos, bloqueos y próxima reserva"
        >
          <div className="p-s3">
            <Segmentado
              etiqueta="Tipo de recurso"
              valor={tab}
              onCambio={setTab}
              opciones={TIPOS.map((tipo) => ({
                valor: tipo,
                etiqueta: TIPO_LABEL[tipo],
                contador: disponibles[tipo],
              }))}
            />
          </div>
          {cargando ? (
            <div className="space-y-s3 p-s4">
              <div className="h-20 animate-pulse rounded-xl bg-superficie-hundida" />
              <div className="h-20 animate-pulse rounded-xl bg-superficie-hundida" />
            </div>
          ) : recursos[tab].length === 0 ? (
            <EstadoVacio
              icono={ICONO_TIPO[tab]}
              titulo={`Sin ${TIPO_SINGULAR[tab]}s configurados`}
              descripcion="Cargue los maestros de flota o amplíe la ventana de fechas."
            />
          ) : (
            <div className="divide-y divide-borde">
              {recursos[tab].map((recurso) => (
                <RecursoCard key={recurso.id} recurso={recurso} />
              ))}
            </div>
          )}
        </Panel>
      </div>

      {nuevoAbierto && (
        <NuevoViajeDialog
          empresaId={empresaId}
          onClose={() => setNuevoAbierto(false)}
          onCreado={() => {
            setNuevoAbierto(false);
            void cargar(true);
          }}
        />
      )}

      <Dialog open={!!viajeSel} onOpenChange={cerrarDialogo}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              {viajeSel?.estado === "asignado" ? "Reasignar viaje" : "Asignar viaje"}{" "}
              {viajeSel?.numero_viaje}
            </DialogTitle>
            <DialogDescription>
              {viajeSel
                ? `${viajeSel.cliente_nombre} · ${viajeSel.origen} → ${viajeSel.destino}`
                : ""}
            </DialogDescription>
          </DialogHeader>

          {viajeSel && (
            <>
              <div className="grid gap-s2 rounded-xl border border-borde bg-superficie-hundida/60 p-s3 text-[14px] text-tinta-2 sm:grid-cols-2">
                <p>Salida: {formatFechaHora(viajeSel.inicio_planificado)}</p>
                <p>Llegada: {formatFechaHora(viajeSel.fin_planificado)}</p>
                <p>OC: {viajeSel.oc_numero ?? "Sin OC (no facturable)"}</p>
                <p>Flete: {formatCLP(viajeSel.flete_total)}</p>
              </div>

              <fieldset className="space-y-s3 border-0">
                <legend className="rotulo float-left mb-s2 w-full">Recursos</legend>
                <div className="grid gap-s3 sm:grid-cols-3">
                  {TIPOS.map((tipo) => {
                    const Icono = ICONO_TIPO[tipo];
                    return (
                      <Campo
                        key={tipo}
                        etiqueta={TIPO_LABEL[tipo]}
                        htmlFor={`asignar-${tipo}`}
                        requerido
                        ayuda={resumenRecurso(seleccionados[tipo])}
                      >
                        <div className="relative">
                          <Icono className="pointer-events-none absolute top-1/2 left-3 z-10 size-4 -translate-y-1/2 text-tinta-3" />
                          <SelectSimple
                            id={`asignar-${tipo}`}
                            valor={form[`${tipo}_id` as keyof FormAsignacion] as string}
                            onCambio={(v) => setRecurso(tipo, v)}
                            placeholder={`Seleccione ${TIPO_SINGULAR[tipo]}`}
                            className="pl-9"
                            opciones={recursos[tipo].map((r) => ({
                              valor: r.id,
                              etiqueta: `${r.etiqueta}${r.disponible ? "" : " · no disponible"}`,
                            }))}
                          />
                        </div>
                      </Campo>
                    );
                  })}
                </div>
              </fieldset>

              <fieldset className="space-y-s3 border-0">
                <legend className="rotulo float-left mb-s2 w-full">Ventana y traslado</legend>
                <div className="grid gap-s3 sm:grid-cols-3">
                  <Campo etiqueta="Inicio" htmlFor="asignar-inicio" requerido>
                    <Input
                      id="asignar-inicio"
                      type="datetime-local"
                      value={form.inicio}
                      onChange={(e) => {
                        setForm((f) => ({ ...f, inicio: e.target.value }));
                        setValidacion(null);
                      }}
                    />
                  </Campo>
                  <Campo etiqueta="Fin" htmlFor="asignar-fin" requerido>
                    <Input
                      id="asignar-fin"
                      type="datetime-local"
                      value={form.fin}
                      onChange={(e) => {
                        setForm((f) => ({ ...f, fin: e.target.value }));
                        setValidacion(null);
                      }}
                    />
                  </Campo>
                  <Campo
                    etiqueta="Traslado en vacío"
                    htmlFor="asignar-traslado"
                    ayuda="Minutos desde la posición actual hasta el origen"
                  >
                    <Input
                      id="asignar-traslado"
                      type="number"
                      min={0}
                      max={1440}
                      value={form.minutos_traslado}
                      onChange={(e) => {
                        setForm((f) => ({ ...f, minutos_traslado: e.target.value }));
                        setValidacion(null);
                      }}
                    />
                  </Campo>
                </div>
              </fieldset>

              {viajeSel.estado === "asignado" && (
                <Campo
                  etiqueta="Motivo de reasignación"
                  htmlFor="asignar-motivo"
                  ayuda="Obligatorio si cambia recursos o ventana; queda en auditoría."
                >
                  <Input
                    id="asignar-motivo"
                    value={form.motivo_reasignacion}
                    onChange={(e) => {
                      setForm((f) => ({ ...f, motivo_reasignacion: e.target.value }));
                      setValidacion(null);
                    }}
                    placeholder="Ej: camión en taller, cliente adelantó la carga"
                  />
                </Campo>
              )}

              {errorAsignacion && (
                <Aviso tono="critico" icono={AlertTriangle}>
                  {errorAsignacion}
                </Aviso>
              )}

              {validacion && (
                <div className="space-y-s3">
                  <Aviso
                    tono={validacion.apto ? "ok" : "critico"}
                    icono={validacion.apto ? CheckCircle2 : AlertTriangle}
                  >
                    <p className="font-medium">{validacion.mensaje}</p>
                    {validacion.apto && (
                      <p className="mt-s1 text-[14px]">
                        Libre desde {formatFechaHora(validacion.libre_desde)} · inicio operativo{" "}
                        {formatFechaHora(validacion.inicio_operativo_posible)}
                      </p>
                    )}
                  </Aviso>

                  {validacion.incidencias.filter(
                    (i) => i.bloqueante && i.codigo !== "CONFLICTO_RESERVA",
                  ).length > 0 && (
                    <div className="rounded-xl border border-critico/20 bg-critico-tenue p-s3">
                      <p className="text-[14px] font-semibold text-critico">Bloqueos</p>
                      <ul className="mt-s2 space-y-s1 text-[14px] text-critico">
                        {validacion.incidencias
                          .filter((i) => i.bloqueante && i.codigo !== "CONFLICTO_RESERVA")
                          .map((i, idx) => (
                            <li key={`${i.codigo}-${idx}`}>• {i.mensaje}</li>
                          ))}
                      </ul>
                    </div>
                  )}

                  {validacion.conflictos.length > 0 && (
                    <div className="rounded-xl border border-critico/20 bg-critico-tenue p-s3">
                      <p className="text-[14px] font-semibold text-critico">Conflictos de reserva</p>
                      <ul className="mt-s2 space-y-s1 text-[14px] text-critico">
                        {validacion.conflictos.map((c, idx) => (
                          <li key={`${c.recurso_id}-${idx}`}>
                            • {c.recurso_tipo}: {c.tipo_reserva} de{" "}
                            {formatFechaHora(c.inicio)} a {formatFechaHora(c.fin)}
                            {c.motivo ? ` — ${c.motivo}` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {validacion.advertencias.length > 0 && (
                    <div className="rounded-xl border border-atencion/25 bg-atencion-tenue p-s3">
                      <p className="text-[14px] font-semibold text-atencion">Advertencias</p>
                      <ul className="mt-s2 space-y-s1 text-[14px] text-atencion">
                        {validacion.advertencias.map((i, idx) => (
                          <li key={`${i.codigo}-${idx}`}>• {i.mensaje}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {erroresAsignacion.length > 0 && !validacion && (
                <div className="rounded-xl border border-critico/20 bg-critico-tenue p-s3">
                  <ul className="space-y-s1 text-[14px] text-critico">
                    {erroresAsignacion.map((i, idx) => (
                      <li key={`${i.codigo}-${idx}`}>• {i.mensaje}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setViajeSel(null)} disabled={asignando}>
              Cancelar
            </Button>
            <Button variant="outline" onClick={() => void validar()} disabled={validando || asignando}>
              <RefreshCw className={cn("size-4", validando && "animate-spin")} />
              Validar disponibilidad
            </Button>
            <Button onClick={() => void confirmar()} disabled={!validacion?.apto || asignando}>
              {asignando ? "Asignando…" : "Confirmar asignación"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RecursoCard({ recurso }: { recurso: RecursoNucleo }) {
  const Icono = ICONO_TIPO[recurso.tipo];
  const bloqueos = recurso.incidencias.filter((i) => i.bloqueante);
  return (
    <div className="space-y-s2 p-s4">
      <div className="flex items-start justify-between gap-s3">
        <div className="flex min-w-0 items-center gap-s2">
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-superficie-hundida text-tinta-3">
            <Icono className="size-[18px]" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-[17px] font-semibold">{recurso.etiqueta}</p>
            <p className="text-[13px] text-tinta-3">
              {recurso.tipo === "tracto"
                ? `${Number(recurso.capacidad_carga_kg ?? 0).toLocaleString("es-CL")} kg`
                : recurso.tipo === "rampla"
                  ? `${recurso.tipo_rampla ?? "rampla"} · ${Number(recurso.volumen_m3 ?? 0).toLocaleString("es-CL")} m³`
                  : `Licencia ${recurso.licencia_clase ?? "sin clase"}`}
            </p>
          </div>
        </div>
        <StatusBadge tono={tonoRecurso(recurso)}>
          {recurso.disponible ? "Disponible" : "No disponible"}
        </StatusBadge>
      </div>

      <div className="flex flex-wrap gap-x-s4 gap-y-s1 text-[14px] text-tinta-2">
        <span className="flex items-center gap-1.5">
          <Clock3 className="size-4 text-tinta-3" />
          {recurso.disponible
            ? recurso.libre_desde
              ? `Libre ${formatFechaHora(recurso.libre_desde)}`
              : "Sin fecha libre"
            : recurso.proximas_reservas[0]
              ? `Próxima reserva ${formatFechaHora(recurso.proximas_reservas[0].inicio)}`
              : "Sin fecha libre"}
        </span>
        <span className={cn("flex items-center gap-1.5", recurso.documentos_ok ? "text-ok" : "text-critico")}>
          {recurso.documentos_ok ? <CheckCircle2 className="size-4" /> : <AlertTriangle className="size-4" />}
          {recurso.documentos_ok ? "Documentos al día" : "Documentos con bloqueo"}
        </span>
        <span className="text-tinta-3">
          {recurso.proximas_reservas.length} reserva(s) próxima(s)
        </span>
      </div>

      {bloqueos.length > 0 && (
        <ul className="space-y-s1 text-[13.5px] text-critico">
          {bloqueos.slice(0, 2).map((i, idx) => (
            <li key={`${i.codigo}-${idx}`}>• {i.mensaje}</li>
          ))}
          {bloqueos.length > 2 && <li>• +{bloqueos.length - 2} bloqueo(s) más</li>}
        </ul>
      )}
    </div>
  );
}
