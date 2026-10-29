"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  FileClock,
  RefreshCw,
  Search,
} from "lucide-react";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import { formatFechaHora } from "@/lib/format";
import type {
  HistorialCambioNucleo,
  PaginaAuditoriaNucleo,
  TablaAuditoriaNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import {
  Aviso,
  PageHeader,
  Panel,
  StatTile,
  StatusBadge,
} from "@/components/sistema";
import { SelectSimple } from "@/components/formulario";

const OPERACIONES = [
  { valor: "", etiqueta: "Todas las operaciones" },
  { valor: "INSERT", etiqueta: "INSERT" },
  { valor: "UPDATE", etiqueta: "UPDATE" },
  { valor: "DELETE", etiqueta: "DELETE" },
];

export default function AuditoriaPage() {
  const [empresaId, setEmpresaId] = useState("");
  const [pagina, setPagina] = useState<PaginaAuditoriaNucleo | null>(null);
  const [tablas, setTablas] = useState<TablaAuditoriaNucleo[]>([]);
  const [tabla, setTabla] = useState("");
  const [operacion, setOperacion] = useState("");
  const [registro, setRegistro] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [offset, setOffset] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detalle, setDetalle] = useState<HistorialCambioNucleo | null>(null);
  const limit = 50;

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
        const params = new URLSearchParams({
          limit: String(limit),
          offset: String(offset),
          ...(tabla ? { tabla } : {}),
          ...(operacion ? { operacion } : {}),
          ...(registro.trim() ? { registro_id: registro.trim() } : {}),
          ...(desde ? { desde: new Date(`${desde}T00:00:00`).toISOString() } : {}),
          ...(hasta ? { hasta: new Date(`${hasta}T23:59:59`).toISOString() } : {}),
        });
        const [pag, tabs] = await Promise.all([
          nucleo.get<PaginaAuditoriaNucleo>(
            `/nucleo/auditoria?${params.toString()}`,
            empresaId,
          ),
          nucleo.get<TablaAuditoriaNucleo[]>("/nucleo/auditoria/tablas", empresaId),
        ]);
        setPagina(pag);
        setTablas(tabs);
      } catch (e) {
        setError(e instanceof Error ? e.message : "No se pudo cargar la auditoría");
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId, tabla, operacion, registro, desde, hasta, offset],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 250);
    return () => clearTimeout(t);
  }, [cargar]);

  const items = pagina?.items ?? [];

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Sistema"
        titulo="Auditoría"
        descripcion="Registro inmutable de inserciones, cambios y borrados. Filtre por tabla, operación, registro o fecha."
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
          etiqueta="Registros en la página"
          valor={items.length}
          detalle={`${pagina?.total ?? 0} en total`}
          tono="info"
          icono={FileClock}
          destacado
        />
        <StatTile
          etiqueta="Tablas auditadas"
          valor={tablas.length}
          detalle="Con al menos un cambio"
          tono="neutro"
          icono={FileClock}
        />
        <StatTile
          etiqueta="Operación filtrada"
          valor={operacion || "Todas"}
          detalle={tabla || "Todas las tablas"}
          tono="neutro"
          icono={FileClock}
        />
      </div>

      <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-6">
        <div className="xl:col-span-2">
          <SelectSimple
            valor={tabla}
            onCambio={(v) => {
              setTabla(v);
              setOffset(0);
            }}
            placeholder="Tabla"
            opciones={[
              { valor: "", etiqueta: "Todas las tablas" },
              ...tablas.map((t) => ({
                valor: t.tabla,
                etiqueta: `${t.tabla.replace("nucleo.", "")} (${t.total})`,
              })),
            ]}
            ariaLabel="Filtrar por tabla"
          />
        </div>
        <div>
          <SelectSimple
            valor={operacion}
            onCambio={(v) => {
              setOperacion(v);
              setOffset(0);
            }}
            opciones={OPERACIONES}
            ariaLabel="Filtrar por operación"
          />
        </div>
        <label className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-tinta-3" />
          <Input
            value={registro}
            onChange={(e) => {
              setRegistro(e.target.value);
              setOffset(0);
            }}
            placeholder="UUID registro"
            className="pl-9"
          />
        </label>
        <Input
          type="date"
          value={desde}
          onChange={(e) => {
            setDesde(e.target.value);
            setOffset(0);
          }}
          aria-label="Desde"
        />
        <Input
          type="date"
          value={hasta}
          onChange={(e) => {
            setHasta(e.target.value);
            setOffset(0);
          }}
          aria-label="Hasta"
        />
      </div>

      <Panel titulo={`Cambios · ${pagina?.total ?? 0}`}>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fecha</TableHead>
                <TableHead>Tabla</TableHead>
                <TableHead>Operación</TableHead>
                <TableHead>Registro</TableHead>
                <TableHead>Usuario</TableHead>
                <TableHead className="text-right">Detalle</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-s6 text-center text-tinta-3">
                    Cargando auditoría…
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-s6 text-center text-tinta-3">
                    Sin registros para los filtros seleccionados.
                  </TableCell>
                </TableRow>
              ) : (
                items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{formatFechaHora(item.ocurrido_en)}</TableCell>
                    <TableCell className="font-mono text-[13px]">
                      {item.tabla.replace("nucleo.", "")}
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        tono={
                          item.operacion === "INSERT"
                            ? "ok"
                            : item.operacion === "UPDATE"
                              ? "atencion"
                              : "critico"
                        }
                      >
                        {item.operacion}
                      </StatusBadge>
                    </TableCell>
                    <TableCell className="font-mono text-[12px] text-tinta-3">
                      {item.registro_id ? `${item.registro_id.slice(0, 8)}…` : "—"}
                    </TableCell>
                    <TableCell className="text-[13px]">
                      {item.auth_id ? `${item.auth_id.slice(0, 8)}…` : "sistema"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button size="xs" variant="outline" onClick={() => setDetalle(item)}>
                        Ver
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
        <div className="flex items-center justify-between border-t border-borde p-s3 text-[14px]">
          <p className="text-tinta-3">
            {pagina ? `${pagina.offset + 1}–${pagina.offset + items.length} de ${pagina.total}` : "—"}
          </p>
          <div className="flex gap-s2">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0 || cargando}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Anterior
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!pagina?.hay_mas || cargando}
              onClick={() => setOffset(offset + limit)}
            >
              Siguiente
            </Button>
          </div>
        </div>
      </Panel>

      {detalle && (
        <Dialog open onOpenChange={(open) => !open && setDetalle(null)}>
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
            <DialogHeader>
              <DialogTitle>
                {detalle.operacion} · {detalle.tabla}
              </DialogTitle>
              <DialogDescription>
                {formatFechaHora(detalle.ocurrido_en)} ·{" "}
                {detalle.auth_id ? `usuario ${detalle.auth_id}` : "sistema"} · registro{" "}
                {detalle.registro_id ?? "—"}
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-s3 sm:grid-cols-2">
              <div>
                <p className="mb-s2 text-[14px] font-semibold">Antes</p>
                <pre className="max-h-[420px] overflow-auto rounded-lg bg-superficie-hundida p-s3 text-[12px]">
                  {detalle.datos_antes ? JSON.stringify(detalle.datos_antes, null, 2) : "—"}
                </pre>
              </div>
              <div>
                <p className="mb-s2 text-[14px] font-semibold">Después</p>
                <pre className="max-h-[420px] overflow-auto rounded-lg bg-superficie-hundida p-s3 text-[12px]">
                  {detalle.datos_despues ? JSON.stringify(detalle.datos_despues, null, 2) : "—"}
                </pre>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
