"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Inbox,
  Lock,
  PencilLine,
  RefreshCw,
} from "lucide-react";
import { getEmpresas, nucleo, NucleoError } from "@/lib/nucleo";
import { formatFechaHora } from "@/lib/format";
import type {
  EmpresaNucleo,
  FiltroEstadoSolicitudNucleo,
  ListaSolicitudesNucleo,
  MisPermisosNucleo,
  SolicitudResumenNucleo,
  TipoSolicitudNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
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
  FilaVacia,
  FilasCargando,
  PageHeader,
  Panel,
  Segmentado,
  StatTile,
  StatTileSkeleton,
  StatusBadge,
} from "@/components/sistema";
import { SelectSimple } from "@/components/formulario";
import { SolicitudDetalleDialog } from "@/components/agente/solicitud-detalle-dialog";
import {
  etiquetaEstadoSolicitud,
  etiquetaSolicitante,
  etiquetaTipoSolicitud,
  tonoEstadoSolicitud,
} from "@/lib/agente";

const LIMITE = 20;

const ESTADOS: {
  valor: FiltroEstadoSolicitudNucleo;
  etiqueta: string;
}[] = [
  { valor: "pendiente", etiqueta: "Pendientes" },
  { valor: "aprobada", etiqueta: "Aprobadas" },
  { valor: "rechazada", etiqueta: "Rechazadas" },
  { valor: "cancelada", etiqueta: "Canceladas" },
  { valor: "todas", etiqueta: "Todas" },
];

const TIPOS: { valor: TipoSolicitudNucleo; etiqueta: string }[] = [
  { valor: "agendamiento", etiqueta: "Agendamiento" },
  { valor: "documentos", etiqueta: "Documentos" },
  { valor: "hoja_de_ruta", etiqueta: "Hoja de ruta" },
  { valor: "otra", etiqueta: "Otra solicitud" },
];

type ErrorPantalla = {
  tipo: "permiso" | "sesion" | "red" | "dominio";
  mensaje: string;
};

function clasificarError(e: unknown): ErrorPantalla {
  if (e instanceof NucleoError) {
    if (e.status === 403) {
      return {
        tipo: "permiso",
        mensaje:
          "No tiene permiso para ver el buzón de solicitudes (agente:buzon). Solicite acceso a un administrador.",
      };
    }
    if (e.status === 401) {
      return {
        tipo: "sesion",
        mensaje: "Su sesión expiró. Vuelva a iniciar sesión para continuar.",
      };
    }
    return { tipo: "dominio", mensaje: e.message };
  }
  return {
    tipo: "red",
    mensaje:
      "No se pudo conectar con el servidor. Revise su conexión e intente nuevamente.",
  };
}

