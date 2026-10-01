import { cn } from "cn";
import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";

export type Tono = "ok" | "atencion" | "critico" | "info" | "neutro";

const PUNTO: Record<Tono, string> = {
  ok: "bg-ok",
  atencion: "bg-atencion",
  critico: "bg-critico",
  info: "bg-marca",
  neutro: "bg-neutro/60",
};

const BARRA: Record<Tono, string> = {
  ok: "bg-ok",
  atencion: "bg-senal",
  critico: "bg-critico",
  info: "bg-marca",
  neutro: "bg-borde-fuerte",
};

/* ------------------------------------------------------------
   Encabezado de página
   ------------------------------------------------------------ */
export function PageHeader({
  titulo,
  descripcion,
  rotulo,
  acciones,
}: {
  titulo: React.ReactNode;
  descripcion?: React.ReactNode;
  rotulo?: string;
  acciones?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-s5 gap-y-s4 pb-s2">
      <div className="min-w-0 space-y-s2">
        {rotulo && <p className="rotulo">{rotulo}</p>}
        <h1 className="text-[30px] leading-[1.1] font-semibold sm:text-[36px]">{titulo}</h1>
        {descripcion && (
          <p className="max-w-2xl text-[16px] leading-relaxed text-tinta-3">{descripcion}</p>
        )}
      </div>
      {acciones && <div className="flex flex-wrap items-center gap-s2">{acciones}</div>}
    </header>
  );
}

/* ------------------------------------------------------------
   Insignia de estado con punto indicador
   ------------------------------------------------------------ */
export function StatusBadge({
  tono,
  children,
  className,
}: {
  tono: Tono;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Badge variant={tono} className={className}>
      <span className={cn("size-1.5 rounded-full", PUNTO[tono])} aria-hidden="true" />
      {children}
    </Badge>
  );
}

/* ------------------------------------------------------------
   Tarjeta de indicador
   ------------------------------------------------------------ */
export function StatTile({
  etiqueta,
  valor,
  detalle,
  tono = "neutro",
  icono: Icono,
  destacado = false,
}: {
  etiqueta: string;
  valor: React.ReactNode;
  detalle?: React.ReactNode;
  tono?: Tono;
  icono?: LucideIcon;
  destacado?: boolean;
}) {
  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-xl border p-s4 transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:shadow-elev-2",
        destacado
          ? "border-marca bg-marca text-white shadow-elev-2"
          : "border-borde bg-superficie shadow-elev-1 hover:border-borde-fuerte",
      )}
    >
      <div className="flex items-start justify-between gap-s3">
        <p className={cn("flex items-center gap-2 text-[15px] font-medium", destacado ? "text-white/75" : "text-tinta-3")}>
          {tono !== "neutro" && !destacado && <span className={cn("size-2 rounded-full", PUNTO[tono])} aria-hidden="true" />}
          {etiqueta}
        </p>
        {Icono && (
          <span
            className={cn(
              "grid size-9 place-items-center rounded-lg transition-colors",
              destacado ? "bg-white/10 text-senal" : "bg-superficie-hundida text-tinta-3 group-hover:bg-marca-tenue group-hover:text-marca",
            )}
          >
            <Icono className="size-[18px]" />
          </span>
        )}
      </div>
      <p className={cn("cifra mt-s3 text-[34px] leading-none font-semibold", destacado ? "text-white" : "text-tinta")}>
        {valor}
      </p>
      {detalle && (
        <p className={cn("mt-s2 text-[14px]", destacado ? "text-white/70" : "text-tinta-3")}>{detalle}</p>
      )}
      <span
        className={cn(
          "absolute inset-x-0 bottom-0 h-[3px] origin-left scale-x-0 transition-transform duration-300 group-hover:scale-x-100",
          destacado ? "bg-senal" : BARRA[tono],
        )}
        aria-hidden="true"
      />
    </div>
  );
}

export function StatTileSkeleton() {
  return (
    <div className="rounded-xl border border-borde bg-superficie p-s4 shadow-elev-1">
      <Skeleton className="h-4 w-28" />
      <Skeleton className="mt-s4 h-8 w-36" />
      <Skeleton className="mt-s3 h-3.5 w-24" />
    </div>
  );
}

/* ------------------------------------------------------------
   Patente de vehículo
   ------------------------------------------------------------ */
export function Patente({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-tinta/15 bg-superficie px-2 py-0.5 font-mono text-[13.5px] font-semibold tracking-[0.06em] text-tinta shadow-[inset_0_-2px_0_rgb(23_21_31/0.06)]",
        className,
      )}
    >
      {children}
    </span>
  );
}

/* ------------------------------------------------------------
   Contenedor de tablas / listas
   ------------------------------------------------------------ */
