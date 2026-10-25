/* Ficha del cliente: guarda solo los datos que cambiaron y permite dar de baja.
 * La baja es segura: si el cliente tiene historia, el servidor lo desactiva en vez de
 * eliminarlo (app/dashboard.py, delete_client). */
(function () {
  var ficha = document.querySelector("[data-ficha-cliente]");
  if (!ficha) return;
  var flag = ficha.querySelector("[data-ficha-flag]");
  var campos = ficha.querySelectorAll(".ficha-edit [name]");

  function valor(control) {
    if (control.type === "checkbox") return control.checked;
    if (control.name === "electronic_invoice") return control.value === "true";
    return control.value;
  }
  var inicial = {};
  campos.forEach(function (c) { inicial[c.name] = valor(c); });

  function enviar(url, cuerpo) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) })
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || "No se pudo guardar"); return d; }); });
  }

  var guardar = ficha.querySelector("[data-ficha-guardar]");
  if (guardar) guardar.addEventListener("click", function () {
    var cambios = {};
    campos.forEach(function (c) { if (valor(c) !== inicial[c.name]) cambios[c.name] = valor(c); });
    if (!Object.keys(cambios).length) { flag.textContent = "No hay cambios"; return; }
    flag.textContent = "Guardando…";
    enviar("/api/dashboard/client-ficha", { client_id: ficha.dataset.clientId, cambios: cambios })
      .then(function () { flag.textContent = "Guardado"; window.location.reload(); })
      .catch(function (e) { flag.textContent = e.message; });
  });

  var baja = ficha.querySelector("[data-ficha-baja]");
  if (baja) baja.addEventListener("click", function () {
    var nombre = baja.dataset.clinicName || "este cliente";
    if (!window.confirm("¿Dar de baja a " + nombre + "? Si tiene solicitudes, pedidos, resultados o facturas, " +
                        "se desactiva y conserva su historia; si no, se elimina.")) return;
    flag.textContent = "Procesando…";
    enviar("/api/dashboard/client-delete", { client_id: ficha.dataset.clientId })
      .then(function (d) {
        if (d.deactivated) { flag.textContent = "Desactivado: tiene historia, se conserva."; window.location.reload(); }
        else window.location.href = "/clientes";
      })
      .catch(function (e) { flag.textContent = e.message; });
  });
})();
