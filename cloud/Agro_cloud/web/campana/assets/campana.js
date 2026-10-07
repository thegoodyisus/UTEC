/* ============================================================
   Prototipo AgroCredit v02 — Módulo Campaña (mock helpers)
   TODO ES FICTICIO. Sin backend, scoring, tasas ni pagos reales.
   Estado en localStorage solo para recorrer la demo (no backend).
   ============================================================ */
(function () {
  "use strict";

  window.goTo = function (page) { window.location.href = page; };

  // ---- Perfil del onboarding (cultivos, ubicación) ----
  window.loadProfile = function () {
    try { return JSON.parse(localStorage.getItem("agrocredit_profile")) || {}; }
    catch (e) { return {}; }
  };
  window.saveProfile = function (patch) {
    var cur = window.loadProfile();
    Object.assign(cur, patch);
    try { localStorage.setItem("agrocredit_profile", JSON.stringify(cur)); } catch (e) {}
    return cur;
  };

  // Nombre registrado del agricultor (para que prevalezca en toda la demo).
  window.profileName = function (fallback) {
    var p = window.loadProfile();
    var nom = (p.nombres || "").trim();
    if (!nom) return fallback || "";
    return nom.split(/\s+/)[0];
  };
  window.profileFullName = function (fallback) {
    var p = window.loadProfile();
    var full = ((p.nombres || "") + " " + (p.apellidos || "")).trim();
    return full || fallback || "";
  };

  // ---- Estado de campaña (persistente en sesión para navegar entre pantallas) ----
  var DEFAULT = {
    cultivo: "Papa",
    ubicacion: "Cusco",
    cosecha: "2026-06-15",
    volumenEsperado: 2000,
    unidad: "kg",                 // "kg" | "tonelada"
    logistica: "Recojo",
    capitalNecesario: 8000,       // S/
    precioAhora: 1.80,            // S/ por unidad (lo define el agricultor)
    precioContraentrega: 2.10,    // S/ por unidad
    referenciaMercado: 1.95,      // S/ por unidad (solo referencial)
    fotos: [],                    // dataURLs de fotos cargadas (mock)
    volumenDisponible: 2000,
    volumenComprometido: 0,
    modalidadElegida: "Pago ahora",
    adelanto: 0,
    creditoAceptado: 0,
    volumenReal: 0,
    volumenEntregado: 0,
    publicada: false,
    estado: "BORRADOR"
  };
  function load() {
    try {
      var s = JSON.parse(localStorage.getItem("agrocredit_campaign"));
      return s || Object.assign({}, DEFAULT);
    } catch (e) { return Object.assign({}, DEFAULT); }
  }
  function save(c) { try { localStorage.setItem("agrocredit_campaign", JSON.stringify(c)); } catch (e) {} }

  window.getCampaign = function () { return load(); };
  window.setCampaign = function (patch) { var c = load(); Object.assign(c, patch); save(c); return c; };
  window.resetCampaign = function () { save(Object.assign({}, DEFAULT)); };

  // ---- Formato ----
  window.money = function (n) {
    return "S/ " + Number(n).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  window.moneyInt = function (n) {
    return "S/ " + Number(n).toLocaleString("es-PE", { maximumFractionDigits: 0 });
  };
  window.unitLabel = function (u) { return u === "tonelada" ? "tonelada" : "kg"; };
  window.vol = function (n, u) {
    return Number(n).toLocaleString("es-PE") + " " + unitLabel(u || getCampaign().unidad);
  };

  // ---- Cálculos ficticios ----
  window.calcAdelanto = function () {
    var c = load();
    return Math.round(c.volumenComprometido * c.precioAhora * 0.4);
  };
  window.calcGap = function () {
    var c = load();
    var cubierto = c.adelanto + c.creditoAceptado;
    var gap = c.capitalNecesario - cubierto;
    return gap > 0 ? gap : 0;
  };
  window.calcValorVenta = function () {
    var c = load();
    var v = c.volumenEntregado || c.volumenComprometido || c.volumenEsperado;
    return Math.round(v * c.precioAhora);
  };
  window.calcLiquidacion = function () {
    var c = load();
    var valor = calcValorVenta();
    var otros = 0; // no se inventan comisiones/impuestos (fuera de alcance)
    var saldo = valor - c.adelanto - c.creditoAceptado - otros;
    return { valor: valor, adelanto: c.adelanto, repagoCredito: c.creditoAceptado, otros: otros, saldo: saldo };
  };

  // ---- Ofertas mock por campaña (agrupadas) ----
  window.getOfertas = function () {
    var c = load();
    var u = c.unidad;
    return [
      { id: "of1", comprador: "Agroexportadora Fértil S.A.", volumen: Math.round(c.volumenEsperado * 0.6), modalidad: "Pago ahora", precio: c.precioAhora, logistica: "Recojo", fecha: c.cosecha },
      { id: "of2", comprador: "Mercado Andino Retail", volumen: Math.round(c.volumenEsperado * 0.4), modalidad: "Pago contraentrega", precio: c.precioContraentrega, logistica: "Envío", fecha: c.cosecha },
      { id: "of3", comprador: "Cooperativa Valle Verde", volumen: c.volumenEsperado, modalidad: "Pago contraentrega", precio: c.precioContraentrega, logistica: "Recojo", fecha: c.cosecha }
    ].map(function (o) { o.total = Math.round(o.volumen * o.precio); o.unidad = u; return o; });
  };
})();
