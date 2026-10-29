"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ChevronRight,
  Cloud,
  CloudOff,
  FileText,
  Loader2,
  LogOut,
  MapPin,
  Phone,
  Plus,
  RefreshCw,
  ShieldAlert,
  Truck,
  WifiOff,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/auth-context";
import { getEmpresas, nucleo, nucleoFetch, nucleoUpload } from "@/lib/nucleo";
import { formatCLP, formatFecha, formatFechaHora } from "@/lib/format";
import {
  encolar,
  guardarUltimoViaje,
  leerCola,
  leerUltimoViaje,
  replayCola,
} from "@/lib/offline-queue";
import type {
  ChecklistItemNucleo,
  EmpresaNucleo,
  EstadoViajeNucleo,
  MiViajeNucleo,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AreaTexto, Campo, SelectSimple } from "@/components/formulario";
import { StatusBadge } from "@/components/sistema";
import { PODPanel } from "@/components/expediente/pod-panel";
import { cn } from "cn";

const PASOS: EstadoViajeNucleo[] = [
  "asignado",
  "en_carga",
  "cargado",
  "en_ruta",
  "en_descarga",
  "descargado",
  "pod_pendiente",
];

const SIGUIENTE: Partial<Record<EstadoViajeNucleo, string>> = {
  asignado: "Llegué al origen / iniciar carga",
  en_carga: "Carga completada",
  cargado: "Iniciar ruta",
  en_ruta: "Llegué al destino / iniciar descarga",
  en_descarga: "Descarga completada",
  descargado: "Registrar POD",
  pod_pendiente: "Esperando cierre del despacho",
};

const DESTINO: Partial<Record<EstadoViajeNucleo, EstadoViajeNucleo>> = {
  asignado: "en_carga",
  en_carga: "cargado",
  cargado: "en_ruta",
  en_ruta: "en_descarga",
  en_descarga: "descargado",
  descargado: "pod_pendiente",
};

function ubicacion(): Promise<{ lat?: number; lon?: number }> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      resolve({});
      return;
    }
    const timer = window.setTimeout(() => resolve({}), 5000);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        window.clearTimeout(timer);
        resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude });
      },
      () => {
        window.clearTimeout(timer);
        resolve({});
      },
      { enableHighAccuracy: true, timeout: 4500, maximumAge: 60000 },
    );
  });
}

