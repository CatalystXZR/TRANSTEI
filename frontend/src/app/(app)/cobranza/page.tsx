"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  FileText,
  Plus,
  RefreshCw,
  Search,
} from "lucide-react";
import { getEmpresas, nucleo } from "@/lib/nucleo";
import { formatCLP, formatFecha } from "@/lib/format";
import type {
  AgingNucleo,
  EmpresaNucleo,
  FacturaNucleo,
  FacturaResumenNucleo,
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
  StatTile,
  StatusBadge,
  type Tono,
} from "@/components/sistema";
import { SelectSimple } from "@/components/formulario";
import { NuevaFacturaDialog } from "@/components/cobranza/nueva-factura-dialog";
import { FacturaDetalleDialog } from "@/components/cobranza/factura-detalle-dialog";

const ESTADOS = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "emitida", etiqueta: "Emitida" },
  { valor: "parcial", etiqueta: "Parcial" },
  { valor: "pagada", etiqueta: "Pagada" },
  { valor: "vencida", etiqueta: "Vencida" },
  { valor: "anulada", etiqueta: "Anulada" },
];

function tonoEstado(estado: string): Tono {
  if (estado === "pagada") return "ok";
  if (estado === "parcial") return "atencion";
  if (estado === "vencida" || estado === "anulada") return "critico";
  return "info";
}

function etiquetaAging(aging: string): string {
  if (aging === "por_vencer") return "Por vencer";
  if (aging === "0_30") return "0–30 días";
  if (aging === "31_60") return "31–60 días";
  if (aging === "61_90") return "61–90 días";
  return "> 90 días";
}

