import { permanentRedirect } from "next/navigation";

/** Ruta legacy retirada (Ola A): clientes se administran en maestros del núcleo. */
export default function ClientesLegacy() {
  permanentRedirect("/maestros");
}
