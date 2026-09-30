export type Rol = "admin" | "operacion" | "contabilidad";

export interface Usuario {
  id: string;
  nombre: string;
  email: string | null;
  rol: Rol;
}

export const ROL_LABEL: Record<Rol, string> = {
  admin: "Administrador",
  operacion: "Operación",
  contabilidad: "Contabilidad",
};

export interface Cliente {
  id: string;
  razon_social: string;
  rut: string;
  giro: string | null;
  dias_pago: number;
  telefono: string | null;
  email: string | null;
  activo: boolean;
}

export interface Chofer {
  id: string;
  nombre: string;
  rut: string;
  sueldo_base: string;
  porcentaje_produccion: string;
  vencimiento_licencia: string | null;
  activo: boolean;
}

export interface Tracto {
  id: string;
  patente: string;
  marca: string | null;
  modelo: string | null;
  ano: number | null;
  km_actual: number;
  vencimiento_revision_tecnica: string | null;
  vencimiento_seguro: string | null;
  activo: boolean;
}

export interface Rampla {
  id: string;
  patente: string;
  tipo: "plana" | "sider";
  vencimiento_revision_tecnica: string | null;
  activo: boolean;
}

export type EstadoViaje = "programado" | "en_ruta" | "finalizado" | "facturado";

export const ESTADO_VIAJE_LABEL: Record<EstadoViaje, string> = {
  programado: "Programado",
  en_ruta: "En Ruta",
  finalizado: "Finalizado",
  facturado: "Facturado",
};

export const ESTADO_VIAJE_COLOR: Record<EstadoViaje, string> = {
  programado: "bg-blue-100 text-blue-800",
  en_ruta: "bg-yellow-500 text-black",
  finalizado: "bg-green-100 text-green-800",
  facturado: "bg-[#2A237A] text-white",
};

export interface Viaje {
  id: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  origen: string;
  destino: string;
  estado: EstadoViaje;
  valor_flete_neto: string;
  cliente_id: string;
  chofer_id: string;
  tracto_id: string;
  rampla_id: string;
  notas: string | null;
  cliente_nombre: string;
  chofer_nombre: string;
  tracto_patente: string;
  rampla_patente: string;
  total_gastos: string;
}

export type CategoriaGasto =
  | "combustible"
  | "peaje"
  | "viatico"
  | "mantenimiento_ruta"
  | "otros";

export const CATEGORIA_GASTO_LABEL: Record<CategoriaGasto, string> = {
  combustible: "Combustible",
  peaje: "Peaje",
  viatico: "Viático",
  mantenimiento_ruta: "Mantenimiento en ruta",
  otros: "Otros",
};

export interface Gasto {
  id: string;
  viaje_id: string;
  categoria: CategoriaGasto;
  monto: string;
  iva_recuperable: boolean;
  respaldo_url: string | null;
  fecha: string;
  notas: string | null;
}

export interface ResumenDashboard {
  mes: string;
  ingresos_mes: string;
  cuentas_por_cobrar: string;
  cuentas_atrasadas: string;
  gastos_mes: string;
  viajes_activos: Viaje[];
}

export interface AlertaVencimiento {
  tipo: "tracto" | "rampla" | "chofer";
  equipo: string;
  concepto: string;
  fecha: string;
  dias_restantes: number;
}

export interface FacturaVencida {
  id: string;
  numero_sii: string;
  cliente: string;
  total: string;
  fecha_vencimiento: string | null;
  dias_atraso: number | null;
}

export interface AlertasDashboard {
  vencimientos: AlertaVencimiento[];
  facturas_vencidas: FacturaVencida[];
}
