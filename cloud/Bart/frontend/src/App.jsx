import { useState } from "react";
import Chat from "./Chat.jsx";
import Bandeja from "./Bandeja.jsx";
import { T } from "./textos.js";

export default function App() {
  const [vista, setVista] = useState("cliente");
  return (
    <div className="app">
      <header className="cabecera">
        <div className="marca">
          <span className="logo" aria-hidden="true">B</span>
          <div>
            <strong>{T.marca}</strong>
            <span>{T.subtitulo}</span>
          </div>
        </div>
        <nav className="tabs" role="tablist">
          <button type="button" role="tab" aria-selected={vista === "cliente"} className={vista === "cliente" ? "activo" : ""} onClick={() => setVista("cliente")}>
            {T.tabCliente}
          </button>
          <button type="button" role="tab" aria-selected={vista === "banco"} className={vista === "banco" ? "activo" : ""} onClick={() => setVista("banco")}>
            {T.tabBanco}
          </button>
        </nav>
      </header>
      <main>
        {/* El chat se mantiene montado para no perder la conversacion al cambiar de vista */}
        <div hidden={vista !== "cliente"}><Chat /></div>
        {vista === "banco" ? <Bandeja /> : null}
      </main>
      <footer className="pie">{T.aviso}</footer>
    </div>
  );
}
