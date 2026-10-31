"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  History,
  ListChecks,
  Plus,
  RefreshCw,
  Truck,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { nucleo } from "@/lib/nucleo";
import { useNucleoEmpresa } from "@/lib/use-nucleo-empresa";
import { formatCLP, formatFecha } from "@/lib/format";
import type {
  EstadoMantenimientoNucleo,
  EstadoSemaforoMantenimientoNucleo,
  MantenimientoCreateNucleo,
  MantenimientoNucleo,
  PautaMantenimientoCreateNucleo,
  PautaMantenimientoNucleo,
  RamplaNucleo,
  RecursoMantenibleNucleo,
  TractoNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputCLP } from "@/components/ui-inputs/input-clp";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  FilaVacia,
  FilasCargando,
  PageHeader,
  Panel,
  Patente,
  Segmentado,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import { AreaTexto, Campo, SelectSimple } from "@/components/formulario";
import { ErrorNucleo } from "@/components/nucleo/estado-error";

const ESTADO_MANT: Record<
  EstadoSemaforoMantenimientoNucleo,
  { tono: Tono; label: string }
> = {
  pendiente: { tono: "critico", label: "Vencido" },
  por_vencer: { tono: "atencion", label: "Por vencer" },
  ok: { tono: "ok", label: "Al día" },
  sin_registro: { tono: "neutro", label: "Sin registro" },
  sin_odometro: { tono: "neutro", label: "Sin odómetro" },
};

const ETIQUETA_RECURSO: Record<RecursoMantenibleNucleo, string> = {
  tracto: "Tracto",
  rampla: "Rampla",
};

function hoyISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function km(valor: string | number | null | undefined) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = Number(valor);
  if (Number.isNaN(n)) return "—";
  return `${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 1 }).format(n)} km`;
}

function mensajeDeError(error: unknown) {
  return error instanceof Error ? error.message : "Ocurrió un error inesperado.";
}