export default function BuzonAgentePage() {
  const router = useRouter();
  const [empresas, setEmpresas] = useState<EmpresaNucleo[]>([]);
  const [empresaId, setEmpresaId] = useState("");
  const [solicitudes, setSolicitudes] = useState<SolicitudResumenNucleo[]>([]);
  const [total, setTotal] = useState(0);
  const [estado, setEstado] =
    useState<FiltroEstadoSolicitudNucleo>("pendiente");
  const [tipo, setTipo] = useState("");
  const [offset, setOffset] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<ErrorPantalla | null>(null);
  const [pendientes, setPendientes] = useState<number | null>(null);
  const [puedeAprobar, setPuedeAprobar] = useState<boolean | null>(null);
  const [permisosListos, setPermisosListos] = useState(false);
  const [detalleId, setDetalleId] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    getEmpresas()
      .then((data) => {
        if (!activo) return;
        setEmpresas(data);
        if (data[0]) {
          setEmpresaId(data[0].id);
        } else {
          setError({
            tipo: "dominio",
            mensaje: "El usuario no tiene una empresa activa asignada.",
          });
          setCargando(false);
        }
      })
      .catch((e) => {
        if (!activo) return;
        setError({
          tipo:
            e instanceof NucleoError && e.status === 401 ? "sesion" : "dominio",
          mensaje:
            e instanceof Error
              ? e.message
              : "No se pudieron cargar las empresas",
        });
        setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  useEffect(() => {
    if (!empresaId) return;
    let activo = true;
    nucleo
      .get<MisPermisosNucleo>("/nucleo/permisos/mios", empresaId)
      .then((permisos) => {
        if (!activo) return;
        setPuedeAprobar(permisos.permisos.includes("agente:aprobar"));
        setPermisosListos(true);
      })
      .catch(() => {
        if (!activo) return;
        // La UI no es la autoridad: sin dato de permisos, no ofrece decidir.
        setPuedeAprobar(false);
        setPermisosListos(true);
      });
    return () => {
      activo = false;
    };
  }, [empresaId]);

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!empresaId) return;
      if (silencioso) setActualizando(true);
      else setCargando(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          estado,
          limit: String(LIMITE),
          offset: String(offset),
        });
        if (tipo) params.set("tipo", tipo);
        const lista = await nucleo.get<ListaSolicitudesNucleo>(
          `/nucleo/agente/solicitudes?${params.toString()}`,
          empresaId,
        );
        setSolicitudes(lista.items);
        setTotal(lista.total);
        // Si la página quedó vacía tras una decisión, vuelve al inicio.
        if (lista.items.length === 0 && offset > 0) setOffset(0);
      } catch (e) {
        const clasificado = clasificarError(e);
        setError(clasificado);
        if (clasificado.tipo === "permiso" || clasificado.tipo === "sesion") {
          setSolicitudes([]);
          setTotal(0);
        }
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId, estado, tipo, offset],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  const cargarPendientes = useCallback(async () => {
    if (!empresaId) return;
    try {
      const lista = await nucleo.get<ListaSolicitudesNucleo>(
        "/nucleo/agente/solicitudes?estado=pendiente&limit=1",
        empresaId,
      );
      setPendientes(lista.total);
    } catch {
      // El contador es accesorio; el error principal se muestra en el listado.
    }
  }, [empresaId]);

  useEffect(() => {
    const t = setTimeout(() => {
      void cargarPendientes();
    }, 0);
    return () => clearTimeout(t);
  }, [cargarPendientes]);

  async function reintentar() {
    if (empresaId) {
      await cargar();
      return;
    }
    setCargando(true);
    setError(null);
    try {
      const data = await getEmpresas();
      setEmpresas(data);
      if (data[0]) {
        setEmpresaId(data[0].id);
      } else {
        setError({
          tipo: "dominio",
          mensaje: "El usuario no tiene una empresa activa asignada.",
        });
      }
    } catch (e) {
      setError({
        tipo:
          e instanceof NucleoError && e.status === 401 ? "sesion" : "dominio",
        mensaje:
          e instanceof Error
            ? e.message
            : "No se pudieron cargar las empresas",
      });
    } finally {
      setCargando(false);
    }
  }

  function recargarTodo() {
    void cargar(true);
    void cargarPendientes();
  }

  function cambiarEstado(valor: FiltroEstadoSolicitudNucleo) {
    setEstado(valor);
    setOffset(0);
  }

  function cambiarTipo(valor: string) {
    setTipo(valor);
    setOffset(0);
  }

  const empresa = empresas.find((e) => e.id === empresaId) ?? null;
  const bloqueado = Boolean(error && solicitudes.length === 0);
  const estadoEtiqueta =
    ESTADOS.find((opcion) => opcion.valor === estado)?.etiqueta ?? "Todas";
  const desde = total === 0 ? 0 : offset + 1;
  const hasta = Math.min(offset + solicitudes.length, total);
  const hayPaginaSiguiente = offset + LIMITE < total;
  const errorTono = error?.tipo === "permiso" || error?.tipo === "sesion";
  const IconoError = errorTono ? Lock : AlertTriangle;

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Operación"
        titulo="Buzón del agente WhatsApp"
        descripcion="Solicitudes creadas por el agente para revisión humana. El backend valida permisos, versión y estado; aquí solo se confirma, rechaza o corrige."
        acciones={
          <>
            {estado !== "pendiente" && (
              <Button
                variant="outline"
                onClick={() => cambiarEstado("pendiente")}
              >
                <Inbox /> Ver pendientes
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => void cargar(true)}
              disabled={!empresaId || actualizando}
            >
              <RefreshCw
                className={actualizando ? "animate-spin" : undefined}
              />
              Actualizar
            </Button>
          </>
        }
      />

      {error && (
        <div role="alert">
          <Aviso
            tono={errorTono ? "atencion" : "critico"}
            icono={IconoError}
          >
            <p className="font-medium">
              {error.tipo === "permiso"
                ? "Sin permiso para ver el buzón"
                : error.tipo === "sesion"
                  ? "Sesión expirada"
                  : "No se pudo cargar el buzón"}
            </p>
            <p className="mt-s1">{error.mensaje}</p>
            <div className="mt-s2 flex flex-wrap gap-s2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void reintentar()}
                disabled={cargando}
              >
                Reintentar
              </Button>
              {error.tipo === "sesion" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    router.replace(
                      `/login?next=${encodeURIComponent("/agente/buzon")}`,
                    )
                  }
                >
                  Iniciar sesión
                </Button>
              )}
            </div>
          </Aviso>
        </div>
      )}

      {!bloqueado && (
        <>
          <div className="grid gap-s3 sm:grid-cols-3">
            {cargando && pendientes === null ? (
              <StatTileSkeleton />
            ) : (
              <StatTile
                etiqueta="Pendientes"
                valor={pendientes ?? "—"}
                detalle="Esperando decisión"
                tono={pendientes === 0 ? "ok" : "atencion"}
                icono={Inbox}
              />
            )}
            <StatTile
              etiqueta="En este filtro"
              valor={total}
              detalle={estadoEtiqueta}
              tono="neutro"
              icono={ClipboardList}
            />
            <StatTile
              etiqueta="Con modificaciones"
              valor={
                solicitudes.filter((s) => s.tiene_modificaciones).length
              }
              detalle="En la página actual"
              tono="neutro"
              icono={PencilLine}
            />
          </div>

          {permisosListos && puedeAprobar === false && !error && (
            <Aviso tono="neutro" icono={Lock}>
              Su usuario puede consultar el buzón, pero no decidir
              solicitudes. Se requiere el permiso agente:aprobar.
            </Aviso>
          )}

          <div className="flex flex-wrap items-end justify-between gap-s3">
            <div className="flex flex-wrap items-end gap-s3">
              <Segmentado
                etiqueta="Filtrar por estado"
                valor={estado}
                onCambio={cambiarEstado}
                opciones={ESTADOS.map((opcion) => ({
                  valor: opcion.valor,
                  etiqueta: opcion.etiqueta,
                  contador:
                    opcion.valor === "pendiente"
                      ? (pendientes ?? undefined)
                      : undefined,
                }))}
              />
              <div className="w-[220px] space-y-s1">
                <span className="block text-[14px] font-medium text-tinta-2">
                  Tipo
                </span>
                <SelectSimple
                  valor={tipo}
                  onCambio={cambiarTipo}
                  opciones={[
                    { valor: "", etiqueta: "Todos los tipos" },
                    ...TIPOS,
                  ]}
                  placeholder="Todos los tipos"
                  ariaLabel="Filtrar por tipo de solicitud"
                />
              </div>
            </div>
          </div>

          <Panel
            titulo={`Solicitudes · ${total}`}
            descripcion={
              empresa
                ? `${empresa.razon_social} · ${empresa.zona_horaria}`
                : "Solicitudes de la empresa activa"
            }
            acciones={<StatusBadge tono="info">{estadoEtiqueta}</StatusBadge>}
          >
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Solicitante</TableHead>
                    <TableHead>Flete</TableHead>
                    <TableHead>Resumen</TableHead>
                    <TableHead>Creada</TableHead>
                    <TableHead>Cambios</TableHead>
                    <TableHead className="text-right">Acciones</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cargando ? (
                    <FilasCargando columnas={8} filas={5} />
                  ) : solicitudes.length === 0 ? (
                    <FilaVacia
                      columnas={8}
                      icono={Inbox}
                      titulo={
                        estado === "pendiente" && !tipo
                          ? "No hay solicitudes pendientes"
                          : "No hay solicitudes en este filtro"
                      }
                      descripcion={
                        estado === "pendiente" && !tipo
                          ? "Cuando el agente cree una solicitud, aparecerá aquí para revisión."
                          : "Pruebe con otro estado o tipo de solicitud."
                      }
                      accion={
                        estado !== "pendiente" || tipo ? (
                          <Button
                            variant="outline"
                            onClick={() => {
                              setEstado("pendiente");
                              setTipo("");
                              setOffset(0);
                            }}
                          >
                            Limpiar filtros
                          </Button>
                        ) : undefined
                      }
                    />
                  ) : (
                    solicitudes.map((solicitud) => (
                      <TableRow
                        key={solicitud.id}
                        className="cursor-pointer"
                        onClick={() => setDetalleId(solicitud.id)}
                      >
                        <TableCell>
                          <p className="font-medium">
                            {etiquetaTipoSolicitud(solicitud.tipo)}
                          </p>
                          <p className="font-mono text-[11.5px] text-tinta-3">
                            {solicitud.tipo}
                          </p>
                        </TableCell>
                        <TableCell>
                          <StatusBadge
                            tono={tonoEstadoSolicitud(solicitud.estado)}
                          >
                            {etiquetaEstadoSolicitud(solicitud.estado)}
                          </StatusBadge>
                        </TableCell>
                        <TableCell>
                          <p className="font-medium">
                            {etiquetaSolicitante(solicitud.solicitante)}
                          </p>
                          <p className="text-[12px] text-tinta-3">
                            {solicitud.solicitante.tipo}
                          </p>
                        </TableCell>
                        <TableCell>
                          <span className="font-mono text-[13px]">
                            {solicitud.id_comercial_flete ?? "—"}
                          </span>
                        </TableCell>
                        <TableCell>
                          <p className="line-clamp-2 max-w-[320px] text-[14px] text-tinta-2">
                            {solicitud.resumen}
                          </p>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-[14px]">
                          {formatFechaHora(solicitud.creada_en)}
                        </TableCell>
                        <TableCell>
                          {solicitud.tiene_modificaciones ? (
                            <StatusBadge tono="atencion">
                              Con cambios
                            </StatusBadge>
                          ) : (
                            <span className="text-[13px] text-tinta-3">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="xs"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              setDetalleId(solicitud.id);
                            }}
                            aria-label={`Ver detalle: ${solicitud.resumen}`}
                          >
                            Ver detalle
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-s3 border-t border-borde px-s4 py-s3">
              <p className="text-[14px] text-tinta-3">
                {total === 0
                  ? "Sin resultados"
                  : `Mostrando ${desde}–${hasta} de ${total}`}
              </p>
              <div className="flex items-center gap-s2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setOffset(Math.max(0, offset - LIMITE))}
                  disabled={offset === 0 || cargando}
                >
                  <ChevronLeft /> Anterior
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setOffset(offset + LIMITE)}
                  disabled={!hayPaginaSiguiente || cargando}
                >
                  Siguiente <ChevronRight />
                </Button>
              </div>
            </div>
          </Panel>
        </>
      )}

      {detalleId && (
        <SolicitudDetalleDialog
          empresaId={empresaId}
          solicitudId={detalleId}
          puedeAprobar={puedeAprobar === true}
          onClose={() => setDetalleId(null)}
          onCambio={recargarTodo}
        />
      )}
    </div>
  );
}
