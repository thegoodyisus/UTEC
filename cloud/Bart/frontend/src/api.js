// Cliente de las APIs de Bart. Las URLs se inyectan al compilar (serverless.yml las lee de los stacks).
const CHAT = import.meta.env.VITE_CHAT_API || "";
const SOL = import.meta.env.VITE_SOLICITUDES_API || "";

async function llamar(base, ruta, metodo = "GET", cuerpo) {
  const opciones = { method: metodo };
  if (cuerpo !== undefined) {
    opciones.headers = { "Content-Type": "application/json" };
    opciones.body = JSON.stringify(cuerpo);
  }
  const r = await fetch(base + ruta, opciones);
  let datos = null;
  try {
    datos = await r.json();
  } catch {
    datos = null;
  }
  if (!r.ok) {
    const e = new Error((datos && datos.error && datos.error.mensaje) || "HTTP " + r.status);
    e.codigo = datos && datos.error && datos.error.codigo;
    e.status = r.status;
    throw e;
  }
  return datos;
}

export const abrirSesion = () => llamar(CHAT, "/chat/sesiones", "POST", {});
export const enviarMensaje = (sesionId, texto, adjunto) =>
  llamar(CHAT, "/chat/mensajes", "POST", { sesion_id: sesionId, texto, adjunto: adjunto || null });
export const leerSesion = (sesionId) => llamar(CHAT, "/chat/sesiones/" + encodeURIComponent(sesionId));

export function listarSolicitudes({ estado, dni }) {
  const q = new URLSearchParams({ limite: "50" });
  if (dni) q.set("dni", dni);
  else if (estado) q.set("estado", estado);
  return llamar(SOL, "/solicitudes?" + q.toString());
}
export const leerSolicitud = (id) => llamar(SOL, "/solicitudes/" + encodeURIComponent(id));
export const cerrarSolicitud = (id, usuarioBanco, productoFinal) =>
  llamar(SOL, "/solicitudes/" + encodeURIComponent(id) + "/cierre", "POST", {
    usuario_banco: usuarioBanco,
    producto_final: productoFinal
  });
