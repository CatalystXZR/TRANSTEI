"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronRight, LogOut, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "cn";
import { gruposParaRol, tituloDeRuta } from "@/lib/navigation";
import { useAuth } from "@/context/auth-context";
import { ROL_LABEL } from "@/types";
import { Button } from "@/components/ui/button";

function iniciales(nombre: string) {
  return nombre
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

function fechaHoy() {
  return new Intl.DateTimeFormat("es-CL", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { usuario, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [hoy, setHoy] = useState("");

  const grupos = gruposParaRol(usuario?.rol);
  const actual = tituloDeRuta(pathname);

  useEffect(() => {
    const t = setTimeout(() => setHoy(fechaHoy()), 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setMenuAbierto(false), 0);
    return () => clearTimeout(t);
  }, [pathname]);

  async function handleLogout() {
    await signOut();
    router.replace("/login");
  }

  const navegacion = (
    <nav aria-label="Navegación principal" className="flex flex-col gap-s4 px-s3 py-s4">
      {!usuario &&
        Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="space-y-s2 px-s3" aria-hidden="true">
            <div className="h-2.5 w-16 rounded bg-white/10" />
            <div className="h-9 rounded-lg bg-white/[0.06]" />
            <div className="h-9 rounded-lg bg-white/[0.06]" />
          </div>
        ))}
      {grupos.map((g) => (
        <div key={g.titulo}>
          <p className="px-s3 pb-s2 font-mono text-[11px] font-medium tracking-[0.14em] text-sidebar-foreground/45 uppercase">
            {g.titulo}
          </p>
          <ul className="flex flex-col gap-0.5">
            {g.items.map((item) => {
              const activo = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={activo ? "page" : undefined}
                    className={cn(
                      "group relative flex items-center gap-s3 rounded-lg px-s3 py-2.5 text-[15.5px] font-medium transition-[background-color,color,padding] duration-150",
                      activo
                        ? "bg-sidebar-accent text-white"
                        : "text-sidebar-foreground hover:bg-white/[0.06] hover:pl-[16px] hover:text-white",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-1/2 left-0 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-senal transition-opacity",
                        activo ? "opacity-100" : "opacity-0",
                      )}
                      aria-hidden="true"
                    />
                    <item.icon
                      className={cn(
                        "size-[19px] shrink-0 transition-colors",
                        activo ? "text-senal" : "text-sidebar-foreground/70 group-hover:text-white",
                      )}
                    />
                    <span className="truncate">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );

  const pieUsuario = usuario && (
    <div className="border-t border-sidebar-border p-s3">
      <div className="flex items-center gap-s3 rounded-lg px-s2 py-s2">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-senal font-heading text-[15px] font-bold text-marca-profundo">
          {iniciales(usuario.nombre) || "?"}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-medium text-white">{usuario.nombre}</p>
          <p className="truncate text-[13px] text-sidebar-foreground/70">{ROL_LABEL[usuario.rol]}</p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          aria-label="Cerrar sesión"
          title="Cerrar sesión"
          className="grid size-9 cursor-pointer place-items-center rounded-lg text-sidebar-foreground/70 transition-colors hover:bg-white/10 hover:text-white"
        >
          <LogOut className="size-[18px]" />
        </button>
      </div>
    </div>
  );

  const marca = (
    <Link href="/dashboard" className="flex items-center gap-s3 rounded-lg">
      <span className="grid size-10 place-items-center rounded-lg bg-white font-heading text-[15px] font-extrabold tracking-tight text-marca">
        TEI
      </span>
      <span className="leading-tight">
        <span className="block font-heading text-[17px] font-semibold text-white">Transportes TEI</span>
        <span className="block text-[12.5px] text-sidebar-foreground/70">Sistema de gestión</span>
      </span>
    </Link>
  );

  return (
    <div className="flex min-h-screen bg-fondo">
      {/* Sidebar escritorio */}
      <aside
        data-slot="sidebar"
        className="contorno sticky top-0 hidden h-screen w-[268px] shrink-0 flex-col self-start bg-sidebar lg:flex"
      >
        <div className="border-b border-sidebar-border px-s4 py-s4">{marca}</div>
        <div className="flex-1 overflow-y-auto">{navegacion}</div>
        {pieUsuario}
      </aside>

      {/* Drawer móvil */}
      {menuAbierto && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menú">
          <button
            type="button"
            className="absolute inset-0 bg-marca-profundo/50 backdrop-blur-[2px] animate-in fade-in-0"
            onClick={() => setMenuAbierto(false)}
            aria-label="Cerrar menú"
          />
          <aside
            data-slot="sidebar"
            className="contorno relative flex h-full w-[min(300px,86vw)] flex-col bg-sidebar shadow-2xl animate-in slide-in-from-left duration-200"
          >
            <div className="flex items-center justify-between border-b border-sidebar-border px-s4 py-s4">
              {marca}
              <button
                type="button"
                onClick={() => setMenuAbierto(false)}
                aria-label="Cerrar menú"
                className="grid size-9 cursor-pointer place-items-center rounded-lg text-sidebar-foreground hover:bg-white/10 hover:text-white"
              >
                <X className="size-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">{navegacion}</div>
            {pieUsuario}
          </aside>
        </div>
      )}

      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-[64px] items-center gap-s3 border-b border-borde bg-fondo/85 px-s4 backdrop-blur-md md:px-s5">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setMenuAbierto(true)}
            aria-label="Abrir menú"
          >
            <Menu className="size-5" />
          </Button>
          <div className="flex min-w-0 items-center gap-1.5 text-[15px]">
            {actual ? (
              <>
                <span className="hidden text-tinta-3 sm:inline">{actual.grupo}</span>
                <ChevronRight className="hidden size-4 text-tinta-3/60 sm:inline" />
                <span className="truncate font-medium text-tinta">{actual.label}</span>
              </>
            ) : (
              <span className="font-medium text-tinta">Transportes TEI</span>
            )}
          </div>
          <p className="ml-auto hidden text-[14px] text-tinta-3 first-letter:uppercase md:block" suppressHydrationWarning>
            {hoy}
          </p>
        </header>

        <main className="reticula flex-1">
          <div className="mx-auto w-full max-w-[1360px] px-s4 py-s5 md:px-s5 lg:py-s6">{children}</div>
        </main>
      </div>
    </div>
  );
}
