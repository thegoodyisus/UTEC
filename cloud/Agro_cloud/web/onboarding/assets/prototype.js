/* ============================================================
   Prototipo AgroCredit — helpers de simulación (TODO ES FICTICIO)
   No hay backend, ni validaciones reales, ni permisos reales.
   Solo lógica en cliente para poder recorrer el flujo.
   ============================================================ */
(function () {
  "use strict";

  // Navegación simple entre pantallas.
  window.goTo = function (page) {
    window.location.href = page;
  };

  // Marca un campo con error (usa clases del design-system).
  function setError(field, message) {
    field.classList.add("text-field--error");
    var input = field.querySelector(".text-field__input");
    var msg = field.querySelector(".text-field__error");
    if (input) input.setAttribute("aria-invalid", "true");
    if (!msg) {
      msg = document.createElement("span");
      msg.className = "text-field__error";
      field.appendChild(msg);
    }
    msg.textContent = message;
  }
  function clearError(field) {
    field.classList.remove("text-field--error");
    var input = field.querySelector(".text-field__input");
    var msg = field.querySelector(".text-field__error");
    if (input) input.removeAttribute("aria-invalid");
    if (msg) msg.textContent = "";
  }

  // Validaciones FICTICIAS (solo formato básico de demostración).
  var validators = {
    celular: function (v) { return /^[0-9]{9}$/.test(v.trim()); },
    correo: function (v) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()); },
    dni: function (v) { return /^[0-9]{8}$/.test(v.trim()); },
    ruc: function (v) { return /^[0-9]{11}$/.test(v.trim()); },
    requerido: function (v) { return v.trim().length > 0; }
  };

  // Valida un formulario marcado con data-validate en cada .text-field.
  // Cada campo declara data-rule="celular|correo|dni|ruc|requerido".
  window.validateForm = function (formSelector, onValid) {
    var form = document.querySelector(formSelector);
    if (!form) return;
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var ok = true;
      var fields = form.querySelectorAll(".text-field[data-rule]");
      fields.forEach(function (field) {
        var input = field.querySelector(".text-field__input");
        var rule = field.getAttribute("data-rule");
        // Regla dinámica de documento según tipo seleccionado (soporta varios grupos de radios).
        if (rule === "documento") {
          var tipo = form.querySelector('input[name="tipo-doc"]:checked')
                  || form.querySelector('input[name="rep-tipo"]:checked')
                  || form.querySelector('input[type="radio"][value="RUC"]:checked, input[type="radio"][value="DNI"]:checked');
          rule = tipo && tipo.value === "RUC" ? "ruc" : "dni";
        }
        var fn = validators[rule] || validators.requerido;
        if (!input || !fn(input.value)) {
          ok = false;
          setError(field, field.getAttribute("data-error") || "Revisa este dato.");
        } else {
          clearError(field);
        }
      });
      if (ok && typeof onValid === "function") onValid(form);
    });
  };

  // OTP: auto-avance entre celdas y validación ficticia (código demo: 123456).
  window.initOtp = function (opts) {
    opts = opts || {};
    var demoCode = opts.demoCode || "123456";
    var cells = Array.prototype.slice.call(document.querySelectorAll(".otp-input__cell"));
    cells.forEach(function (cell, i) {
      cell.value = "";
      cell.addEventListener("input", function () {
        if (cell.value && i < cells.length - 1) cells[i + 1].focus();
      });
      cell.addEventListener("keydown", function (e) {
        if (e.key === "Backspace" && !cell.value && i > 0) cells[i - 1].focus();
      });
    });
    var btn = opts.button && document.querySelector(opts.button);
    var errEl = opts.error && document.querySelector(opts.error);
    if (btn) {
      btn.addEventListener("click", function () {
        var code = cells.map(function (c) { return c.value; }).join("");
        if (code === demoCode) {
          if (opts.onValid) opts.onValid();
        } else if (errEl) {
          errEl.textContent = "Código incorrecto. Pista de prueba: " + demoCode;
          errEl.style.display = "block";
        }
      });
    }
  };

  // Evalúa reglas de contraseña en vivo y coincidencia (ficticio).
  window.initPassword = function (opts) {
    var pass = document.querySelector(opts.password);
    var confirm = document.querySelector(opts.confirm);
    var submit = document.querySelector(opts.button);
    var rules = {
      length: document.querySelector('[data-rule-id="length"]'),
      upper: document.querySelector('[data-rule-id="upper"]'),
      number: document.querySelector('[data-rule-id="number"]'),
      match: document.querySelector('[data-rule-id="match"]')
    };
    function mark(el, ok) { if (el) el.classList.toggle("is-valid", ok); }
    function evaluate() {
      var v = pass.value;
      var okLen = v.length >= 8, okUp = /[A-Z]/.test(v), okNum = /[0-9]/.test(v);
      var okMatch = v.length > 0 && v === confirm.value;
      mark(rules.length, okLen); mark(rules.upper, okUp);
      mark(rules.number, okNum); mark(rules.match, okMatch);
      var allOk = okLen && okUp && okNum && okMatch;
      if (submit) submit.disabled = !allOk;
      return allOk;
    }
    [pass, confirm].forEach(function (el) { if (el) el.addEventListener("input", evaluate); });
    if (submit) {
      submit.disabled = true;
      submit.addEventListener("click", function () { if (evaluate() && opts.onValid) opts.onValid(); });
    }
  };

  // Simula la solicitud de un permiso/biometría del dispositivo.
  window.simulatePermission = function (label, onResult) {
    // Sin diálogo nativo real: se simula concesión inmediata.
    if (onResult) onResult(true, label);
  };
})();

