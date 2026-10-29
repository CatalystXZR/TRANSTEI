"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  CalendarDays,
  Pencil,
  Plus,
  RefreshCw,
  Truck,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import { formatFechaHora, toDatetimeLocal } from "@/lib/format";
import type {
  AgendaNucleo,
  AgendaRecursoNucleo,
  BloqueoNucleo,
  EmpresaNucleo,
  TipoRecurso,
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
  Segmentado,
  StatTile,
  StatusBadge,
} from "@/components/sistema";
import { BloqueoDialog } from "@/components/agenda/bloqueo-dialog";

const TIPOS: TipoRecurso[] = ["tracto", "rampla", "chofer"];
const LABEL: Record<TipoRecurso, string> = {
  tracto: "Tractos",
  rampla: "Ramplas",
  chofer: "Choferes",
};

const COLOR_BLOQUEO: Record<string, string> = {
  mantenimiento: "bg-atencion",
  descanso: "bg-marca",
  vacaciones: "bg-ok",
  siniestro: "bg-critico",
  bloqueo_manual: "bg-neutro/70",
  otro: "bg-neutro/70",
};

function rangoInicial() {
  const desde = new Date();
  desde.setHours(0, 0, 0, 0);
  const hasta = new Date(desde);
  hasta.setDate(hasta.getDate() + 7);
  hasta.setHours(23, 59, 0, 0);
  return { desde: toDatetimeLocal(desde), hasta: toDatetimeLocal(hasta) };
}

function etiquetaTipo(tipo: string): string {
  return tipo.replaceAll("_", " ");
}

