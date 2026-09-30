import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function descargarArchivo(path: string, nombreArchivo: string) {
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${data.session?.access_token}` },
  });
  if (!res.ok) throw new Error("No se pudo descargar el archivo");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombreArchivo;
  a.click();
  URL.revokeObjectURL(url);
}
