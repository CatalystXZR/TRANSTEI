import { permanentRedirect } from "next/navigation";

/** Ruta legacy retirada (Ola A): la facturación se emite desde cobranza del núcleo. */
export default function FacturacionLegacy() {
  permanentRedirect("/cobranza");
}