/* ============================================================
   i18n del prototipo (ficticio, solo para la bienvenida).
   Cambia textos con data-i18n según el idioma elegido.
   ============================================================ */
(function () {
  "use strict";
  var DICT = {
    es: {
      hello: "Bienvenido a",
      start: "Empezar",
      langLabel: "Elige tu idioma",
      roleQuestion: "¿Cómo quieres usar AgroCredit?",
      roleFarmerT: "Soy Agricultor",
      roleFarmerD: "Publica tu producción y encuentra compradores formales.",
      roleBuyerT: "Soy Comprador",
      roleBuyerD: "Encuentra producción disponible y reserva volumen de agricultores.",
      soon: "Próximamente",
      b1t: "Publica tu producción",
      b1d: "Registra tus cultivos y hazlos visibles para compradores formales.",
      b2t: "Encuentra compradores",
      b2d: "Empresas reservan tu volumen antes de la siembra, a precio de mercado.",
      b3t: "Negocia directamente",
      b3d: "Acuerda condiciones con compradores verificados, sin intermediarios.",
      cb1t: "Reserva volumen antes de la siembra",
      cb1d: "Asegura tu abastecimiento pactando el volumen con anticipación.",
      cb2t: "Productores y parcelas verificadas",
      cb2d: "Compra con confianza a agricultores y lotes validados.",
      cb3t: "Trato directo con el productor",
      cb3d: "Acuerdas volumen, precio y entrega con cada productor.",
      disclaimer: "Prototipo de demostración · datos ficticios"
    },
    qu: {
      hello: "Allin hamusqayki",
      start: "Qallariy",
      langLabel: "Rimayniykita akllay",
      roleQuestion: "¿Imaynatan AgroCredit-ta llamk'achiyta munanki?",
      roleFarmerT: "Chakra runam kani",
      roleFarmerD: "Kawsayniykita riqsichiy, rantiqkunata tariy.",
      roleBuyerT: "Rantiqmi kani",
      roleBuyerD: "Kawsay kaqta tariy, chakra runakunamanta mikhuyta waqaychay.",
      soon: "Ñaqhalla",
      b1t: "Kawsayniykita riqsichiy",
      b1d: "Chakraykikunata qillqay, rantiqkunapaq rikuchinapaq.",
      b2t: "Rantiqkunata tariy",
      b2d: "Empresakuna mikhuyniykita tarpuy ñawpaqta waqaychanku, qhatu chaninpi.",
      b3t: "Negocia directamente",
      b3d: "Acuerda condiciones con compradores verificados, sin intermediarios.",
      cb1t: "Tarpuy manaraq volumen-ta waqaychay",
      cb1d: "Ñawpaqmanta volumen-ta rimanakuspa abastecimiento-ykita amachay.",
      cb2t: "Riqsisqa chakra runakuna, riqsisqa chakrakuna",
      cb2d: "Riqsisqa chakra runakunamanta hark'aspa rantiy.",
      cb3t: "Trato directo con el productor",
      cb3d: "Acuerdas volumen, precio y entrega con cada productor.",
      disclaimer: "Qhaway prototipo · llulla willakuykuna"
    },
    ay: {
      hello: "Sumaya jutawi",
      start: "Qalltaña",
      langLabel: "Arumsa ajlliña",
      roleQuestion: "¿Kunjamsa AgroCredit apnaqaña munta?",
      roleFarmerT: "Yapuchirïtwa",
      roleFarmerD: "Yapuñama uñacht'ayaña, alañ munirinaka jikxataña.",
      roleBuyerT: "Alirïtwa",
      roleBuyerD: "Utji yapu jikxataña, yapuchirinakat yapuñ katuqaña.",
      soon: "Jank'akiw jutani",
      b1t: "Achunakama uñacht'ayaña",
      b1d: "Yapunakama qillqt'aña, alañ munirinakaru uñacht'ayañataki.",
      b2t: "Alañ munirinaka jikxataña",
      b2d: "Empresanakax yapuñ nayraru katuqapxi, qhatu chaninampi.",
      b3t: "Negocia directamente",
      b3d: "Acuerda condiciones con compradores verificados, sin intermediarios.",
      cb1t: "Yapuñ nayraru volumen katuqaña",
      cb1d: "Nayraru volumen arustʼasa abastecimientoma jarkʼaña.",
      cb2t: "Uñt'ata yapuchirinaka, uñt'ata yapunaka",
      cb2d: "Uñt'ata yapuchirinakat confianzampi alaña.",
      cb3t: "Trato directo con el productor",
      cb3d: "Acuerdas volumen, precio y entrega con cada productor.",
      disclaimer: "Uñacht'awi prototipo · k'ari yatiyawinaka"
    }
  };
  window.setLang = function (lang) {
    var d = DICT[lang] || DICT.es;
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      if (d[key]) el.textContent = d[key];
    });
    document.documentElement.setAttribute("lang", lang);
    document.querySelectorAll("[data-lang-btn]").forEach(function (btn) {
      btn.classList.toggle("is-selected", btn.getAttribute("data-lang-btn") === lang);
    });
  };
})();

