"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Loader2, Lock, Mail } from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function LoginForm() {
  const { signIn } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setCargando(true);
    const { error } = await signIn(email, password);
    setCargando(false);
    if (error) {
      setError("Correo o contraseña incorrectos. Intente nuevamente.");
      return;
    }
    const destino = searchParams.get("next") ?? "/dashboard";
    router.replace(destino.startsWith("/") ? destino : "/dashboard");
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-s4" noValidate>
      <div className="space-y-s2">
        <Label htmlFor="email">Correo electrónico</Label>
        <div className="relative">
          <Mail className="pointer-events-none absolute top-1/2 left-3 size-[18px] -translate-y-1/2 text-tinta-3" />
          <Input
            id="email"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-12 pl-10 text-[17px]"
            placeholder="nombre@transportestei.cl"
            aria-invalid={!!error}
          />
        </div>
      </div>
      <div className="space-y-s2">
        <Label htmlFor="password">Contraseña</Label>
        <div className="relative">
          <Lock className="pointer-events-none absolute top-1/2 left-3 size-[18px] -translate-y-1/2 text-tinta-3" />
          <Input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-12 pl-10 text-[17px]"
            aria-invalid={!!error}
          />
        </div>
      </div>
      {error && (
        <p role="alert" className="rounded-lg border border-critico/20 bg-critico-tenue px-s3 py-s3 text-[15px] text-critico">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" disabled={cargando || !email || !password} className="w-full">
        {cargando ? (
          <>
            <Loader2 className="animate-spin" /> Ingresando…
          </>
        ) : (
          <>
            Ingresar <ArrowRight className="transition-transform group-hover/button:translate-x-0.5" />
          </>
        )}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="grid min-h-screen bg-fondo lg:grid-cols-[1.05fr_1fr]">
      <aside className="contorno relative hidden flex-col justify-between overflow-hidden bg-sidebar p-s6 text-white lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            backgroundImage:
              "linear-gradient(rgb(255 255 255 / 0.04) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 255 / 0.04) 1px, transparent 1px)",
            backgroundSize: "52px 52px",
          }}
          aria-hidden="true"
        />
        <div className="relative flex items-center gap-s3">
          <span className="grid size-11 place-items-center rounded-lg bg-white font-heading text-[16px] font-extrabold text-marca">
            TEI
          </span>
          <span className="font-heading text-[18px] font-semibold">Transportes TEI SpA</span>
        </div>
        <div className="relative max-w-lg">
          <p className="rotulo !text-senal">Sistema de gestión</p>
          <h1 className="mt-s3 font-heading text-[52px] leading-[1.02] font-semibold tracking-tight !text-white">
            Viajes, flota y cobranzas en un solo lugar.
          </h1>
          <p className="mt-s4 text-[18px] leading-relaxed text-white/70">
            Sepa qué se debe cobrar, qué camión requiere mantención y cuánto deja cada flete.
          </p>
        </div>
        <div className="relative grid grid-cols-3 gap-s4 border-t border-white/10 pt-s4 text-[14px] text-white/60">
          <div><span className="block font-heading text-[22px] font-semibold text-white">Viajes</span>estado en tiempo real</div>
          <div><span className="block font-heading text-[22px] font-semibold text-white">Cobros</span>vencimientos al día</div>
          <div><span className="block font-heading text-[22px] font-semibold text-white">Flota</span>mantención por km</div>
        </div>
      </aside>

      <main className="flex items-center justify-center p-s4 sm:p-s6">
        <div className="w-full max-w-[420px]">
          <div className="mb-s5 flex items-center gap-s3 lg:hidden">
            <span className="grid size-11 place-items-center rounded-lg bg-marca font-heading text-[16px] font-extrabold text-white">
              TEI
            </span>
            <span className="font-heading text-[18px] font-semibold">Transportes TEI</span>
          </div>
          <h2 className="text-[32px] leading-tight font-semibold">Iniciar sesión</h2>
          <p className="mt-s2 mb-s5 text-[16px] text-tinta-3">Ingrese con el correo y contraseña asignados.</p>
          <Suspense fallback={null}>
            <LoginForm />
          </Suspense>
          <p className="mt-s5 text-[14px] text-tinta-3">¿Problemas para ingresar? Contacte al administrador.</p>
        </div>
      </main>
    </div>
  );
}
