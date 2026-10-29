"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Building2,
  FileSpreadsheet,
  Plus,
  RefreshCw,
  Search,
  ShoppingCart,
} from "lucide-react";
import { toast } from "sonner";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import { formatCLP, formatFecha } from "@/lib/format";
import type {
  CentroCostoNucleo,
  EmpresaNucleo,
  OrdenCompraNucleo,
  OrdenCompraResumenNucleo,
  TarifaNucleo,
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
  type Tono,
} from "@/components/sistema";
import { CentroCostoDialog } from "@/components/comercial/centro-costo-dialog";
import { TarifaDialog } from "@/components/comercial/tarifa-dialog";
import { OrdenCompraDialog } from "@/components/comercial/orden-compra-dialog";
import { OrdenCompraDetalleDialog } from "@/components/comercial/oc-detalle-dialog";

type Tab = "tarifas" | "ordenes" | "centros";

function tonoAlerta(alerta: string): Tono {
  if (alerta === "sobregiro" || alerta === "100") return "critico";
  if (alerta === "90" || alerta === "80") return "atencion";
  return "ok";
}

function etiquetaAlerta(alerta: string): string {
  if (alerta === "normal") return "Normal";
  if (alerta === "80") return "80 %";
  if (alerta === "90") return "90 %";
  if (alerta === "100") return "100 %";
  return "Sobregiro";
}

function etiquetaEstadoOC(oc: OrdenCompraResumenNucleo): string {
  if (oc.vencida && oc.estado !== "anulada") return "Vencida";
  return oc.estado.replaceAll("_", " ");
}

