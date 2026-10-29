"use client";

import type { MiViajeNucleo } from "@/types/nucleo";

const COLA_KEY = "tei_conductor_cola_v1";
const ULTIMO_KEY = "tei_conductor_ultimo_viaje_v1";

export interface AccionCola {
  id: string;
  path: string;
  method: "POST" | "PUT";
  body: unknown;
  creadaEn: string;
  etiqueta: string;
}

function leer<T>(clave: string, porDefecto: T): T {
  if (typeof window === "undefined") return porDefecto;
  try {
    const raw = window.localStorage.getItem(clave);
    return raw ? (JSON.parse(raw) as T) : porDefecto;
  } catch {
    return porDefecto;
  }
}

function escribir(clave: string, valor: unknown): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(clave, JSON.stringify(valor));
  } catch {
    /* almacenamiento lleno o bloqueado */
  }
}

export function leerCola(): AccionCola[] {
  return leer<AccionCola[]>(COLA_KEY, []);
}

export function encolar(accion: Omit<AccionCola, "id" | "creadaEn">): AccionCola {
  const item: AccionCola = {
    ...accion,
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    creadaEn: new Date().toISOString(),
  };
  const cola = [...leerCola(), item];
  escribir(COLA_KEY, cola);
  return item;
}

export function quitarDeCola(id: string): void {
  escribir(
    COLA_KEY,
    leerCola().filter((item) => item.id !== id),
  );
}

export function guardarUltimoViaje(data: MiViajeNucleo): void {
  escribir(ULTIMO_KEY, data);
}

export function leerUltimoViaje(): MiViajeNucleo | null {
  return leer<MiViajeNucleo | null>(ULTIMO_KEY, null);
}

export async function replayCola(
  enviar: (accion: AccionCola) => Promise<unknown>,
): Promise<{ enviadas: number; fallidas: number }> {
  const cola = leerCola();
  let enviadas = 0;
  let fallidas = 0;
  for (const accion of cola) {
    try {
      await enviar(accion);
      quitarDeCola(accion.id);
      enviadas += 1;
    } catch {
      fallidas += 1;
    }
  }
  return { enviadas, fallidas };
}
