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
