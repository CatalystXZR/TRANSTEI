import {
  LayoutDashboard,
  Truck,
  Users,
  UserRound,
  Container,
  Wrench,
  FileText,
  HandCoins,
  Calculator,
  Wallet,
  Settings,
  Gauge,
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
    items: [{ href: "/dashboard", label: "Panel de control", icon: LayoutDashboard, roles: TODOS }],
  },
  {
    titulo: "Operación",
    items: [
      { href: "/viajes", label: "Viajes", icon: Truck, roles: TODOS },
      { href: "/flota", label: "Flota", icon: Container, roles: ["admin", "operacion"] },
      { href: "/mantenimiento", label: "Mantenimiento", icon: Wrench, roles: ["admin", "operacion"] },
    ],
  },
  {
    titulo: "Finanzas",
    items: [
      { href: "/facturacion", label: "Facturación", icon: FileText, roles: TODOS },
      { href: "/cobranzas", label: "Cobranzas", icon: HandCoins, roles: ["admin", "contabilidad"] },
      { href: "/iva", label: "IVA mensual", icon: Calculator, roles: ["admin", "contabilidad"] },
      { href: "/liquidaciones", label: "Liquidaciones", icon: Wallet, roles: ["admin", "contabilidad"] },
    ],
  },
  {
    titulo: "Maestros",
    items: [
      { href: "/clientes", label: "Clientes", icon: Users, roles: ["admin", "operacion"] },
      { href: "/choferes", label: "Choferes", icon: UserRound, roles: ["admin", "operacion"] },
    ],
  },
  {
    titulo: "Sistema",
    items: [
      { href: "/kpis", label: "Indicadores", icon: Gauge, roles: ["admin"] },
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
