/* Sugerencias de veterinaria mientras se escribe.
 *
 * Consulta el mismo endpoint que ya usa la pantalla de Resultados
 * (GET /clientes/buscar, sobre db.search_clients_for_dashboard), así que busca en los 992
 * clientes y no en la página que se está viendo. Elegir una sugerencia abre su ficha.
 *
 * Las inactivas se muestran igual, con su etiqueta: que un cliente no aparezca hace pensar
 * que no está cargado, y casi siempre está pero inactivo.
 */
(function () {
  var caja = document.querySelector("[data-client-suggest]");
  var lista = document.querySelector("[data-client-suggest-list]");
  if (!caja || !lista) return;
  var destino = caja.getAttribute("data-client-suggest-target") || "/clientes/";
  var timer = null;

  function pintar(filas) {
    lista.innerHTML = "";
    if (!filas.length) {
      lista.hidden = true;
      return;
    }
    filas.forEach(function (f) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = destino + f.id;
      var nombre = document.createElement("strong");
      nombre.textContent = f.nombre;
      var detalle = document.createElement("span");
      detalle.textContent =
        (f.nit ? "NIT " + f.nit : "sin NIT") +
        (f.zona ? " · " + f.zona : "") +
        (f.activo ? "" : " · inactivo");
      a.appendChild(nombre);
      a.appendChild(detalle);
      li.appendChild(a);
      lista.appendChild(li);
    });
    lista.hidden = false;
  }

  caja.addEventListener("input", function () {
    clearTimeout(timer);
    var q = caja.value.trim();
    if (q.length < 2) {
      lista.hidden = true;
      return;
    }
    timer = setTimeout(function () {
      fetch("/clientes/buscar?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (d) { pintar(d.resultados || []); })
        .catch(function () { lista.hidden = true; });
    }, 220);
  });

  // Enter envía el formulario (búsqueda completa en la tabla), no elige la sugerencia.
  caja.addEventListener("keydown", function (e) {
    if (e.key === "Escape") lista.hidden = true;
  });

  document.addEventListener("click", function (e) {
    if (!lista.contains(e.target) && e.target !== caja) lista.hidden = true;
  });
})();
