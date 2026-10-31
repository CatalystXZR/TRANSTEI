import { permanentRedirect } from "next/navigation";

/** Ruta legacy retirada (Ola A): las cobranzas se gestionan en cobranza del núcleo. */
export default function CobranzasLegacy() {
  permanentRedirect("/cobranza");
}