/* ============================================================
   Teclado numérico dinámico + PIN (contraseña numérica ficticia).
   El keypad baraja las teclas en cada carga (dinámico).
   ============================================================ */
(function () {
  "use strict";
  function shuffle(arr) {
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    }
    return arr;
  }
  // opts: { keypad, dots, length=6, button, onValid }
  window.initPinPad = function (opts) {
    var length = opts.length || 6;
    var pin = "";
    var keypadEl = document.querySelector(opts.keypad);
    var dotsEl = document.querySelector(opts.dots);
    var btn = opts.button && document.querySelector(opts.button);

    function renderDots() {
      dotsEl.innerHTML = "";
      for (var i = 0; i < length; i++) {
        var dot = document.createElement("span");
        dot.className = "pin-dot" + (i < pin.length ? " is-filled" : "");
        dotsEl.appendChild(dot);
      }
      if (btn) btn.disabled = pin.length !== length;
    }
    function buildKeypad() {
      var nums = shuffle(["0","1","2","3","4","5","6","7","8","9"]);
      keypadEl.innerHTML = "";
      // 9 dígitos en la grilla, luego "Borrar", el dígito restante y sin acción extra
      var order = nums.slice(0, 9);
      var last = nums[9];
      order.forEach(function (n) { addKey(n); });
      // fila final: borrar, último dígito, (vacío)
      addAction("Borrar", function () { pin = pin.slice(0, -1); renderDots(); });
      addKey(last);
      var filler = document.createElement("span");
      keypadEl.appendChild(filler);
    }
    function addKey(n) {
      var k = document.createElement("button");
      k.type = "button";
      k.className = "keypad__key";
      k.textContent = n;
      k.setAttribute("data-testid", "keypad-" + n);
      k.addEventListener("click", function () {
        if (pin.length < length) { pin += n; renderDots(); }
      });
      keypadEl.appendChild(k);
    }
    function addAction(label, fn) {
      var k = document.createElement("button");
      k.type = "button";
      k.className = "keypad__key keypad__key--action";
      k.textContent = label;
      k.addEventListener("click", fn);
      keypadEl.appendChild(k);
    }

    buildKeypad();
    renderDots();
    if (btn) {
      btn.disabled = true;
      btn.addEventListener("click", function () {
        if (pin.length === length && opts.onValid) opts.onValid(pin);
      });
    }
  };
})();

/* ============================================================
   Perfil compartido (ficticio) entre onboarding y campaña.
   Usa localStorage del navegador solo para la demo (no backend).
   ============================================================ */
(function () {
  "use strict";
  window.saveProfile = function (patch) {
    var cur = window.loadProfile();
    Object.assign(cur, patch);
    try { localStorage.setItem("agrocredit_profile", JSON.stringify(cur)); } catch (e) {}
  };
  window.loadProfile = function () {
    try { return JSON.parse(localStorage.getItem("agrocredit_profile")) || {}; }
    catch (e) { return {}; }
  };

  // Nombre registrado del agricultor (para que prevalezca en toda la demo).
  // profileName(): solo nombres (primer nombre para saludos).
  // profileFullName(): nombres + apellidos (para la campaña / productor).
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
})();
