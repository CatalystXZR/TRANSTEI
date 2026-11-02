export type Rol = "admin" | "operacion" | "contabilidad";

/**
 * Perfil del usuario autenticado: contrato de `GET /auth/me`.
 * El backend deriva `rol` de los roles del núcleo y es la autoridad de permisos.
 */
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
