"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  Download,
  FileCheck2,
  Lock,
  Plus,
  RefreshCw,
  Wallet,
} from "lucide-react";
import { toast } from "sonner";
import { descargarNucleo, nucleo } from "@/lib/nucleo";
import { useNucleoEmpresa } from "@/lib/use-nucleo-empresa";
import { formatCLP, formatFecha, formatFechaHora } from "@/lib/format";
import type {
  AjusteCreateNucleo,
  AjusteNucleo,
  AnticipoCreateNucleo,
  AnticipoNucleo,
  ChoferNucleo,
  LiquidacionCreateNucleo,
  LiquidacionNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputCLP } from "@/components/ui-inputs/input-clp";
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
  FilaVacia,
  FilasCargando,
  PageHeader,
  Panel,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import { AreaTexto, Campo, SelectSimple } from "@/components/formulario";
import { ErrorNucleo } from "@/components/nucleo/estado-error";

const ESTADOS_LIQ: Record<string, { tono: Tono; label: string }> = {
  borrador: { tono: "atencion", label: "Borrador" },
  emitida: { tono: "ok", label: "Emitida" },
  anulada: { tono: "critico", label: "Anulada" },
};

function mesActual() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function hoyISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function mensajeDeError(error: unknown) {
  return error instanceof Error ? error.message : "Ocurrió un error inesperado.";
}

function nombreChofer(chofer: ChoferNucleo) {
  return [chofer.nombre, chofer.apellido_paterno].filter(Boolean).join(" ");
}

function etiquetaEstado(estado: string) {
  return ESTADOS_LIQ[estado] ?? { tono: "neutro" as Tono, label: estado };
}

