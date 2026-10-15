// Interacciones de Euthyna: pestañas, filtros, apertura de detalle y aparición suave.
(function () {
  "use strict";

  // 1) Pestañas "Por votación" / "Por grupo"
  var botones = document.querySelectorAll(".vistas__btn");
  var paneles = document.querySelectorAll(".vista");
  function mostrar(nombre) {
    botones.forEach(function (b) {
      var on = b.getAttribute("data-vista") === nombre;
      b.classList.toggle("vistas__btn--on", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    paneles.forEach(function (p) {
      p.hidden = p.getAttribute("data-panel") !== nombre;
    });
  }
  botones.forEach(function (b) {
    b.addEventListener("click", function () { mostrar(b.getAttribute("data-vista")); });
  });
  mostrar("votacion");

  // 2) Filtros del historial de cada grupo (tema y fecha)
  var HOY = new Date("2026-10-02T00:00:00");
  document.querySelectorAll(".grupo__cuerpo").forEach(function (caja) {
    var chips = caja.querySelectorAll(".chip");
    var select = caja.querySelector(".select");
    var filas = caja.querySelectorAll(".hist__fila");
    var vacio = caja.querySelector(".vacio");
    if (!chips.length || !select) return;
    var tema = "";
    function aplicar() {
      var dias = select.value === "all" ? null : parseInt(select.value, 10);
      var visibles = 0;
      filas.forEach(function (f) {
        var okTema = !tema || f.getAttribute("data-tema") === tema;
        var okFecha = true;
        if (dias !== null) {
          var d = new Date(f.getAttribute("data-fecha") + "T00:00:00");
          okFecha = (HOY - d) / 86400000 <= dias;
        }
        var ok = okTema && okFecha;
        f.hidden = !ok;
        if (ok) visibles++;
      });
      if (vacio) vacio.hidden = visibles !== 0;
    }
    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        chips.forEach(function (o) { o.classList.remove("chip--on"); });
        c.classList.add("chip--on");
        tema = c.getAttribute("data-tema");
        aplicar();
      });
    });
    select.addEventListener("change", aplicar);
  });

  // 3) "Ver detalle" en las tarjetas abre la votación correspondiente
  function abrirVotacion(id) {
    var d = document.getElementById("votacion-" + id);
    if (!d) return;
    mostrar("votacion");
    d.open = true;
    d.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  document.querySelectorAll("[data-abre]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      abrirVotacion(a.getAttribute("data-abre"));
    });
  });

  // 4) Aparición suave de los bloques al hacer scroll
  var items = document.querySelectorAll(".aparece");
  if (!("IntersectionObserver" in window)) {
    items.forEach(function (el) { el.classList.add("visible"); });
    return;
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) { e.target.classList.add("visible"); io.unobserve(e.target); }
    });
  }, { threshold: 0.08 });
  items.forEach(function (el) { io.observe(el); });
})();
