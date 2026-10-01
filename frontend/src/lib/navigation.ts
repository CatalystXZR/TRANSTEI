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
  fase: string;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Panel de Control", icon: LayoutDashboard, roles: ["admin", "operacion", "contabilidad"], fase: "Fase 2" },
  { href: "/viajes", label: "Viajes", icon: Truck, roles: ["admin", "operacion", "contabilidad"], fase: "Fase 2" },
  { href: "/clientes", label: "Clientes", icon: Users, roles: ["admin", "operacion"], fase: "Fase 1" },
  { href: "/choferes", label: "Choferes", icon: UserRound, roles: ["admin", "operacion"], fase: "Fase 1" },
  { href: "/flota", label: "Flota", icon: Container, roles: ["admin", "operacion"], fase: "Fase 1" },
  { href: "/mantenimiento", label: "Mantenimiento", icon: Wrench, roles: ["admin", "operacion"], fase: "Fase 4" },
  { href: "/facturacion", label: "Facturación", icon: FileText, roles: ["admin", "operacion", "contabilidad"], fase: "Fase 3" },
  { href: "/cobranzas", label: "Cobranzas", icon: HandCoins, roles: ["admin", "contabilidad"], fase: "Fase 3" },
  { href: "/iva", label: "IVA", icon: Calculator, roles: ["admin", "contabilidad"], fase: "Fase 3" },
  { href: "/liquidaciones", label: "Liquidaciones", icon: Wallet, roles: ["admin", "contabilidad"], fase: "Fase 4" },
  { href: "/kpis", label: "Indicadores (KPIs)", icon: Gauge, roles: ["admin"], fase: "Fase 6" },
  { href: "/configuracion", label: "Configuración", icon: Settings, roles: ["admin"], fase: "Fase 0" },
];