export default function LiquidacionesPage() {
  const {
    empresa,
    empresaId,
    permisos,
    cargando: cargandoSesion,
    error: errorSesion,
  } = useNucleoEmpresa();

  const puedeEscribir = permisos.includes("liquidaciones:escribir");
  const puedeVerChoferes = permisos.includes("maestros:leer");

  const [mes, setMes] = useState("");
  const [choferFiltro, setChoferFiltro] = useState("");
  const [estadoFiltro, setEstadoFiltro] = useState("");
  const [liquidaciones, setLiquidaciones] = useState<LiquidacionNucleo[]>([]);
  const [choferes, setChoferes] = useState<ChoferNucleo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [errorDatos, setErrorDatos] = useState<unknown>(null);
  const [recarga, setRecarga] = useState(0);

  const [detalle, setDetalle] = useState<LiquidacionNucleo | null>(null);
  const [anticipos, setAnticipos] = useState<AnticipoNucleo[]>([]);
  const [ajustes, setAjustes] = useState<AjusteNucleo[]>([]);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [errorDetalle, setErrorDetalle] = useState<unknown>(null);

  const [dialogoNueva, setDialogoNueva] = useState(false);
  const [formNueva, setFormNueva] = useState({
    chofer_id: "",
    sueldo_base: 0,
    notas: "",
  });
  const [errorNueva, setErrorNueva] = useState<string | null>(null);

  const [emitiendo, setEmitiendo] = useState<LiquidacionNucleo | null>(null);
  const [anulando, setAnulando] = useState<LiquidacionNucleo | null>(null);
  const [motivo, setMotivo] = useState("");
  const [errorAnulacion, setErrorAnulacion] = useState<string | null>(null);

  const [dialogoAnticipo, setDialogoAnticipo] = useState(false);
  const [formAnticipo, setFormAnticipo] = useState({
    monto: 0,
    fecha: hoyISO(),
    mes_imputacion: "",
    notas: "",
  });
  const [errorAnticipo, setErrorAnticipo] = useState<string | null>(null);

  const [dialogoAjuste, setDialogoAjuste] = useState(false);
  const [formAjuste, setFormAjuste] = useState<{
    tipo: "bono" | "descuento";
    concepto: string;
    monto: number;
  }>({ tipo: "bono", concepto: "", monto: 0 });
  const [errorAjuste, setErrorAjuste] = useState<string | null>(null);

  const [procesando, setProcesando] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setMes(mesActual()), 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!empresaId || !puedeVerChoferes) return;
    let activo = true;
    nucleo
      .get<ChoferNucleo[]>("/nucleo/choferes", empresaId)
      .then((data) => {
        if (activo) setChoferes(data);
      })
      .catch(() => {
        if (activo) setChoferes([]);
      });
    return () => {
      activo = false;
    };
  }, [empresaId, puedeVerChoferes]);

  useEffect(() => {
    if (!empresaId || !mes) return;
    let activo = true;
    const t = setTimeout(() => {
      setCargando(true);
      setErrorDatos(null);
      const params = new URLSearchParams({ mes });
      if (choferFiltro) params.set("chofer_id", choferFiltro);
      if (estadoFiltro) params.set("estado", estadoFiltro);
      nucleo
        .get<LiquidacionNucleo[]>(
          `/nucleo/liquidaciones?${params.toString()}`,
          empresaId,
        )
        .then((data) => {
          if (activo) setLiquidaciones(data);
        })
        .catch((e) => {
          if (activo) setErrorDatos(e);
        })
        .finally(() => {
          if (activo) setCargando(false);
        });
    }, 150);
    return () => {
      activo = false;
      clearTimeout(t);
    };
  }, [empresaId, mes, choferFiltro, estadoFiltro, recarga]);

  const recargar = useCallback(() => {
    setRecarga((valor) => valor + 1);
  }, []);

  const cargarDetalle = useCallback(
    async (liquidacion: LiquidacionNucleo) => {
      if (!empresaId) return;
      setCargandoDetalle(true);
      setErrorDetalle(null);
      try {
        const [listaAnticipos, listaAjustes] = await Promise.all([
          nucleo.get<AnticipoNucleo[]>(
            `/nucleo/anticipos?chofer_id=${liquidacion.chofer_id}&mes=${liquidacion.mes}`,
            empresaId,
          ),
          nucleo.get<AjusteNucleo[]>(
            `/nucleo/ajustes?chofer_id=${liquidacion.chofer_id}&mes=${liquidacion.mes}`,
            empresaId,
          ),
        ]);
        setAnticipos(listaAnticipos);
        setAjustes(listaAjustes);
      } catch (e) {
        setErrorDetalle(e);
      } finally {
        setCargandoDetalle(false);
      }
    },
    [empresaId],
  );

  const abrirDetalle = (liquidacion: LiquidacionNucleo) => {
    setDetalle(liquidacion);
    setAnticipos([]);
    setAjustes([]);
    void cargarDetalle(liquidacion);
  };

  const contadores = useMemo(() => {
    return {
      total: liquidaciones.length,
      borradores: liquidaciones.filter((l) => l.estado === "borrador").length,
      emitidas: liquidaciones.filter((l) => l.estado === "emitida").length,
      anuladas: liquidaciones.filter((l) => l.estado === "anulada").length,
    };
  }, [liquidaciones]);

  async function crearBorrador() {
    setErrorNueva(null);
    if (!formNueva.chofer_id) {
      setErrorNueva("Seleccione un chofer.");
      return;
    }
    if (!mes) {
      setErrorNueva("Seleccione el mes de la liquidación.");
      return;
    }
    const body: LiquidacionCreateNucleo = {
      chofer_id: formNueva.chofer_id,
      mes,
      ...(formNueva.sueldo_base > 0
        ? { sueldo_base: formNueva.sueldo_base }
        : {}),
      ...(formNueva.notas.trim() ? { notas: formNueva.notas.trim() } : {}),
    };
    setProcesando("nueva");
    try {
      const liquidacion = await nucleo.post<LiquidacionNucleo>(
        "/nucleo/liquidaciones",
        empresaId,
        body,
      );
      toast.success("Liquidación creada como borrador");
      setDialogoNueva(false);
      setFormNueva({ chofer_id: "", sueldo_base: 0, notas: "" });
      setDetalle(liquidacion);
      void cargarDetalle(liquidacion);
      recargar();
    } catch (e) {
      const mensaje = mensajeDeError(e);
      setErrorNueva(mensaje);
      toast.error(mensaje);
    } finally {
      setProcesando(null);
    }
  }

  async function emitir() {
    if (!emitiendo) return;
    setProcesando("emitir");
    try {
      const liquidacion = await nucleo.post<LiquidacionNucleo>(
        `/nucleo/liquidaciones/${emitiendo.id}/emitir`,
        empresaId,
        {},
      );
      toast.success("Liquidación emitida");
      setEmitiendo(null);
      if (detalle?.id === liquidacion.id) {
        setDetalle(liquidacion);
        void cargarDetalle(liquidacion);
      }
      recargar();
    } catch (e) {
      toast.error(mensajeDeError(e));
    } finally {
      setProcesando(null);
    }
  }

  async function anular() {
    if (!anulando) return;
    setErrorAnulacion(null);
    if (motivo.trim().length < 3) {
      setErrorAnulacion("El motivo debe tener al menos 3 caracteres.");
      return;
    }
    setProcesando("anular");
    try {
      const liquidacion = await nucleo.post<LiquidacionNucleo>(
        `/nucleo/liquidaciones/${anulando.id}/anular`,
        empresaId,
        { motivo: motivo.trim() },
      );
      toast.success("Liquidación anulada; el documento se conserva");
      setAnulando(null);
      setMotivo("");
      if (detalle?.id === liquidacion.id) {
        setDetalle(liquidacion);
        void cargarDetalle(liquidacion);
      }
      recargar();
    } catch (e) {
      const mensaje = mensajeDeError(e);
      setErrorAnulacion(mensaje);
      toast.error(mensaje);
    } finally {
      setProcesando(null);
    }
  }

  async function guardarAnticipo() {
    if (!detalle) return;
    setErrorAnticipo(null);
    if (formAnticipo.monto <= 0) {
      setErrorAnticipo("El monto del anticipo debe ser mayor que cero.");
      return;
    }
    if (!/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(formAnticipo.mes_imputacion)) {
      setErrorAnticipo("Indique el mes de imputación en formato AAAA-MM.");
      return;
    }
    const body: AnticipoCreateNucleo = {
      chofer_id: detalle.chofer_id,
      fecha: formAnticipo.fecha || hoyISO(),
      monto: formAnticipo.monto,
      mes_imputacion: formAnticipo.mes_imputacion,
      ...(formAnticipo.notas.trim() ? { notas: formAnticipo.notas.trim() } : {}),
    };
    setProcesando("anticipo");
    try {
      await nucleo.post<AnticipoNucleo>("/nucleo/anticipos", empresaId, body);
      toast.success("Anticipo registrado");
      setDialogoAnticipo(false);
      setFormAnticipo({
        monto: 0,
        fecha: hoyISO(),
        mes_imputacion: detalle.mes,
        notas: "",
      });
      await cargarDetalle(detalle);
    } catch (e) {
      const mensaje = mensajeDeError(e);
      setErrorAnticipo(mensaje);
      toast.error(mensaje);
    } finally {
      setProcesando(null);
    }
  }

  async function guardarAjuste() {
    if (!detalle) return;
    setErrorAjuste(null);
    if (!formAjuste.concepto.trim()) {
      setErrorAjuste("El concepto es obligatorio.");
      return;
    }
    if (formAjuste.monto < 0) {
      setErrorAjuste("El monto no puede ser negativo.");
      return;
    }
    const body: AjusteCreateNucleo = {
      chofer_id: detalle.chofer_id,
      mes: detalle.mes,
      tipo: formAjuste.tipo,
      concepto: formAjuste.concepto.trim(),
      monto: formAjuste.monto,
    };
    setProcesando("ajuste");
    try {
      await nucleo.post<AjusteNucleo>("/nucleo/ajustes", empresaId, body);
      toast.success(
        formAjuste.tipo === "bono" ? "Bono registrado" : "Descuento registrado",
      );
      setDialogoAjuste(false);
      setFormAjuste({ tipo: "bono", concepto: "", monto: 0 });
      await cargarDetalle(detalle);
    } catch (e) {
      const mensaje = mensajeDeError(e);
      setErrorAjuste(mensaje);
      toast.error(mensaje);
    } finally {
      setProcesando(null);
    }
  }

  async function exportar() {
    if (!mes) return;
    try {
      await descargarNucleo(
        `/nucleo/export/liquidaciones?mes=${mes}`,
        empresaId,
        `liquidaciones_${mes}.csv`,
      );
    } catch (e) {
      toast.error(mensajeDeError(e));
    }
  }

  const cargandoVista = cargandoSesion || !mes || cargando;
  const bloqueado = Boolean(errorSesion || errorDatos);
  const opcionesChofer = choferes.map((c) => ({
    valor: c.id,
    etiqueta: `${nombreChofer(c)} · ${c.rut}`,
  }));
  const puedeEditarDetalle = puedeEscribir && detalle?.estado === "borrador";

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Finanzas"
        titulo="Liquidaciones de sueldo"
        descripcion="Documentos del núcleo con montos almacenados: base, comisión de fletes, bonos, descuentos y anticipos. Emitir es idempotente y anular conserva el documento."
        acciones={
          <>
            <label className="flex items-center gap-s2 text-tinta-3">
              <CalendarDays className="size-[18px]" />
              <span className="sr-only">Mes de liquidación</span>
              <Input
                type="month"
                value={mes}
                onChange={(e) => e.target.value && setMes(e.target.value)}
                className="w-48"
                aria-label="Mes de liquidación"
              />
            </label>
            <Button
              variant="outline"
              onClick={() => void exportar()}
              disabled={!mes || bloqueado}
            >
              <Download /> Exportar CSV
            </Button>
            <Button
              variant="outline"
              onClick={recargar}
              disabled={!empresaId || cargando}
            >
              <RefreshCw className={cargando ? "animate-spin" : undefined} />
              Actualizar
            </Button>
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

      <div className="flex flex-wrap items-end gap-s3">
        <div className="w-[260px]">
          <SelectSimple
            valor={choferFiltro}
            onCambio={setChoferFiltro}
            opciones={opcionesChofer}
            placeholder="Todos los choferes"
            ariaLabel="Filtrar por chofer"
          />
        </div>
        <div className="w-[200px]">
          <SelectSimple
            valor={estadoFiltro}
            onCambio={setEstadoFiltro}
            opciones={[
              { valor: "borrador", etiqueta: "Borrador" },
              { valor: "emitida", etiqueta: "Emitida" },
              { valor: "anulada", etiqueta: "Anulada" },
            ]}
            placeholder="Todos los estados"
            ariaLabel="Filtrar por estado"
          />
        </div>
        {puedeEscribir && (
          <Button
            onClick={() => {
              setErrorNueva(null);
              setFormNueva({ chofer_id: "", sueldo_base: 0, notas: "" });
              setDialogoNueva(true);
            }}
            disabled={!empresaId || !puedeVerChoferes}
          >
            <Plus /> Nuevo borrador
          </Button>
        )}
      </div>

      <div className="grid gap-s3 sm:grid-cols-4">
        <div className="rounded-xl border border-borde bg-superficie px-s4 py-s3 shadow-elev-1">
          <p className="text-[14px] text-tinta-3">Documentos del mes</p>
          <p className="cifra text-[26px] font-semibold">{contadores.total}</p>
        </div>
        <div className="rounded-xl border border-borde bg-superficie px-s4 py-s3 shadow-elev-1">
          <p className="text-[14px] text-tinta-3">Borradores</p>
          <p className="cifra text-[26px] font-semibold">{contadores.borradores}</p>
        </div>
        <div className="rounded-xl border border-borde bg-superficie px-s4 py-s3 shadow-elev-1">
          <p className="text-[14px] text-tinta-3">Emitidas</p>
          <p className="cifra text-[26px] font-semibold">{contadores.emitidas}</p>
        </div>
        <div className="rounded-xl border border-borde bg-superficie px-s4 py-s3 shadow-elev-1">
          <p className="text-[14px] text-tinta-3">Anuladas</p>
          <p className="cifra text-[26px] font-semibold">{contadores.anuladas}</p>
        </div>
      </div>

      <Panel titulo={`Liquidaciones · ${liquidaciones.length}`}>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Chofer</TableHead>
                <TableHead className="text-right">Base</TableHead>
                <TableHead className="text-right">Comisión</TableHead>
                <TableHead className="text-right">Bonos</TableHead>
                <TableHead className="text-right">Descuentos</TableHead>
                <TableHead className="text-right">Anticipos</TableHead>
                <TableHead className="text-right">Líquido</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargandoVista ? (
                <FilasCargando columnas={9} />
              ) : liquidaciones.length === 0 ? (
                <FilaVacia
                  columnas={9}
                  icono={Wallet}
                  titulo="Sin liquidaciones en el período"
                  descripcion="Cree un borrador para el chofer y mes seleccionados."
                  accion={
                    puedeEscribir && puedeVerChoferes ? (
                      <Button onClick={() => setDialogoNueva(true)}>
                        <Plus /> Nuevo borrador
                      </Button>
                    ) : undefined
                  }
                />
              ) : (
                liquidaciones.map((liquidacion) => {
                  const estado = etiquetaEstado(liquidacion.estado);
                  return (
                    <TableRow key={liquidacion.id}>
                      <TableCell>
                        <span className="font-medium">
                          {liquidacion.chofer_nombre ?? "Chofer"}
                        </span>
                        <span className="block text-[13px] text-tinta-3">
                          {liquidacion.mes}
                        </span>
                      </TableCell>
                      <TableCell className="cifra text-right text-tinta-2">
                        {formatCLP(liquidacion.sueldo_base)}
                      </TableCell>
                      <TableCell className="cifra text-right text-tinta-2">
                        {formatCLP(liquidacion.comision)}
                      </TableCell>
                      <TableCell className="cifra text-right text-ok">
                        {formatCLP(liquidacion.bonos)}
                      </TableCell>
                      <TableCell className="cifra text-right text-critico">
                        {formatCLP(liquidacion.descuentos)}
                      </TableCell>
                      <TableCell className="cifra text-right text-critico">
                        {formatCLP(liquidacion.anticipos)}
                      </TableCell>
                      <TableCell className="cifra text-right text-[17px] font-semibold">
                        {formatCLP(liquidacion.total_liquido)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge tono={estado.tono}>{estado.label}</StatusBadge>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap justify-end gap-1">
                          <Button
                            size="xs"
                            variant="outline"
                            onClick={() => abrirDetalle(liquidacion)}
                          >
                            Detalle
                          </Button>
                          {puedeEscribir && liquidacion.estado === "borrador" && (
                            <Button
                              size="xs"
                              variant="secondary"
                              onClick={() => setEmitiendo(liquidacion)}
                            >
                              <FileCheck2 /> Emitir
                            </Button>
                          )}
                          {puedeEscribir && liquidacion.estado !== "anulada" && (
                            <Button
                              size="xs"
                              variant="destructive"
                              onClick={() => {
                                setMotivo("");
                                setErrorAnulacion(null);
                                setAnulando(liquidacion);
                              }}
                            >
                              Anular
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>
      </Panel>

      <Dialog
        open={!!detalle}
        onOpenChange={(abierto) => {
          if (!abierto) setDetalle(null);
        }}
      >
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{detalle?.chofer_nombre ?? "Liquidación"}</DialogTitle>
            <DialogDescription>
              Período {detalle?.mes} · Estado{" "}
              {detalle ? etiquetaEstado(detalle.estado).label : ""}
            </DialogDescription>
          </DialogHeader>

          {detalle && (
            <>
              <dl className="space-y-s2 rounded-xl bg-superficie-hundida px-s4 py-s3 text-[15.5px]">
                {[
                  ["Sueldo base", formatCLP(detalle.sueldo_base), ""],
                  ["Comisión por fletes", formatCLP(detalle.comision), ""],
                  ["Bonos", formatCLP(detalle.bonos), "text-ok"],
                  ["Descuentos", formatCLP(detalle.descuentos), "text-critico"],
                  ["Anticipos", formatCLP(detalle.anticipos), "text-critico"],
                ].map(([etiqueta, valor, clase]) => (
                  <div key={etiqueta} className="flex justify-between gap-s3">
                    <dt className="text-tinta-3">{etiqueta}</dt>
                    <dd className={`cifra ${clase}`}>{valor}</dd>
                  </div>
                ))}
                <div className="flex items-baseline justify-between border-t border-borde-fuerte pt-s2">
                  <dt className="font-medium">Total líquido</dt>
                  <dd className="cifra text-[24px] font-semibold text-marca">
                    {formatCLP(detalle.total_liquido)}
                  </dd>
                </div>
              </dl>

              {detalle.estado === "emitida" && (
                <Aviso tono="neutro" icono={Lock}>
                  Documento emitido el{" "}
                  {detalle.emitida_en ? formatFechaHora(detalle.emitida_en) : "—"}. No se
                  recalcula: los anticipos y ajustes nuevos no modifican este documento.
                </Aviso>
              )}
              {detalle.estado === "anulada" && (
                <Aviso tono="critico">
                  Anulada{detalle.motivo_anulacion ? `: ${detalle.motivo_anulacion}` : "."}
                </Aviso>
              )}
              {detalle.notas && (
                <p className="text-[14px] text-tinta-3">Notas: {detalle.notas}</p>
              )}

              <ErrorNucleo error={errorDetalle} />

              <section className="space-y-s2">
                <div className="flex items-center justify-between">
                  <h3 className="text-[16px] font-semibold">Anticipos del período</h3>
                  {puedeEditarDetalle && (
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() => {
                        setErrorAnticipo(null);
                        setFormAnticipo({
                          monto: 0,
                          fecha: hoyISO(),
                          mes_imputacion: detalle.mes,
                          notas: "",
                        });
                        setDialogoAnticipo(true);
                      }}
                    >
                      <Plus /> Anticipo
                    </Button>
                  )}
                </div>
                {cargandoDetalle ? (
                  <p className="text-[14px] text-tinta-3">Cargando anticipos…</p>
                ) : anticipos.length === 0 ? (
                  errorDetalle ? null : (
                    <p className="text-[14px] text-tinta-3">
                      Sin anticipos en este período.
                    </p>
                  )
                ) : (
                  <ul className="divide-y divide-borde rounded-xl border border-borde">
                    {anticipos.map((anticipo) => (
                      <li
                        key={anticipo.id}
                        className="flex flex-wrap items-center justify-between gap-s2 px-s3 py-s2 text-[15px]"
                      >
                        <span>
                          {formatFecha(anticipo.fecha)} ·{" "}
                          <span className="cifra font-medium">
                            {formatCLP(anticipo.monto)}
                          </span>
                        </span>
                        <StatusBadge
                          tono={anticipo.estado === "pendiente" ? "atencion" : "neutro"}
                        >
                          {anticipo.estado}
                        </StatusBadge>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="space-y-s2">
                <div className="flex items-center justify-between">
                  <h3 className="text-[16px] font-semibold">Bonos y descuentos</h3>
                  {puedeEditarDetalle && (
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() => {
                        setErrorAjuste(null);
                        setFormAjuste({ tipo: "bono", concepto: "", monto: 0 });
                        setDialogoAjuste(true);
                      }}
                    >
                      <Plus /> Ajuste
                    </Button>
                  )}
                </div>
                {cargandoDetalle ? (
                  <p className="text-[14px] text-tinta-3">Cargando ajustes…</p>
                ) : ajustes.length === 0 ? (
                  errorDetalle ? null : (
                    <p className="text-[14px] text-tinta-3">
                      Sin ajustes en este período.
                    </p>
                  )
                ) : (
                  <ul className="divide-y divide-borde rounded-xl border border-borde">
                    {ajustes.map((ajuste) => (
                      <li
                        key={ajuste.id}
                        className="flex flex-wrap items-center justify-between gap-s2 px-s3 py-s2 text-[15px]"
                      >
                        <span className="flex items-center gap-s2">
                          <StatusBadge
                            tono={ajuste.tipo === "bono" ? "ok" : "critico"}
                          >
                            {ajuste.tipo === "bono" ? "Bono" : "Descuento"}
                          </StatusBadge>
                          {ajuste.concepto}
                        </span>
                        <span className="cifra font-medium">{formatCLP(ajuste.monto)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setDetalle(null)}>
              Cerrar
            </Button>
            {puedeEscribir && detalle?.estado === "borrador" && (
              <Button
                onClick={() => {
                  setEmitiendo(detalle);
                  setDetalle(null);
                }}
              >
                <FileCheck2 /> Emitir liquidación
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoNueva} onOpenChange={setDialogoNueva}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nuevo borrador de liquidación</DialogTitle>
            <DialogDescription>
              La comisión se calcula en el servidor desde los viajes facturados del mes.
              Si ya existe un documento para el chofer y mes —aunque esté anulado— el
              servidor responde 409.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <Campo etiqueta="Chofer" htmlFor="liq-chofer" requerido>
              <SelectSimple
                id="liq-chofer"
                valor={formNueva.chofer_id}
                onCambio={(v) => setFormNueva({ ...formNueva, chofer_id: v })}
                placeholder="Seleccione chofer"
                opciones={opcionesChofer}
              />
            </Campo>
            <Campo etiqueta="Mes" htmlFor="liq-mes" requerido>
              <Input
                id="liq-mes"
                type="month"
                value={mes}
                onChange={(e) => e.target.value && setMes(e.target.value)}
              />
            </Campo>
            <Campo
              etiqueta="Sueldo base"
              htmlFor="liq-base"
              ayuda="Déjelo en cero para usar el sueldo base registrado del chofer."
            >
              <InputCLP
                key={dialogoNueva ? "liq-abierto" : "liq-cerrado"}
                id="liq-base"
                value={formNueva.sueldo_base}
                onChange={(v) => setFormNueva({ ...formNueva, sueldo_base: v })}
                placeholder="$ 0"
              />
            </Campo>
            <Campo etiqueta="Notas" htmlFor="liq-notas">
              <AreaTexto
                id="liq-notas"
                rows={3}
                value={formNueva.notas}
                onChange={(e) => setFormNueva({ ...formNueva, notas: e.target.value })}
                placeholder="Observaciones del borrador"
              />
            </Campo>
            {errorNueva && (
              <p className="text-[14px] text-critico" role="alert">
                {errorNueva}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoNueva(false)}>
              Cancelar
            </Button>
            <Button
              onClick={() => void crearBorrador()}
              disabled={procesando === "nueva"}
            >
              {procesando === "nueva" ? "Guardando…" : "Crear borrador"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!emitiendo}
        onOpenChange={(abierto) => {
          if (!abierto) setEmitiendo(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Emitir liquidación</DialogTitle>
            <DialogDescription>
              Se emitirá la liquidación de{" "}
              <strong>{emitiendo?.chofer_nombre ?? "el chofer"}</strong> por{" "}
              <strong>{emitiendo ? formatCLP(emitiendo.total_liquido) : ""}</strong>. La
              operación es idempotente: reintentar no vuelve a imputar anticipos.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmitiendo(null)}>
              Cancelar
            </Button>
            <Button onClick={() => void emitir()} disabled={procesando === "emitir"}>
              {procesando === "emitir" ? "Emitiendo…" : "Emitir"}
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
            <DialogTitle>Anular liquidación</DialogTitle>
            <DialogDescription>
              El documento se conserva con estado anulado. Repetir con el mismo motivo es
              idempotente; con otro motivo el servidor responde 409.
            </DialogDescription>
          </DialogHeader>
          <Campo etiqueta="Motivo" htmlFor="liq-motivo" requerido>
            <AreaTexto
              id="liq-motivo"
              rows={3}
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Error de cálculo, período incorrecto…"
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
              onClick={() => void anular()}
              disabled={procesando === "anular"}
            >
              {procesando === "anular" ? "Anulando…" : "Anular"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoAnticipo} onOpenChange={setDialogoAnticipo}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar anticipo</DialogTitle>
            <DialogDescription>
              Queda pendiente para el período indicado y se imputa al emitir la
              liquidación. No se edita ni se borra desde esta pantalla.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Monto" htmlFor="ant-monto" requerido>
                <InputCLP
                  key={dialogoAnticipo ? "ant-abierto" : "ant-cerrado"}
                  id="ant-monto"
                  value={formAnticipo.monto}
                  onChange={(v) => setFormAnticipo({ ...formAnticipo, monto: v })}
                  placeholder="$ 0"
                />
              </Campo>
              <Campo etiqueta="Fecha" htmlFor="ant-fecha">
                <Input
                  id="ant-fecha"
                  type="date"
                  value={formAnticipo.fecha}
                  onChange={(e) =>
                    setFormAnticipo({ ...formAnticipo, fecha: e.target.value })
                  }
                />
              </Campo>
              <Campo etiqueta="Mes de imputación" htmlFor="ant-mes" requerido>
                <Input
                  id="ant-mes"
                  type="month"
                  value={formAnticipo.mes_imputacion}
                  onChange={(e) =>
                    setFormAnticipo({
                      ...formAnticipo,
                      mes_imputacion: e.target.value,
                    })
                  }
                />
              </Campo>
            </div>
            <Campo etiqueta="Notas" htmlFor="ant-notas">
              <AreaTexto
                id="ant-notas"
                rows={2}
                value={formAnticipo.notas}
                onChange={(e) =>
                  setFormAnticipo({ ...formAnticipo, notas: e.target.value })
                }
              />
            </Campo>
            {errorAnticipo && (
              <p className="text-[14px] text-critico" role="alert">
                {errorAnticipo}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoAnticipo(false)}>
              Cancelar
            </Button>
            <Button
              onClick={() => void guardarAnticipo()}
              disabled={procesando === "anticipo"}
            >
              {procesando === "anticipo" ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogoAjuste} onOpenChange={setDialogoAjuste}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar ajuste</DialogTitle>
            <DialogDescription>
              Un bono suma y un descuento resta en el cálculo del borrador. El documento
              emitido no se recalcula.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-s4">
            <div className="grid gap-s3 sm:grid-cols-2">
              <Campo etiqueta="Tipo" htmlFor="aj-tipo">
                <SelectSimple
                  id="aj-tipo"
                  valor={formAjuste.tipo}
                  onCambio={(v) =>
                    setFormAjuste({
                      ...formAjuste,
                      tipo: v === "descuento" ? "descuento" : "bono",
                    })
                  }
                  opciones={[
                    { valor: "bono", etiqueta: "Bono (suma)" },
                    { valor: "descuento", etiqueta: "Descuento (resta)" },
                  ]}
                />
              </Campo>
              <Campo etiqueta="Monto" htmlFor="aj-monto" requerido>
                <InputCLP
                  key={dialogoAjuste ? "aj-abierto" : "aj-cerrado"}
                  id="aj-monto"
                  value={formAjuste.monto}
                  onChange={(v) => setFormAjuste({ ...formAjuste, monto: v })}
                  placeholder="$ 0"
                />
              </Campo>
            </div>
            <Campo etiqueta="Concepto" htmlFor="aj-concepto" requerido>
              <Input
                id="aj-concepto"
                value={formAjuste.concepto}
                onChange={(e) =>
                  setFormAjuste({ ...formAjuste, concepto: e.target.value })
                }
                placeholder="Bono de puntualidad"
              />
            </Campo>
            {errorAjuste && (
              <p className="text-[14px] text-critico" role="alert">
                {errorAjuste}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoAjuste(false)}>
              Cancelar
            </Button>
            <Button
              onClick={() => void guardarAjuste()}
              disabled={procesando === "ajuste"}
            >
              {procesando === "ajuste" ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
        </>
      )}
    </div>
  );
}