export default function ConductorPage() {
  const { session, loading: cargandoSesion, signOut } = useAuth();
  const router = useRouter();
  const [empresaId, setEmpresaId] = useState("");
  const [empresa, setEmpresa] = useState<EmpresaNucleo | null>(null);
  const [data, setData] = useState<MiViajeNucleo | null>(() => leerUltimoViaje());
  const [cargando, setCargando] = useState(true);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [cola, setCola] = useState(0);
  const [procesando, setProcesando] = useState(false);
  const [mostrarIncidente, setMostrarIncidente] = useState(false);
  const [nuevoIncidente, setNuevoIncidente] = useState({
    tipo: "novedad",
    severidad: "media",
    descripcion: "",
  });
  const [mostrarGasto, setMostrarGasto] = useState(false);
  const [nuevoGasto, setNuevoGasto] = useState({
    tipo: "combustible",
    monto_total: "",
    iva: "0",
    litros: "",
    precio_litro: "",
    km_odometro: "",
    proveedor: "",
  });

  useEffect(() => {
    if (!cargandoSesion && !session) {
      router.replace("/login?next=%2Fconductor");
    }
  }, [cargandoSesion, session, router]);

  useEffect(() => {
    const t = setTimeout(() => {
      setOffline(!navigator.onLine);
      setCola(leerCola().length);
    }, 0);
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      clearTimeout(t);
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);

  useEffect(() => {
    if (!session || typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      return;
    }
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* el navegador puede bloquear el SW; la app sigue funcionando */
    });
  }, [session]);

  useEffect(() => {
    if (!session) return;
    let activo = true;
    getEmpresas()
      .then((empresas) => {
        if (!activo) return;
        if (empresas[0]) {
          setEmpresa(empresas[0]);
          setEmpresaId(empresas[0].id);
        } else {
          setError("Su usuario no tiene una empresa activa asignada.");
          setCargando(false);
        }
      })
      .catch((e) => {
        if (!activo) return;
        setError(e instanceof Error ? e.message : "No se pudieron cargar las empresas");
        setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [session]);

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!empresaId) return;
      if (silencioso) setActualizando(true);
      else setCargando(true);
      setError(null);
      try {
        const respuesta = await nucleo.get<MiViajeNucleo>(
          "/nucleo/conductor/mi-viaje",
          empresaId,
        );
        setData(respuesta);
        guardarUltimoViaje(respuesta);
      } catch (e) {
        if (typeof navigator !== "undefined" && !navigator.onLine) {
          const ultimo = leerUltimoViaje();
          if (ultimo) setData(ultimo);
          setOffline(true);
        } else {
          setError(e instanceof Error ? e.message : "No se pudo cargar su viaje");
        }
      } finally {
        setCargando(false);
        setActualizando(false);
      }
    },
    [empresaId],
  );

  useEffect(() => {
    const t = setTimeout(() => {
      void cargar();
    }, 0);
    return () => clearTimeout(t);
  }, [cargar]);

  const sincronizar = useCallback(async () => {
    if (!empresaId || typeof navigator === "undefined" || !navigator.onLine) return;
    if (leerCola().length === 0) return;
    const resultado = await replayCola((accion) =>
      nucleoFetch(
        accion.path,
        {
          method: accion.method,
          body: JSON.stringify(accion.body),
        },
        empresaId,
      ),
    );
    setCola(leerCola().length);
    if (resultado.enviadas > 0) {
      toast.success(`${resultado.enviadas} acción(es) sincronizada(s)`);
      await cargar(true);
    }
    if (resultado.fallidas > 0) {
      toast.error(`${resultado.fallidas} acción(es) no se pudieron sincronizar`);
    }
  }, [empresaId, cargar]);

  useEffect(() => {
    if (!empresaId) return;
    const t = setTimeout(() => {
      void sincronizar();
    }, 0);
    const on = () => {
      setOffline(false);
      void sincronizar();
    };
    window.addEventListener("online", on);
    return () => {
      clearTimeout(t);
      window.removeEventListener("online", on);
    };
  }, [empresaId, sincronizar]);

  function actualizarEstadoLocal(destino: EstadoViajeNucleo) {
    setData((prev) => {
      if (!prev?.viaje) return prev;
      const actualizado: MiViajeNucleo = {
        ...prev,
        viaje: { ...prev.viaje, estado: destino },
        siguiente_accion: SIGUIENTE[destino] ?? null,
        acciones_disponibles: DESTINO[destino] ? [DESTINO[destino] as string] : [],
      };
      guardarUltimoViaje(actualizado);
      return actualizado;
    });
  }

  async function enviarAccion(
    path: string,
    method: "POST" | "PUT",
    body: unknown,
    etiqueta: string,
    destino?: EstadoViajeNucleo,
  ) {
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      encolar({ path, method, body, etiqueta });
      setCola(leerCola().length);
      if (destino) actualizarEstadoLocal(destino);
      toast.info("Sin conexión: acción guardada para sincronizar.");
      return false;
    }
    try {
      await nucleoFetch(path, { method, body: JSON.stringify(body) }, empresaId);
      toast.success(etiqueta);
      await cargar(true);
      return true;
    } catch (e) {
      if (e instanceof TypeError) {
        encolar({ path, method, body, etiqueta });
        setCola(leerCola().length);
        if (destino) actualizarEstadoLocal(destino);
        toast.info("Sin conexión: acción guardada para sincronizar.");
        return false;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo completar la acción");
      return false;
    }
  }

  async function avanzar() {
    if (!data?.viaje || procesando) return;
    const viaje = data.viaje;
    const estado = viaje.estado;
    const destino = DESTINO[estado];
    if (!destino) {
      toast.info("No hay una acción disponible para este estado.");
      return;
    }
    setProcesando(true);
    try {
      const pos = await ubicacion();
      if (estado === "asignado") {
        await enviarAccion(
          `/nucleo/conductor/viajes/${viaje.id}/check-in`,
          "POST",
          { ...pos, nota: "Check-in desde PWA" },
          "Check-in registrado",
          destino,
        );
      } else if (estado === "en_descarga") {
        await enviarAccion(
          `/nucleo/conductor/viajes/${viaje.id}/check-out`,
          "POST",
          { ...pos, nota: "Check-out desde PWA" },
          "Check-out registrado",
          destino,
        );
      } else {
        await enviarAccion(
          `/nucleo/conductor/viajes/${viaje.id}/transicion`,
          "POST",
          { estado_destino: destino, ...pos },
          `Viaje en ${destino.replaceAll("_", " ")}`,
          destino,
        );
      }
    } finally {
      setProcesando(false);
    }
  }

  function toggleChecklist(item: ChecklistItemNucleo) {
    if (!data?.viaje) return;
    const nuevo = !item.completado;
    setData((prev) => {
      if (!prev?.viaje) return prev;
      const actualizado: MiViajeNucleo = {
        ...prev,
        viaje: {
          ...prev.viaje,
          checklist: prev.viaje.checklist.map((i) =>
            i.id === item.id ? { ...i, completado: nuevo } : i,
          ),
        },
      };
      guardarUltimoViaje(actualizado);
      return actualizado;
    });
    void enviarAccion(
      `/nucleo/expediente/viajes/${data.viaje.id}/checklist/${item.id}`,
      "PUT",
      {
        completado: nuevo,
        notas: item.notas,
        evidencia_url: item.evidencia_url,
        version: item.version,
      },
      nuevo ? "Ítem completado" : "Ítem reabierto",
    );
  }

  function reportarIncidente() {
    if (!data?.viaje || !nuevoIncidente.descripcion.trim()) return;
    void enviarAccion(
      `/nucleo/expediente/viajes/${data.viaje.id}/incidentes`,
      "POST",
      {
        tipo: nuevoIncidente.tipo,
        severidad: nuevoIncidente.severidad,
        descripcion: nuevoIncidente.descripcion.trim(),
      },
      "Incidente reportado",
    ).then(() => {
      setNuevoIncidente({ tipo: "novedad", severidad: "media", descripcion: "" });
      setMostrarIncidente(false);
    });
  }

  function registrarGasto() {
    if (!data?.viaje) return;
    const iva = Number(nuevoGasto.iva || 0);
    const total =
      nuevoGasto.tipo === "combustible" && nuevoGasto.litros && nuevoGasto.precio_litro
        ? Number(nuevoGasto.litros) * Number(nuevoGasto.precio_litro) + iva
        : Number(nuevoGasto.monto_total || 0);
    if (total <= 0) return;
    void enviarAccion(
      `/nucleo/expediente/viajes/${data.viaje.id}/gastos`,
      "POST",
      {
        tipo: nuevoGasto.tipo,
        fecha: new Date().toISOString().slice(0, 10),
        monto_total: total,
        iva,
        moneda: data.viaje.moneda,
        litros: nuevoGasto.litros ? Number(nuevoGasto.litros) : null,
        precio_litro: nuevoGasto.precio_litro ? Number(nuevoGasto.precio_litro) : null,
        km_odometro: nuevoGasto.km_odometro ? Number(nuevoGasto.km_odometro) : null,
        proveedor: nuevoGasto.proveedor.trim() || null,
      },
      "Gasto registrado; queda pendiente de aprobación",
    ).then(() => {
      setNuevoGasto({
        tipo: "combustible",
        monto_total: "",
        iva: "0",
        litros: "",
        precio_litro: "",
        km_odometro: "",
        proveedor: "",
      });
      setMostrarGasto(false);
    });
  }

  async function subirFoto(file: File) {
    if (!data?.viaje) return;
    if (!navigator.onLine) {
      toast.error("Las fotos requieren conexión. Se pueden adjuntar al recuperar señal.");
      return;
    }
    const formData = new FormData();
    formData.set("tipo", "evidencia_conductor");
    formData.set("archivo", file);
    try {
      await nucleoUpload(
        `/nucleo/expediente/viajes/${data.viaje.id}/documentos`,
        empresaId,
        formData,
      );
      toast.success("Foto adjuntada al expediente");
      await cargar(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo subir la foto");
    }
  }

  const viaje = data?.viaje;
  const indicePaso = viaje ? PASOS.indexOf(viaje.estado) : -1;
  const puedePOD =
    viaje && ["descargado", "pod_pendiente"].includes(viaje.estado) && !viaje.pod;
  const accionesPendientes = cola > 0;

  const checklistPendientes = useMemo(
    () => viaje?.checklist.filter((i) => i.requerido && !i.completado).length ?? 0,
    [viaje],
  );

  if (cargandoSesion) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-fondo">
        <Loader2 className="size-6 animate-spin text-marca" />
      </div>
    );
  }
  if (!session) return null;

  return (
    <div className="min-h-screen bg-fondo pb-10">
      <header className="sticky top-0 z-20 border-b border-borde bg-sidebar px-s4 py-s3 text-white shadow-elev-1">
        <div className="mx-auto flex max-w-lg items-center justify-between gap-s3">
          <div className="flex items-center gap-s2">
            <span className="grid size-9 place-items-center rounded-lg bg-white font-heading text-[13px] font-extrabold text-marca">
              TEI
            </span>
            <div>
              <p className="text-[13px] font-semibold">Conductor</p>
              <p className="text-[12px] text-white/60">{data?.chofer.nombre ?? "Cargando…"}</p>
            </div>
          </div>
          <div className="flex items-center gap-s2">
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-1 text-[12px] font-medium",
                offline ? "bg-critico/20 text-white" : "bg-ok/20 text-white",
              )}
            >
              {offline ? <WifiOff className="size-3" /> : <Cloud className="size-3" />}
              {offline ? "Offline" : "Online"}
            </span>
            {accionesPendientes && (
              <span className="rounded-full bg-senal px-2 py-1 text-[12px] font-semibold text-tinta">
                {cola} pendiente(s)
              </span>
            )}
            <button
              type="button"
              onClick={() => void signOut()}
              className="rounded-lg p-2 text-white/70 hover:bg-white/10"
              aria-label="Cerrar sesión"
            >
              <LogOut className="size-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-lg space-y-s4 px-s4 pt-s4">
        {error && (
          <div className="flex items-start gap-s2 rounded-xl border border-critico/20 bg-critico-tenue p-s3 text-[14px] text-critico">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {offline && (
          <div className="flex items-start gap-s2 rounded-xl border border-atencion/25 bg-atencion-tenue p-s3 text-[14px] text-atencion">
            <CloudOff className="mt-0.5 size-4 shrink-0" />
            <span>
              Sin conexión. Puede revisar su viaje y las acciones se guardarán para
              sincronizar cuando vuelva la señal.
            </span>
          </div>
        )}

        {cargando && !viaje ? (
          <div className="space-y-s3">
            <div className="h-32 animate-pulse rounded-xl bg-superficie-hundida" />
            <div className="h-48 animate-pulse rounded-xl bg-superficie-hundida" />
          </div>
        ) : !viaje ? (
          <section className="rounded-2xl border border-borde bg-superficie p-s5 text-center shadow-elev-1">
            <span className="mx-auto grid size-14 place-items-center rounded-xl bg-superficie-hundida text-tinta-3">
              <Truck className="size-6" />
            </span>
            <h1 className="mt-s3 text-[22px] font-semibold">Sin viaje activo</h1>
            <p className="mt-s2 text-[15px] text-tinta-3">
              {data?.mensaje ?? "No tiene viajes asignados en este momento."}
            </p>
            <Button className="mt-s4 w-full" onClick={() => void cargar()} disabled={actualizando}>
              <RefreshCw className={actualizando ? "animate-spin" : undefined} /> Actualizar
            </Button>
          </section>
        ) : (
          <>
            <section className="overflow-hidden rounded-2xl border border-borde bg-superficie shadow-elev-1">
              <div className="bg-marca px-s4 py-s3 text-white">
                <div className="flex items-start justify-between gap-s3">
                  <div>
                    <p className="font-mono text-[13px] font-semibold text-white/70">
                      {viaje.numero_viaje}
                    </p>
                    <h1 className="mt-1 text-[21px] leading-tight font-semibold">
                      {viaje.origen_nombre} <ChevronRight className="inline size-4" />{" "}
                      {viaje.destino_nombre}
                    </h1>
                    <p className="text-[13px] text-white/70">{viaje.cliente_nombre}</p>
                  </div>
                  <StatusBadge tono="info" className="!bg-white/15 !text-white">
                    {viaje.estado.replaceAll("_", " ")}
                  </StatusBadge>
                </div>
                <div className="mt-s3 flex items-center gap-1">
                  {PASOS.map((paso, indice) => (
                    <span
                      key={paso}
                      className={cn(
                        "h-1.5 flex-1 rounded-full",
                        indice <= indicePaso ? "bg-senal" : "bg-white/20",
                      )}
                    />
                  ))}
                </div>
              </div>

              <div className="grid gap-s2 p-s4 text-[14px] sm:grid-cols-2">
                <p className="flex items-center gap-2">
                  <MapPin className="size-4 text-tinta-3" /> {viaje.origen_nombre}
                </p>
                <p className="flex items-center gap-2">
                  <MapPin className="size-4 text-critico" /> {viaje.destino_nombre}
                </p>
                <p className="text-tinta-3">{formatFechaHora(viaje.inicio_planificado)}</p>
                <p className="text-tinta-3">{formatFechaHora(viaje.fin_planificado)}</p>
                <p>
                  <span className="text-tinta-3">Carga:</span>{" "}
                  {viaje.peso_bruto_kg
                    ? `${Number(viaje.peso_bruto_kg).toLocaleString("es-CL")} kg`
                    : "—"}
                </p>
                <p>
                  <span className="text-tinta-3">Flete:</span>{" "}
                  {formatCLP(viaje.monto_total_neto ?? viaje.valor_flete_neto)}
                </p>
              </div>

              <div className="border-t border-borde p-s4">
                <Button
                  className="w-full"
                  size="lg"
                  onClick={() => void avanzar()}
                  disabled={procesando || !DESTINO[viaje.estado]}
                >
                  {procesando ? (
                    <>
                      <Loader2 className="animate-spin" /> Registrando…
                    </>
                  ) : (
                    <>
                      <CheckCircle2 /> {SIGUIENTE[viaje.estado] ?? "Sin acción"}
                    </>
                  )}
                </Button>
                {accionesPendientes && (
                  <p className="mt-s2 text-center text-[13px] text-atencion">
                    Hay acciones sin sincronizar. Se enviarán al recuperar señal.
                  </p>
                )}
              </div>
            </section>

            <section className="rounded-2xl border border-borde bg-superficie p-s4 shadow-elev-1">
              <div className="flex items-center justify-between gap-s3">
                <div>
                  <h2 className="text-[17px] font-semibold">Checklist</h2>
                  <p className="text-[13px] text-tinta-3">
                    {checklistPendientes} obligatorio(s) pendiente(s)
                  </p>
                </div>
                <StatusBadge tono={checklistPendientes ? "atencion" : "ok"}>
                  {viaje.checklist.filter((i) => i.completado).length}/{viaje.checklist.length}
                </StatusBadge>
              </div>
              <div className="mt-s3 divide-y divide-borde">
                {viaje.checklist.map((item) => (
                  <label
                    key={item.id}
                    className="flex cursor-pointer items-start gap-s3 py-s3"
                  >
                    <input
                      type="checkbox"
                      className="mt-1 size-5 accent-marca"
                      checked={item.completado}
                      onChange={() => toggleChecklist(item)}
                    />
                    <span className="min-w-0">
                      <span className={cn("block text-[15px] font-medium", item.completado && "text-tinta-3 line-through")}>
                        {item.item}
                      </span>
                      <span className="text-[12px] text-tinta-3">
                        {item.requerido ? "Obligatorio" : "Opcional"} · {item.categoria}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </section>

            <section className="grid grid-cols-2 gap-s3">
              <button
                type="button"
                onClick={() => setMostrarIncidente((v) => !v)}
                className="flex items-center justify-center gap-s2 rounded-xl border border-borde bg-superficie p-s3 text-[14px] font-medium shadow-elev-1"
              >
                <ShieldAlert className="size-4 text-critico" /> Incidente
              </button>
              <label className="flex cursor-pointer items-center justify-center gap-s2 rounded-xl border border-borde bg-superficie p-s3 text-[14px] font-medium shadow-elev-1">
                <Camera className="size-4 text-marca" /> Foto
                <input
                  type="file"
                  accept=".jpg,.jpeg,.png,.webp,.heic"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void subirFoto(file);
                    e.target.value = "";
                  }}
                />
              </label>
            </section>

            {mostrarIncidente && (
              <section className="space-y-s3 rounded-2xl border border-borde bg-superficie p-s4 shadow-elev-1">
                <h2 className="text-[17px] font-semibold">Reportar incidente</h2>
                <Campo etiqueta="Tipo">
                  <Input
                    value={nuevoIncidente.tipo}
                    onChange={(e) =>
                      setNuevoIncidente((i) => ({ ...i, tipo: e.target.value }))
                    }
                    placeholder="avería, demora, daño, otro"
                  />
                </Campo>
                <Campo etiqueta="Severidad">
                  <SelectSimple
                    valor={nuevoIncidente.severidad}
                    onCambio={(v) => setNuevoIncidente((i) => ({ ...i, severidad: v }))}
                    opciones={[
                      { valor: "baja", etiqueta: "Baja" },
                      { valor: "media", etiqueta: "Media" },
                      { valor: "alta", etiqueta: "Alta" },
                      { valor: "critica", etiqueta: "Crítica" },
                    ]}
                  />
                </Campo>
                <Campo etiqueta="Descripción" requerido>
                  <AreaTexto
                    rows={3}
                    value={nuevoIncidente.descripcion}
                    onChange={(e) =>
                      setNuevoIncidente((i) => ({ ...i, descripcion: e.target.value }))
                    }
                  />
                </Campo>
                <Button
                  className="w-full"
                  onClick={reportarIncidente}
                  disabled={!nuevoIncidente.descripcion.trim()}
                >
                  <Plus /> Reportar
                </Button>
              </section>
            )}

            {puedePOD && (
              <section>
                <h2 className="mb-s3 text-[18px] font-semibold">Prueba de entrega</h2>
                <PODPanel
                  empresaId={empresaId}
                  viaje={viaje}
                  onCambio={() => void cargar(true)}
                />
              </section>
            )}

            {viaje.pod && (
              <section className="rounded-2xl border border-ok/30 bg-ok-tenue p-s4">
                <p className="flex items-center gap-2 text-[15px] font-semibold text-ok">
                  <CheckCircle2 className="size-5" /> POD registrado
                </p>
                <p className="mt-s1 text-[14px] text-ok/80">
                  Receptor: {viaje.pod.receptor_nombre} ·{" "}
                  {formatFechaHora(viaje.pod.fecha_hora)}
                </p>
              </section>
            )}

            <section className="rounded-2xl border border-borde bg-superficie p-s4 text-[14px] text-tinta-2 shadow-elev-1">
              <h2 className="text-[16px] font-semibold">Contactos e instrucciones</h2>
              <p className="mt-s2 flex items-center gap-2">
                <Phone className="size-4 text-tinta-3" /> {viaje.cliente_nombre} ·{" "}
                {viaje.cliente_rut ?? "sin RUT"}
              </p>
              {viaje.instrucciones_especiales && (
                <p className="mt-s1 whitespace-pre-line text-tinta-3">
                  {viaje.instrucciones_especiales}
                </p>
              )}
              <Link
                href={`/expediente/${viaje.id}`}
                className="mt-s3 inline-flex items-center gap-2 font-medium text-marca hover:underline"
              >
                <FileText className="size-4" /> Ver expediente completo
              </Link>
            </section>

            <section className="rounded-2xl border border-borde bg-superficie p-s4 shadow-elev-1">
              <div className="flex items-center justify-between gap-s3">
                <div>
                  <h2 className="text-[17px] font-semibold">Gastos del viaje</h2>
                  <p className="text-[13px] text-tinta-3">
                    {viaje.gastos.length} registrado(s) ·{" "}
                    {viaje.costos ? `costo real ${formatCLP(viaje.costos.costo_variable)}` : "sin costo calculado"}
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={() => setMostrarGasto((v) => !v)}>
                  <Plus /> Gasto
                </Button>
              </div>

              {mostrarGasto && (
                <div className="mt-s3 space-y-s3 rounded-xl border border-borde bg-superficie-hundida/40 p-s3">
                  <Campo etiqueta="Tipo">
                    <SelectSimple
                      valor={nuevoGasto.tipo}
                      onCambio={(v) => setNuevoGasto((g) => ({ ...g, tipo: v }))}
                      opciones={[
                        { valor: "combustible", etiqueta: "Combustible" },
                        { valor: "peaje", etiqueta: "Peaje / TAG" },
                        { valor: "estadia", etiqueta: "Estadía" },
                        { valor: "viatico", etiqueta: "Viático" },
                        { valor: "otro", etiqueta: "Otro" },
                      ]}
                    />
                  </Campo>
                  {nuevoGasto.tipo === "combustible" ? (
                    <div className="grid grid-cols-2 gap-s3">
                      <Campo etiqueta="Litros" requerido>
                        <Input
                          type="number"
                          min={0}
                          step="0.001"
                          value={nuevoGasto.litros}
                          onChange={(e) => setNuevoGasto((g) => ({ ...g, litros: e.target.value }))}
                        />
                      </Campo>
                      <Campo etiqueta="Precio/L">
                        <Input
                          type="number"
                          min={0}
                          step="0.0001"
                          value={nuevoGasto.precio_litro}
                          onChange={(e) =>
                            setNuevoGasto((g) => ({ ...g, precio_litro: e.target.value }))
                          }
                        />
                      </Campo>
                      <Campo etiqueta="Km odómetro">
                        <Input
                          type="number"
                          min={0}
                          step="0.1"
                          value={nuevoGasto.km_odometro}
                          onChange={(e) =>
                            setNuevoGasto((g) => ({ ...g, km_odometro: e.target.value }))
                          }
                        />
                      </Campo>
                      <Campo etiqueta="Proveedor">
                        <Input
                          value={nuevoGasto.proveedor}
                          onChange={(e) =>
                            setNuevoGasto((g) => ({ ...g, proveedor: e.target.value }))
                          }
                        />
                      </Campo>
                    </div>
                  ) : (
                    <Campo etiqueta="Monto total" requerido>
                      <Input
                        type="number"
                        min={0}
                        step="0.01"
                        value={nuevoGasto.monto_total}
                        onChange={(e) =>
                          setNuevoGasto((g) => ({ ...g, monto_total: e.target.value }))
                        }
                      />
                    </Campo>
                  )}
                  <Button
                    className="w-full"
                    onClick={registrarGasto}
                    disabled={
                      procesando ||
                      (nuevoGasto.tipo === "combustible"
                        ? !nuevoGasto.litros || !nuevoGasto.precio_litro
                        : Number(nuevoGasto.monto_total) <= 0)
                    }
                  >
                    <Plus /> Registrar gasto
                  </Button>
                </div>
              )}

              <div className="mt-s3 divide-y divide-borde">
                {viaje.gastos.length === 0 ? (
                  <p className="py-s3 text-[14px] text-tinta-3">Sin gastos registrados.</p>
                ) : (
                  viaje.gastos.map((gasto) => (
                    <div key={gasto.id} className="flex items-center justify-between gap-s3 py-s2">
                      <div>
                        <p className="text-[14px] font-medium capitalize">{gasto.tipo}</p>
                        <p className="text-[12px] text-tinta-3">
                          {formatFecha(gasto.fecha)} · {gasto.proveedor ?? "sin proveedor"}
                          {gasto.litros ? ` · ${Number(gasto.litros).toLocaleString("es-CL")} L` : ""}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-[14px] font-semibold">{formatCLP(gasto.monto_total)}</p>
                        <StatusBadge tono={gasto.estado === "aprobado" ? "ok" : gasto.estado === "rechazado" ? "critico" : "atencion"}>
                          {gasto.estado}
                        </StatusBadge>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>
          </>
        )}

        <footer className="pt-s3 text-center text-[12px] text-tinta-3">
          {empresa?.razon_social} · PWA del conductor · v1
        </footer>
      </main>
    </div>
  );
}
