"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Info,
  Loader2,
  Lock,
  PencilLine,
  Save,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { nucleo, NucleoError } from "@/lib/nucleo";
import { formatFechaHora } from "@/lib/format";
import {
  calcularCambiosSolicitud,
  esValorEstructurado,
  etiquetaCampo,
  etiquetaEstadoSolicitud,
  etiquetaSolicitante,
  etiquetaTipoSolicitud,
  igualesJson,
  parsearValorSolicitud,
  tonoEstadoSolicitud,
  valorATexto,
} from "@/lib/agente";
import type {
  AccionDecisionSolicitudNucleo,
  DecisionSolicitudNucleo,
  JsonNucleo,
  ResultadoSolicitudNucleo,
  SolicitudDetalleNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AreaTexto, Campo } from "@/components/formulario";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Aviso, Panel, StatusBadge, type Tono } from "@/components/sistema";

type ErrorCarga = { mensaje: string; tono: Tono };
type ErrorDecision = { mensaje: string; tono: Tono };

function clasificarErrorCarga(e: unknown): ErrorCarga {
  if (e instanceof NucleoError) {
    if (e.status === 403) {
      return {
        tono: "atencion",
        mensaje: "No tiene permiso para ver esta solicitud (agente:buzon).",
      };
    }
    if (e.status === 404) {
      return {
        tono: "atencion",
        mensaje:
          "La solicitud no existe o ya no está disponible para esta empresa.",
      };
    }
    if (e.status === 401) {
      return {
        tono: "critico",
        mensaje: "Su sesión expiró. Vuelva a iniciar sesión.",
      };
    }
    return { tono: "critico", mensaje: e.message };
  }
  return {
    tono: "critico",
    mensaje:
      "No se pudo conectar con el servidor. Revise su conexión e intente nuevamente.",
  };
}

function ValorJson({ valor }: { valor: JsonNucleo }) {
  if (valor === null) {
    return <span className="font-mono text-tinta-3">null</span>;
  }
  if (typeof valor === "boolean") {
    return <span className="font-mono">{valor ? "true" : "false"}</span>;
  }
  if (typeof valor === "number") {
    return <span className="font-mono tabular-nums">{String(valor)}</span>;
  }
  if (typeof valor === "string") {
    return (
      <span className="break-words whitespace-pre-wrap">{valor || "—"}</span>
    );
  }
  return (
    <pre className="max-h-48 overflow-auto rounded-md bg-superficie-hundida p-s2 font-mono text-[12.5px] leading-relaxed">
      {JSON.stringify(valor, null, 2)}
    </pre>
  );
}

function Dato({
  rotulo,
  valor,
  detalle,
}: {
  rotulo: string;
  valor: React.ReactNode;
  detalle?: React.ReactNode;
}) {
  return (
    <div>
      <p className="rotulo">{rotulo}</p>
      <p className="mt-s1 text-[15px] font-medium text-tinta">{valor}</p>
      {detalle && (
        <p className="mt-s1 text-[13px] break-all text-tinta-3">{detalle}</p>
      )}
    </div>
  );
}

