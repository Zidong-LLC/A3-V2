/* Equipo de motorizados: cada tarjeta se edita y se guarda de verdad.
 *
 * Antes el color solo repintaba el cuadrito en pantalla y se perdía al recargar, y no
 * había forma de crear un motorizado, renombrarlo ni darlo de baja. Todo pasa ahora por
 * /api/dashboard/courier (edición) y /api/dashboard/courier-create (alta), que validan
 * del lado del servidor.
 */
(function () {
  var contenedor = document.querySelector(".courier-cards");
  if (!contenedor) return;

  function avisar(tarjeta, texto, error) {
    var flag = tarjeta.querySelector("[data-courier-flag]");
    if (!flag) return;
    flag.textContent = texto;
    flag.style.color = error ? "var(--danger)" : "";
    if (!error) setTimeout(function () { flag.textContent = ""; }, 2000);
  }

  function guardar(tarjeta, campo, valor) {
    var cuerpo = { courier_id: tarjeta.dataset.courierId };
    cuerpo[campo] = valor;
    avisar(tarjeta, "Guardando…");
    return fetch("/api/dashboard/courier", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.d.error || "No se pudo guardar");
        avisar(tarjeta, "Guardado");
        return res.d;
      })
      .catch(function (e) { avisar(tarjeta, e.message, true); throw e; });
  }

  contenedor.addEventListener("change", function (e) {
    var control = e.target.closest("[data-courier-field]");
    if (!control) return;
    var tarjeta = control.closest(".courier-card");
    var campo = control.dataset.courierField;
    var valor = control.type === "checkbox" ? control.checked : control.value;

    guardar(tarjeta, campo, valor).then(function () {
      if (campo === "is_active") {
        // La tarjeta se atenúa y la etiqueta acompaña, sin recargar la pantalla.
        tarjeta.classList.toggle("is-inactive", !valor);
        var etiqueta = control.parentElement;
        etiqueta.lastChild.textContent = valor ? " Activo" : " Inactivo";
      }
      if (campo === "color") {
        var punto = tarjeta.querySelector(".courier-dot");
        if (punto) punto.style.background = valor;
      }
    }).catch(function () {
      // El valor de la pantalla vuelve a lo que había: no se guardó nada.
      if (control.type === "checkbox") control.checked = !valor;
    });
  });

  // ── Alta ───────────────────────────────────────────────────────────────────
  var form = document.querySelector("[data-courier-form]");
  var botonNuevo = document.querySelector("[data-courier-new]");
  var flagNuevo = document.querySelector("[data-courier-new-flag]");

  if (botonNuevo && form) {
    botonNuevo.addEventListener("click", function () {
      form.hidden = !form.hidden;
      if (!form.hidden) form.querySelector('[name="name"]').focus();
    });
    form.querySelector("[data-courier-cancel]").addEventListener("click", function () {
      form.reset();
      form.hidden = true;
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var datos = new FormData(form);
      flagNuevo.textContent = "Creando…";
      fetch("/api/dashboard/courier-create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: datos.get("name"),
          phone: datos.get("phone"),
          color: datos.get("color"),
          availability: datos.get("availability"),
        }),
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.d.error || "No se pudo crear");
          flagNuevo.textContent = "Creado";
          // Se recarga para que el nuevo aparezca con su carga y en los desplegables.
          window.location.reload();
        })
        .catch(function (e) { flagNuevo.textContent = e.message; });
    });
  }
})();
