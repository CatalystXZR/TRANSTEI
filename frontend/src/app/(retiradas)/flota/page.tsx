import { permanentRedirect } from "next/navigation";

/** Ruta legacy retirada (Ola A): flota se administra en maestros del núcleo. */
export default function FlotaLegacy() {
  permanentRedirect("/maestros");
}
