"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, FileText, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import { nucleo, nucleoUpload } from "@/lib/nucleo";
import type {
  DocumentoArchivoNucleo,
  DocumentoUrlNucleo,
  TipoRecurso,
} from "@/types/nucleo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Campo, SelectSimple } from "@/components/formulario";
import {
  Aviso,
  EstadoVacio,
  StatusBadge,
  Vencimiento,
} from "@/components/sistema";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const TIPOS_DOCUMENTO = [
  { valor: "revision_tecnica", etiqueta: "Revisión técnica" },
  { valor: "permiso_circulacion", etiqueta: "Permiso de circulación" },
  { valor: "seguro_obligatorio", etiqueta: "Seguro obligatorio" },
  { valor: "soap", etiqueta: "SOAP" },
  { valor: "seguro_carga", etiqueta: "Seguro de carga" },
  { valor: "tachografo", etiqueta: "Tacógrafo" },
  { valor: "limitador_velocidad", etiqueta: "Limitador de velocidad" },
  { valor: "certificado_gases", etiqueta: "Certificado de gases" },
  { valor: "permiso_carga_peligrosa", etiqueta: "Permiso carga peligrosa" },
  { valor: "licencia_conducir", etiqueta: "Licencia de conducir" },
  { valor: "examen_medico", etiqueta: "Examen médico" },
  { valor: "curso_carga_peligrosa", etiqueta: "Curso carga peligrosa" },
  { valor: "curso_manejo_defensivo", etiqueta: "Curso manejo defensivo" },
  { valor: "contrato_laboral", etiqueta: "Contrato laboral" },
  { valor: "otro", etiqueta: "Otro" },
];

