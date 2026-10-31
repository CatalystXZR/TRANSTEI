"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { AppShell } from "@/components/app-shell";
import { esRutaLegacy } from "@/lib/navigation";
import { Loader2, ShieldAlert } from "lucide-react";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { session, usuario, loading, perfilCargando } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  // `es_legacy === undefined` no bloquea: el perfil se normaliza en el contexto
  // y el backend sigue siendo la autoridad (403 LEGACY_SOLO_TEI).
  const sinLegacy = usuario?.es_legacy === false;
  const rutaBloqueada = sinLegacy && esRutaLegacy(pathname);

  useEffect(() => {
    if (!loading && !session) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, session, router, pathname]);

  // Defensa en profundidad: una URL directa a una pantalla legacy con
  // `es_legacy === false` no monta la pantalla; se avisa en la mesa de despacho.
  useEffect(() => {
    if (!rutaBloqueada) return;
    router.replace(
      `/despacho?aviso=sin-acceso-legacy&ruta=${encodeURIComponent(pathname)}`,
    );
  }, [rutaBloqueada, pathname, router]);

  // También evita montar una pantalla legacy mientras `/auth/me` está en vuelo.
  if (loading || (!!session && perfilCargando)) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-s3 bg-fondo" role="status">
        <span className="grid size-12 place-items-center rounded-xl bg-marca font-heading text-[15px] font-extrabold text-white">
          TEI
        </span>
        <Loader2 className="size-5 animate-spin text-tinta-3" />
        <span className="sr-only">Cargando</span>
      </div>
    );
  }

  if (!session) return null;

  if (rutaBloqueada) {
    return (
      <div className="grid min-h-screen place-items-center bg-fondo px-s4" role="alert">
        <div className="max-w-md space-y-s3 text-center">
          <span className="mx-auto grid size-12 place-items-center rounded-xl border border-atencion/25 bg-atencion-tenue text-atencion">
            <ShieldAlert className="size-6" aria-hidden="true" />
          </span>
          <h1 className="text-[24px] leading-tight font-semibold">Sin permiso para esta pantalla</h1>
          <p className="text-[15px] leading-relaxed text-tinta-3">
            La pantalla solicitada pertenece al sistema legacy monoempresa y su empresa no lo
            opera. Lo estamos llevando a la mesa de despacho del núcleo.
          </p>
          <span className="inline-flex items-center gap-2 text-[14px] text-tinta-3">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            Redirigiendo…
          </span>
        </div>
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
