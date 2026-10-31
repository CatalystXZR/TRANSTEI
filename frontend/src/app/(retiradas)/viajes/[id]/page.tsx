import { permanentRedirect } from "next/navigation";

/**
 * Ruta legacy retirada (Ola A). El detalle legacy (`/viajes/<id numérico>`)
 * no tiene id equivalente en el núcleo (UUID), por lo que se redirige al
 * listado de expedientes.
 */
export default function ViajeLegacy() {
  permanentRedirect("/expediente");
}