export default function MantenimientoPage() {
  const {
    empresa,
    empresaId,
    permisos,
    cargando: cargandoSesion,
    error: errorSesion,
  } = useNucleoEmpresa();

  const [pestana, setPestana] = useState<"estado" | "pauta" | "historial">("estado");
  const [estados, setEstados] = useState<EstadoMantenimientoNucleo[]>([]);
  const [pautas, setPautas] = useState<PautaMantenimientoNucleo[]>([]);
  const [registros, setRegistros] = useState<MantenimientoNucleo[]>([]);
  const [tractos, setTractos] = useState<TractoNucleo[]>([]);
  const [ramplas, setRamplas] = useState<RamplaNucleo[]>([]);
  const [cargandoDatos, setCargandoDatos] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [errorDatos, setErrorDatos] = useState<unknown>(null);

  const [dialogoPauta, setDialogoPauta] = useState(false);
  const [formPauta, setFormPauta] = useState({
    recurso_tipo: "tracto" as RecursoMantenibleNucleo,
    item: "",
    intervalo_km: "20000",
    intervalo_meses: "",
    alerta_km: "",
    orden: "",
  });
  const [guardandoPauta, setGuardandoPauta] = useState(false);
  const [errorPauta, setErrorPauta] = useState<string | null>(null);

  const [dialogoMant, setDialogoMant] = useState(false);
  const [formMant, setFormMant] = useState({
    recurso_tipo: "tracto" as RecursoMantenibleNucleo,
    recurso_id: "",
    pauta_id: "",
    fecha: hoyISO(),
    km: "",
    costo: 0,
    observaciones: "",
  });
  const [guardandoMant, setGuardandoMant] = useState(false);
  const [errorMant, setErrorMant] = useState<string | null>(null);

  const [anulando, setAnulando] = useState<MantenimientoNucleo | null>(null);
  const [motivo, setMotivo] = useState("");
  const [procesandoAnulacion, setProcesandoAnulacion] = useState(false);
  const [errorAnulacion, setErrorAnulacion] = useState<string | null>(null);

  const puedeEscribir = permisos.includes("mantenimiento:escribir");

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!empresaId) return;
      if (silencioso) setActualizando(true);
      else setCargandoDatos(true);
      setErrorDatos(null);
      try {
        const [estado, listaPautas, listaRegistros, listaTractos, listaRamplas] =
          await Promise.all([
            nucleo.get<EstadoMantenimientoNucleo[]>(
              "/nucleo/mantenimiento/estado",
              empresaId,
            ),
            nucleo.get<PautaMantenimientoNucleo[]>(
              "/nucleo/mantenimiento/pautas?incluir_inactivas=true",
              empresaId,
            ),
            nucleo.get<MantenimientoNucleo[]>(
              "/nucleo/mantenimiento/mantenimientos",
              empresaId,
            ),
            nucleo
              .get<TractoNucleo[]>("/nucleo/tractos", empresaId)
              .catch((): TractoNucleo[] => []),
            nucleo
              .get<RamplaNucleo[]>("/nucleo/ramplas", empresaId)
              .catch((): RamplaNucleo[] => []),
          ]);
        setEstados(estado);
        setPautas(listaPautas);
        setRegistros(listaRegistros);
        setTractos(listaTractos);
        setRamplas(listaRamplas);
      } catch (e) {
        setErrorDatos(e);
      } finally {
        setCargandoDatos(false);
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

  const cargando = cargandoSesion || cargandoDatos;
  const bloqueado = Boolean(errorSesion || errorDatos);

  const nombrePorRecurso = useMemo(() => {
    const mapa = new Map<string, string>();
    tractos.forEach((t) => mapa.set(`tracto:${t.id}`, t.patente));
    ramplas.forEach((r) => mapa.set(`rampla:${r.id}`, r.patente));
    return mapa;
  }, [tractos, ramplas]);

  const pautaPorId = useMemo(
    () => new Map(pautas.map((p) => [p.id, p])),
    [pautas],
  );

  const grupos = useMemo(() => {
    const mapa = new Map<
      string,
      {
        recurso_tipo: RecursoMantenibleNucleo;
        recurso_id: string;
        items: EstadoMantenimientoNucleo[];
      }
    >();
    for (const item of estados) {
      const clave = `${item.recurso_tipo}:${item.recurso_id}`;
      const actual = mapa.get(clave);
      if (actual) actual.items.push(item);
      else
        mapa.set(clave, {
          recurso_tipo: item.recurso_tipo,
          recurso_id: item.recurso_id,
          items: [item],
        });
    }
    return [...mapa.values()].sort((a, b) => {
      const pa = nombrePorRecurso.get(`${a.recurso_tipo}:${a.recurso_id}`) ?? "";
      const pb = nombrePorRecurso.get(`${b.recurso_tipo}:${b.recurso_id}`) ?? "";
      return pa.localeCompare(pb, "es");
    });
  }, [estados, nombrePorRecurso]);

  const resumen = useMemo(() => {
    let vencidos = 0;
    let proximos = 0;
    estados.forEach((item) => {
      if (item.estado === "pendiente") vencidos++;
      if (item.estado === "por_vencer") proximos++;
    });
    return { vencidos, proximos };
  }, [estados]);

  const pautasDisponibles = useMemo(
    () =>
      pautas.filter(
        (p) => p.activo && p.recurso_tipo === formMant.recurso_tipo,
      ),
    [pautas, formMant.recurso_tipo],
  );

  const recursosDisponibles =
    formMant.recurso_tipo === "tracto" ? tractos : ramplas;

  function etiquetaRecurso(tipo: RecursoMantenibleNucleo, id: string | null) {
    if (!id) return "—";
    return nombrePorRecurso.get(`${tipo}:${id}`) ?? `${id.slice(0, 8)}…`;
  }

  function abrirMantencion(
    recursoTipo: RecursoMantenibleNucleo = "tracto",
    recursoId = "",
    pautaId = "",
  ) {
    const tracto = tractos.find((t) => t.id === recursoId);
    setFormMant({
      recurso_tipo: recursoTipo,
      recurso_id: recursoId,
      pauta_id: pautaId,
      fecha: hoyISO(),
      km: tracto ? tracto.km_actual : "",
      costo: 0,
      observaciones: "",
    });
    setErrorMant(null);
    setDialogoMant(true);
  }

  async function guardarPauta() {
    setErrorPauta(null);
    const item = formPauta.item.trim();
    const intervaloKm = Number(formPauta.intervalo_km);
    if (!item) {
      setErrorPauta("El ítem es obligatorio.");
      return;
    }
    if (!Number.isFinite(intervaloKm) || intervaloKm <= 0) {
      setErrorPauta("El intervalo en kilómetros debe ser mayor que cero.");
      return;
    }
    const body: PautaMantenimientoCreateNucleo = {
      recurso_tipo: formPauta.recurso_tipo,
      item,
      intervalo_km: intervaloKm,
      ...(Number(formPauta.intervalo_meses) > 0
        ? { intervalo_meses: Number(formPauta.intervalo_meses) }
        : {}),
      ...(formPauta.alerta_km !== ""
        ? { alerta_km: Number(formPauta.alerta_km) }
        : {}),
      ...(formPauta.orden !== "" ? { orden: Number(formPauta.orden) } : {}),
    };
    setGuardandoPauta(true);
    try {
      await nucleo.post<PautaMantenimientoNucleo>(
        "/nucleo/mantenimiento/pautas",
        empresaId,
        body,
      );
      toast.success("Pauta creada");
      setDialogoPauta(false);
      setFormPauta({
        recurso_tipo: "tracto",
        item: "",
        intervalo_km: "20000",
        intervalo_meses: "",
        alerta_km: "",
        orden: "",
      });
      await cargar(true);
    } catch (e) {
      const mensaje = mensajeDeError(e);
      setErrorPauta(mensaje);
      toast.error(mensaje);
    } finally {
      setGuardandoPauta(false);
    }
  }

  async function guardarMantencion() {
    setErrorMant(null);
    if (!formMant.recurso_id) {
      setErrorMant("Seleccione el tracto o la rampla.");
      return;
    }
    if (!formMant.pauta_id) {
      setErrorMant("Seleccione la pauta realizada.");
      return;
    }
    if (!formMant.fecha) {
      setErrorMant("Indique la fecha de la mantención.");
      return;
    }
    const kmNumero = Number(formMant.km);
    if (formMant.km === "" || !Number.isFinite(kmNumero) || kmNumero < 0) {
      setErrorMant("Ingrese un kilometraje válido (mayor o igual a cero).");
      return;
    }
    const body: MantenimientoCreateNucleo = {
      pauta_id: formMant.pauta_id,
      fecha: formMant.fecha,
      km: kmNumero,
      costo: formMant.costo,
      ...(formMant.recurso_tipo === "tracto"
        ? { tracto_id: formMant.recurso_id }
        : { rampla_id: formMant.recurso_id }),
      ...(formMant.observaciones.trim()
        ? { observaciones: formMant.observaciones.trim() }
        : {}),
    };
    setGuardandoMant(true);
    try {
      await nucleo.post<MantenimientoNucleo>(
        "/nucleo/mantenimiento/mantenimientos",
        empresaId,
        body,
      );
      toast.success("Mantención registrada");
      setDialogoMant(false);
      await cargar(true);
    } catch (e) {
      const mensaje = mensajeDeError(e);
      setErrorMant(mensaje);
      toast.error(mensaje);
    } finally {
      setGuardandoMant(false);
    }
  }

  async function confirmarAnulacion() {
    if (!anulando) return;
    setErrorAnulacion(null);
    if (motivo.trim().length < 3) {
      setErrorAnulacion("El motivo debe tener al menos 3 caracteres.");
      return;
    }
    setProcesandoAnulacion(true);
    try {
      await nucleo.post<MantenimientoNucleo>(
        `/nucleo/mantenimiento/mantenimientos/${anulando.id}/anular`,
        empresaId,
        { motivo: motivo.trim() },
      );
      toast.success("Mantención anulada; el registro se conserva en el historial");
      setAnulando(null);
      setMotivo("");
      await cargar(true);
    } catch (e) {
      const mensaje = mensajeDeError(e);
      setErrorAnulacion(mensaje);
      toast.error(mensaje);
    } finally {
      setProcesandoAnulacion(false);
    }
  }

  const peorTono = (items: EstadoMantenimientoNucleo[]): Tono => {
    if (items.some((i) => i.estado === "pendiente")) return "critico";
    if (items.some((i) => i.estado === "por_vencer")) return "atencion";
    if (items.every((i) => i.estado === "sin_registro" || i.estado === "sin_odometro"))
      return "neutro";
    return "ok";
  };

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Operación"
        titulo="Mantenimiento"
        descripcion="Pauta preventiva por kilometraje del núcleo. El estado sale de la vista del servidor; anular conserva el historial."
        acciones={
          <>
            <Button
              variant="outline"
              onClick={() => void cargar(true)}
              disabled={!empresaId || actualizando}
            >
              <RefreshCw className={actualizando ? "animate-spin" : undefined} />
              Actualizar
            </Button>
            {puedeEscribir && (
              <Button onClick={() => abrirMantencion()} disabled={bloqueado}>
                <Wrench /> Registrar mantención
              </Button>
            )}
          </>
        }
      />

      <ErrorNucleo error={errorSesion ?? errorDatos} />

      {!bloqueado && (
        <>
      {empresa && (
        <p className="text-[14px] text-tinta-3">
          Empresa: <span className="font-medium text-tinta-2">{empresa.razon_social}</span>
        </p>
      )}

      {!cargando && (resumen.vencidos > 0 || resumen.proximos > 0) && (
        <Aviso tono={resumen.vencidos > 0 ? "critico" : "atencion"} icono={AlertTriangle}>
          {resumen.vencidos > 0 && (
            <>
              <strong>{resumen.vencidos}</strong>{" "}
              {resumen.vencidos === 1 ? "ítem vencido" : "ítems vencidos"}
            </>
          )}
          {resumen.vencidos > 0 && resumen.proximos > 0 && " y "}
          {resumen.proximos > 0 && (
            <>
              <strong>{resumen.proximos}</strong>{" "}
              {resumen.proximos === 1 ? "próximo a vencer" : "próximos a vencer"}
            </>
          )}
          . El semáforo se calcula en el servidor con el snapshot de la pauta.
        </Aviso>
      )}

      <Segmentado
        etiqueta="Vista de mantenimiento"
        valor={pestana}
        onCambio={setPestana}
        opciones={[
          { valor: "estado", etiqueta: "Estado de la flota", contador: grupos.length },
          { valor: "pauta", etiqueta: "Pauta", contador: pautas.length },
          { valor: "historial", etiqueta: "Historial", contador: registros.length },
        ]}
      />

      {pestana === "estado" &&
        (cargando ? (
          <div className="space-y-s3">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-48 w-full rounded-xl" />
            ))}
          </div>
        ) : grupos.length === 0 ? (
          <Panel>
            <EstadoVacio
              icono={Truck}
              titulo="Sin estado de mantenimiento"
              descripcion="Cree una pauta y registre la primera mantención para ver el semáforo de la flota."
              accion={
                puedeEscribir ? (
                  <Button onClick={() => setDialogoPauta(true)}>
                    <Plus /> Nueva pauta
                  </Button>
                ) : undefined
              }
            />
          </Panel>
        ) : (
          <div className="space-y-s4">
            {grupos.map((grupo) => {
              const tono = peorTono(grupo.items);
              return (
                <Panel
                  key={`${grupo.recurso_tipo}:${grupo.recurso_id}`}
                  titulo={
                    <span className="flex flex-wrap items-center gap-s3">
                      <Patente>
                        {etiquetaRecurso(grupo.recurso_tipo, grupo.recurso_id)}
                      </Patente>
                      <span className="text-[13px] font-normal text-tinta-3">
                        {ETIQUETA_RECURSO[grupo.recurso_tipo]}
                      </span>
                    </span>
                  }
                  acciones={
                    <StatusBadge tono={tono}>
                      {tono === "critico"
                        ? "Requiere mantención"
                        : tono === "atencion"
                          ? "Próximo a mantención"
                          : tono === "neutro"
                            ? "Sin registro"
                            : "Al día"}
                    </StatusBadge>
                  }
                >
                  <div className="grid gap-px bg-borde sm:grid-cols-2 xl:grid-cols-3">
                    {grupo.items.map((item) => {
                      const estado = ESTADO_MANT[item.estado];
                      const ultimo =
                        item.ultimo_km === null ? null : Number(item.ultimo_km);
                      const proximo =
                        item.proximo_km === null ? null : Number(item.proximo_km);
                      const restante =
                        item.restante_km === null ? null : Number(item.restante_km);
                      const intervalo = item.intervalo_km ?? 0;
                      const actual =
                        proximo !== null && restante !== null
                          ? proximo - restante
                          : null;
                      const usado =
                        ultimo !== null &&
                        actual !== null &&
                        intervalo > 0
                          ? Math.min(
                              100,
                              Math.max(0, ((actual - ultimo) / intervalo) * 100),
                            )
                          : 0;
                      return (
                        <div key={item.pauta_id} className="bg-superficie p-s4">
                          <div className="flex items-start justify-between gap-s2">
                            <p className="text-[15.5px] font-medium">{item.item}</p>
                            <StatusBadge tono={estado.tono}>{estado.label}</StatusBadge>
                          </div>
                          <div className="mt-s3 h-1.5 overflow-hidden rounded-full bg-superficie-hundida">
                            <div
                              className={cn(
                                "h-full rounded-full transition-[width] duration-700",
                                item.estado === "pendiente"
                                  ? "bg-critico"
                                  : item.estado === "por_vencer"
                                    ? "bg-senal"
                                    : item.estado === "ok"
                                      ? "bg-ok"
                                      : "bg-borde-fuerte",
                              )}
                              style={{ width: `${usado}%` }}
                            />
                          </div>
                          <p className="mt-s2 text-[13.5px] text-tinta-3">
                            {item.estado === "sin_registro" ? (
                              <>Cada {km(item.intervalo_km)} · sin mantención registrada</>
                            ) : item.estado === "sin_odometro" ? (
                              <>Cada {km(item.intervalo_km)} · el recurso no tiene odómetro</>
                            ) : item.estado === "pendiente" ? (
                              <span className="font-medium text-critico">
                                Excedido en {km(restante === null ? null : -restante)}
                              </span>
                            ) : (
                              <>
                                Faltan{" "}
                                <span
                                  className={cn(
                                    "font-medium",
                                    item.estado === "por_vencer"
                                      ? "text-atencion"
                                      : "text-tinta-2",
                                  )}
                                >
                                  {km(item.restante_km)}
                                </span>{" "}
                                · próximo a los {km(item.proximo_km)}
                              </>
                            )}
                          </p>
                          {item.ultima_fecha && (
                            <p className="text-[13px] text-tinta-3">
                              Último: {formatFecha(item.ultima_fecha)} a los{" "}
                              {km(item.ultimo_km)}
                            </p>
                          )}
                          {puedeEscribir && (
                            <Button
                              size="xs"
                              variant="outline"
                              className="mt-s3"
                              onClick={() =>
                                abrirMantencion(
                                  grupo.recurso_tipo,
                                  grupo.recurso_id,
                                  item.pauta_id,
                                )
                              }
                            >
                              <Wrench /> Registrar
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </Panel>
              );
            })}
          </div>
        ))}

      {pestana === "pauta" && (
        <Panel
          titulo="Pautas de mantenimiento"
          descripcion="El servidor valida el recurso y evita duplicados activos. No existe edición: una pauta nueva reemplaza la vigencia operativa."
          acciones={
            puedeEscribir && (
              <Button
                size="sm"
                onClick={() => {
                  setErrorPauta(null);
                  setDialogoPauta(true);
                }}
              >
                <Plus /> Nueva pauta
              </Button>
            )
          }
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ítem</TableHead>
                  <TableHead>Recurso</TableHead>
                  <TableHead className="text-right">Intervalo</TableHead>
                  <TableHead className="text-right">Alerta</TableHead>
                  <TableHead>Estado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cargando ? (
                  <FilasCargando columnas={5} />
                ) : pautas.length === 0 ? (
                  <FilaVacia
                    columnas={5}
                    icono={ListChecks}
                    titulo="Pauta vacía"
                    descripcion="Cree ítems como cambio de aceite o engrase."
                  />
                ) : (
                  pautas.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-medium">{p.item}</TableCell>
                      <TableCell>{ETIQUETA_RECURSO[p.recurso_tipo]}</TableCell>
                      <TableCell className="cifra text-right">
                        {km(p.intervalo_km)}
                      </TableCell>
                      <TableCell className="cifra text-right">
                        {p.alerta_km === null ? "—" : km(p.alerta_km)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge tono={p.activo ? "ok" : "neutro"}>
                          {p.activo ? "Activa" : "Inactiva"}
                        </StatusBadge>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </Panel>
      )}

      {pestana === "historial" && (
        <Panel
          titulo="Historial de mantenciones"
          descripcion="Anular no borra: conserva el registro y su motivo."
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fecha</TableHead>
                  <TableHead>Recurso</TableHead>
                  <TableHead>Ítem</TableHead>
                  <TableHead className="text-right">Kilometraje</TableHead>
                  <TableHead className="text-right">Costo</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cargando ? (
                  <FilasCargando columnas={7} />
                ) : registros.length === 0 ? (
                  <FilaVacia
                    columnas={7}
                    icono={History}
                    titulo="Sin mantenciones registradas"
                    descripcion="Registre la primera mantención desde la pauta."
                  />
                ) : (
                  registros.map((registro) => {
                    const tipo: RecursoMantenibleNucleo = registro.tracto_id
                      ? "tracto"
                      : "rampla";
                    const recursoId = registro.tracto_id ?? registro.rampla_id;
                    const pauta = pautaPorId.get(registro.pauta_id);
                    return (
                      <TableRow key={registro.id}>
                        <TableCell className="text-tinta-2">
                          {formatFecha(registro.fecha)}
                        </TableCell>
                        <TableCell>
                          <Patente>{etiquetaRecurso(tipo, recursoId)}</Patente>
                        </TableCell>
                        <TableCell className="font-medium">
                          {pauta?.item ?? "Pauta no visible"}
                        </TableCell>
                        <TableCell className="cifra text-right">
                          {km(registro.km)}
                        </TableCell>
                        <TableCell className="cifra text-right">
                          {Number(registro.costo) ? formatCLP(registro.costo) : "—"}
                        </TableCell>
                        <TableCell>
                          <StatusBadge
                            tono={registro.estado === "anulado" ? "critico" : "ok"}
                          >
                            {registro.estado === "anulado" ? "Anulada" : "Realizada"}
                          </StatusBadge>
                        </TableCell>
                        <TableCell className="text-right">
                          {puedeEscribir && registro.estado !== "anulado" && (
                            <Button
                              size="xs"
                              variant="destructive"
                              onClick={() => {
                                setMotivo("");
                                setErrorAnulacion(null);
                                setAnulando(registro);
                              }}
                            >
                              Anular
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </Panel>
      )}

      <Dialog open={dialogoPauta} onOpenChange={setDialogoPauta}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nueva pauta de mantenimiento</DialogTitle>
            <DialogDescription>
              Se aplica a todos los recursos del tipo elegido. El intervalo y la alerta
              quedan guardados como snapshot en cada mantención.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <Campo etiqueta="Recurso" htmlFor="pauta-recurso" requerido>
              <SelectSimple
                id="pauta-recurso"
                valor={formPauta.recurso_tipo}
                onCambio={(v) =>
                  setFormPauta({
                    ...formPauta,
                    recurso_tipo: v === "rampla" ? "rampla" : "tracto",
                  })
                }
                opciones={[
                  { valor: "tracto", etiqueta: "Tracto" },
                  { valor: "rampla", etiqueta: "Rampla" },
                ]}
              />
            </Campo>
            <Campo
              etiqueta="Ítem"
              htmlFor="pauta-item"
              requerido
              error={errorPauta && !formPauta.item.trim() ? errorPauta : null}
            >
              <Input
                id="pauta-item"
                value={formPauta.item}
                onChange={(e) =>
                  setFormPauta({ ...formPauta, item: e.target.value })
                }
                placeholder="Cambio de aceite"
              />
            </Campo>
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Intervalo (km)" htmlFor="pauta-km" requerido>
                <Input
                  id="pauta-km"
                  type="number"
                  min={1}
                  step={100}
                  value={formPauta.intervalo_km}
                  onChange={(e) =>
                    setFormPauta({ ...formPauta, intervalo_km: e.target.value })
                  }
                />
              </Campo>
              <Campo etiqueta="Intervalo (meses)" htmlFor="pauta-meses">
                <Input
                  id="pauta-meses"
                  type="number"
                  min={1}
                  step={1}
                  value={formPauta.intervalo_meses}
                  onChange={(e) =>
                    setFormPauta({ ...formPauta, intervalo_meses: e.target.value })
                  }
                />
              </Campo>
              <Campo etiqueta="Alerta (km antes)" htmlFor="pauta-alerta">
                <Input
                  id="pauta-alerta"
                  type="number"
                  min={0}
                  step={100}
                  value={formPauta.alerta_km}
                  onChange={(e) =>
                    setFormPauta({ ...formPauta, alerta_km: e.target.value })
                  }
                />
              </Campo>
              <Campo etiqueta="Orden" htmlFor="pauta-orden">
                <Input
                  id="pauta-orden"
                  type="number"
                  min={0}
                  step={1}
                  value={formPauta.orden}
                  onChange={(e) =>
                    setFormPauta({ ...formPauta, orden: e.target.value })
                  }
                />
              </Campo>
            </div>
            {errorPauta && formPauta.item.trim() && (
              <p className="text-[14px] text-critico" role="alert">
                {errorPauta}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoPauta(false)}>
              Cancelar
            </Button>
            <Button onClick={() => void guardarPauta()} disabled={guardandoPauta}>
              {guardandoPauta ? "Guardando…" : "Crear pauta"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoMant} onOpenChange={setDialogoMant}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar mantención</DialogTitle>
            <DialogDescription>
              El kilometraje no puede ser menor al odómetro actual del tracto. El
              servidor vuelve a validar pauta, recurso y costo.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Tipo de recurso" htmlFor="mant-tipo" requerido>
                <SelectSimple
                  id="mant-tipo"
                  valor={formMant.recurso_tipo}
                  onCambio={(v) =>
                    setFormMant({
                      ...formMant,
                      recurso_tipo: v === "rampla" ? "rampla" : "tracto",
                      recurso_id: "",
                      pauta_id: "",
                      km: "",
                    })
                  }
                  opciones={[
                    { valor: "tracto", etiqueta: "Tracto" },
                    { valor: "rampla", etiqueta: "Rampla" },
                  ]}
                />
              </Campo>
              <Campo etiqueta="Recurso" htmlFor="mant-recurso" requerido>
                <SelectSimple
                  id="mant-recurso"
                  valor={formMant.recurso_id}
                  onCambio={(v) => {
                    const tracto = tractos.find((t) => t.id === v);
                    setFormMant({
                      ...formMant,
                      recurso_id: v,
                      km: tracto ? tracto.km_actual : formMant.km,
                    });
                  }}
                  placeholder="Seleccione recurso"
                  opciones={recursosDisponibles.map((r) => ({
                    valor: r.id,
                    etiqueta: r.patente,
                  }))}
                />
              </Campo>
              <Campo etiqueta="Pauta" htmlFor="mant-pauta" requerido>
                <SelectSimple
                  id="mant-pauta"
                  valor={formMant.pauta_id}
                  onCambio={(v) => setFormMant({ ...formMant, pauta_id: v })}
                  placeholder="Seleccione pauta"
                  opciones={pautasDisponibles.map((p) => ({
                    valor: p.id,
                    etiqueta: p.item,
                  }))}
                />
              </Campo>
              <Campo etiqueta="Fecha" htmlFor="mant-fecha" requerido>
                <Input
                  id="mant-fecha"
                  type="date"
                  value={formMant.fecha}
                  onChange={(e) =>
                    setFormMant({ ...formMant, fecha: e.target.value })
                  }
                />
              </Campo>
              <Campo
                etiqueta="Kilometraje"
                htmlFor="mant-km"
                requerido
                ayuda={
                  formMant.recurso_tipo === "tracto"
                    ? "El servidor compara con el odómetro del tracto."
                    : "La rampla no tiene odómetro propio."
                }
              >
                <Input
                  id="mant-km"
                  type="number"
                  min={0}
                  step="0.1"
                  value={formMant.km}
                  onChange={(e) => setFormMant({ ...formMant, km: e.target.value })}
                />
              </Campo>
              <Campo etiqueta="Costo" htmlFor="mant-costo">
                <InputCLP
                  key={dialogoMant ? "abierto" : "cerrado"}
                  id="mant-costo"
                  value={formMant.costo}
                  onChange={(v) => setFormMant({ ...formMant, costo: v })}
                  placeholder="$ 0"
                />
              </Campo>
            </div>
            <Campo etiqueta="Observaciones" htmlFor="mant-obs">
              <AreaTexto
                id="mant-obs"
                rows={3}
                value={formMant.observaciones}
                onChange={(e) =>
                  setFormMant({ ...formMant, observaciones: e.target.value })
                }
                placeholder="Detalle opcional de la mantención"
              />
            </Campo>
            {errorMant && (
              <p className="text-[14px] text-critico" role="alert">
                {errorMant}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoMant(false)}>
              Cancelar
            </Button>
            <Button onClick={() => void guardarMantencion()} disabled={guardandoMant}>
              {guardandoMant ? "Guardando…" : "Registrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!anulando}
        onOpenChange={(abierto) => {
          if (!abierto) setAnulando(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Anular mantención</DialogTitle>
            <DialogDescription>
              El registro no se borra: queda con estado anulado y su motivo en el
              historial.
            </DialogDescription>
          </DialogHeader>
          <Campo etiqueta="Motivo" htmlFor="anular-motivo" requerido>
            <AreaTexto
              id="anular-motivo"
              rows={3}
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Error de digitación, mantención duplicada…"
            />
          </Campo>
          {errorAnulacion && (
            <p className="text-[14px] text-critico" role="alert">
              {errorAnulacion}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setAnulando(null)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => void confirmarAnulacion()}
              disabled={procesandoAnulacion}
            >
              {procesandoAnulacion ? "Anulando…" : "Anular"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
        </>
      )}
    </div>
  );
}