export function SolicitudDetalleDialog({
  empresaId,
  solicitudId,
  puedeAprobar,
  onClose,
  onCambio,
}: {
  empresaId: string;
  solicitudId: string;
  puedeAprobar: boolean;
  onClose: () => void;
  onCambio: () => void;
}) {
  const [solicitud, setSolicitud] = useState<SolicitudDetalleNucleo | null>(
    null,
  );
  const [cargando, setCargando] = useState(true);
  const [errorCarga, setErrorCarga] = useState<ErrorCarga | null>(null);
  const [procesando, setProcesando] = useState(false);
  const procesandoRef = useRef(false);
  const [accion, setAccion] =
    useState<AccionDecisionSolicitudNucleo | null>(null);
  const [motivo, setMotivo] = useState("");
  const [errorMotivo, setErrorMotivo] = useState<string | null>(null);
  const [valores, setValores] = useState<Record<string, string>>({});
  const [erroresCampos, setErroresCampos] = useState<Record<string, string>>(
    {},
  );
  const [errorDecision, setErrorDecision] = useState<ErrorDecision | null>(
    null,
  );
  const [resultado, setResultado] = useState<ResultadoSolicitudNucleo | null>(
    null,
  );
  const [sinEjecutor, setSinEjecutor] = useState(false);
  const [autoaprobacion, setAutoaprobacion] = useState(false);
  const [sinPermisoDecision, setSinPermisoDecision] = useState(false);

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!silencioso) setCargando(true);
      setErrorCarga(null);
      try {
        const data = await nucleo.get<SolicitudDetalleNucleo>(
          `/nucleo/agente/solicitudes/${solicitudId}`,
          empresaId,
        );
        setSolicitud(data);
      } catch (e) {
        setErrorCarga(clasificarErrorCarga(e));
      } finally {
        setCargando(false);
      }
    },
    [empresaId, solicitudId],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  const campos = useMemo(() => {
    if (!solicitud) return [];
    return Array.from(
      new Set([
        ...Object.keys(solicitud.payload),
        ...Object.keys(solicitud.valores_modificados ?? {}),
      ]),
    );
  }, [solicitud]);

  const hayCambios = useMemo(() => {
    if (!solicitud || accion !== "modificar") return false;
    return Object.keys(valores).some((campo) => {
      const resultadoCampo = parsearValorSolicitud(
        valores[campo] ?? "",
        solicitud.payload[campo],
      );
      if ("error" in resultadoCampo) return true;
      return !igualesJson(resultadoCampo.valor, solicitud.payload[campo]);
    });
  }, [solicitud, accion, valores]);

  function abrirModificar() {
    if (!solicitud) return;
    const base: Record<string, JsonNucleo> = {
      ...solicitud.payload,
      ...(solicitud.valores_modificados ?? {}),
    };
    const entradas: [string, string][] = Object.entries(base).map(
      ([campo, valor]) => [campo, valorATexto(valor)],
    );
    setValores(Object.fromEntries(entradas));
    setErroresCampos({});
    setAccion("modificar");
    setErrorDecision(null);
    setResultado(null);
  }

  async function manejarErrorDecision(e: unknown) {
    if (!(e instanceof NucleoError)) {
      setErrorDecision({
        tono: "critico",
        mensaje:
          "No se pudo conectar con el servidor. Revise su conexión e intente nuevamente.",
      });
      return;
    }

    if (
      e.codigo === "SOLICITUD_YA_DECIDIDA" ||
      e.codigo === "CONFLICTO_CONCURRENCIA"
    ) {
      const yaDecidida = e.codigo === "SOLICITUD_YA_DECIDIDA";
      setErrorDecision({
        tono: "atencion",
        mensaje: yaDecidida
          ? "Otra persona ya decidió esta solicitud. Actualizamos el detalle para mostrar el estado actual."
          : "La solicitud cambió mientras la revisaba. Actualizamos el detalle para que vuelva a intentar con la versión vigente.",
      });
      setAccion(null);
      await cargar(true);
      onCambio();
      return;
    }

    if (e.codigo === "TIPO_SIN_EJECUTOR") {
      setSinEjecutor(true);
      setAccion(null);
      setErrorDecision({
        tono: "atencion",
        mensaje:
          "Este tipo de solicitud todavía no se puede confirmar: el backend no tiene un ejecutor registrado para él. Puede rechazarla o modificarla.",
      });
      return;
    }

    if (e.codigo === "AUTOAPROBACION") {
      setAutoaprobacion(true);
      setAccion(null);
      setErrorDecision(null);
      return;
    }

    if (e.codigo === "ACCESO_DENEGADO" || e.status === 403) {
      setSinPermisoDecision(true);
      setAccion(null);
      setErrorDecision(null);
      return;
    }

    if (e.status === 401) {
      setErrorDecision({
        tono: "critico",
        mensaje: "Su sesión expiró. Vuelva a iniciar sesión.",
      });
      return;
    }

    if (e.status === 404) {
      setErrorDecision({
        tono: "atencion",
        mensaje:
          "La solicitud ya no existe en esta empresa. Actualizamos el listado.",
      });
      setAccion(null);
      onCambio();
      return;
    }

    setErrorDecision({ tono: "critico", mensaje: e.message });
  }

  async function decidir(tipoAccion: AccionDecisionSolicitudNucleo) {
    if (!solicitud || procesandoRef.current) return;

    if (tipoAccion === "rechazar") {
      const limpio = motivo.trim();
      if (!limpio) {
        setErrorMotivo("Escriba el motivo del rechazo.");
        document.getElementById("motivo-rechazo")?.focus();
        return;
      }
    }

    const body: DecisionSolicitudNucleo = {
      accion: tipoAccion,
      version: solicitud.version,
    };

    if (tipoAccion === "rechazar") {
      body.motivo_rechazo = motivo.trim();
    }

    if (tipoAccion === "modificar") {
      const { cambios, errores } = calcularCambiosSolicitud(
        solicitud.payload,
        valores,
      );
      if (Object.keys(errores).length > 0) {
        setErroresCampos(errores);
        const primerCampo = Object.keys(errores)[0];
        document.getElementById(`mod-${primerCampo}`)?.focus();
        return;
      }
      if (Object.keys(cambios).length === 0) {
        setErrorDecision({
          tono: "atencion",
          mensaje:
            "No hay cambios respecto del payload original. Ajuste al menos un campo.",
        });
        return;
      }
      body.valores_modificados = cambios;
    }

    if (
      tipoAccion === "confirmar" &&
      solicitud.valores_modificados &&
      Object.keys(solicitud.valores_modificados).length > 0
    ) {
      // El backend aplica la corrección vigente al confirmar (§6.9).
      body.valores_modificados = solicitud.valores_modificados;
    }

    procesandoRef.current = true;
    setProcesando(true);
    setErrorDecision(null);
    setResultado(null);
    setErrorMotivo(null);
    try {
      const respuesta = await nucleo.post<{
        solicitud: SolicitudDetalleNucleo;
        resultado: ResultadoSolicitudNucleo | null;
      }>(
        `/nucleo/agente/solicitudes/${solicitud.id}/decidir`,
        empresaId,
        body,
      );
      setSolicitud(respuesta.solicitud);
      setResultado(respuesta.resultado);
      setAccion(null);
      setErroresCampos({});
      if (tipoAccion === "confirmar") {
        toast.success("Solicitud confirmada");
      } else if (tipoAccion === "rechazar") {
        toast.success("Solicitud rechazada");
      } else {
        toast.success("Cambios guardados; la solicitud sigue pendiente");
      }
      onCambio();
    } catch (e) {
      await manejarErrorDecision(e);
    } finally {
      procesandoRef.current = false;
      setProcesando(false);
    }
  }

  function cerrar(open: boolean) {
    if (!open && !procesando) onClose();
  }

  const puedeDecidir =
    puedeAprobar && !autoaprobacion && !sinPermisoDecision;
  const motivoSinDecision = autoaprobacion
    ? "No puede decidir una solicitud que usted mismo generó. Otro aprobador debe revisarla."
    : sinPermisoDecision
      ? "Su usuario no tiene el permiso agente:aprobar. No se envió la decisión."
      : "Su usuario puede consultar el buzón, pero no decidir solicitudes. Se requiere el permiso agente:aprobar.";

  return (
    <Dialog open onOpenChange={cerrar}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-s3">
            {solicitud ? etiquetaTipoSolicitud(solicitud.tipo) : "Solicitud"}
            {solicitud && (
              <StatusBadge tono={tonoEstadoSolicitud(solicitud.estado)}>
                {etiquetaEstadoSolicitud(solicitud.estado)}
              </StatusBadge>
            )}
          </DialogTitle>
          <DialogDescription>
            {solicitud
              ? `${etiquetaSolicitante(solicitud.solicitante)} · ${solicitud.id_comercial_flete ?? "sin flete"} · ${formatFechaHora(solicitud.creada_en)}`
              : "Cargando solicitud…"}
          </DialogDescription>
        </DialogHeader>

        {errorCarga && (
          <div role="alert">
            <Aviso tono={errorCarga.tono} icono={AlertTriangle}>
              <p>{errorCarga.mensaje}</p>
              <div className="mt-s2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void cargar()}
                  disabled={cargando}
                >
                  Reintentar
                </Button>
              </div>
            </Aviso>
          </div>
        )}

        {cargando && !solicitud ? (
          <div className="space-y-s3" aria-busy="true">
            <span className="sr-only" role="status">
              Cargando solicitud…
            </span>
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : solicitud ? (
          <div className="space-y-s4">
            <div className="grid gap-s3 rounded-xl border border-borde bg-superficie-hundida/50 p-s4 sm:grid-cols-2 lg:grid-cols-4">
              <Dato
                rotulo="Solicitante"
                valor={etiquetaSolicitante(solicitud.solicitante)}
                detalle={solicitud.solicitante.tipo}
              />
              <Dato
                rotulo="Flete"
                valor={solicitud.id_comercial_flete ?? "—"}
                detalle={
                  solicitud.viaje_id
                    ? `Viaje ${solicitud.viaje_id}`
                    : "Sin viaje asociado"
                }
              />
              <Dato
                rotulo="Creada"
                valor={formatFechaHora(solicitud.creada_en)}
                detalle={`Versión ${solicitud.version}`}
              />
              <Dato
                rotulo="Decisión"
                valor={
                  solicitud.decidida_en
                    ? formatFechaHora(solicitud.decidida_en)
                    : "Pendiente"
                }
                detalle={solicitud.aprobado_por ?? undefined}
              />
            </div>

            <Panel
              titulo="Hoja de ruta"
              descripcion="Estado del documento asociado y campos que faltan."
            >
              {solicitud.hoja_ruta ? (
                <div className="space-y-s3 p-s4">
                  <div className="flex flex-wrap items-center gap-s2">
                    <StatusBadge
                      tono={
                        solicitud.hoja_ruta.faltantes.length > 0
                          ? "atencion"
                          : "ok"
                      }
                    >
                      {etiquetaEstadoSolicitud(solicitud.hoja_ruta.estado)}
                    </StatusBadge>
                    <span className="font-mono text-[12px] break-all text-tinta-3">
                      {solicitud.hoja_ruta.id}
                    </span>
                  </div>
                  {solicitud.hoja_ruta.faltantes.length > 0 ? (
                    <div>
                      <p className="text-[14px] font-medium text-tinta-2">
                        Campos faltantes
                      </p>
                      <ul className="mt-s2 flex flex-wrap gap-s2">
                        {solicitud.hoja_ruta.faltantes.map((faltante) => (
                          <li key={faltante}>
                            <StatusBadge tono="atencion">
                              {faltante}
                            </StatusBadge>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <p className="text-[14px] text-tinta-3">
                      Sin campos faltantes informados.
                    </p>
                  )}
                </div>
              ) : (
                <p className="p-s4 text-[14px] text-tinta-3">
                  Esta solicitud no tiene una hoja de ruta asociada.
                </p>
              )}
            </Panel>

            <Panel
              titulo="Payload propuesto"
              descripcion="Valores originales enviados por el agente. El payload no se reescribe al decidir."
            >
              {Object.keys(solicitud.payload).length > 0 ? (
                <dl className="grid gap-s3 p-s4 sm:grid-cols-2">
                  {Object.entries(solicitud.payload).map(([campo, valor]) => (
                    <div
                      key={campo}
                      className={cn(
                        "rounded-lg border border-borde bg-superficie-hundida/40 p-s3",
                        esValorEstructurado(valor) && "sm:col-span-2",
                      )}
                    >
                      <dt className="rotulo font-mono">{campo}</dt>
                      <dd className="mt-s1 text-[14px] text-tinta-2">
                        <ValorJson valor={valor} />
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="p-s4 text-[14px] text-tinta-3">
                  La solicitud no incluye payload.
                </p>
              )}
            </Panel>

            <Panel
              titulo={`Diferencias${solicitud.diff.length > 0 ? ` · ${solicitud.diff.length}` : ""}`}
              descripcion="Valores modificados por el aprobador frente al payload propuesto por el agente."
            >
              {solicitud.diff.length > 0 ? (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Campo</TableHead>
                        <TableHead>Propuesto</TableHead>
                        <TableHead>Modificado</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {solicitud.diff.map((cambio) => (
                        <TableRow key={cambio.campo}>
                          <TableCell className="font-mono text-[13px]">
                            {cambio.campo}
                          </TableCell>
                          <TableCell>
                            <ValorJson valor={cambio.propuesto} />
                          </TableCell>
                          <TableCell className="bg-atencion-tenue/60">
                            <ValorJson valor={cambio.modificado} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="p-s4 text-[14px] text-tinta-3">
                  {solicitud.valores_modificados
                    ? "Los valores modificados coinciden con el payload original."
                    : "Sin cambios propuestos."}
                </p>
              )}
            </Panel>

            <Panel
              titulo="Evidencia"
              descripcion="Solo referencias. El contenido se consulta con su propio permiso."
            >
              {solicitud.evidencia.length > 0 ? (
                <ul className="divide-y divide-borde">
                  {solicitud.evidencia.map((evidencia, indice) => (
                    <li
                      key={`${evidencia.tipo ?? "ref"}-${indice}`}
                      className="flex flex-wrap items-center justify-between gap-s2 p-s3 text-[14px]"
                    >
                      <span className="font-medium">
                        {evidencia.tipo ?? "Referencia"}
                      </span>
                      <span className="font-mono text-[12px] break-all text-tinta-3">
                        {evidencia.ref ?? "—"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="p-s4 text-[14px] text-tinta-3">
                  Sin evidencia referenciada.
                </p>
              )}
            </Panel>

            <Panel
              titulo="Decisión"
              descripcion="Confirmar aplica el efecto en el módulo; rechazar exige motivo; modificar guarda la corrección sin ejecutarla."
            >
              <div className="space-y-s3 p-s4">
                {resultado && (
                  <Aviso tono="ok" icono={CheckCircle2}>
                    <p className="font-medium">Solicitud aprobada.</p>
                    <p className="mt-s1 text-[14px]">
                      Se aplicó {resultado.tipo} {resultado.ref}; el registro
                      quedó en estado {resultado.estado}.
                    </p>
                  </Aviso>
                )}

                {errorDecision && (
                  <div role="alert">
                    <Aviso tono={errorDecision.tono} icono={AlertTriangle}>
                      {errorDecision.mensaje}
                    </Aviso>
                  </div>
                )}

                {solicitud.estado !== "pendiente" ? (
                  <Aviso tono="neutro" icono={Info}>
                    Esta solicitud está{" "}
                    {etiquetaEstadoSolicitud(solicitud.estado).toLowerCase()} y
                    no admite nuevas decisiones.
                  </Aviso>
                ) : !puedeDecidir ? (
                  <Aviso tono="neutro" icono={Lock}>
                    {motivoSinDecision}
                  </Aviso>
                ) : (
                  <>
                    {!accion && (
                      <div className="flex flex-wrap gap-s2">
                        <Button
                          onClick={() => {
                            setAccion("confirmar");
                            setErrorDecision(null);
                            setResultado(null);
                          }}
                          disabled={procesando || sinEjecutor}
                        >
                          <Check /> Confirmar
                        </Button>
                        <Button
                          variant="destructive"
                          onClick={() => {
                            setAccion("rechazar");
                            setErrorDecision(null);
                            setResultado(null);
                          }}
                          disabled={procesando}
                        >
                          <X /> Rechazar
                        </Button>
                        <Button
                          variant="outline"
                          onClick={abrirModificar}
                          disabled={procesando}
                        >
                          <PencilLine /> Modificar
                        </Button>
                      </div>
                    )}

                    {sinEjecutor && !accion && (
                      <Aviso tono="atencion" icono={Info}>
                        Este tipo de solicitud aún no tiene ejecutor en el
                        backend: no se puede confirmar. Puede rechazarla o
                        corregir sus valores.
                      </Aviso>
                    )}

                    {accion === "confirmar" && (
                      <div className="space-y-s3">
                        <Aviso tono="info" icono={CheckCircle2}>
                          Al confirmar, el backend aplicará el efecto de esta
                          solicitud y la dejará aprobada.
                          {solicitud.valores_modificados
                            ? " Se aplicarán los valores modificados que aparecen en el diff."
                            : ""}
                        </Aviso>
                        <p className="text-[13px] text-tinta-3">
                          La confirmación depende de que el tipo de solicitud
                          tenga un ejecutor registrado en el backend.
                        </p>
                        <div className="flex flex-wrap gap-s2">
                          <Button
                            onClick={() => void decidir("confirmar")}
                            disabled={procesando}
                          >
                            {procesando ? (
                              <Loader2 className="animate-spin" />
                            ) : (
                              <Check />
                            )}
                            Confirmar solicitud
                          </Button>
                          <Button
                            variant="ghost"
                            onClick={() => setAccion(null)}
                            disabled={procesando}
                          >
                            Volver
                          </Button>
                        </div>
                      </div>
                    )}

                    {accion === "rechazar" && (
                      <div className="space-y-s3">
                        <Campo
                          etiqueta="Motivo del rechazo"
                          htmlFor="motivo-rechazo"
                          requerido
                          error={errorMotivo}
                          ayuda="Quedará registrado en la solicitud y en la auditoría."
                        >
                          <AreaTexto
                            id="motivo-rechazo"
                            autoFocus
                            rows={3}
                            maxLength={500}
                            value={motivo}
                            onChange={(e) => {
                              setMotivo(e.target.value);
                              if (errorMotivo) setErrorMotivo(null);
                            }}
                            aria-invalid={Boolean(errorMotivo)}
                            aria-describedby={
                              errorMotivo ? "motivo-rechazo-error" : undefined
                            }
                          />
                        </Campo>
                        {errorMotivo && (
                          <span id="motivo-rechazo-error" className="sr-only">
                            {errorMotivo}
                          </span>
                        )}
                        <div className="flex flex-wrap gap-s2">
                          <Button
                            variant="destructive"
                            onClick={() => void decidir("rechazar")}
                            disabled={procesando}
                          >
                            {procesando ? (
                              <Loader2 className="animate-spin" />
                            ) : (
                              <X />
                            )}
                            Rechazar solicitud
                          </Button>
                          <Button
                            variant="ghost"
                            onClick={() => {
                              setAccion(null);
                              setErrorMotivo(null);
                            }}
                            disabled={procesando}
                          >
                            Volver
                          </Button>
                        </div>
                      </div>
                    )}

                    {accion === "modificar" && (
                      <div className="space-y-s3">
                        <Aviso tono="info" icono={PencilLine}>
                          Ajuste los valores propuestos. Se guardarán como
                          corrección y la solicitud seguirá pendiente hasta que
                          se confirme.
                        </Aviso>
                        {campos.length === 0 ? (
                          <p className="text-[14px] text-tinta-3">
                            El payload no tiene campos editables.
                          </p>
                        ) : (
                          <div className="grid gap-s3 sm:grid-cols-2">
                            {campos.map((campo) => {
                              const propuesto = solicitud.payload[campo];
                              const efectivo =
                                solicitud.valores_modificados?.[campo] ??
                                propuesto;
                              const id = `mod-${campo}`;
                              const error = erroresCampos[campo];
                              const multilinea =
                                esValorEstructurado(efectivo) ||
                                (typeof efectivo === "string" &&
                                  efectivo.includes("\n"));
                              return (
                                <Campo
                                  key={campo}
                                  etiqueta={etiquetaCampo(campo)}
                                  htmlFor={id}
                                  ayuda={
                                    <span className="font-mono text-[12px]">
                                      {campo}
                                    </span>
                                  }
                                  error={error}
                                  className={
                                    multilinea ? "sm:col-span-2" : undefined
                                  }
                                >
                                  {typeof efectivo === "boolean" ? (
                                    <div className="flex items-center gap-s2">
                                      <input
                                        id={id}
                                        type="checkbox"
                                        className="size-4 accent-marca"
                                        checked={valores[campo] === "true"}
                                        onChange={(e) =>
                                          setValores((previos) => ({
                                            ...previos,
                                            [campo]: e.target.checked
                                              ? "true"
                                              : "false",
                                          }))
                                        }
                                        aria-invalid={Boolean(error)}
                                      />
                                      <span className="text-[14px] text-tinta-2">
                                        {valores[campo] === "true" ? "Sí" : "No"}
                                      </span>
                                    </div>
                                  ) : multilinea ? (
                                    <AreaTexto
                                      id={id}
                                      rows={3}
                                      className="font-mono text-[13px]"
                                      value={valores[campo] ?? ""}
                                      onChange={(e) =>
                                        setValores((previos) => ({
                                          ...previos,
                                          [campo]: e.target.value,
                                        }))
                                      }
                                      aria-invalid={Boolean(error)}
                                    />
                                  ) : (
                                    <Input
                                      id={id}
                                      type={
                                        typeof efectivo === "number"
                                          ? "number"
                                          : "text"
                                      }
                                      step={
                                        typeof efectivo === "number"
                                          ? "any"
                                          : undefined
                                      }
                                      value={valores[campo] ?? ""}
                                      onChange={(e) =>
                                        setValores((previos) => ({
                                          ...previos,
                                          [campo]: e.target.value,
                                        }))
                                      }
                                      aria-invalid={Boolean(error)}
                                    />
                                  )}
                                </Campo>
                              );
                            })}
                          </div>
                        )}
                        <div className="flex flex-wrap items-center gap-s2">
                          <Button
                            onClick={() => void decidir("modificar")}
                            disabled={procesando || !hayCambios}
                          >
                            {procesando ? (
                              <Loader2 className="animate-spin" />
                            ) : (
                              <Save />
                            )}
                            Guardar cambios
                          </Button>
                          <Button
                            variant="ghost"
                            onClick={() => setAccion(null)}
                            disabled={procesando}
                          >
                            Volver
                          </Button>
                          {!hayCambios && (
                            <span className="text-[13px] text-tinta-3">
                              Ajuste al menos un campo para guardar.
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </Panel>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
