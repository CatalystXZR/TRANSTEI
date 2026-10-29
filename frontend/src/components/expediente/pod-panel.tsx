"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Eraser,
  FileImage,
  Loader2,
  PenLine,
  RotateCcw,
} from "lucide-react";
import { toast } from "sonner";
import { nucleoUpload } from "@/lib/nucleo";
import { formatFechaHora, toDatetimeLocal } from "@/lib/format";
import type { PODNucleo, ViajeExpedienteNucleo } from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AreaTexto, Campo } from "@/components/formulario";
import { Aviso, Panel, StatusBadge } from "@/components/sistema";

function ahoraLocal(): string {
  return toDatetimeLocal(new Date());
}

export function PODPanel({
  empresaId,
  viaje,
  onCambio,
}: {
  empresaId: string;
  viaje: ViajeExpedienteNucleo;
  onCambio: () => void;
}) {
  const pod = viaje.pod;
  const [editando, setEditando] = useState(!pod);
  const [receptorNombre, setReceptorNombre] = useState(pod?.receptor_nombre ?? "");
  const [receptorRut, setReceptorRut] = useState(pod?.receptor_rut ?? "");
  const [receptorCargo, setReceptorCargo] = useState(pod?.receptor_cargo ?? "");
  const [fechaHora, setFechaHora] = useState(
    pod ? toDatetimeLocal(pod.fecha_hora) : ahoraLocal(),
  );
  const [lat, setLat] = useState(pod?.lat ?? "");
  const [lon, setLon] = useState(pod?.lon ?? "");
  const [danios, setDanios] = useState(pod?.danios ?? "");
  const [observaciones, setObservaciones] = useState(pod?.observaciones ?? "");
  const [firmado, setFirmado] = useState(false);
  const [firmaArchivo, setFirmaArchivo] = useState<File | null>(null);
  const [archivos, setArchivos] = useState<File[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dibujando, setDibujando] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = 640;
    canvas.height = 200;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.lineWidth = 2.4;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#17151f";
    }
  }, [editando]);

  function posicion(evento: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((evento.clientX - rect.left) / rect.width) * canvas.width,
      y: ((evento.clientY - rect.top) / rect.height) * canvas.height,
    };
  }

  function iniciarTrazo(evento: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.setPointerCapture(evento.pointerId);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { x, y } = posicion(evento);
    ctx.beginPath();
    ctx.moveTo(x, y);
    setDibujando(true);
  }

  function trazar(evento: React.PointerEvent<HTMLCanvasElement>) {
    if (!dibujando) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!ctx) return;
    const { x, y } = posicion(evento);
    ctx.lineTo(x, y);
    ctx.stroke();
    setFirmado(true);
  }

  function terminarTrazo() {
    setDibujando(false);
  }

  function limpiarFirma() {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setFirmado(false);
  }

  async function firmaBlob(): Promise<Blob | null> {
    const canvas = canvasRef.current;
    if (!canvas || !firmado) return null;
    return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  }

  async function guardar() {
    if (!receptorNombre.trim()) {
      setError("El nombre del receptor es obligatorio.");
      return;
    }
    const blob = await firmaBlob();
    const archivoFirma = blob ?? firmaArchivo;
    if (!pod && !archivoFirma) {
      setError("Capture o adjunte la firma del receptor antes de guardar el POD.");
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.set("receptor_nombre", receptorNombre.trim());
      if (receptorRut.trim()) formData.set("receptor_rut", receptorRut.trim());
      if (receptorCargo.trim()) formData.set("receptor_cargo", receptorCargo.trim());
      if (fechaHora) formData.set("fecha_hora", new Date(fechaHora).toISOString());
      if (lat.trim()) formData.set("lat", lat.trim());
      if (lon.trim()) formData.set("lon", lon.trim());
      if (danios.trim()) formData.set("danios", danios.trim());
      if (observaciones.trim()) formData.set("observaciones", observaciones.trim());
      if (archivoFirma) {
        formData.append(
          "firma",
          archivoFirma,
          archivoFirma instanceof File ? archivoFirma.name : "firma.png",
        );
      }
      for (const archivo of archivos) {
        formData.append("fotos", archivo, archivo.name);
      }
      if (pod) {
        formData.set("version", String(pod.version));
      }
      await nucleoUpload<PODNucleo>(
        `/nucleo/expediente/viajes/${viaje.id}/pod`,
        empresaId,
        formData,
        pod ? "PUT" : "POST",
      );
      toast.success(pod ? "POD actualizado" : "POD registrado");
      setEditando(false);
      setArchivos([]);
      setFirmaArchivo(null);
      setFirmado(false);
      onCambio();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar el POD");
    } finally {
      setGuardando(false);
    }
  }

  function cancelarEdicion() {
    if (!pod) return;
    setEditando(false);
    setError(null);
  }

  return (
    <div className="space-y-s4">
      {!pod && (
        <Aviso tono="atencion" icono={AlertTriangle}>
          Este viaje no tiene POD. Sin firma y evidencia no se puede facturar.
        </Aviso>
      )}

      {pod && !editando ? (
        <>
          <Panel
            titulo="POD registrado"
            descripcion="Evidencia de entrega firmada por el receptor."
            acciones={
              <div className="flex items-center gap-s2">
                <StatusBadge tono="ok">Facturación habilitada</StatusBadge>
                <Button size="sm" variant="outline" onClick={() => setEditando(true)}>
                  <RotateCcw /> Reemplazar / actualizar
                </Button>
              </div>
            }
          >
            <div className="grid gap-s4 p-s4 sm:grid-cols-2">
              <div className="space-y-s1 text-[14px]">
                <p><span className="text-tinta-3">Receptor:</span> {pod.receptor_nombre}</p>
                <p><span className="text-tinta-3">RUT:</span> {pod.receptor_rut ?? "—"}</p>
                <p><span className="text-tinta-3">Cargo:</span> {pod.receptor_cargo ?? "—"}</p>
                <p><span className="text-tinta-3">Fecha/hora:</span> {formatFechaHora(pod.fecha_hora)}</p>
                <p><span className="text-tinta-3">Ubicación:</span> {pod.lat && pod.lon ? `${pod.lat}, ${pod.lon}` : "No informada"}</p>
                <p><span className="text-tinta-3">Daños:</span> {pod.danios ?? "Sin daños declarados"}</p>
                {pod.observaciones && <p><span className="text-tinta-3">Observaciones:</span> {pod.observaciones}</p>}
              </div>
              <div className="rounded-xl border border-borde bg-white p-s2">
                {pod.firma_url_firmada ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={pod.firma_url_firmada}
                    alt={`Firma de ${pod.receptor_nombre}`}
                    className="h-40 w-full object-contain"
                  />
                ) : (
                  <p className="p-s3 text-[14px] text-tinta-3">Firma no disponible.</p>
                )}
              </div>
            </div>
            <div className="border-t border-borde p-s4">
              <p className="mb-s2 flex items-center gap-2 text-[14px] font-medium">
                <Camera className="size-4" /> Fotos de evidencia ({pod.fotos.length})
              </p>
              {pod.fotos.length === 0 ? (
                <p className="text-[14px] text-tinta-3">Sin fotos adjuntas.</p>
              ) : (
                <div className="grid gap-s3 sm:grid-cols-2 lg:grid-cols-3">
                  {pod.fotos.map((foto) => (
                    <a
                      key={foto.path}
                      href={foto.url_firmada ?? "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-s2 rounded-lg border border-borde p-s2 text-[14px] hover:border-borde-fuerte"
                    >
                      <FileImage className="size-5 text-marca" />
                      <span className="truncate">{foto.nombre ?? "Evidencia"}</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          </Panel>
        </>
      ) : (
        <Panel
          titulo={pod ? "Actualizar POD" : "Registrar POD"}
          descripcion="Firma del receptor, fotos, RUT, geolocalización y daños. Queda auditado."
          acciones={
            pod ? (
              <Button variant="outline" size="sm" onClick={cancelarEdicion} disabled={guardando}>
                Cancelar
              </Button>
            ) : undefined
          }
        >
          {error && (
            <div className="p-s4 pb-0">
              <Aviso tono="critico" icono={AlertTriangle}>{error}</Aviso>
            </div>
          )}
          <div className="grid gap-s3 p-s4 sm:grid-cols-2">
            <Campo etiqueta="Nombre del receptor" requerido>
              <Input value={receptorNombre} onChange={(e) => setReceptorNombre(e.target.value)} />
            </Campo>
            <Campo etiqueta="RUT del receptor">
              <Input value={receptorRut} onChange={(e) => setReceptorRut(e.target.value)} placeholder="12.345.678-9" />
            </Campo>
            <Campo etiqueta="Cargo">
              <Input value={receptorCargo} onChange={(e) => setReceptorCargo(e.target.value)} />
            </Campo>
            <Campo etiqueta="Fecha y hora de entrega" requerido>
              <Input type="datetime-local" value={fechaHora} onChange={(e) => setFechaHora(e.target.value)} />
            </Campo>
            <Campo etiqueta="Latitud" ayuda="Opcional; se puede capturar desde la PWA">
              <Input type="number" step="0.000001" value={lat} onChange={(e) => setLat(e.target.value)} />
            </Campo>
            <Campo etiqueta="Longitud">
              <Input type="number" step="0.000001" value={lon} onChange={(e) => setLon(e.target.value)} />
            </Campo>
            <Campo etiqueta="Daños observados" className="sm:col-span-2">
              <AreaTexto rows={2} value={danios} onChange={(e) => setDanios(e.target.value)} />
            </Campo>
            <Campo etiqueta="Observaciones" className="sm:col-span-2">
              <AreaTexto rows={2} value={observaciones} onChange={(e) => setObservaciones(e.target.value)} />
            </Campo>
          </div>

          <div className="space-y-s2 border-t border-borde p-s4">
            <div className="flex flex-wrap items-center justify-between gap-s2">
              <p className="flex items-center gap-2 text-[15px] font-medium">
                <PenLine className="size-4" /> Firma del receptor {pod ? "(opcional para reemplazar)" : ""}
              </p>
              <Button size="sm" variant="outline" onClick={limpiarFirma} type="button">
                <Eraser /> Limpiar
              </Button>
            </div>
            <canvas
              ref={canvasRef}
              onPointerDown={iniciarTrazo}
              onPointerMove={trazar}
              onPointerUp={terminarTrazo}
              onPointerLeave={terminarTrazo}
              className="h-44 w-full cursor-crosshair touch-none rounded-xl border-2 border-dashed border-borde-fuerte bg-white"
              aria-label="Área de firma"
            />
            <p className="text-[13px] text-tinta-3">
              {firmado
                ? "Firma capturada."
                : pod
                  ? "No se reemplazará la firma actual."
                  : "Dibuje la firma con el mouse o el dedo, o adjunte una imagen."}
            </p>
            <div className="pt-s1">
              <p className="mb-s1 text-[13px] font-medium text-tinta-2">O adjunte la firma escaneada</p>
              <input
                type="file"
                accept=".png,.jpg,.jpeg,.webp"
                aria-label="Firma escaneada"
                onChange={(e) => setFirmaArchivo(e.target.files?.[0] ?? null)}
                className="block w-full text-[14px]"
              />
              {firmaArchivo && (
                <p className="mt-s1 text-[13px] text-tinta-3">{firmaArchivo.name}</p>
              )}
            </div>
          </div>

          <div className="space-y-s2 border-t border-borde p-s4">
            <p className="flex items-center gap-2 text-[15px] font-medium">
              <Camera className="size-4" /> Fotos de evidencia
            </p>
            <input
              type="file"
              multiple
              aria-label="Fotos de evidencia"
              accept=".pdf,.jpg,.jpeg,.png,.webp,.heic"
              onChange={(e) => setArchivos(Array.from(e.target.files ?? []))}
              className="block w-full text-[14px]"
            />
            {archivos.length > 0 && (
              <p className="text-[13px] text-tinta-3">{archivos.length} archivo(s) seleccionado(s).</p>
            )}
          </div>

          <div className="flex justify-end gap-s2 border-t border-borde p-s4">
            <Button onClick={() => void guardar()} disabled={guardando}>
              {guardando ? (
                <>
                  <Loader2 className="animate-spin" /> Guardando…
                </>
              ) : (
                <>
                  <CheckCircle2 /> {pod ? "Guardar nueva versión" : "Registrar POD"}
                </>
              )}
            </Button>
          </div>
        </Panel>
      )}
    </div>
  );
}
