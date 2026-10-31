import type { Tono } from "@/components/sistema";
import type {
  JsonNucleo,
  SolicitanteSolicitudNucleo,
} from "@/types/nucleo";

/* ------------------------------------------------------------------ */
/* Etiquetas y semántica visual del buzón                              */
/* ------------------------------------------------------------------ */

export const TIPO_SOLICITUD_LABEL: Record<string, string> = {
  agendamiento: "Agendamiento",
  documentos: "Documentos",
  hoja_de_ruta: "Hoja de ruta",
  otra: "Otra solicitud",
};

export const ESTADO_SOLICITUD_LABEL: Record<string, string> = {
  pendiente: "Pendiente",
  aprobada: "Aprobada",
  rechazada: "Rechazada",
  cancelada: "Cancelada",
};

export function etiquetaTipoSolicitud(tipo: string): string {
  return TIPO_SOLICITUD_LABEL[tipo] ?? tipo.replaceAll("_", " ");
}

export function etiquetaEstadoSolicitud(estado: string): string {
  return ESTADO_SOLICITUD_LABEL[estado] ?? estado.replaceAll("_", " ");
}

export function tonoEstadoSolicitud(estado: string): Tono {
  if (estado === "aprobada") return "ok";
  if (estado === "rechazada") return "critico";
  if (estado === "pendiente") return "atencion";
  return "neutro";
}

export function etiquetaSolicitante(
  solicitante: SolicitanteSolicitudNucleo,
): string {
  if (solicitante.nombre) return solicitante.nombre;
  return solicitante.tipo === "contacto"
    ? "Contacto sin nombre"
    : "Usuario del sistema";
}

export function etiquetaCampo(campo: string): string {
  const texto = campo.replaceAll("_", " ").trim();
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : campo;
}

/* ------------------------------------------------------------------ */
/* Payload y diff                                                      */
/* ------------------------------------------------------------------ */

export function esObjetoJson(
  valor: JsonNucleo,
): valor is Record<string, JsonNucleo> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

export function esValorEstructurado(valor: JsonNucleo | undefined): boolean {
  return valor !== null && valor !== undefined &&
    (Array.isArray(valor) || esObjetoJson(valor));
}

export function valorATexto(valor: JsonNucleo | undefined): string {
  if (valor === undefined || valor === null) return "";
  if (typeof valor === "boolean") return valor ? "true" : "false";
  if (typeof valor === "number") return String(valor);
  if (typeof valor === "string") return valor;
  return JSON.stringify(valor, null, 2);
}

export function parsearValorSolicitud(
  texto: string,
  original: JsonNucleo | undefined,
): { valor: JsonNucleo } | { error: string } {
  if (typeof original === "boolean") return { valor: texto === "true" };
  if (typeof original === "number") {
    const numero = Number(texto);
    if (texto.trim() === "" || !Number.isFinite(numero)) {
      return { error: "Ingrese un número válido." };
    }
    return { valor: numero };
  }
  if (original === null || original === undefined) {
    const limpio = texto.trim();
    if (!limpio) return { valor: null };
    try {
      return { valor: JSON.parse(limpio) as JsonNucleo };
    } catch {
      return { valor: texto };
    }
  }
  if (esValorEstructurado(original)) {
    try {
      return { valor: JSON.parse(texto) as JsonNucleo };
    } catch {
      return { error: "JSON no válido. Revise comillas, llaves y corchetes." };
    }
  }
  return { valor: texto };
}

export function igualesJson(
  a: JsonNucleo | undefined,
  b: JsonNucleo | undefined,
): boolean {
  if (a === b) return true;
  if (a === undefined || b === undefined || a === null || b === null) {
    return false;
  }
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
      return false;
    }
    return a.every((valor, indice) => igualesJson(valor, b[indice]));
  }
  if (esObjetoJson(a) && esObjetoJson(b)) {
    const clavesA = Object.keys(a);
    const clavesB = Object.keys(b);
    if (clavesA.length !== clavesB.length) return false;
    return clavesA.every((clave) => igualesJson(a[clave], b[clave]));
  }
  return false;
}

/**
 * Deriva `valores_modificados` comparando el formulario con el payload
 * original. Solo se envían los campos que realmente cambian; los demás
 * conservan el valor propuesto por el agente.
 */
export function calcularCambiosSolicitud(
  payload: Record<string, JsonNucleo>,
  valores: Record<string, string>,
): {
  cambios: Record<string, JsonNucleo>;
  errores: Record<string, string>;
} {
  const cambios: Record<string, JsonNucleo> = {};
  const errores: Record<string, string> = {};
  for (const campo of Object.keys(valores)) {
    const original = payload[campo];
    const texto = valores[campo] ?? "";
    // Un campo nuevo y vacío no es una modificación.
    if (original === undefined && texto.trim() === "") continue;
    const resultado = parsearValorSolicitud(texto, original);
    if ("error" in resultado) {
      errores[campo] = resultado.error;
      continue;
    }
    if (!igualesJson(resultado.valor, original)) {
      cambios[campo] = resultado.valor;
    }
  }
  return { cambios, errores };
}
