"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";
import type { Usuario } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

/**
 * Respuesta de `GET /auth/me`. `es_legacy` se declara opcional en el borde
 * porque el backend puede no exponerlo todavía: se normaliza antes de guardarlo.
 */
type PerfilApi = Omit<Usuario, "es_legacy"> & { es_legacy?: boolean };

interface AuthContextValue {
  session: Session | null;
  usuario: Usuario | null;
  /** `true` mientras se resuelve `/auth/me` para la sesión actual. */
  perfilCargando: boolean;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Normaliza el perfil del servidor. Un backend sin `es_legacy` se interpreta
 * como legacy (`true`), que es el comportamiento histórico de TEI: nunca se
 * habilita una pantalla legacy por ausencia de dato.
 */
function normalizarPerfil(data: PerfilApi): Usuario {
  return {
    id: data.id,
    nombre: data.nombre,
    email: data.email,
    rol: data.rol,
    es_legacy: data.es_legacy !== false,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [perfil, setPerfil] = useState<{ userId: string; usuario: Usuario | null } | null>(null);
  const [loading, setLoading] = useState(
    !process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
      ? false
      : true,
  );

  useEffect(() => {
    let supabase;
    try {
      supabase = createClient();
    } catch {
      return;
    }
    let cancelled = false;

    supabase.auth.getSession().then(({ data }) => {
      if (cancelled) return;
      setSession(data.session);
      setLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      if (cancelled) return;
      setSession(newSession);
    });

    return () => {
      cancelled = true;
      listener.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    const userId = session.user.id;
    let cancelled = false;
    fetch(`${API_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error("perfil");
        return (await res.json()) as PerfilApi;
      })
      .then((data) => {
        if (!cancelled) setPerfil({ userId, usuario: normalizarPerfil(data) });
      })
      .catch(() => {
        // Sin perfil no se puede afirmar el tenant: la UI no oculta nada y el
        // backend sigue rechazando lo que no corresponda (403 LEGACY_SOLO_TEI).
        if (!cancelled) setPerfil({ userId, usuario: null });
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  // Derivado (no estado): evita setState síncrono en efectos y descarta un
  // perfil que pertenezca a otra sesión (p. ej. tras cerrar sesión).
  const usuario = session && perfil?.userId === session.user.id ? perfil.usuario : null;
  const perfilCargando = !!session && perfil?.userId !== session.user.id;

  async function signIn(email: string, password: string) {
    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) return { error: error.message };
      return { error: null };
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Error al iniciar sesión" };
    }
  }

  async function signOut() {
    try {
      const supabase = createClient();
      await supabase.auth.signOut();
    } finally {
      setSession(null);
      setPerfil(null);
    }
  }

  return (
    <AuthContext.Provider value={{ session, usuario, perfilCargando, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return ctx;
}
