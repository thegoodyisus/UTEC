// Copia algunas boletas dummy de Data/boletas a public/demo para descargarlas desde la web (panel "Datos de demostracion").
// Se ejecuta solo antes de "npm run build". Son PDF sinteticos, marcados "sin valor legal".
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const destino = join(raiz, "frontend", "public", "demo");
const casos = [
  ["99990069", "boleta_2026-10.pdf", "boleta_99990069.pdf"],
  ["99990006", "boleta_2026-10_neto_bajo.pdf", "boleta_99990006_neto_bajo.pdf"],
  ["99990019", "boleta_2026-10.pdf", "boleta_99990019.pdf"],
  ["99990025", "boleta_2026-10_dni_otro.pdf", "boleta_99990025_dni_otro.pdf"],
  ["99990040", "boleta_2026-10_sin_texto.pdf", "boleta_99990040_sin_texto.pdf"]
];
mkdirSync(destino, { recursive: true });
for (const [dni, origen, nombre] of casos) {
  copyFileSync(join(raiz, "Data", "boletas", "boletas_" + dni, origen), join(destino, nombre));
}
console.log("boletas de demo copiadas:", casos.length);
