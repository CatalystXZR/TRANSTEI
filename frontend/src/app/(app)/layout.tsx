"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { AppShell } from "@/components/app-shell";
import { Loader2 } from "lucide-react";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !session) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, session, router, pathname]);

  if (loading) {
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

  return <AppShell>{children}</AppShell>;
}
