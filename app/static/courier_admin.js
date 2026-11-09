/* Motorizados: eliminar, ver historial y trasladar o reemplazar (cierre v1).
 * El servidor decide si se puede eliminar (sin clientes, cobertura ni recogidas) y
 * el traslado siempre muestra primero cuántos registros va a mover. */
(function () {
  function enviar(url, cuerpo) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) })
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || "No se pudo completar"); return d; }); });
  }
  function esc(v) { return String(v == null ? "—" : v).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }

  // ── Eliminar e historial en cada tarjeta ────────────────────────────────────
  var tarjetas = document.querySelector(".courier-cards");
  if (tarjetas) tarjetas.addEventListener("click", function (e) {
    var tarjeta = e.target.closest(".courier-card");
    if (!tarjeta) return;
    var flag = tarjeta.querySelector("[data-courier-flag]");
    if (e.target.closest("[data-courier-delete]")) {
      var nombre = (tarjeta.querySelector(".courier-name") || {}).value || "este motorizado";
      if (!window.confirm("¿Eliminar a " + nombre + "? Solo se puede si no tiene clientes, cobertura ni recogidas.")) return;
      enviar("/api/dashboard/courier-delete", { courier_id: tarjeta.dataset.courierId })
        .then(function () { tarjeta.remove(); })
        .catch(function (err) { if (flag) { flag.textContent = err.message; flag.style.color = "var(--danger)"; } });
    }
    if (e.target.closest("[data-courier-historial]")) {
      var caja = tarjeta.querySelector("[data-courier-historial-box]");
      if (!caja.hidden) { caja.hidden = true; return; }
      fetch("/api/dashboard/historial?entidad=courier&id=" + encodeURIComponent(tarjeta.dataset.courierId))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var filas = (d.cambios || []).map(function (h) {
            var detalle = Object.keys(h.changes || {}).map(function (k) { return esc(k) + ": " + esc(h.changes[k]); }).join(" · ");
            return "<li>" + esc((h.created_at || "").slice(0, 16).replace("T", " ")) + " · " + esc(h.username) + " · " + esc(h.action) + " · " + detalle + "</li>";
          });
          caja.innerHTML = filas.length ? "<ul>" + filas.join("") + "</ul>" : "Sin cambios registrados todavía.";
          caja.hidden = false;
        });
    }
  });

  // ── Agregar municipio a la cobertura ───────────────────────────────────────
  var formMunicipio = document.querySelector("[data-municipio-form]");
  if (formMunicipio) formMunicipio.querySelector("[data-municipio-agregar]").addEventListener("click", function () {
    var flagM = formMunicipio.querySelector("[data-municipio-flag]");
    var nombre = formMunicipio.querySelector("[data-municipio-nombre]").value;
    flagM.textContent = "Guardando…";
    enviar("/api/dashboard/municipio", { nombre: nombre }).then(function (d) {
      flagM.textContent = d.en_mapa ? "Agregado" : "Agregado (sin punto en el mapa)";
      setTimeout(function () { window.location.reload(); }, 900);
    }).catch(function (e) { flagM.textContent = e.message; });
  });

  // ── Traslado o reemplazo ────────────────────────────────────────────────────
  var panel = document.querySelector("[data-traslado]");
  if (!panel) return;
  var resumen = panel.querySelector("[data-traslado-resumen]");
  var confirmar = panel.querySelector("[data-traslado-confirmar]");
  var fecha = panel.querySelector('[name="fecha"]');
  if (!fecha.value) { var hoy = new Date(); hoy.setMinutes(hoy.getMinutes() - hoy.getTimezoneOffset()); fecha.value = hoy.toISOString().slice(0, 10); }

  function datos(confirmado) {
    var v = function (n) { return panel.querySelector('[name="' + n + '"]'); };
    var cuerpo = { origen: v("origen").value, destino: v("destino").value, recogidas: v("recogidas").value,
                   fecha: v("fecha").value, zona: v("zona").value, clientes: v("clientes").value === "todos",
                   localidades: v("localidades").checked, confirmar: confirmado };
    if (v("clientes").value === "elegir") cuerpo.client_ids = marcados();
    return cuerpo;
  }

  // Clientes puntuales: se cargan los del motorizado de origen y se marcan los que pasan.
  var lista = panel.querySelector("[data-traslado-lista]");
  var cajas = panel.querySelector("[data-traslado-clientes]");
  var buscar = panel.querySelector("[data-traslado-buscar]");
  var cuenta = panel.querySelector("[data-traslado-cuenta]");
  function marcados() {
    return Array.prototype.map.call(cajas.querySelectorAll("input:checked"), function (c) { return c.value; });
  }
  function contar() { cuenta.textContent = marcados().length + " marcado(s)"; }
  function cargarClientes() {
    var modo = panel.querySelector('[name="clientes"]').value;
    lista.hidden = modo !== "elegir";
    if (modo !== "elegir") return;
    cajas.textContent = "Cargando…";
    var origen = panel.querySelector('[name="origen"]').value;
    fetch("/api/dashboard/courier-clients?courier_id=" + encodeURIComponent(origen)).then(function (r) { return r.json(); })
      .then(function (d) {
        var filas = d.clientes || [];
        cajas.innerHTML = filas.length ? filas.map(function (c) {
          var texto = c.nombre + (c.nit ? " · " + c.nit : "") + (c.zona ? " · " + c.zona : "");
          return '<label class="portal-check" style="display:block" data-texto="' + esc(texto.toLowerCase()) + '">' +
                 '<input type="checkbox" value="' + esc(c.id) + '"> ' + esc(texto) + "</label>";
        }).join("") : "Este motorizado no tiene clientes fijos.";
        contar();
      }).catch(function () { cajas.textContent = "No se pudo cargar la lista."; });
  }
  buscar.addEventListener("input", function () {
    var q = buscar.value.trim().toLowerCase();
    Array.prototype.forEach.call(cajas.querySelectorAll("label"), function (l) { l.hidden = q && l.dataset.texto.indexOf(q) < 0; });
  });
  function marcarVisibles(valor) {
    Array.prototype.forEach.call(cajas.querySelectorAll("label"), function (l) { if (!valor || !l.hidden) l.querySelector("input").checked = valor; });
    contar(); confirmar.hidden = true; resumen.textContent = "";
  }
  panel.querySelector("[data-traslado-marcar]").addEventListener("click", function () { marcarVisibles(true); });
  panel.querySelector("[data-traslado-desmarcar]").addEventListener("click", function () { marcarVisibles(false); });
  panel.addEventListener("change", function (e) {
    confirmar.hidden = true; resumen.textContent = ""; contar();
    if (e.target.name === "clientes" || e.target.name === "origen") cargarClientes();
  });
  panel.querySelector("[data-traslado-ver]").addEventListener("click", function () {
    resumen.textContent = "Calculando…";
    enviar("/api/dashboard/courier-transfer", datos(false)).then(function (d) {
      var p = d.plan;
      var total = p.clientes + p.localidades + p.zonas + p.recogidas;
      resumen.textContent = "Pasan a " + d.destino + ": " + p.recogidas + " recogida(s), " + p.clientes +
        " cliente(s), " + p.localidades + " localidad(es) y " + p.zonas + " zona(s)." + (total ? "" : " No hay nada para mover.");
      confirmar.hidden = !total;
    }).catch(function (e) { resumen.textContent = e.message; });
  });
  confirmar.addEventListener("click", function () {
    confirmar.hidden = true;
    resumen.textContent = "Trasladando…";
    enviar("/api/dashboard/courier-transfer", datos(true)).then(function (d) {
      var h = d.hecho;
      var sinAviso = h.recogidas - (d.avisos || 0);
      var aviso = !h.recogidas ? "" : sinAviso > 0
        ? " No le llegó el aviso de " + sinAviso + " recogida(s) (sin chat vinculado): avísale por otro medio."
        : " Se avisó al motorizado.";
      resumen.textContent = "Listo: " + h.recogidas + " recogida(s), " + h.clientes + " cliente(s), " +
        h.localidades + " localidad(es) y " + h.zonas + " zona(s) trasladados." + aviso;
      if (sinAviso <= 0) setTimeout(function () { window.location.reload(); }, 1800);
    }).catch(function (e) { resumen.textContent = e.message; });
  });
})();