export default function AgendaPage() {
  const inicial = useMemo(() => rangoInicial(), []);
  const [empresaId, setEmpresaId] = useState("");
  const [empresa, setEmpresa] = useState<EmpresaNucleo | null>(null);
  const [desde, setDesde] = useState(inicial.desde);
  const [hasta, setHasta] = useState(inicial.hasta);
  const [tab, setTab] = useState<TipoRecurso>("tracto");
  const [agenda, setAgenda] = useState<AgendaNucleo | null>(null);
  const [bloqueos, setBloqueos] = useState<BloqueoNucleo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialogo, setDialogo] = useState<{ bloqueo: BloqueoNucleo | null } | null>(
    null,
  );

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
      if (!empresaId || !desde || !hasta) return;
      if (silencioso) setActualizando(true);
      else setCargando(true);
      setError(null);
      try {
        const desdeISO = new Date(desde).toISOString();
        const hastaISO = new Date(hasta).toISOString();
        const [ag, bl] = await Promise.all([
          nucleo.get<AgendaNucleo>(
            `/nucleo/agenda?desde=${encodeURIComponent(desdeISO)}&hasta=${encodeURIComponent(hastaISO)}&recurso_tipo=${tab}`,
            empresaId,
          ),
          nucleo.get<BloqueoNucleo[]>(
            `/nucleo/bloqueos?desde=${encodeURIComponent(desdeISO)}&hasta=${encodeURIComponent(hastaISO)}&recurso_tipo=${tab}`,
            empresaId,
          ),
        ]);
        setAgenda(ag);
        setBloqueos(bl);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar la agenda");
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId, desde, hasta, tab],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  const puedeEscribir = ["admin", "gerente", "despacho", "taller"].includes(
    empresa?.rol ?? "",
  );

  async function cancelar(bloqueo: BloqueoNucleo) {
    const motivo = window.prompt(
      `Motivo para cancelar el bloqueo de ${bloqueo.etiqueta}:`,
    );
    if (!motivo || motivo.trim().length < 3) return;
    try {
      await nucleo.post(
        `/nucleo/bloqueos/${bloqueo.id}/cancelar`,
        empresaId,
        { motivo: motivo.trim() },
      );
      toast.success("Bloqueo cancelado");
      await cargar(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo cancelar");
    }
  }

  const desdeMs = new Date(desde).getTime();
  const hastaMs = new Date(hasta).getTime();
  const dias = Math.max(1, Math.ceil((hastaMs - desdeMs) / 86400000));
  const fechas = Array.from({ length: Math.min(dias, 31) }, (_, i) => {
    const d = new Date(desdeMs + i * 86400000);
    return d;
  });
  const recursos = agenda?.recursos ?? [];

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Operación"
        titulo="Agenda de recursos"
        descripcion="Mantenciones, descansos, vacaciones y bloqueos manuales compiten en el mismo libro de reservas que los viajes. La base impide solapamientos."
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
            <Button
              onClick={() => setDialogo({ bloqueo: null })}
              disabled={!empresaId || !puedeEscribir}
            >
              <Plus /> Nuevo bloqueo
            </Button>
          </>
        }
      />

      {error && (
        <Aviso tono="critico" icono={AlertTriangle}>
          {error}
        </Aviso>
      )}

      <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          etiqueta="Bloqueos en ventana"
          valor={agenda?.total_bloqueos ?? 0}
          detalle="Mantención, descanso, vacaciones…"
          tono="atencion"
          icono={CalendarClock}
          destacado
        />
        <StatTile
          etiqueta="Viajes reservados"
          valor={agenda?.total_viajes ?? 0}
          detalle="En la misma ventana"
          tono="info"
          icono={Truck}
        />
        <StatTile
          etiqueta="Recursos en agenda"
          valor={recursos.filter((r) => r.activo).length}
          detalle={LABEL[tab]}
          tono="neutro"
          icono={CalendarDays}
        />
        <StatTile
          etiqueta="Días consultados"
          valor={dias}
          detalle={`${formatFechaHora(desde)} → ${formatFechaHora(hasta)}`}
          tono="neutro"
          icono={CalendarDays}
        />
      </div>

      <Panel titulo="Ventana de la agenda" className="p-s3">
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
            {agenda?.mensaje ?? "Cargando agenda…"}
          </p>
        </div>
      </Panel>

      <div className="flex flex-wrap items-end justify-between gap-s3">
        <Segmentado
          etiqueta="Tipo de recurso"
          valor={tab}
          onCambio={setTab}
          opciones={TIPOS.map((tipo) => ({
            valor: tipo,
            etiqueta: LABEL[tipo],
            contador: recursos.filter((r) => r.recurso_tipo === tipo).length,
          }))}
        />
        <div className="flex flex-wrap gap-s3 text-[13px] text-tinta-3">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-marca" /> Viaje
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-atencion" /> Mantención
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-ok" /> Vacaciones
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-critico" /> Siniestro
          </span>
        </div>
      </div>

      <Panel
        titulo={`Calendario · ${LABEL[tab]}`}
        descripcion="Cada barra es una reserva activa. Pase el cursor para ver el detalle."
      >
        {cargando ? (
          <div className="space-y-s3 p-s4">
            <div className="h-12 animate-pulse rounded-lg bg-superficie-hundida" />
            <div className="h-12 animate-pulse rounded-lg bg-superficie-hundida" />
            <div className="h-12 animate-pulse rounded-lg bg-superficie-hundida" />
          </div>
        ) : recursos.length === 0 ? (
          <EstadoVacio
            icono={CalendarDays}
            titulo={`Sin ${LABEL[tab].toLowerCase()} activos`}
            descripcion="Cargue los maestros del recurso para ver su agenda."
          />
        ) : (
          <div className="overflow-x-auto">
            <div className="min-w-[760px]">
              <div className="flex border-b border-borde">
                <div className="w-[200px] shrink-0 px-s3 py-s2 text-[13px] font-semibold text-tinta-3">
                  Recurso
                </div>
                <div
                  className="grid flex-1"
                  style={{ gridTemplateColumns: `repeat(${fechas.length}, minmax(0, 1fr))` }}
                >
                  {fechas.map((fecha, i) => (
                    <div
                      key={i}
                      className="border-l border-borde px-1 py-s2 text-center text-[12px] text-tinta-3"
                    >
                      <p className="font-semibold text-tinta-2">
                        {fecha.toLocaleDateString("es-CL", { day: "2-digit" })}
                      </p>
                      <p>{fecha.toLocaleDateString("es-CL", { weekday: "short" })}</p>
                    </div>
                  ))}
                </div>
              </div>
              {recursos.map((recurso) => (
                <FilaAgenda
                  key={recurso.recurso_id}
                  recurso={recurso}
                  desdeMs={desdeMs}
                  hastaMs={hastaMs}
                  dias={fechas.length}
                />
              ))}
            </div>
          </div>
        )}
      </Panel>

      <Panel
        titulo="Bloqueos de la ventana"
        descripcion="Se cancelan, no se borran: la trazabilidad queda en auditoría."
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Recurso</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Inicio</TableHead>
                <TableHead>Fin</TableHead>
                <TableHead>Motivo</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-s5 text-center text-tinta-3">
                    Cargando bloqueos…
                  </TableCell>
                </TableRow>
              ) : bloqueos.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-s5 text-center text-tinta-3">
                    No hay bloqueos en esta ventana.
                  </TableCell>
                </TableRow>
              ) : (
                bloqueos.map((bloqueo) => (
                  <TableRow key={bloqueo.id}>
                    <TableCell className="font-medium">{bloqueo.etiqueta}</TableCell>
                    <TableCell className="capitalize">
                      {etiquetaTipo(bloqueo.tipo_reserva)}
                    </TableCell>
                    <TableCell>{formatFechaHora(bloqueo.inicio)}</TableCell>
                    <TableCell>{formatFechaHora(bloqueo.fin)}</TableCell>
                    <TableCell className="max-w-[260px] truncate text-tinta-2">
                      {bloqueo.motivo ?? "—"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge tono={bloqueo.activa ? "atencion" : "neutro"}>
                        {bloqueo.activa ? "Activo" : "Cancelado"}
                      </StatusBadge>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-s2">
                        {bloqueo.activa && puedeEscribir && (
                          <>
                            <Button
                              size="xs"
                              variant="outline"
                              onClick={() => setDialogo({ bloqueo })}
                            >
                              <Pencil /> Editar
                            </Button>
                            <Button
                              size="xs"
                              variant="destructive"
                              onClick={() => void cancelar(bloqueo)}
                            >
                              <XCircle /> Cancelar
                            </Button>
                          </>
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
        <BloqueoDialog
          empresaId={empresaId}
          recursoTipo={tab}
          bloqueo={dialogo.bloqueo}
          onClose={() => setDialogo(null)}
          onGuardado={() => {
            setDialogo(null);
            void cargar(true);
          }}
        />
      )}
    </div>
  );
}

function FilaAgenda({
  recurso,
  desdeMs,
  hastaMs,
  dias,
}: {
  recurso: AgendaRecursoNucleo;
  desdeMs: number;
  hastaMs: number;
  dias: number;
}) {
  const total = Math.max(1, hastaMs - desdeMs);
  return (
    <div className="flex items-stretch border-b border-borde last:border-b-0">
      <div className="w-[200px] shrink-0 px-s3 py-s3">
        <p className="truncate text-[15px] font-semibold">{recurso.etiqueta}</p>
        <p className="text-[12px] text-tinta-3">
          {recurso.estado} · {recurso.items.length} reserva(s)
        </p>
      </div>
      <div className="relative flex-1">
        <div
          className="pointer-events-none absolute inset-0 grid"
          style={{ gridTemplateColumns: `repeat(${dias}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: dias }).map((_, i) => (
            <span key={i} className="border-l border-borde/70" />
          ))}
        </div>
        <div className="relative h-[62px]">
          {recurso.items.map((item) => {
            const start = Math.max(new Date(item.inicio).getTime(), desdeMs);
            const end = Math.min(new Date(item.fin).getTime(), hastaMs);
            if (end <= start) return null;
            const left = ((start - desdeMs) / total) * 100;
            const width = Math.max(0.6, ((end - start) / total) * 100);
            const color =
              item.origen === "viaje"
                ? "bg-marca/45 border-marca"
                : `${COLOR_BLOQUEO[item.tipo_reserva] ?? "bg-neutro/70"} border-black/10`;
            return (
              <div
                key={`${item.id}-${item.inicio}`}
                title={`${item.origen === "viaje" ? item.numero_viaje ?? "Viaje" : etiquetaTipo(item.tipo_reserva)} · ${formatFechaHora(item.inicio)} → ${formatFechaHora(item.fin)}${item.motivo ? ` · ${item.motivo}` : ""}`}
                className={`absolute top-[14px] h-[30px] overflow-hidden rounded-md border px-1.5 text-[11px] leading-[28px] text-white ${color}`}
                style={{ left: `${left}%`, width: `${width}%` }}
              >
                <span className="truncate">
                  {item.origen === "viaje"
                    ? item.numero_viaje ?? "Viaje"
                    : etiquetaTipo(item.tipo_reserva)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
