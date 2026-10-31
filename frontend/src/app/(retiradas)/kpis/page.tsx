import { permanentRedirect } from "next/navigation";

/** Ruta legacy retirada (Ola A): los indicadores se consultan en rentabilidad del núcleo. */
export default function KpisLegacy() {
  permanentRedirect("/rentabilidad");
}
