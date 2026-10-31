import { permanentRedirect } from "next/navigation";

/**
 * Ruta legacy retirada (Ola A). El panel legacy se reemplazó por el tablero
 * del núcleo; se conserva la URL con una redirección permanente (308).
 */
export default function DashboardLegacy() {
  permanentRedirect("/tablero");
}
