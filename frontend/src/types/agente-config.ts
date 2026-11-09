/**
 * Tipos del contrato HTTP de configuración de capacidades de los agentes
 * (`/nucleo/agente/configuracion`).
 *
 * Contrato fijado para esta pantalla; la UI no inventa campos ni estados. El
 * backend es la autoridad: valida el permiso `agente:configurar`, la empresa
 * (`X-Empresa-ID`) y la disponibilidad de cada capacidad.
 *
 * Endpoints:
 * - `GET /nucleo/agente/configuracion` → `ConfiguracionAgentesNucleo`
 * - `PUT /nucleo/agente/configuracion` → `AgenteConfigNucleo`
 * - `POST /nucleo/agente/configuracion/restablecer` → `AgenteConfigNucleo`
 */

export type AgenteConfigClave = "gerente" | "secretaria";

export type RiesgoCapacidad = "bajo" | "medio" | "alto";

/**
 * Motivos de indisponibilidad declarados por el backend. Si en el futuro
 * aparece otro valor, la UI lo trata como no disponible sin inventar el motivo
 * (el tipo se mantiene acotado al contrato vigente).
 */
export type MotivoNoDisponibleCapacidad = "permiso" | "modulo_inactivo";

export interface CapacidadAgenteNucleo {
  clave: string;
  nombre: string;
  descripcion: string;
  grupo: string;
  riesgo: RiesgoCapacidad;
  habilitada: boolean;
  por_defecto: boolean;
  disponible: boolean;
  motivo_no_disponible: MotivoNoDisponibleCapacidad | null;
  /** Módulo del que depende la capacidad, si aplica. */
  modulo: string | null;
  /** `null` cuando la capacidad no depende de un módulo. */
  modulo_activo: boolean | null;
}

export interface AgenteConfigNucleo {
  clave: AgenteConfigClave;
  nombre: string;
  capacidades: CapacidadAgenteNucleo[];
}

export interface ConfiguracionAgentesNucleo {
  agentes: AgenteConfigNucleo[];
}

/** Un solo cambio por llamada PUT, según el contrato. */
export interface CambioCapacidadNucleo {
  capacidad: string;
  habilitada: boolean;
}

export interface ActualizarConfiguracionAgenteNucleo {
  agente: AgenteConfigClave;
  cambios: CambioCapacidadNucleo[];
}

export interface RestablecerConfiguracionAgenteNucleo {
  agente: AgenteConfigClave;
}
