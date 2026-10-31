export type Rol = "admin" | "operacion" | "contabilidad";

export interface Usuario {
  id: string;
  nombre: string;
  email: string | null;
  rol: Rol;
  /**
   * `GET /auth/me`: `true` si el usuario puede operar el legacy monoempresa
   * (TEI); `false` si pertenece solo a empresas del núcleo (las rutas
   * `/api/v1/<legacy>` le responden 403 `LEGACY_SOLO_TEI`).
   *
   * El contexto de auth normaliza `undefined` a `true` para tolerar un backend
   * que aún no expone el flag: el servidor sigue siendo la autoridad.
   *
   * Nota Ola C: con el retiro de las pantallas legacy, este flag solo se usa
   * para elegir la pantalla de inicio en `AppShell`. Su retiro definitivo
   * (contexto, tipo y backend) queda para la Ola E.
   */
  es_legacy: boolean;
}

export const ROL_LABEL: Record<Rol, string> = {
  admin: "Administrador",
  operacion: "Operación",
  contabilidad: "Contabilidad",
};
