import { useEffect, useState } from "react";
import { cerrarSolicitud, leerSolicitud, listarSolicitudes } from "./api.js";
import { T } from "./textos.js";
import { dniDe, fecha, pct, soles } from "./formato.js";

const ESTADOS = ["PRE_APROBADA", "CONTRAOFERTA", "EN_PROCESO", "NO_ELEGIBLE", "DOC_INCONSISTENTE", "DESISTIDA", "CERRADA", "ERROR"];

function Insignia({ estado }) {
  return <span className={"insignia " + estado.toLowerCase()}>{T.estados[estado] || estado}</span>;
}

function Dato({ etiqueta, valor }) {
  return (
    <div className="dato">
      <span>{etiqueta}</span>
      <strong>{valor}</strong>
    </div>
  );
}

function valorRegla(r) {
  if (typeof r.valor !== "number") return r.valor;
  if (r.regla === "R5_AHORRO") return pct(r.valor);
  return soles(r.valor);
}

function umbralRegla(r) {
  if (typeof r.umbral !== "number") return r.umbral;
  if (r.regla === "R5_AHORRO") return pct(r.umbral);
  return soles(r.umbral);
}

function Detalle({ solicitud, alCerrar }) {
  const [usuario, setUsuario] = useState("analista.demo");
  const [referencia, setReferencia] = useState("");
  const [verJson, setVerJson] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState("");
  const s = solicitud;
  const ev = s.evaluacion;
  const cd = s.compra_deuda;
  const b = s.boleta || {};

  function descargar() {
    const blob = new Blob([JSON.stringify(s, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "solicitud_" + s.solicitud_id + ".json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function cerrar(e) {
    e.preventDefault();
    setOcupado(true);
    setAviso("");
    try {
      await cerrarSolicitud(s.solicitud_id, usuario.trim(), referencia.trim());
      setAviso(T.cerrada);
      alCerrar(s.solicitud_id);
    } catch (err) {
      setAviso(err.message);
    } finally {
      setOcupado(false);
    }
  }

  return (
    <article className="detalle">
      <header>
        <div>
          <Insignia estado={s.estado} />
          {s.motivo ? <span className="motivo">{T.motivos[s.motivo] || s.motivo}</span> : null}
        </div>
        <h3>{T.productos[s.producto.producto_id] || s.producto.nombre}</h3>
        <p className="meta">
          DNI {dniDe(s.documento)} {"·"} {fecha(s.creado_en)} {"·"} <code>{s.solicitud_id.slice(0, 8)}</code>
        </p>
      </header>

      <h4>{T.detMontos}</h4>
      <div className="datos">
        <Dato etiqueta={T.detSolicitado} valor={soles(s.monto_solicitado)} />
        <Dato etiqueta={T.detAprobable} valor={soles(ev && ev.monto_aprobable)} />
        <Dato etiqueta={T.detPreaprobado} valor={soles(ev && ev.monto_preaprobado)} />
        <Dato etiqueta={T.detCuota} valor={soles(ev && ev.cuota_mensual_estimada)} />
        <Dato etiqueta={T.detPlazo} valor={s.oferta.plazo_meses ? s.oferta.plazo_meses + " " + T.ofertaMeses : "-"} />
        <Dato etiqueta={T.detTea} valor={pct(s.oferta.tea)} />
      </div>

      {ev ? (
        <>
          <h4>{T.detEvaluacion}</h4>
          <div className="datos">
            <Dato etiqueta={T.detIngreso} valor={soles(ev.ingreso_neto_validado)} />
            <Dato etiqueta={T.detCuotaRcc} valor={soles(ev.cuota_rcc_actual)} />
            <Dato etiqueta={T.detCapacidad} valor={soles(ev.capacidad_mensual)} />
            <Dato etiqueta={T.detClasificacion} valor={ev.clasificacion_sbs} />
            <Dato etiqueta={T.detRatio} valor={pct(ev.ratio_endeudamiento)} />
            <Dato etiqueta={T.detVersion} valor={ev.version_reglas} />
          </div>
          <h4>{T.detReglas}</h4>
          <div className="tabla-scroll">
            <table className="reglas">
              <thead>
                <tr><th>{T.detRegla}</th><th>{T.detValor}</th><th>{T.detUmbral}</th><th>{T.detResultado}</th></tr>
              </thead>
              <tbody>
                {ev.reglas_evaluadas.map((r) => (
                  <tr key={r.regla}>
                    <td>{T.reglas[r.regla] || r.regla}</td>
                    <td>{valorRegla(r)}</td>
                    <td>{umbralRegla(r)}</td>
                    <td className={r.cumple ? "ok" : "no"}>{r.cumple ? T.cumple : T.noCumple}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {cd ? (
        <>
          <h4>{T.detCompraDeuda}</h4>
          <div className="datos">
            <Dato etiqueta={T.detSaldoComprable} valor={soles(cd.saldo_comprable_actual)} />
            <Dato etiqueta={T.detAhorro} valor={cd.ahorro_mensual !== undefined ? soles(cd.ahorro_mensual) + " (" + pct(cd.ahorro_pct) + ")" : "-"} />
          </div>
        </>
      ) : null}

      <h4>{T.detBoleta}</h4>
      <div className="datos">
        <Dato etiqueta={T.detPeriodo} valor={b.periodo || "-"} />
        <Dato etiqueta={T.detPuntaje} valor={b.score_consistencia === null || b.score_consistencia === undefined ? "-" : b.score_consistencia + " / 100"} />
        <Dato etiqueta={T.detBanderas} valor={b.banderas && b.banderas.length ? b.banderas.join(", ") : T.sinBanderas} />
      </div>

      {s.explicacion ? (
        <>
          <h4>{T.detExplicacion}</h4>
          <blockquote>{s.explicacion}</blockquote>
        </>
      ) : null}

      <h4>{T.detHistorial}</h4>
      <ol className="historial">
        {s.historial.map((h, i) => (
          <li key={i}>
            <Insignia estado={h.estado} /> <span>{T.origenes[h.origen] || h.origen}</span> <time>{fecha(h.fecha)}</time>
          </li>
        ))}
      </ol>

      {s.cierre ? (
        <>
          <h4>{T.detCierre}</h4>
          <div className="datos">
            <Dato etiqueta={T.usuarioBanco} valor={s.cierre.usuario_banco} />
            <Dato etiqueta={T.productoFinal} valor={s.cierre.producto_final} />
          </div>
        </>
      ) : null}

      {s.estado === "PRE_APROBADA" ? (
        <form className="cierre" onSubmit={cerrar}>
          <label>
            {T.usuarioBanco}
            <input value={usuario} maxLength={50} onChange={(e) => setUsuario(e.target.value)} required />
          </label>
          <label>
            {T.productoFinal}
            <input value={referencia} maxLength={50} placeholder="PLD-DEMO-0001" onChange={(e) => setReferencia(e.target.value)} required />
          </label>
          <button type="submit" disabled={ocupado}>{T.cerrar}</button>
        </form>
      ) : null}
      {aviso ? <div className="aviso">{aviso}</div> : null}

      <div className="acciones">
        <button type="button" className="secundario" onClick={descargar}>{T.descargarJson}</button>
        <button type="button" className="secundario" onClick={() => setVerJson(!verJson)}>{verJson ? T.ocultarJson : T.verJson}</button>
      </div>
      {verJson ? <pre className="json">{JSON.stringify(s, null, 2)}</pre> : null}
    </article>
  );
}

export default function Bandeja() {
  const [estado, setEstado] = useState("PRE_APROBADA");
  const [dni, setDni] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [items, setItems] = useState([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  const [seleccion, setSeleccion] = useState(null);

  async function cargar() {
    setCargando(true);
    setError("");
    try {
      const r = await listarSolicitudes(busqueda ? { dni: busqueda } : { estado });
      setItems(r.items);
    } catch (err) {
      setError(err.message);
      setItems([]);
    } finally {
      setCargando(false);
    }
  }

  useEffect(() => {
    cargar();
  }, [estado, busqueda]);

  async function abrir(id) {
    try {
      setSeleccion(await leerSolicitud(id));
    } catch (err) {
      setError(err.message);
    }
  }

  async function alCerrar(id) {
    await abrir(id);
    cargar();
  }

  return (
    <div className="banco">
      <section className="lista">
        <div className="filtros">
          <div className="chips">
            {ESTADOS.map((e) => (
              <button
                type="button"
                key={e}
                className={"chip" + (!busqueda && estado === e ? " activo" : "")}
                onClick={() => { setBusqueda(""); setDni(""); setEstado(e); }}
              >
                {T.estados[e]}
              </button>
            ))}
          </div>
          <form className="busqueda" onSubmit={(e) => { e.preventDefault(); setBusqueda(dni.trim()); }}>
            <input value={dni} inputMode="numeric" maxLength={8} placeholder={T.buscarDni} onChange={(e) => setDni(e.target.value.replace(/[^0-9]/g, ""))} />
            <button type="submit" disabled={dni.length !== 8}>{T.buscar}</button>
            {busqueda ? <button type="button" className="secundario" onClick={() => { setBusqueda(""); setDni(""); }}>{T.limpiar}</button> : null}
            <button type="button" className="secundario" onClick={cargar}>{T.actualizar}</button>
          </form>
        </div>
        {error ? <div className="aviso">{error}</div> : null}
        {cargando ? <p className="nota">{T.cargando}</p> : null}
        {!cargando && !items.length ? <p className="nota">{T.sinSolicitudes}</p> : null}
        <ul className="solicitudes">
          {items.map((i) => (
            <li key={i.solicitud_id}>
              <button type="button" className={seleccion && seleccion.solicitud_id === i.solicitud_id ? "fila activa" : "fila"} onClick={() => abrir(i.solicitud_id)}>
                <span className="col-producto">{T.productos[i.producto_id] || i.producto_id}</span>
                <span className="col-cliente">DNI {dniDe(i.documento)}</span>
                <span className="col-monto">{soles(i.monto_preaprobado !== null && i.monto_preaprobado !== undefined ? i.monto_preaprobado : i.monto_solicitado)}</span>
                <Insignia estado={i.estado} />
                <span className="col-fecha">{fecha(i.creado_en)}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section className="lado-detalle">
        {seleccion ? <Detalle key={seleccion.solicitud_id + seleccion.version} solicitud={seleccion} alCerrar={alCerrar} /> : <p className="nota vacio">{T.elegirSolicitud}</p>}
      </section>
    </div>
  );
}
