/* ============================================================
   tooltip.js — Interacción del tooltip informativo
   Origen Figma: file qkyZrZ17ur7zSThXvLvqDh (flujo de préstamo)

   REGLA DE PRODUCTO:
   El tooltip informativo es SIEMPRE interactivo. Se abre cuando el cliente
   selecciona el ícono (i) (tap/click/Enter/Espacio) y se cierra al volver
   a tocarlo, al tocar fuera, o con la tecla Escape.

   Uso (markup):
   <span class="tooltip-anchor" data-tooltip>
     <button class="info-icon-button" type="button" aria-label="Más información"
             aria-expanded="false" aria-describedby="tt-1"> ...svg (i)... </button>
     <span class="tooltip" id="tt-1" role="tooltip">Texto informativo</span>
   </span>

   Inicialización: initTooltips() se autoejecuta en DOMContentLoaded.
   ============================================================ */

(function () {
  "use strict";

  function closeAll(except) {
    document.querySelectorAll(".tooltip-anchor.is-open").forEach(function (anchor) {
      if (anchor === except) return;
      anchor.classList.remove("is-open");
      var btn = anchor.querySelector(".info-icon-button");
      if (btn) btn.setAttribute("aria-expanded", "false");
    });
  }

  function toggle(anchor) {
    var isOpen = anchor.classList.contains("is-open");
    closeAll(anchor);
    if (isOpen) {
      anchor.classList.remove("is-open");
    } else {
      anchor.classList.add("is-open");
    }
    var btn = anchor.querySelector(".info-icon-button");
    if (btn) btn.setAttribute("aria-expanded", String(!isOpen));
  }

  function initTooltips(root) {
    root = root || document;

    root.querySelectorAll("[data-tooltip]").forEach(function (anchor) {
      var btn = anchor.querySelector(".info-icon-button");
      if (!btn || btn.dataset.tooltipBound) return;
      btn.dataset.tooltipBound = "true";

      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        toggle(anchor);
      });
    });

    // Cerrar al tocar fuera
    if (!document.body.dataset.tooltipGlobalBound) {
      document.body.dataset.tooltipGlobalBound = "true";
      document.addEventListener("click", function () { closeAll(null); });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") closeAll(null);
      });
    }
  }

  // Exponer y autoiniciar
  window.initTooltips = initTooltips;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { initTooltips(); });
  } else {
    initTooltips();
  }
})();