export default function CobranzaPage() {
  const [empresaId, setEmpresaId] = useState("");
  const [empresa, setEmpresa] = useState<EmpresaNucleo | null>(null);
  const [facturas, setFacturas] = useState<FacturaResumenNucleo[]>([]);
  const [aging, setAging] = useState<AgingNucleo | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [estado, setEstado] = useState("");
  const [soloVencidas, setSoloVencidas] = useState(false);
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nuevaAbierta, setNuevaAbierta] = useState(false);
  const [detalleId, setDetalleId] = useState<string | null>(null);

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
      if (!empresaId) return;
      if (silencioso) setActualizando(true);
      else setCargando(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          ...(estado ? { estado } : {}),
          ...(soloVencidas ? { solo_vencidas: "true" } : {}),
          ...(busqueda.trim() ? { q: busqueda.trim() } : {}),
        });
        const [lista, ag] = await Promise.all([
          nucleo.get<FacturaResumenNucleo[]>(
            `/nucleo/cobranza/facturas?${params.toString()}`,
            empresaId,
          ),
          nucleo.get<AgingNucleo>("/nucleo/cobranza/aging", empresaId),
        ]);
        setFacturas(lista);
        setAging(ag);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar cobranza");
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId, estado, soloVencidas, busqueda],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 250);
    return () => clearTimeout(t);
  }, [cargar]);

  const puedeEscribir = ["admin", "gerente", "contador", "tesoreria"].includes(
    empresa?.rol ?? "",
  );
  const totalFacturado = useMemo(
    () => facturas.reduce((acc, f) => acc + Number(f.total), 0),
    [facturas],
  );
  const abiertas = facturas.filter((f) => Number(f.saldo) > 0 && f.estado !== "anulada").length;

  return (
    <div className="space-y-s5">
      <PageHeader
        rotulo="Finanzas"
        titulo="Facturación y cobranza"
        descripcion="Facturas simuladas del piloto: OC ↔ viaje ↔ factura, POD obligatorio, pagos parciales, notas de crédito, promesas y aging."
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
              onClick={() => setNuevaAbierta(true)}
              disabled={!empresaId || !puedeEscribir}
            >
              <Plus /> Nueva factura
            </Button>
          </>
        }
      />

      {error && <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>}

      <div className="grid gap-s3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          etiqueta="Cuentas por cobrar"
          valor={formatCLP(aging?.total_cxc ?? 0)}
          detalle={`${aging?.facturas_abiertas ?? 0} factura(s) abiertas`}
          tono="info"
          icono={Banknote}
          destacado
        />
        <StatTile
          etiqueta="CxC vencida"
          valor={formatCLP(aging?.total_vencido ?? 0)}
          detalle="Vencimiento anterior a hoy"
          tono={Number(aging?.total_vencido ?? 0) > 0 ? "critico" : "ok"}
          icono={AlertTriangle}
        />
        <StatTile
          etiqueta="Facturado visible"
          valor={formatCLP(totalFacturado)}
          detalle={`${facturas.length} factura(s) en la lista`}
          tono="ok"
          icono={FileText}
        />
        <StatTile
          etiqueta="Abiertas"
          valor={abiertas}
          detalle="Con saldo pendiente"
          tono={abiertas ? "atencion" : "ok"}
          icono={ArrowRight}
        />
      </div>

      <Panel titulo="Aging de cartera" descripcion={aging?.mensaje}>
        <div className="grid gap-s3 p-s4 sm:grid-cols-5">
          {(aging?.buckets ?? []).map((bucket) => (
            <div key={bucket.etiqueta} className="rounded-xl border border-borde bg-superficie-hundida/40 p-s3">
              <p className="text-[13px] font-medium text-tinta-3">{bucket.etiqueta}</p>
              <p className="cifra mt-s1 text-[20px] font-semibold">{formatCLP(bucket.monto)}</p>
              <p className="text-[12px] text-tinta-3">{bucket.facturas} factura(s)</p>
            </div>
          ))}
        </div>
      </Panel>

      <div className="flex flex-wrap items-end justify-between gap-s3">
        <div className="flex flex-wrap items-end gap-s3">
          <div className="w-[220px]">
            <SelectSimple
              valor={estado}
              onCambio={setEstado}
              opciones={ESTADOS}
              placeholder="Estado"
              ariaLabel="Filtrar por estado"
            />
          </div>
          <label className="flex items-center gap-s2 pb-2 text-[14px]">
            <input
              type="checkbox"
              className="size-4 accent-marca"
              checked={soloVencidas}
              onChange={(e) => setSoloVencidas(e.target.checked)}
            />
            Solo vencidas
          </label>
        </div>
        <label className="relative w-full sm:w-[340px]">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-tinta-3" />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar por número de factura…"
            className="pl-9"
          />
        </label>
      </div>

      <Panel titulo={`Facturas · ${facturas.length}`}>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Factura</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Vencimiento</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="text-right">Pagado</TableHead>
                <TableHead className="text-right">Saldo</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Aging</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <TableRow>
                  <TableCell colSpan={9} className="py-s6 text-center text-tinta-3">
                    Cargando facturas…
                  </TableCell>
                </TableRow>
              ) : facturas.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="p-0">
                    <EstadoVacio
                      icono={FileText}
                      titulo="Sin facturas"
                      descripcion="Emita una factura desde viajes cerrados con POD."
                      accion={
                        puedeEscribir ? (
                          <Button onClick={() => setNuevaAbierta(true)}>
                            <Plus /> Nueva factura
                          </Button>
                        ) : undefined
                      }
                    />
                  </TableCell>
                </TableRow>
              ) : (
                facturas.map((factura) => (
                  <TableRow key={factura.id}>
                    <TableCell>
                      <p className="font-mono text-[13px] font-semibold">{factura.numero_factura}</p>
                      <p className="text-[12px] text-tinta-3">{factura.oc_numero ?? "Sin OC"}</p>
                    </TableCell>
                    <TableCell className="font-medium">{factura.cliente_nombre}</TableCell>
                    <TableCell>
                      {formatFecha(factura.fecha_vencimiento)}
                      {factura.dias_atraso > 0 && (
                        <p className="text-[12px] text-critico">{factura.dias_atraso} día(s) atraso</p>
                      )}
                    </TableCell>
                    <TableCell className="text-right">{formatCLP(factura.total)}</TableCell>
                    <TableCell className="text-right">{formatCLP(factura.pagado)}</TableCell>
                    <TableCell className="text-right font-medium">{formatCLP(factura.saldo)}</TableCell>
                    <TableCell>
                      <StatusBadge tono={tonoEstado(factura.estado)}>{factura.estado}</StatusBadge>
                    </TableCell>
                    <TableCell className="text-[13px]">{etiquetaAging(factura.aging)}</TableCell>
                    <TableCell className="text-right">
                      <Button size="xs" variant="outline" onClick={() => setDetalleId(factura.id)}>
                        Ver / cobrar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </Panel>

      {nuevaAbierta && (
        <NuevaFacturaDialog
          empresaId={empresaId}
          onClose={() => setNuevaAbierta(false)}
          onCreada={(factura: FacturaNucleo) => {
            setNuevaAbierta(false);
            setDetalleId(factura.id);
            void cargar(true);
          }}
        />
      )}

      {detalleId && (
        <FacturaDetalleDialog
          empresaId={empresaId}
          facturaId={detalleId}
          puedeEscribir={puedeEscribir}
          onClose={() => setDetalleId(null)}
          onCambio={() => void cargar(true)}
        />
      )}
    </div>
  );
}
