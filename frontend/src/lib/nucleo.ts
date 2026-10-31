import { createClient } from "@/lib/supabase/client";
import type { EmpresaNucleo, IncidenciaNucleo } from "@/types/nucleo";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class NucleoError extends Error {
  status: number;
  codigo?: string;
  errores: IncidenciaNucleo[];

  constructor(
    message: string,
    status: number,
    codigo?: string,
    errores: IncidenciaNucleo[] = [],
  ) {
    super(message);
    this.name = "NucleoError";
    this.status = status;
    this.codigo = codigo;
    this.errores = errores;
  }
}

async function authHeaders(empresaId?: string): Promise<HeadersInit> {
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new NucleoError("Sesión expirada. Vuelva a iniciar sesión.", 401);
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
    ...(empresaId ? { "X-Empresa-ID": empresaId } : {}),
  };
}

export async function nucleoFetch<T>(
  path: string,
  options: RequestInit = {},
  empresaId?: string,
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    cache: "no-store",
    headers: {
      ...(await authHeaders(empresaId)),
      ...(options.headers ?? {}),
    },
  });

  if (res.status === 204) return undefined as T;

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }

  if (!res.ok) {
    const payload = (body ?? {}) as {
      mensaje?: string;
      codigo?: string;
      errores?: IncidenciaNucleo[];
      detail?: string | { msg?: string }[];
    };
    const detail = payload.detail;
    const detalle =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail[0]?.msg
          : undefined;
    throw new NucleoError(
      payload.mensaje ?? detalle ?? "Error del núcleo operacional",
      res.status,
      payload.codigo,
      payload.errores ?? [],
    );
  }

  return body as T;
}

export async function getEmpresas(): Promise<EmpresaNucleo[]> {
  return nucleoFetch<EmpresaNucleo[]>("/nucleo/mis-empresas");
}

export const nucleo = {
  get: <T>(path: string, empresaId: string) =>
    nucleoFetch<T>(path, { method: "GET" }, empresaId),
  post: <T>(path: string, empresaId: string, body: unknown) =>
    nucleoFetch<T>(
      path,
      { method: "POST", body: JSON.stringify(body) },
      empresaId,
    ),
  put: <T>(path: string, empresaId: string, body: unknown) =>
    nucleoFetch<T>(
      path,
      { method: "PUT", body: JSON.stringify(body) },
      empresaId,
    ),
  del: (path: string, empresaId: string) =>
    nucleoFetch<void>(path, { method: "DELETE" }, empresaId),
};

/**
 * Descarga un archivo del núcleo (CSV) reutilizando el mismo JWT y
 * `X-Empresa-ID` que el resto del cliente. No se construyen URLs de storage:
 * la ruta es siempre un endpoint del backend.
 */
export async function descargarNucleo(
  path: string,
  empresaId: string,
  nombreArchivo: string,
): Promise<void> {
  const res = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    headers: await authHeaders(empresaId),
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    const payload = (body ?? {}) as {
      mensaje?: string;
      codigo?: string;
      errores?: IncidenciaNucleo[];
      detail?: string | { msg?: string }[];
    };
    const detail = payload.detail;
    const detalle =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail[0]?.msg
          : undefined;
    throw new NucleoError(
      payload.mensaje ?? detalle ?? "No se pudo descargar el archivo",
      res.status,
      payload.codigo,
      payload.errores ?? [],
    );
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

export async function nucleoUpload<T>(
  path: string,
  empresaId: string,
  formData: FormData,
  method: "POST" | "PUT" = "POST",
): Promise<T> {
  const headers = { ...(await authHeaders(empresaId)) } as Record<string, string>;
  delete headers["Content-Type"];
  const res = await fetch(`${API_URL}${path}`, {
    method,
    body: formData,
    cache: "no-store",
    headers,
  });
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    const payload = (body ?? {}) as {
      mensaje?: string;
      codigo?: string;
      errores?: IncidenciaNucleo[];
      detail?: string | { msg?: string }[];
    };
    const detail = payload.detail;
    const detalle =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail[0]?.msg
          : undefined;
    throw new NucleoError(
      payload.mensaje ?? detalle ?? "Error al subir el archivo",
      res.status,
      payload.codigo,
      payload.errores ?? [],
    );
  }
  return body as T;
}
