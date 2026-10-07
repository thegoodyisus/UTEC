/* agrocredit: modulo comun de la web (cognito, api, flujo y guardas de navegacion)
   requiere vendor/amazon-cognito-identity-6.3.20.min.js cargado antes */
(function () {
  "use strict";

  var CLAVE_FLUJO = "agro_flujo";
  var CLAVE_CONFIG = "agro_config";

  //flujos por rol: registro (antes de la cuenta) y alta de perfil (ya con sesion)
  var REGISTRO = {
    agricultor: ["01-bienvenida", "cuenta", "04-contrasena", "03-otp"],
    comprador: ["comprador-01-bienvenida", "cuenta", "04-contrasena", "03-otp"]
  };
  var ALTA = {
    agricultor: ["02-datos-personales", "04c-abrir-cuenta", "05-biometria", "06-productos", "07-ubicacion", "08-permisos", "09-perfil-listo"],
    comprador: ["comprador-02-empresa", "comprador-03-representante", "comprador-05-pagos", "comprador-04-preferencias", "comprador-06-verificacion"]
  };
  var INICIO = { agricultor: "/campana/home.html", comprador: "/campana/home-comprador.html" };

  //---- utilidades ----
  function pagina(nombre) { return "/onboarding/" + nombre + ".html"; }
  function ir(ruta) { window.location.replace(ruta); }
  function mostrar() { document.body.style.visibility = "visible"; }
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    var h = Array.prototype.map.call(b, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
    return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
  }
  function leer(clave) { try { return JSON.parse(sessionStorage.getItem(clave)) || null; } catch (e) { return null; } }
  function grabar(clave, valor) { try { sessionStorage.setItem(clave, JSON.stringify(valor)); } catch (e) {} }

  //---- flujo de la pestana (sessionStorage): rol, cuenta en registro, pasos hechos y datos parciales ----
  function flujo() { return leer(CLAVE_FLUJO) || { rol: null, cuenta: null, hechos: [], datos: {}, sub: null }; }
  function guardarFlujo(f) { grabar(CLAVE_FLUJO, f); }
  function reiniciarFlujo(rol) { guardarFlujo({ rol: rol || null, cuenta: null, hechos: [], datos: {}, sub: null }); }
  function completar(paso, datos) {
    var f = flujo();
    if (f.hechos.indexOf(paso) < 0) f.hechos.push(paso);
    if (datos) Object.keys(datos).forEach(function (k) { f.datos[k] = datos[k]; });
    guardarFlujo(f);
    return f;
  }
  function siguiente(rol, paso, fase) {
    var lista = (fase === "alta" ? ALTA : REGISTRO)[rol] || [];
    var i = lista.indexOf(paso);
    return i >= 0 && i < lista.length - 1 ? pagina(lista[i + 1]) : null;
  }

  //---- configuracion y cognito ----
  function config() {
    var c = leer(CLAVE_CONFIG);
    if (c) return Promise.resolve(c);
    return fetch("/api/v1/config", { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw { estado: r.status, detalle: "no se pudo leer la configuracion" };
      return r.json();
    }).then(function (j) { grabar(CLAVE_CONFIG, j); return j; });
  }
  function pool() {
    return config().then(function (c) {
      return new AmazonCognitoIdentity.CognitoUserPool({ UserPoolId: c.userPoolId, ClientId: c.clientId });
    });
  }
  function usuarioCognito(p, documento) { return new AmazonCognitoIdentity.CognitoUser({ Username: documento, Pool: p }); }

  var MENSAJES = {
    UsernameExistsException: "Ya existe una cuenta con ese documento. Inicia sesión.",
    CodeMismatchException: "El código no es correcto. Revisa el correo.",
    ExpiredCodeException: "El código venció. Pide uno nuevo.",
    LimitExceededException: "Demasiados intentos. Espera unos minutos.",
    TooManyRequestsException: "Demasiados intentos. Espera unos minutos.",
    NotAuthorizedException: "Documento o clave incorrectos.",
    UserNotFoundException: "Documento o clave incorrectos.",
    UserNotConfirmedException: "Tu cuenta aún no está verificada.",
    InvalidPasswordException: "La clave no cumple el formato.",
    InvalidParameterException: "Algún dato no tiene el formato correcto.",
    CodeDeliveryFailureException: "No se pudo enviar el correo. Revisa la dirección."
  };
  function mensaje(e) {
    if (!e) return "Ocurrió un error.";
    if (e.code && MENSAJES[e.code]) return MENSAJES[e.code];
    if (e.estado === 503) return e.detalle || "Sistema no disponible.";
    if (e.detalle) return e.detalle;
    return e.message || "Ocurrió un error. Intenta de nuevo.";
  }
  function promesa(fn) { return new Promise(function (ok, mal) { fn(function (err, r) { if (err) mal(err); else ok(r); }); }); }

  function registrar(datos) {
    return pool().then(function (p) {
      var atributos = [
        new AmazonCognitoIdentity.CognitoUserAttribute({ Name: "email", Value: datos.correo }),
        new AmazonCognitoIdentity.CognitoUserAttribute({ Name: "custom:rol", Value: datos.rol })
      ];
      return promesa(function (cb) { p.signUp(datos.documento, datos.pin, atributos, null, cb); });
    });
  }
  function confirmar(documento, codigo) {
    return pool().then(function (p) { return promesa(function (cb) { usuarioCognito(p, documento).confirmRegistration(codigo, true, cb); }); });
  }
  function reenviar(documento) {
    return pool().then(function (p) { return promesa(function (cb) { usuarioCognito(p, documento).resendConfirmationCode(cb); }); });
  }
  function entrar(documento, pin) {
    return pool().then(function (p) {
      return new Promise(function (ok, mal) {
        var detalles = new AmazonCognitoIdentity.AuthenticationDetails({ Username: documento, Password: pin });
        usuarioCognito(p, documento).authenticateUser(detalles, { onSuccess: ok, onFailure: mal });
      });
    });
  }
  function sesion() {
    return pool().then(function (p) {
      var u = p.getCurrentUser();
      if (!u) return null;
      return new Promise(function (ok) {
        u.getSession(function (err, s) { ok(err || !s || !s.isValid() ? null : s); });
      });
    });
  }
  function usuario(s) {
    var p = s.getIdToken().decodePayload();
    return { sub: p.sub, rol: p["custom:rol"], correo: p.email, documento: p["cognito:username"] };
  }
  function salir() {
    return pool().then(function (p) {
      var u = p.getCurrentUser();
      if (u) u.signOut();
      reiniciarFlujo(null);
      try { sessionStorage.removeItem("agro_perfil"); } catch (e) {}
    });
  }

  //---- api con el id token; los errores llegan como problem+json ----
  function api(metodo, ruta, cuerpo) {
    return sesion().then(function (s) {
      if (!s) { ir(pagina("00b-login")); throw { estado: 401, detalle: "sesion vencida" }; }
      var opciones = { method: metodo, headers: { Authorization: "Bearer " + s.getIdToken().getJwtToken() }, cache: "no-store" };
      if (cuerpo !== undefined) {
        opciones.headers["Content-Type"] = "application/json";
        opciones.body = JSON.stringify(cuerpo);
      }
      return fetch("/api/v1" + ruta, opciones).then(function (r) {
        var tipo = r.headers.get("content-type") || "";
        var lectura = tipo.indexOf("json") >= 0 ? r.json() : Promise.resolve(null);
        return lectura.then(function (j) {
          if (r.ok) return j;
          if (r.status === 401) ir(pagina("00b-login"));
          throw { estado: r.status, titulo: j && j.title, detalle: j && j.detail };
        });
      });
    });
  }

  //perfil en cache de la pestana: null = no existe todavia
  function perfil(forzar) {
    var cache = leer("agro_perfil");
    if (cache && !forzar) return Promise.resolve(cache.perfil);
    return api("GET", "/perfil").then(function (p) {
      grabar("agro_perfil", { perfil: p });
      return p;
    }, function (e) {
      if (e.estado === 404) { grabar("agro_perfil", { perfil: null }); return null; }
      throw e;
    });
  }

  /* guardas de navegacion (decision 2a del 7c): llevan al ultimo paso valido; no es seguridad (eso lo hace la api)
     fase: "registro" (antes de la cuenta), "alta" (con sesion, sin perfil), "app" (con sesion y perfil) */
  function proteger(opciones) {
    var paso = opciones.paso;
    var f = flujo();
    if (opciones.fase === "registro") {
      if (paso === "03-otp" && f.cuenta && f.cuenta.registrada) { mostrar(); return Promise.resolve({ flujo: f }); }
      if (!f.rol) { ir(pagina("00-rol")); return new Promise(function () {}); }
      var lista = REGISTRO[f.rol];
      if (lista.indexOf(paso) < 0) { ir(pagina(lista[0])); return new Promise(function () {}); }
      for (var i = 0; i < lista.indexOf(paso); i++) {
        if (f.hechos.indexOf(lista[i]) < 0) { ir(pagina(lista[i])); return new Promise(function () {}); }
      }
      mostrar();
      return Promise.resolve({ flujo: f });
    }
    return sesion().then(function (s) {
      if (!s) { ir(pagina("00b-login")); return new Promise(function () {}); }
      var u = usuario(s);
      if (f.sub !== u.sub) { reiniciarFlujo(u.rol); f = flujo(); f.sub = u.sub; f.rol = u.rol; guardarFlujo(f); try { sessionStorage.removeItem("agro_perfil"); } catch (e) {} }
      return perfil().then(function (p) {
        if (opciones.fase === "alta") {
          if (p) { ir(INICIO[u.rol]); return new Promise(function () {}); }
          var lista = ALTA[u.rol];
          if (lista.indexOf(paso) < 0) { ir(pagina(lista[0])); return new Promise(function () {}); }
          for (var i = 0; i < lista.indexOf(paso); i++) {
            if (f.hechos.indexOf(lista[i]) < 0) { ir(pagina(lista[i])); return new Promise(function () {}); }
          }
        } else {
          if (!p) { ir(pagina(ALTA[u.rol][0])); return new Promise(function () {}); }
          if (opciones.rol && opciones.rol !== u.rol) { ir(INICIO[u.rol]); return new Promise(function () {}); }
        }
        mostrar();
        return { usuario: u, perfil: p, flujo: flujo() };
      });
    });
  }

  //despues de iniciar sesion: a su inicio si ya tiene perfil, o al primer paso del alta
  function destinoTrasLogin() {
    return sesion().then(function (s) {
      var u = usuario(s);
      reiniciarFlujo(u.rol);
      var f = flujo(); f.sub = u.sub; guardarFlujo(f);
      try { sessionStorage.removeItem("agro_perfil"); } catch (e) {}
      return perfil(true).then(function (p) { return p ? INICIO[u.rol] : pagina(ALTA[u.rol][0]); });
    });
  }

  //---- utilidades de la app (entrega 2) ----
  //ubigeo de demostracion (referencia, no son datos personales); el mismo de la pantalla de ubicacion
  var UBIGEO = {
    "Cusco": { "Quispicanchi": ["Andahuaylillas", "Urcos"], "Calca": ["Pisac", "Lamay"], "Urubamba": ["Ollantaytambo", "Maras"] },
    "La Libertad": { "Trujillo": ["Laredo", "Moche"], "Virú": ["Chao", "Guadalupito"], "Sánchez Carrión": ["Huamachuco", "Sanagorán"] }
  };
  function soles(texto) {
    var n = Number(texto || 0);
    return "S/ " + n.toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function aDinero(numero) {
    var n = Math.round(Number(numero || 0) * 100);
    return Math.floor(n / 100) + "." + ("0" + (n % 100)).slice(-2);
  }
  function kg(n) { return Number(n).toLocaleString("es-PE") + " kg"; }
  function escapar(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function parametro(nombre) { return new URLSearchParams(location.search).get(nombre); }
  //lista completa siguiendo el cursor (maximo 5 paginas para la demo)
  function listarTodo(ruta) {
    var items = [];
    function pagina(cursor, n) {
      var sep = ruta.indexOf("?") >= 0 ? "&" : "?";
      return api("GET", ruta + sep + "limite=50" + (cursor ? "&cursor=" + encodeURIComponent(cursor) : "")).then(function (r) {
        items = items.concat(r.items || []);
        return r.siguienteCursor && n < 5 ? pagina(r.siguienteCursor, n + 1) : items;
      });
    }
    return pagina(null, 1);
  }
  //los post de campana y oferta responden 202: se consulta hasta que el worker lo registre
  function esperar(fn, segundos) {
    var limite = Date.now() + (segundos || 20) * 1000;
    function intento() {
      return fn().then(function (r) {
        if (r) return r;
        if (Date.now() > limite) throw { detalle: "Se está procesando; aparecerá en unos segundos." };
        return new Promise(function (ok) { setTimeout(ok, 1500); }).then(intento);
      }, function (e) {
        if (e.estado !== 404 || Date.now() > limite) throw e;
        return new Promise(function (ok) { setTimeout(ok, 1500); }).then(intento);
      });
    }
    return intento();
  }
  //borrador de campana en la pestana: id generado al empezar (clave de idempotencia)
  function borrador(cambios) {
    var b = leer("agro_borrador");
    if (!b) b = { campaniaId: uuid(), fotos: [] };
    if (cambios) Object.keys(cambios).forEach(function (k) { b[k] = cambios[k]; });
    grabar("agro_borrador", b);
    return b;
  }
  function borrarBorrador() { try { sessionStorage.removeItem("agro_borrador"); } catch (e) {} }
  //foto directo a s3 con url prefirmada (post); la etiqueta la pone la lambda despues
  function subirFoto(campaniaId, archivo) {
    var fotoId = uuid();
    return api("POST", "/campanas/" + campaniaId + "/fotos/url", { fotoId: fotoId, tipoContenido: archivo.type, tamanoBytes: archivo.size }).then(function (r) {
      var datos = new FormData();
      Object.keys(r.campos).forEach(function (k) { datos.append(k, r.campos[k]); });
      datos.append("file", archivo);
      return fetch(r.url, { method: "POST", body: datos }).then(function (s3) {
        if (!s3.ok) throw { detalle: "S3 rechazó la foto (" + s3.status + ")" };
        return fotoId;
      });
    });
  }
  var catalogoCache = null;
  function catalogo() {
    if (catalogoCache) return Promise.resolve(catalogoCache);
    return api("GET", "/catalogo/cultivos").then(function (l) {
      catalogoCache = {};
      l.forEach(function (c) { catalogoCache[c.slug] = c; });
      return catalogoCache;
    });
  }
  function nombreCultivo(cat, slug) { return cat && cat[slug] ? cat[slug].nombre : slug; }
  function salirA() { salir().then(function () { location.replace("/onboarding/00-inicio.html"); }); }

  window.Agro = {
    UBIGEO: UBIGEO, soles: soles, aDinero: aDinero, kg: kg, escapar: escapar, parametro: parametro, listarTodo: listarTodo,
    esperar: esperar, borrador: borrador, borrarBorrador: borrarBorrador, subirFoto: subirFoto, catalogo: catalogo,
    nombreCultivo: nombreCultivo, salirA: salirA,
    flujo: flujo, guardarFlujo: guardarFlujo, reiniciarFlujo: reiniciarFlujo, completar: completar, siguiente: siguiente,
    registrar: registrar, confirmar: confirmar, reenviar: reenviar, entrar: entrar, sesion: sesion, usuario: usuario, salir: salir,
    api: api, perfil: perfil, proteger: proteger, destinoTrasLogin: destinoTrasLogin, mensaje: mensaje, uuid: uuid,
    pagina: pagina, ir: function (r) { window.location.href = r; }, INICIO: INICIO
  };
})();