function fechaISO(dias: number): string {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

export function DocumentosDialog({
  empresaId,
  recursoTipo,
  recursoId,
  etiqueta,
  onClose,
}: {
  empresaId: string;
  recursoTipo: TipoRecurso;
  recursoId: string;
  etiqueta: string;
  onClose: () => void;
}) {
  const [documentos, setDocumentos] = useState<DocumentoArchivoNucleo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tipo, setTipo] = useState(
    recursoTipo === "chofer" ? "licencia_conducir" : "revision_tecnica",
  );
  const [numero, setNumero] = useState("");
  const [entidad, setEntidad] = useState("");
  const [emitido, setEmitido] = useState("");
  const [vence, setVence] = useState(fechaISO(365));
  const [observaciones, setObservaciones] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);

  useEffect(() => {
    let activo = true;
    nucleo
      .get<DocumentoArchivoNucleo[]>(
        `/nucleo/documentos?recurso_tipo=${recursoTipo}&recurso_id=${recursoId}`,
        empresaId,
      )
      .then((data) => {
        if (activo) setDocumentos(data);
      })
      .catch((e) => {
        if (activo) setError(e instanceof Error ? e.message : "Error al cargar documentos");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [empresaId, recursoTipo, recursoId]);

  async function recargar() {
    const data = await nucleo.get<DocumentoArchivoNucleo[]>(
      `/nucleo/documentos?recurso_tipo=${recursoTipo}&recurso_id=${recursoId}`,
      empresaId,
    );
    setDocumentos(data);
  }

  async function subir() {
    if (!archivo) {
      setError("Seleccione un archivo.");
      return;
    }
    setSubiendo(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("recurso_tipo", recursoTipo);
      fd.append("recurso_id", recursoId);
      fd.append("tipo", tipo);
      fd.append("vence_en", vence);
      if (numero.trim()) fd.append("numero", numero.trim());
      if (entidad.trim()) fd.append("entidad_emisora", entidad.trim());
      if (emitido) fd.append("emitido_en", emitido);
      if (observaciones.trim()) fd.append("observaciones", observaciones.trim());
      fd.append("archivo", archivo);
      await nucleoUpload<DocumentoArchivoNucleo>("/nucleo/documentos", empresaId, fd);
      toast.success("Documento cargado; la versión anterior quedó como histórica");
      setArchivo(null);
      setFileKey((k) => k + 1);
      setNumero("");
      setEntidad("");
      setObservaciones("");
      await recargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo subir el documento");
    } finally {
      setSubiendo(false);
    }
  }

  async function ver(documento: DocumentoArchivoNucleo) {
    try {
      const data = await nucleo.get<DocumentoUrlNucleo>(
        `/nucleo/documentos/${documento.id}/url`,
        empresaId,
      );
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo abrir el documento");
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !subiendo) onClose();
      }}
    >
      <DialogContent
        showCloseButton={!subiendo}
        className="max-h-[92vh] overflow-y-auto sm:max-w-3xl"
      >
        <DialogHeader>
          <DialogTitle>Documentos · {etiqueta}</DialogTitle>
          <DialogDescription>
            Cada nuevo documento del mismo tipo desactiva la versión anterior. No se
            borran: quedan como historial auditable.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Aviso tono="critico" icono={AlertTriangle}>
            {error}
          </Aviso>
        )}

        <div className="overflow-hidden rounded-xl border border-borde">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tipo</TableHead>
                <TableHead>Número</TableHead>
                <TableHead>Vence</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Archivo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cargando ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-s5 text-center text-tinta-3">
                    <Loader2 className="mx-auto size-5 animate-spin" />
                  </TableCell>
                </TableRow>
              ) : documentos.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="p-0">
                    <EstadoVacio
                      icono={FileText}
                      titulo="Sin documentos"
                      descripcion="Cargue el primer documento de este recurso."
                    />
                  </TableCell>
                </TableRow>
              ) : (
                documentos.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell>
                      {TIPOS_DOCUMENTO.find((t) => t.valor === doc.tipo)?.etiqueta ??
                        doc.tipo}
                    </TableCell>
                    <TableCell>{doc.numero ?? "—"}</TableCell>
                    <TableCell>
                      <Vencimiento fecha={doc.vence_en ?? null} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge tono={doc.es_vigente ? "ok" : "neutro"}>
                        {doc.es_vigente ? "Vigente" : "Histórico"}
                      </StatusBadge>
                    </TableCell>
                    <TableCell className="text-right">
                      {doc.archivo_url ? (
                        <Button
                          size="xs"
                          variant="outline"
                          onClick={() => void ver(doc)}
                        >
                          Ver
                        </Button>
                      ) : (
                        <span className="text-tinta-3">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        <fieldset className="space-y-s3 border-0">
          <legend className="rotulo float-left mb-s2 w-full">Nueva versión</legend>
          <div className="grid gap-s3 sm:grid-cols-2">
            <Campo etiqueta="Tipo de documento" htmlFor="doc-tipo" requerido>
              <SelectSimple
                id="doc-tipo"
                valor={tipo}
                onCambio={setTipo}
                opciones={TIPOS_DOCUMENTO}
              />
            </Campo>
            <Campo etiqueta="Número" htmlFor="doc-numero">
              <Input
                id="doc-numero"
                value={numero}
                onChange={(e) => setNumero(e.target.value)}
                placeholder="Opcional"
              />
            </Campo>
            <Campo etiqueta="Entidad emisora" htmlFor="doc-entidad">
              <Input
                id="doc-entidad"
                value={entidad}
                onChange={(e) => setEntidad(e.target.value)}
                placeholder="Opcional"
              />
            </Campo>
            <Campo etiqueta="Fecha de emisión" htmlFor="doc-emitido">
              <Input
                id="doc-emitido"
                type="date"
                value={emitido}
                onChange={(e) => setEmitido(e.target.value)}
              />
            </Campo>
            <Campo etiqueta="Vence" htmlFor="doc-vence" requerido>
              <Input
                id="doc-vence"
                type="date"
                value={vence}
                onChange={(e) => setVence(e.target.value)}
              />
            </Campo>
            <Campo etiqueta="Archivo" htmlFor="doc-archivo" requerido>
              <Input
                key={fileKey}
                id="doc-archivo"
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.webp,.heic"
                onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
              />
            </Campo>
            <Campo
              etiqueta="Observaciones"
              htmlFor="doc-observaciones"
              className="sm:col-span-2"
            >
              <Input
                id="doc-observaciones"
                value={observaciones}
                onChange={(e) => setObservaciones(e.target.value)}
                placeholder="Opcional"
              />
            </Campo>
          </div>
        </fieldset>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={subiendo}>
            Cerrar
          </Button>
          <Button onClick={() => void subir()} disabled={subiendo || !archivo}>
            {subiendo ? (
              <>
                <Loader2 className="animate-spin" /> Subiendo…
              </>
            ) : (
              <>
                <Upload /> Cargar documento
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