export default function ComercialPage() {
  const [empresaId, setEmpresaId] = useState("");
  const [empresa, setEmpresa] = useState<EmpresaNucleo | null>(null);
  const [tab, setTab] = useState<Tab>("tarifas");
  const [busqueda, setBusqueda] = useState("");

  const [tarifas, setTarifas] = useState<TarifaNucleo[]>([]);
  const [ocs, setOcs] = useState<OrdenCompraResumenNucleo[]>([]);
  const [centros, setCentros] = useState<CentroCostoNucleo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [dialogoTarifa, setDialogoTarifa] = useState<{
    tarifa: TarifaNucleo | null;
  } | null>(null);
  const [dialogoCentro, setDialogoCentro] = useState<{
    centro: CentroCostoNucleo | null;
  } | null>(null);
  const [dialogoOc, setDialogoOc] = useState<{
    oc: OrdenCompraNucleo | null;
  } | null>(null);
  const [ocDetalleId, setOcDetalleId] = useState<string | null>(null);

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
        const [t, o, c] = await Promise.all([
          nucleo.get<TarifaNucleo[]>("/nucleo/tarifas", empresaId),
          nucleo.get<OrdenCompraResumenNucleo[]>("/nucleo/ordenes-compra", empresaId),
          nucleo.get<CentroCostoNucleo[]>("/nucleo/centros-costo", empresaId),
        ]);
        setTarifas(t);
        setOcs(o);
        setCentros(c);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar comercial");
      } finally {
        setCargando(false);
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

  const filtro = busqueda.trim().toLowerCase();
  const tarifasFiltradas = useMemo(
    () =>
      tarifas.filter((t) =>
        [t.codigo, t.nombre, t.cliente_nombre, t.origen, t.destino, t.modalidad]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(filtro),
      ),
    [tarifas, filtro],
  );
  const ocsFiltradas = useMemo(
    () =>
      ocs.filter((o) =>
        [o.numero_oc, o.cliente_nombre, o.referencia_interna, o.centro_costo_nombre]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(filtro),
      ),
    [ocs, filtro],
  );
  const centrosFiltrados = useMemo(
    () =>
      centros.filter((c) =>
        [c.codigo, c.nombre, c.descripcion]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(filtro),
      ),
    [centros, filtro],
  );

  const tarifasActivas = tarifas.filter((t) => t.activo).length;
  const ocsAlerta = ocs.filter((o) => o.alerta !== "normal").length;
  const saldoTotal = ocs.reduce((acc, o) => acc + Number(o.saldo_disponible || 0), 0);
  const puedeSobregiro = empresa?.rol === "admin" || empresa?.rol === "gerente";

  async function abrirEdicionOc(id: string) {
    try {
      const detalle = await nucleo.get<OrdenCompraNucleo>(
        `/nucleo/ordenes-compra/${id}`,
        empresaId,
      );
      setDialogoOc({ oc: detalle });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo abrir la OC");
    }
  }

  async function desactivarTarifa(tarifa: TarifaNucleo) {
    if (!window.confirm(`¿Desactivar la tarifa ${tarifa.codigo}?`)) return;
    try {
      await nucleo.del(`/nucleo/tarifas/${tarifa.id}`, empresaId);
      toast.success("Tarifa desactivada");
      await cargar(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo desactivar");
    }
  }

  async function anularOc(oc: OrdenCompraResumenNucleo) {
    if (!window.confirm(`¿Anular la OC ${oc.numero_oc}? No se borra: queda auditada.`)) {
      return;
    }
    try {
      await nucleo.del(`/nucleo/ordenes-compra/${oc.id}`, empresaId);
      toast.success("OC anulada");
      await cargar(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo anular la OC");
    }
  }

  async function desactivarCentro(centro: CentroCostoNucleo) {
    if (!window.confirm(`¿Desactivar el centro ${centro.codigo}?`)) return;
    try {
      await nucleo.del(`/nucleo/centros-costo/${centro.id}`, empresaId);
      toast.success("Centro de costo desactivado");
      await cargar(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo desactivar");
    }
  }

  function nuevo() {
    if (tab === "tarifas") setDialogoTarifa({ tarifa: null });
    else if (tab === "ordenes") setDialogoOc({ oc: null });
    else setDialogoCentro({ centro: null });
  }

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Comercial"
        titulo="Tarifas, OC y centros de costo"
        descripcion="Administre el tarifario y las órdenes de compra. El consumo se calcula desde los viajes y alerta al 80 %, 90 % y 100 %."
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
            <Button onClick={nuevo} disabled={!empresaId}>
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

      <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          etiqueta="Tarifas activas"
          valor={tarifasActivas}
          detalle={`${tarifas.length} en el tarifario`}
          tono="ok"
          icono={FileSpreadsheet}
          destacado
        />
        <StatTile
          etiqueta="OC con alerta"
          valor={ocsAlerta}
          detalle="80 %, 90 %, 100 % o sobregiro"
          tono={ocsAlerta > 0 ? "atencion" : "ok"}
          icono={ShoppingCart}
        />
        <StatTile
          etiqueta="Saldo disponible OC"
          valor={formatCLP(saldoTotal)}
          detalle={`${ocs.length} orden(es) de compra`}
          tono={saldoTotal >= 0 ? "ok" : "critico"}
          icono={Building2}
        />
        <StatTile
          etiqueta="Centros de costo"
          valor={centros.filter((c) => c.activo).length}
          detalle={`${centros.length} registrados`}
          tono="neutro"
          icono={Building2}
        />
      </div>

      <div className="flex flex-wrap items-end justify-between gap-s3">
        <Segmentado
          etiqueta="Sección comercial"
          valor={tab}
          onCambio={(v) => {
            setTab(v);
            setBusqueda("");
          }}
          opciones={[
            { valor: "tarifas", etiqueta: "Tarifas", contador: tarifas.length },
            { valor: "ordenes", etiqueta: "Órdenes de compra", contador: ocs.length },
            { valor: "centros", etiqueta: "Centros de costo", contador: centros.length },
          ]}
        />
        <label className="relative w-full sm:w-[340px]">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-tinta-3" />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar…"
            className="pl-9"
          />
        </label>
      </div>

      {tab === "tarifas" && (
        <Panel
          titulo={`Tarifas · ${tarifasFiltradas.length}`}
          descripcion={empresa?.razon_social}
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Código</TableHead>
                  <TableHead>Cliente / ruta</TableHead>
                  <TableHead>Modalidad</TableHead>
                  <TableHead>Precio</TableHead>
                  <TableHead>Vigencia</TableHead>
                  <TableHead>Viajes</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cargando ? (
                  <TableRow>
                    <TableCell colSpan={8} className="py-s6 text-center text-tinta-3">
                      Cargando tarifas…
                    </TableCell>
                  </TableRow>
                ) : tarifasFiltradas.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="p-0">
                      <EstadoVacio
                        icono={FileSpreadsheet}
                        titulo="Sin tarifas"
                        descripcion="Cree la primera tarifa para poder cotizar viajes."
                        accion={
                          <Button onClick={() => setDialogoTarifa({ tarifa: null })}>
                            <Plus /> Nueva tarifa
                          </Button>
                        }
                      />
                    </TableCell>
                  </TableRow>
                ) : (
                  tarifasFiltradas.map((tarifa) => (
                    <TableRow key={tarifa.id}>
                      <TableCell className="font-mono text-[13px] font-semibold">
                        {tarifa.codigo}
                      </TableCell>
                      <TableCell>
                        <p className="font-medium">{tarifa.cliente_nombre}</p>
                        <p className="text-[13px] text-tinta-3">
                          {tarifa.origen ?? "—"} → {tarifa.destino ?? "—"}
                        </p>
                      </TableCell>
                      <TableCell className="capitalize">
                        {tarifa.modalidad.replaceAll("_", " ")}
                      </TableCell>
                      <TableCell>{formatCLP(tarifa.precio_unitario)}</TableCell>
                      <TableCell className="text-[14px]">
                        {formatFecha(tarifa.vigencia_desde)}
                        <br />
                        <span className="text-tinta-3">
                          {tarifa.vigencia_hasta ? formatFecha(tarifa.vigencia_hasta) : "sin fin"}
                        </span>
                      </TableCell>
                      <TableCell>{tarifa.viajes_activos}</TableCell>
                      <TableCell>
                        <StatusBadge
                          tono={
                            !tarifa.activo
                              ? "neutro"
                              : tarifa.vencida
                                ? "critico"
                                : "ok"
                          }
                        >
                          {!tarifa.activo ? "Inactiva" : tarifa.vencida ? "Vencida" : "Activa"}
                        </StatusBadge>
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-s2">
                          <Button
                            size="xs"
                            variant="outline"
                            onClick={() => setDialogoTarifa({ tarifa })}
                          >
                            Editar
                          </Button>
                          {tarifa.activo && (
                            <Button
                              size="xs"
                              variant="destructive"
                              onClick={() => void desactivarTarifa(tarifa)}
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
      )}

      {tab === "ordenes" && (
        <Panel
          titulo={`Órdenes de compra · ${ocsFiltradas.length}`}
          descripcion="El saldo y las alertas se calculan en backend desde los viajes."
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>OC</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Vigencia</TableHead>
                  <TableHead className="text-right">Autorizado</TableHead>
                  <TableHead className="min-w-[160px]">Consumo</TableHead>
                  <TableHead className="text-right">Saldo</TableHead>
                  <TableHead>Alerta</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cargando ? (
                  <TableRow>
                    <TableCell colSpan={9} className="py-s6 text-center text-tinta-3">
                      Cargando órdenes de compra…
                    </TableCell>
                  </TableRow>
                ) : ocsFiltradas.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={9} className="p-0">
                      <EstadoVacio
                        icono={ShoppingCart}
                        titulo="Sin órdenes de compra"
                        descripcion="Cree una OC para controlar el consumo por viaje."
                        accion={
                          <Button onClick={() => setDialogoOc({ oc: null })}>
                            <Plus /> Nueva OC
                          </Button>
                        }
                      />
                    </TableCell>
                  </TableRow>
                ) : (
                  ocsFiltradas.map((oc) => {
                    const pct = Math.min(100, Number(oc.porcentaje_consumo || 0));
                    return (
                      <TableRow key={oc.id}>
                        <TableCell>
                          <p className="font-mono text-[13px] font-semibold">{oc.numero_oc}</p>
                          <p className="text-[12px] text-tinta-3">
                            {oc.centro_costo_nombre ?? "Sin centro"}
                          </p>
                        </TableCell>
                        <TableCell className="font-medium">{oc.cliente_nombre}</TableCell>
                        <TableCell className="text-[14px]">
                          {formatFecha(oc.vigencia_desde)}
                          <br />
                          <span className="text-tinta-3">{formatFecha(oc.vigencia_hasta)}</span>
                        </TableCell>
                        <TableCell className="text-right">{formatCLP(oc.monto_autorizado)}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-s2">
                            <div className="h-2 w-24 overflow-hidden rounded-full bg-superficie-hundida">
                              <div
                                className={`h-full rounded-full ${
                                  oc.alerta === "normal"
                                    ? "bg-ok"
                                    : oc.alerta === "80" || oc.alerta === "90"
                                      ? "bg-atencion"
                                      : "bg-critico"
                                }`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="text-[13px] tabular-nums">
                              {Number(oc.porcentaje_consumo).toFixed(0)}%
                            </span>
                          </div>
                          <p className="text-[12px] text-tinta-3">
                            {formatCLP(oc.monto_consumido)}
                          </p>
                        </TableCell>
                        <TableCell className="text-right">{formatCLP(oc.saldo_disponible)}</TableCell>
                        <TableCell>
                          <StatusBadge tono={tonoAlerta(oc.alerta)}>
                            {etiquetaAlerta(oc.alerta)}
                          </StatusBadge>
                        </TableCell>
                        <TableCell>
                          <StatusBadge tono={oc.estado === "anulada" ? "neutro" : oc.vencida ? "critico" : "info"}>
                            {etiquetaEstadoOC(oc)}
                          </StatusBadge>
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-s2">
                            <Button size="xs" onClick={() => setOcDetalleId(oc.id)}>
                              Ver
                            </Button>
                            <Button
                              size="xs"
                              variant="outline"
                              onClick={() => void abrirEdicionOc(oc.id)}
                              disabled={oc.estado === "anulada"}
                            >
                              Editar
                            </Button>
                            {oc.estado !== "anulada" && (
                              <Button
                                size="xs"
                                variant="destructive"
                                onClick={() => void anularOc(oc)}
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
      )}

      {tab === "centros" && (
        <Panel titulo={`Centros de costo · ${centrosFiltrados.length}`}>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Código</TableHead>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Descripción</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cargando ? (
                  <TableRow>
                    <TableCell colSpan={5} className="py-s6 text-center text-tinta-3">
                      Cargando centros de costo…
                    </TableCell>
                  </TableRow>
                ) : centrosFiltrados.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="p-0">
                      <EstadoVacio
                        icono={Building2}
                        titulo="Sin centros de costo"
                        descripcion="Cree centros para imputar OC y líneas."
                        accion={
                          <Button onClick={() => setDialogoCentro({ centro: null })}>
                            <Plus /> Nuevo centro
                          </Button>
                        }
                      />
                    </TableCell>
                  </TableRow>
                ) : (
                  centrosFiltrados.map((centro) => (
                    <TableRow key={centro.id}>
                      <TableCell className="font-mono text-[13px] font-semibold">
                        {centro.codigo}
                      </TableCell>
                      <TableCell className="font-medium">{centro.nombre}</TableCell>
                      <TableCell className="text-tinta-3">
                        {centro.descripcion ?? "—"}
                      </TableCell>
                      <TableCell>
                        <StatusBadge tono={centro.activo ? "ok" : "neutro"}>
                          {centro.activo ? "Activo" : "Inactivo"}
                        </StatusBadge>
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-s2">
                          <Button
                            size="xs"
                            variant="outline"
                            onClick={() => setDialogoCentro({ centro })}
                          >
                            Editar
                          </Button>
                          {centro.activo && (
                            <Button
                              size="xs"
                              variant="destructive"
                              onClick={() => void desactivarCentro(centro)}
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
      )}

      {dialogoTarifa && (
        <TarifaDialog
          empresaId={empresaId}
          moneda={empresa?.moneda ?? "CLP"}
          tarifa={dialogoTarifa.tarifa}
          onClose={() => setDialogoTarifa(null)}
          onGuardado={() => {
            setDialogoTarifa(null);
            void cargar(true);
          }}
        />
      )}

      {dialogoCentro && (
        <CentroCostoDialog
          empresaId={empresaId}
          centro={dialogoCentro.centro}
          onClose={() => setDialogoCentro(null)}
          onGuardado={() => {
            setDialogoCentro(null);
            void cargar(true);
          }}
        />
      )}

      {dialogoOc && (
        <OrdenCompraDialog
          empresaId={empresaId}
          moneda={empresa?.moneda ?? "CLP"}
          oc={dialogoOc.oc}
          puedeSobregiro={puedeSobregiro}
          onClose={() => setDialogoOc(null)}
          onGuardado={() => {
            setDialogoOc(null);
            void cargar(true);
          }}
        />
      )}

      {ocDetalleId && (
        <OrdenCompraDetalleDialog
          empresaId={empresaId}
          ocId={ocDetalleId}
          rol={empresa?.rol ?? ""}
          onClose={() => setOcDetalleId(null)}
          onEditar={(oc) => {
            setOcDetalleId(null);
            setDialogoOc({ oc });
          }}
          onCambio={() => void cargar(true)}
        />
      )}
    </div>
  );
}
