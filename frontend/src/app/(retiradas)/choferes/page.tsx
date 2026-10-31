import { permanentRedirect } from "next/navigation";

/** Ruta legacy retirada (Ola A): choferes se administran en maestros del núcleo. */
export default function ChoferesLegacy() {
  permanentRedirect("/maestros");
}
