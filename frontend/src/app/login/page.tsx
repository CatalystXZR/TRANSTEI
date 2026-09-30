"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2 } from "lucide-react";

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
    router.replace(destino);
  }

  return (
    <Card className="w-full max-w-md border-t-4 border-t-[#2A237A]">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl font-bold text-[#2A237A]">
          Transportes TEI
        </CardTitle>
        <p className="text-base text-gray-500">Sistema de Gestión</p>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="email" className="text-base">
              Correo electrónico
            </Label>
            <Input
              id="email"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="text-base"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password" className="text-base">
              Contraseña
            </Label>
            <Input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="text-base"
            />
          </div>
          {error && (
            <p className="rounded-md bg-red-50 p-3 text-base text-red-700">{error}</p>
          )}
          <Button
            type="submit"
            disabled={cargando}
            className="w-full bg-[#2A237A] text-base hover:bg-[#2A237A]/90"
          >
            {cargando ? <Loader2 className="h-5 w-5 animate-spin" /> : "Ingresar"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F9FAFB] p-4">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
