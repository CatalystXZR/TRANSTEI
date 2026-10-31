import { permanentRedirect } from "next/navigation";

/** Ruta legacy retirada (Ola A): los viajes se operan en la mesa de despacho. */
export default function ViajesLegacy() {
  permanentRedirect("/despacho");
}
