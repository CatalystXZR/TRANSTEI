"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, FileText, Plus, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import type {
  ChoferNucleo,
  ClienteNucleo,
  EmpresaNucleo,
  RamplaNucleo,
  TipoRecurso,
  TractoNucleo,
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
  Patente,
  Segmentado,
  StatusBadge,
} from "@/components/sistema";
import { MaestroDialog } from "@/components/maestros/maestro-dialog";
import { DocumentosDialog } from "@/components/maestros/documentos-dialog";
import {
  ETIQUETA_MAESTRO,
  type TipoMaestro,
} from "@/components/maestros/config";

type Registro = Record<string, unknown>;

const TABS: TipoMaestro[] = ["clientes", "tractos", "ramplas", "choferes"];

const RECURSO_DOC: Partial<Record<TipoMaestro, TipoRecurso>> = {
  tractos: "tracto",
  ramplas: "rampla",
  choferes: "chofer",
};

export default function MaestrosPage() {
  const [empresaId, setEmpresaId] = useState("");
  const [empresa, setEmpresa] = useState<EmpresaNucleo | null>(null);
  const [tab, setTab] = useState<TipoMaestro>("clientes");
  const [registros, setRegistros] = useState<Registro[]>([]);
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [dialogo, setDialogo] = useState<{
    tipo: TipoMaestro;
    registro: Registro | null;
  } | null>(null);
  const [docs, setDocs] = useState<{
    tipo: TipoRecurso;
    id: string;
    etiqueta: string;
  } | null>(null);

  useEffect(() => {
    let activo = true;
    getEmpresas()
      .then((data) => {
        if (!activo) return;
        if (data[0]) {
          setEmpresa(data[0]);
          setEmpresaId(data[0].id);
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
        const data = await nucleo.get<Registro[]>(`/nucleo/${tab}`, empresaId);
        setRegistros(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar maestros");
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId, tab],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  const filtrados = registros.filter((r) =>
    JSON.stringify(r).toLowerCase().includes(busqueda.trim().toLowerCase()),
  );

  async function desactivar(registro: Registro) {
    const etiqueta =
      String(registro.razon_social ?? registro.patente ?? registro.nombre ?? "registro");
    if (!window.confirm(`¿Desactivar ${etiqueta}? No se borra; queda inactivo.`)) return;
    try {
      await nucleo.del(`/nucleo/${tab}/${registro.id}`, empresaId);
      toast.success("Registro desactivado");
      await cargar(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo desactivar");
    }
  }

  function etiquetaRegistro(registro: Registro): string {
    if (tab === "clientes") return String(registro.razon_social ?? "");
    if (tab === "choferes") {
      const c = registro as unknown as ChoferNucleo;
      return [c.nombre, c.apellido_paterno].filter(Boolean).join(" ");
    }
    return String(registro.patente ?? "");
  }

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Operación"
        titulo="Maestros del núcleo"
        descripcion="Clientes, tractos, ramplas y choferes con sus documentos. Los registros no se borran: se desactivan."
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
            <Button onClick={() => setDialogo({ tipo: tab, registro: null })}>
              <Plus /> Nuevo
            </Button>
          </>
        }
      />

      {error && (
        <Aviso tono="critico" icono={AlertTriangle}>
          {error}
        </Aviso>
      )}

      <div className="flex flex-wrap items-end justify-between gap-s3">
        <Segmentado
          etiqueta="Tipo de maestro"
          valor={tab}
          onCambio={(v) => {
            setTab(v);
            setBusqueda("");
          }}
          opciones={TABS.map((t) => ({ valor: t, etiqueta: ETIQUETA_MAESTRO[t] }))}
        />
        <label className="relative w-full sm:w-[320px]">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-tinta-3" />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder={`Buscar en ${ETIQUETA_MAESTRO[tab].toLowerCase()}…`}
            className="pl-9"
          />
        </label>
      </div>

      <Panel
        titulo={`${ETIQUETA_MAESTRO[tab]} · ${filtrados.length}`}
        descripcion={empresa ? empresa.razon_social : undefined}
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {tab === "clientes" && (
                  <>
                    <TableHead>Cliente</TableHead>
                    <TableHead>RUT</TableHead>
                    <TableHead>Pago</TableHead>
                    <TableHead>OC</TableHead>
                    <TableHead>Estado</TableHead>
                  </>
                )}
                {tab === "tractos" && (
                  <>
                    <TableHead>Patente</TableHead>
                    <TableHead>Marca / modelo</TableHead>
                    <TableHead>Capacidad</TableHead>
                    <TableHead>Licencias</TableHead>
                    <TableHead>Estado</TableHead>
                  </>
                )}
                {tab === "ramplas" && (
                  <>
                    <TableHead>Patente</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Capacidad</TableHead>
                    <TableHead>Volumen</TableHead>
                    <TableHead>Estado</TableHead>
                  </>
                )}
                {tab === "choferes" && (
                  <>
                    <TableHead>Chofer</TableHead>
                    <TableHead>RUT</TableHead>
                    <TableHead>Licencia</TableHead>
                    <TableHead>Comisión</TableHead>
                    <TableHead>Estado</TableHead>
                  </>
                )}
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-s6 text-center text-tinta-3">
                    Cargando maestros…
                  </TableCell>
                </TableRow>
              ) : filtrados.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="p-0">
                    <EstadoVacio
                      icono={FileText}
                      titulo="Sin registros"
                      descripcion="Cree el primer maestro de esta pestaña."
                      accion={
                        <Button onClick={() => setDialogo({ tipo: tab, registro: null })}>
                          <Plus /> Nuevo
                        </Button>
                      }
                    />
                  </TableCell>
                </TableRow>
              ) : (
                filtrados.map((registro) => (
                  <TableRow key={String(registro.id)}>
                    {tab === "clientes" && (
                      <>
                        <TableCell className="font-medium">
                          {(registro as unknown as ClienteNucleo).razon_social}
                        </TableCell>
                        <TableCell>{(registro as unknown as ClienteNucleo).rut}</TableCell>
                        <TableCell>{(registro as unknown as ClienteNucleo).dias_pago} días</TableCell>
                        <TableCell>
                          {(registro as unknown as ClienteNucleo).exige_oc ? (
                            <StatusBadge tono="atencion">Exige</StatusBadge>
                          ) : (
                            <span className="text-tinta-3">No</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <StatusBadge tono={registro.activo ? "ok" : "neutro"}>
                            {registro.activo ? "Activo" : "Inactivo"}
                          </StatusBadge>
                        </TableCell>
                      </>
                    )}
                    {tab === "tractos" && (
                      <>
                        <TableCell><Patente>{String(registro.patente)}</Patente></TableCell>
                        <TableCell>
                          {[registro.marca, registro.modelo].filter(Boolean).join(" · ") || "—"}
                        </TableCell>
                        <TableCell>
                          {Number((registro as unknown as TractoNucleo).capacidad_carga_kg).toLocaleString("es-CL")} kg
                        </TableCell>
                        <TableCell>
                          {((registro as unknown as TractoNucleo).licencias_permitidas ?? []).join(", ") || "—"}
                        </TableCell>
                        <TableCell>
                          <StatusBadge tono={registro.activo ? "ok" : "neutro"}>
                            {String(registro.estado ?? "—")}
                          </StatusBadge>
                        </TableCell>
                      </>
                    )}
                    {tab === "ramplas" && (
                      <>
                        <TableCell><Patente>{String(registro.patente)}</Patente></TableCell>
                        <TableCell>{String(registro.tipo ?? "—")}</TableCell>
                        <TableCell>
                          {Number((registro as unknown as RamplaNucleo).capacidad_carga_kg).toLocaleString("es-CL")} kg
                        </TableCell>
                        <TableCell>
                          {(registro as unknown as RamplaNucleo).volumen_m3
                            ? `${Number((registro as unknown as RamplaNucleo).volumen_m3).toLocaleString("es-CL")} m³`
                            : "—"}
                        </TableCell>
                        <TableCell>
                          <StatusBadge tono={registro.activo ? "ok" : "neutro"}>
                            {String(registro.estado ?? "—")}
                          </StatusBadge>
                        </TableCell>
                      </>
                    )}
                    {tab === "choferes" && (
                      <>
                        <TableCell className="font-medium">
                          {etiquetaRegistro(registro)}
                        </TableCell>
                        <TableCell>{String(registro.rut ?? "—")}</TableCell>
                        <TableCell>
                          {String((registro as unknown as ChoferNucleo).licencia_clase ?? "—")}
                        </TableCell>
                        <TableCell>
                          {(
                            Number((registro as unknown as ChoferNucleo).porcentaje_comision) * 100
                          ).toLocaleString("es-CL", { maximumFractionDigits: 2 })}
                          %
                        </TableCell>
                        <TableCell>
                          <StatusBadge tono={registro.activo ? "ok" : "neutro"}>
                            {String(registro.estado ?? "—")}
                          </StatusBadge>
                        </TableCell>
                      </>
                    )}
                    <TableCell>
                      <div className="flex justify-end gap-s2">
                        <Button
                          size="xs"
                          variant="outline"
                          onClick={() => setDialogo({ tipo: tab, registro })}
                        >
                          Editar
                        </Button>
                        {RECURSO_DOC[tab] && (
                          <Button
                            size="xs"
                            variant="outline"
                            onClick={() =>
                              setDocs({
                                tipo: RECURSO_DOC[tab] as TipoRecurso,
                                id: String(registro.id),
                                etiqueta: etiquetaRegistro(registro),
                              })
                            }
                          >
                            <FileText /> Documentos
                          </Button>
                        )}
                        {Boolean(registro.activo) && (
                          <Button
                            size="xs"
                            variant="destructive"
                            onClick={() => void desactivar(registro)}
                          >
                            Desactivar
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </Panel>

      {dialogo && (
        <MaestroDialog
          tipo={dialogo.tipo}
          empresaId={empresaId}
          registro={dialogo.registro}
          onClose={() => setDialogo(null)}
          onGuardado={() => {
            setDialogo(null);
            void cargar(true);
          }}
        />
      )}

      {docs && (
        <DocumentosDialog
          empresaId={empresaId}
          recursoTipo={docs.tipo}
          recursoId={docs.id}
          etiqueta={docs.etiqueta}
          onClose={() => setDocs(null)}
        />
      )}
    </div>
  );
}
