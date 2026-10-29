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
      { href: "/dashboard", label: "Panel de control", icon: LayoutDashboard, roles: TODOS },
      { href: "/tablero", label: "Tablero del dueño", icon: Crown, roles: ["admin", "contabilidad"] },
    ],
  },
  {
    titulo: "Operación",
    items: [
      { href: "/despacho", label: "Mesa de despacho", icon: CalendarClock, roles: TODOS },
      { href: "/agenda", label: "Agenda de recursos", icon: CalendarDays, roles: TODOS },
      { href: "/expediente", label: "Expediente del viaje", icon: ClipboardList, roles: TODOS },
      { href: "/conductor", label: "Modo conductor", icon: Smartphone, roles: TODOS },
      { href: "/viajes", label: "Viajes", icon: Truck, roles: TODOS },
      { href: "/flota", label: "Flota", icon: Container, roles: ["admin", "operacion"] },
      { href: "/mantenimiento", label: "Mantenimiento", icon: Wrench, roles: ["admin", "operacion"] },
    ],
  },
  {
    titulo: "Comercial",
    items: [
      { href: "/comercial", label: "Tarifas y OC", icon: ShoppingCart, roles: TODOS },
      { href: "/rentabilidad", label: "Rentabilidad y score", icon: TrendingUp, roles: TODOS },
    ],
  },
  {
    titulo: "Finanzas",
    items: [
      { href: "/facturacion", label: "Facturación", icon: FileText, roles: TODOS },
      { href: "/cobranza", label: "Cobranza núcleo", icon: Receipt, roles: TODOS },
      { href: "/cobranzas", label: "Cobranzas legacy", icon: HandCoins, roles: ["admin", "contabilidad"] },
      { href: "/iva", label: "IVA mensual", icon: Calculator, roles: ["admin", "contabilidad"] },
      { href: "/liquidaciones", label: "Liquidaciones", icon: Wallet, roles: ["admin", "contabilidad"] },
    ],
  },
  {
    titulo: "Maestros",
    items: [
      { href: "/maestros", label: "Maestros núcleo", icon: Boxes, roles: ["admin", "operacion"] },
      { href: "/clientes", label: "Clientes", icon: Users, roles: ["admin", "operacion"] },
      { href: "/choferes", label: "Choferes", icon: UserRound, roles: ["admin", "operacion"] },
    ],
  },
  {
    titulo: "Sistema",
    items: [
      { href: "/kpis", label: "Indicadores", icon: Gauge, roles: ["admin"] },
      { href: "/auditoria", label: "Auditoría", icon: FileClock, roles: TODOS },
      { href: "/permisos", label: "Roles y permisos", icon: KeyRound, roles: TODOS },
      { href: "/cutover", label: "Cutover legacy", icon: ArrowRightLeft, roles: ["admin", "contabilidad"] },
      { href: "/configuracion", label: "Configuración", icon: Settings, roles: ["admin"] },
    ],
  },
];

/** Lista plana (compatibilidad) */
export const NAV_ITEMS: NavItem[] = NAV_GRUPOS.flatMap((g) => g.items);

export function gruposParaRol(rol: Rol | undefined): NavGrupo[] {
  if (!rol) return [];
  return NAV_GRUPOS.map((g) => ({ ...g, items: g.items.filter((i) => i.roles.includes(rol)) })).filter(
    (g) => g.items.length > 0,
  );
}

export function tituloDeRuta(pathname: string): { grupo: string; label: string } | null {
  for (const g of NAV_GRUPOS) {
    for (const i of g.items) {
      if (pathname === i.href || pathname.startsWith(`${i.href}/`)) return { grupo: g.titulo, label: i.label };
    }
  }
  return null;
}
