import {
  LayoutDashboard,
  CalendarClock,
  CalendarDays,
  Boxes,
  ClipboardList,
  Truck,
  Users,
  UserRound,
  Container,
  Wrench,
  FileText,
  HandCoins,
  Receipt,
  Calculator,
  Wallet,
  Settings,
  Gauge,
  ShoppingCart,
  Smartphone,
  Inbox,
  TrendingUp,
  Crown,
  FileClock,
  KeyRound,
  ArrowRightLeft,
  type LucideIcon,
} from "lucide-react";
import type { Rol } from "@/types";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  roles: Rol[];
  /**
   * `true` = pantalla servida por el legacy monoempresa (`/api/v1/...`).
   * Un usuario con `es_legacy === false` no la ve ni puede operarla.
   */
  legacy: boolean;
}

export interface NavGrupo {
  titulo: string;
  items: NavItem[];
}

const TODOS: Rol[] = ["admin", "operacion", "contabilidad"];

export const NAV_GRUPOS: NavGrupo[] = [
  {
    titulo: "General",
    items: [
      { href: "/dashboard", label: "Panel de control", icon: LayoutDashboard, roles: TODOS, legacy: true },
      { href: "/tablero", label: "Tablero del dueño", icon: Crown, roles: ["admin", "contabilidad"], legacy: false },
    ],
  },
  {
    titulo: "Operación",
    items: [
      { href: "/despacho", label: "Mesa de despacho", icon: CalendarClock, roles: TODOS, legacy: false },
      { href: "/agenda", label: "Agenda de recursos", icon: CalendarDays, roles: TODOS, legacy: false },
      { href: "/expediente", label: "Expediente del viaje", icon: ClipboardList, roles: TODOS, legacy: false },
      { href: "/agente/buzon", label: "Buzón del agente", icon: Inbox, roles: ["admin"], legacy: false },
      { href: "/conductor", label: "Modo conductor", icon: Smartphone, roles: TODOS, legacy: false },
      { href: "/viajes", label: "Viajes", icon: Truck, roles: TODOS, legacy: true },
      { href: "/flota", label: "Flota", icon: Container, roles: ["admin", "operacion"], legacy: true },
      { href: "/mantenimiento", label: "Mantenimiento", icon: Wrench, roles: ["admin", "operacion"], legacy: true },
    ],
  },
  {
    titulo: "Comercial",
    items: [
      { href: "/comercial", label: "Tarifas y OC", icon: ShoppingCart, roles: TODOS, legacy: false },
      { href: "/rentabilidad", label: "Rentabilidad y score", icon: TrendingUp, roles: TODOS, legacy: false },
    ],
  },
  {
    titulo: "Finanzas",
    items: [
      { href: "/facturacion", label: "Facturación", icon: FileText, roles: TODOS, legacy: true },
      { href: "/cobranza", label: "Cobranza núcleo", icon: Receipt, roles: TODOS, legacy: false },
      { href: "/cobranzas", label: "Cobranzas legacy", icon: HandCoins, roles: ["admin", "contabilidad"], legacy: true },
      { href: "/iva", label: "IVA mensual", icon: Calculator, roles: ["admin", "contabilidad"], legacy: true },
      { href: "/liquidaciones", label: "Liquidaciones", icon: Wallet, roles: ["admin", "contabilidad"], legacy: true },
    ],
  },
  {
    titulo: "Maestros",
    items: [
      { href: "/maestros", label: "Maestros núcleo", icon: Boxes, roles: ["admin", "operacion"], legacy: false },
      { href: "/clientes", label: "Clientes", icon: Users, roles: ["admin", "operacion"], legacy: true },
      { href: "/choferes", label: "Choferes", icon: UserRound, roles: ["admin", "operacion"], legacy: true },
    ],
  },
  {
    titulo: "Sistema",
    items: [
      { href: "/kpis", label: "Indicadores", icon: Gauge, roles: ["admin"], legacy: true },
      { href: "/auditoria", label: "Auditoría", icon: FileClock, roles: TODOS, legacy: false },
      { href: "/permisos", label: "Roles y permisos", icon: KeyRound, roles: TODOS, legacy: false },
      { href: "/cutover", label: "Cutover legacy", icon: ArrowRightLeft, roles: ["admin", "contabilidad"], legacy: false },
      { href: "/configuracion", label: "Configuración", icon: Settings, roles: ["admin"], legacy: true },
    ],
  },
];

/** Lista plana (compatibilidad) */
export const NAV_ITEMS: NavItem[] = NAV_GRUPOS.flatMap((g) => g.items);

/**
 * Rutas del legacy monoempresa derivadas de la navegación, para que la lista
 * no se desincronice al agregar o retirar una pantalla.
 */
export const RUTAS_LEGACY: string[] = NAV_ITEMS.filter((i) => i.legacy).map((i) => i.href);

/** ¿La ruta pertenece a una pantalla del legacy monoempresa? */
export function esRutaLegacy(pathname: string): boolean {
  return RUTAS_LEGACY.some((href) => pathname === href || pathname.startsWith(`${href}/`));
}

/**
 * Ítems visibles según rol y pertenencia al legacy.
 * `esLegacy` por defecto es `true` (sin sesión no se decide nada; el rol
 * tampoco existe y la lista queda vacía).
 */
export function gruposParaRol(rol: Rol | undefined, esLegacy = true): NavGrupo[] {
  if (!rol) return [];
  return NAV_GRUPOS.map((g) => ({
    ...g,
    items: g.items.filter((i) => i.roles.includes(rol) && (esLegacy || !i.legacy)),
  })).filter((g) => g.items.length > 0);
}

export function tituloDeRuta(pathname: string): { grupo: string; label: string } | null {
  for (const g of NAV_GRUPOS) {
    for (const i of g.items) {
      if (pathname === i.href || pathname.startsWith(`${i.href}/`)) return { grupo: g.titulo, label: i.label };
    }
  }
  return null;
}
