import { useEffect, useRef, useState } from "react";
import { abrirSesion, enviarMensaje, leerSesion } from "./api.js";
import { T } from "./textos.js";
import { fechaCorta, pct, soles } from "./formato.js";

const PASOS = ["INICIO", "PEDIR_DNI", "ELEGIR_PRODUCTO", "PEDIR_MONTO", "PEDIR_BOLETA", "EN_PROCESO", "DECIDIR_CONTRAOFERTA", "FIN"];
const MAX_PDF = 2 * 1024 * 1024;
const POLL_MS = 3000;
const POLL_MAX_MS = 120000;

function leerComoBase64(archivo) {
  return new Promise((resolver, rechazar) => {
    const lector = new FileReader();
    lector.onload = () => resolver(String(lector.result).split(",")[1]);
    lector.onerror = rechazar;
    lector.readAsDataURL(archivo);
  });
}

function Ofertas({ ofertas }) {
  return (
    <div className="ofertas">
      {ofertas.map((o) => (
        <div className="oferta" key={o.oferta_id}>
          <div className="oferta-producto">{T.productos[o.producto_id] || o.producto_nombre}</div>
          <div className="oferta-monto">
            <span>{o.producto_id === "TC" ? T.ofertaLinea : T.ofertaHasta}</span> {soles(o.monto_maximo)}
          </div>
          <div className="oferta-datos">
            {o.plazo_meses ? <span>{T.ofertaPlazo}: {o.plazo_meses} {T.ofertaMeses}</span> : null}
            <span>{T.ofertaTea}: {pct(o.tea)}</span>
            <span>{T.ofertaVigencia}: {fechaCorta(o.fecha_fin_vigencia)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function PanelEstado({ sesion, visitados }) {
  const actual = sesion ? sesion.paso : null;
  return (
    <section className="panel">
      <h2>{T.panelTitulo}</h2>
      <p className="nota">{T.panelExplica}</p>
      <ol className="pasos">
        {PASOS.map((p) => (
          <li key={p} className={p === actual ? "actual" : visitados.includes(p) ? "hecho" : ""}>
            <span className="punto" />
            {T.pasos[p]}
          </li>
        ))}
      </ol>
      {sesion ? (
        <dl className="variables">
          <dt>{T.panelPaso}</dt>
          <dd><code>{sesion.paso}</code></dd>
          <dt>{T.panelEspera}</dt>
          <dd>{T.esperas[sesion.espera] || sesion.espera}</dd>
          <dt>{T.panelSolicitud}</dt>
          <dd>{sesion.solicitud ? <><code>{sesion.solicitud.solicitud_id.slice(0, 8)}</code> {T.estados[sesion.solicitud.estado]}</> : "-"}</dd>
          <dt>{T.panelSesion}</dt>
          <dd><code>{sesion.sesion_id.slice(0, 8)}</code></dd>
        </dl>
      ) : null}
    </section>
  );
}

function Demo() {
  return (
    <section className="panel">
      <h2>{T.demoTitulo}</h2>
      <p className="nota">{T.demoExplica}</p>
      <ul className="demo">
        {T.demoCasos.map((c) => (
          <li key={c.dni}>
            <code>{c.dni}</code>
            <span>{c.caso}</span>
            {c.archivo ? <a href={"demo/" + c.archivo} download>{T.demoBoleta}</a> : null}
          </li>
        ))}
      </ul>
      <p className="nota">{T.demoNota}</p>
    </section>
  );
}

export default function Chat() {
  const [sesion, setSesionBase] = useState(null);
  const [visitados, setVisitados] = useState([]);
  // Cada respuesta trae el paso actual: se acumulan los pasos visitados para el panel de estado
  const setSesion = (s) => {
    setSesionBase(s);
    if (s) setVisitados((v) => (v.includes(s.paso) ? v : [...v, s.paso]));
  };
  const [mensajes, setMensajes] = useState([]);
  const [texto, setTexto] = useState("");
  const [adjunto, setAdjunto] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState("");
  const finRef = useRef(null);
  const archivoRef = useRef(null);

  const agregar = (m) => setMensajes((prev) => [...prev, m]);

  async function iniciar() {
    setMensajes([]);
    setAviso("");
    setAdjunto(null);
    setSesion(null);
    setVisitados([]);
    setOcupado(true);
    try {
      const s = await abrirSesion();
      setSesion(s);
      agregar({ autor: "bart", texto: s.mensaje });
    } catch {
      setAviso(T.errorConexion);
    } finally {
      setOcupado(false);
    }
  }

  const iniciadoRef = useRef(false);
  useEffect(() => {
    // StrictMode ejecuta los efectos dos veces en desarrollo: se abre una sola sesion
    if (iniciadoRef.current) return;
    iniciadoRef.current = true;
    iniciar();
  }, []);

  useEffect(() => {
    if (finRef.current) finRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [mensajes, ocupado]);

  // Polling mientras el workflow evalua la solicitud
  useEffect(() => {
    if (!sesion || sesion.paso !== "EN_PROCESO") return undefined;
    const inicio = Date.now();
    const id = setInterval(async () => {
      try {
        const s = await leerSesion(sesion.sesion_id);
        if (s.paso !== "EN_PROCESO") {
          clearInterval(id);
          setSesion(s);
          if (s.mensaje) agregar({ autor: "bart", texto: s.mensaje });
        } else if (Date.now() - inicio > POLL_MAX_MS) {
          clearInterval(id);
          setAviso(T.demora);
        }
      } catch {
        /* reintenta en el siguiente ciclo */
      }
    }, POLL_MS);
    return () => clearInterval(id);
  }, [sesion]);

  async function elegirArchivo(e) {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    if (f.type !== "application/pdf" || f.size > MAX_PDF) {
      setAviso(T.pdfInvalido);
      return;
    }
    setAviso("");
    setAdjunto({ nombre_archivo: f.name, tipo: "application/pdf", contenido_base64: await leerComoBase64(f) });
  }

  async function enviar(e) {
    e.preventDefault();
    if (!sesion || ocupado || (!texto.trim() && !adjunto)) return;
    const t = texto.trim();
    agregar({ autor: "cliente", texto: t, archivo: adjunto ? adjunto.nombre_archivo : null });
    setTexto("");
    setAviso("");
    setOcupado(true);
    try {
      const s = await enviarMensaje(sesion.sesion_id, t, adjunto);
      setAdjunto(null);
      setSesion(s);
      agregar({ autor: "bart", texto: s.mensaje, ofertas: s.ofertas });
    } catch (err) {
      if (err.codigo === "SESION_FINALIZADA") setAviso(T.conversacionTerminada);
      else if (err.codigo === "SESION_EXPIRADA") setAviso(T.sesionExpirada);
      else setAviso(err.message || T.errorConexion);
    } finally {
      setOcupado(false);
    }
  }

  const terminado = sesion && sesion.paso === "FIN";
  const pideBoleta = sesion && sesion.espera === "BOLETA";
  const evaluando = sesion && sesion.paso === "EN_PROCESO";

  return (
    <div className="cliente">
      <section className="chat">
        <div className="mensajes" aria-live="polite">
          {!sesion && ocupado ? <div className="estado-chat">{T.conectando}</div> : null}
          {mensajes.map((m, i) => (
            <div key={i} className={"burbuja " + m.autor}>
              {m.texto ? <p>{m.texto}</p> : null}
              {m.archivo ? <p className="archivo">PDF: {m.archivo}</p> : null}
              {m.ofertas && m.ofertas.length ? <Ofertas ofertas={m.ofertas} /> : null}
            </div>
          ))}
          {ocupado && sesion ? <div className="burbuja bart escribiendo"><span /><span /><span /></div> : null}
          {evaluando ? <div className="estado-chat">{T.evaluando}</div> : null}
          <div ref={finRef} />
        </div>
        {aviso ? <div className="aviso">{aviso}</div> : null}
        {terminado ? (
          <div className="fin">
            <span>{T.conversacionTerminada}</span>
            <button type="button" onClick={iniciar}>{T.nuevaConversacion}</button>
          </div>
        ) : (
          <form className="entrada" onSubmit={enviar}>
            {pideBoleta ? (
              <>
                <input ref={archivoRef} type="file" accept="application/pdf" hidden onChange={elegirArchivo} />
                {adjunto ? (
                  <span className="adjunto">
                    {adjunto.nombre_archivo}
                    <button type="button" className="enlace" onClick={() => setAdjunto(null)}>{T.quitarAdjunto}</button>
                  </span>
                ) : (
                  <button type="button" className="secundario" onClick={() => archivoRef.current.click()}>{T.adjuntar}</button>
                )}
              </>
            ) : null}
            <input
              type="text"
              value={texto}
              maxLength={500}
              placeholder={T.escribe}
              onChange={(e) => setTexto(e.target.value)}
              disabled={!sesion || evaluando}
            />
            <button type="submit" disabled={!sesion || ocupado || evaluando || (!texto.trim() && !adjunto)}>{T.enviar}</button>
          </form>
        )}
      </section>
      <aside className="lateral">
        <PanelEstado sesion={sesion} visitados={visitados} />
        <Demo />
      </aside>
    </div>
  );
}
