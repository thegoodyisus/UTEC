// Escribe frontend/.env.production.local con las URLs de las APIs (las recibe del hook de serverless.yml).
// Asi el build funciona igual en Mac, Linux y Windows (sin la sintaxis VAR=valor de bash).
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const [chat, solicitudes] = process.argv.slice(2);
if (!chat || !solicitudes || !chat.startsWith("https://") || !solicitudes.startsWith("https://")) {
  console.error("Uso: node scripts/escribir_env.mjs <URL API chat> <URL API solicitudes>");
  process.exit(1);
}
const destino = join(dirname(fileURLToPath(import.meta.url)), "..", ".env.production.local");
writeFileSync(destino, "VITE_CHAT_API=" + chat + "\nVITE_SOLICITUDES_API=" + solicitudes + "\n");
console.log("URLs de las APIs escritas en .env.production.local");