export function Panel({
  children,
  className,
  titulo,
  acciones,
  descripcion,
}: {
  children: React.ReactNode;
  className?: string;
  titulo?: React.ReactNode;
  acciones?: React.ReactNode;
  descripcion?: React.ReactNode;
}) {
  return (
    <section className={cn("overflow-hidden rounded-xl border border-borde bg-superficie shadow-elev-1", className)}>
      {(titulo || acciones) && (
        <div className="flex flex-wrap items-center justify-between gap-s3 border-b border-borde px-s4 py-s3">
          <div>
            {titulo && <h2 className="text-[18px] font-semibold">{titulo}</h2>}
            {descripcion && <p className="text-[14px] text-tinta-3">{descripcion}</p>}
          </div>
          {acciones && <div className="flex items-center gap-s2">{acciones}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/* ------------------------------------------------------------
   Estado vacío
   ------------------------------------------------------------ */
export function EstadoVacio({
  icono: Icono,
  titulo,
  descripcion,
  accion,
}: {
  icono?: LucideIcon;
  titulo: string;
  descripcion?: string;
  accion?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-s2 px-s4 py-s6 text-center">
      {Icono && (
        <span className="mb-s2 grid size-12 place-items-center rounded-xl border border-borde bg-superficie-hundida text-tinta-3">
          <Icono className="size-[22px]" />
        </span>
      )}
      <p className="text-[17px] font-semibold text-tinta">{titulo}</p>
      {descripcion && <p className="max-w-sm text-[15px] text-tinta-3">{descripcion}</p>}
      {accion && <div className="mt-s3">{accion}</div>}
    </div>
  );
}

export function FilaVacia({
  columnas,
  ...props
}: { columnas: number } & React.ComponentProps<typeof EstadoVacio>) {
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={columnas} className="p-0">
        <EstadoVacio {...props} />
      </TableCell>
    </TableRow>
  );
}

/* ------------------------------------------------------------
   Filas de carga para tablas
   ------------------------------------------------------------ */
export function FilasCargando({ columnas, filas = 4 }: { columnas: number; filas?: number }) {
  return (
    <>
      {Array.from({ length: filas }).map((_, i) => (
        <TableRow key={i} className="hover:bg-transparent">
          {Array.from({ length: columnas }).map((__, j) => (
            <TableCell key={j}>
              <Skeleton className={cn("h-4", j === 0 ? "w-40" : "w-24")} />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

/* ------------------------------------------------------------
   Control segmentado (pestañas)
   ------------------------------------------------------------ */
export function Segmentado<T extends string>({
  opciones,
  valor,
  onCambio,
  etiqueta,
}: {
  opciones: { valor: T; etiqueta: React.ReactNode; contador?: number }[];
  valor: T;
  onCambio: (v: T) => void;
  etiqueta: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={etiqueta}
      className="inline-flex max-w-full gap-1 overflow-x-auto rounded-xl border border-borde bg-superficie-hundida p-1"
    >
      {opciones.map((o) => {
        const activo = o.valor === valor;
        return (
          <button
            key={o.valor}
            type="button"
            role="tab"
            aria-selected={activo}
            onClick={() => onCambio(o.valor)}
            className={cn(
              "inline-flex cursor-pointer items-center gap-2 rounded-lg px-s3 py-2 text-[15px] font-medium whitespace-nowrap transition-[background-color,color,box-shadow] duration-150",
              activo
                ? "bg-superficie text-marca shadow-elev-1"
                : "text-tinta-3 hover:bg-superficie/70 hover:text-tinta",
            )}
          >
            {o.etiqueta}
            {o.contador !== undefined && (
              <span
                className={cn(
                  "min-w-6 rounded-md px-1.5 font-mono text-[12px] tabular-nums",
                  activo ? "bg-marca-tenue text-marca" : "bg-borde/70 text-tinta-3",
                )}
              >
                {o.contador}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------
   Fecha de vencimiento con estado (vencido / próximo / vigente)
   ------------------------------------------------------------ */
export function diasHasta(fechaISO: string): number {
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const f = new Date(`${fechaISO}T00:00:00`);
  return Math.round((f.getTime() - hoy.getTime()) / 86400000);
}

export function Vencimiento({ fecha, umbral = 30 }: { fecha: string | null; umbral?: number }) {
  if (!fecha) return <span className="text-[14px] text-tinta-3">—</span>;
  const dias = diasHasta(fecha);
  const texto = new Intl.DateTimeFormat("es-CL", { day: "2-digit", month: "2-digit", year: "numeric" }).format(
    new Date(`${fecha}T00:00:00`),
  );
  const tono: Tono = dias < 0 ? "critico" : dias <= umbral ? "atencion" : "ok";
  const detalle = dias < 0 ? `vencido hace ${-dias} d` : dias === 0 ? "vence hoy" : dias <= umbral ? `en ${dias} d` : null;
  return (
    <span className="inline-flex items-center gap-2">
      <span className={cn("size-2 shrink-0 rounded-full", PUNTO[tono])} aria-hidden="true" />
      <span className="tabular-nums text-tinta-2">{texto}</span>
      {detalle && (
        <span className={cn("text-[13px] font-medium", tono === "critico" ? "text-critico" : "text-atencion")}>
          {detalle}
        </span>
      )}
    </span>
  );
}

/* ------------------------------------------------------------
   Aviso informativo en línea
   ------------------------------------------------------------ */
export function Aviso({
  tono = "info",
  children,
  icono: Icono,
}: {
  tono?: Tono;
  children: React.ReactNode;
  icono?: LucideIcon;
}) {
  const estilos: Record<Tono, string> = {
    ok: "border-ok/20 bg-ok-tenue text-ok",
    atencion: "border-atencion/25 bg-atencion-tenue text-atencion",
    critico: "border-critico/20 bg-critico-tenue text-critico",
    info: "border-marca/15 bg-marca-tenue text-marca",
    neutro: "border-borde bg-superficie-hundida text-tinta-2",
  };
  return (
    <div className={cn("flex items-start gap-s3 rounded-xl border px-s4 py-s3 text-[15px] leading-relaxed", estilos[tono])}>
      {Icono && <Icono className="mt-0.5 size-[18px] shrink-0" />}
      <div className="min-w-0">{children}</div>
    </div>
  );
}
