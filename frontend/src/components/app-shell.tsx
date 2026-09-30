"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, X } from "lucide-react";
import { useState } from "react";
import { NAV_ITEMS } from "@/lib/navigation";
import { useAuth } from "@/context/auth-context";
import { ROL_LABEL } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { usuario, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [menuAbierto, setMenuAbierto] = useState(false);

  const items = NAV_ITEMS.filter((i) => usuario && i.roles.includes(usuario.rol));

  async function handleLogout() {
    await signOut();
    router.replace("/login");
  }

  const nav = (
    <nav className="flex flex-col gap-1 p-3">
      {items.map((item) => {
        const activo = pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setMenuAbierto(false)}
            className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-base font-medium transition-colors ${
              activo
                ? "bg-white/15 text-white"
                : "text-indigo-100 hover:bg-white/10 hover:text-white"
            }`}
          >
            <item.icon className="h-5 w-5 shrink-0" />
            <span className="flex-1">{item.label}</span>
            {activo && <span className="h-2 w-2 rounded-full bg-[#FCD116]" />}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="hidden w-64 shrink-0 flex-col bg-[#2A237A] text-white md:flex">
        <div className="border-b border-white/10 p-5">
          <p className="text-xl font-bold">Transportes TEI</p>
          <p className="mt-1 text-sm text-indigo-200">Sistema de Gestión</p>
        </div>
        <div className="flex-1 overflow-y-auto">{nav}</div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b bg-white px-4 py-3 md:px-6">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={() => setMenuAbierto(!menuAbierto)}
              aria-label="Menú"
            >
              {menuAbierto ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
            <span className="hidden text-sm text-gray-500 md:block">
              Transportes TEI SpA
            </span>
          </div>
          <div className="flex items-center gap-3">
            {usuario && (
              <>
                <div className="hidden text-right sm:block">
                  <p className="text-base font-medium leading-tight">{usuario.nombre}</p>
                  <p className="text-sm text-gray-500">{ROL_LABEL[usuario.rol]}</p>
                </div>
                <Badge className="bg-[#2A237A] text-sm">{ROL_LABEL[usuario.rol]}</Badge>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleLogout}
                  className="gap-2"
                >
                  <LogOut className="h-4 w-4" />
                  Salir
                </Button>
              </>
            )}
          </div>
        </header>

        {menuAbierto && (
          <div className="border-b bg-[#2A237A] text-white md:hidden">
            {nav}
            <div className="p-3 pt-0">
              <Button
                variant="secondary"
                className="w-full justify-center gap-2"
                onClick={handleLogout}
              >
                <LogOut className="h-4 w-4" />
                Salir
              </Button>
            </div>
          </div>
        )}

        <main className="flex-1 bg-[#F9FAFB] p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
