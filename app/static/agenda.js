/* Agenda de recogidas: reasignar motorizado y reprogramar fecha.
 *
 * No hay endpoint nuevo: se llama a /api/dashboard/request-operation, el mismo
 * que ya usa la tabla de solicitudes, que valida y deja el evento de auditoría.
 * Tras un cambio de fecha la tarjeta tiene que mudarse de columna, así que se
 * recarga la vista; el cambio de motorizado también, para que las cuentas por
 * fila queden bien.
 */
(function () {
  var aviso = document.getElementById("agenda-flag");

  function decir(texto, error) {
    if (!aviso) return;
    aviso.textContent = texto;
    aviso.style.color = error ? "var(--os-danger, #b3261e)" : "";
  }

  function guardar(requestId, cambio) {
    decir("Guardando…");
    fetch("/api/dashboard/request-operation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ request_id: requestId }, cambio)),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function () {
        decir("Guardado");
        window.location.reload();
      })
      .catch(function () {
        decir("No se pudo guardar el cambio", true);
      });
  }

  document.querySelectorAll(".agenda-card").forEach(function (card) {
    var requestId = card.getAttribute("data-request-id");

    var courier = card.querySelector("[data-agenda-courier]");
    if (courier) {
      courier.addEventListener("change", function () {
        guardar(requestId, { assigned_courier_id: courier.value || null });
      });
    }

    var fecha = card.querySelector("[data-agenda-date]");
    if (fecha) {
      fecha.addEventListener("change", function () {
        if (!fecha.value) return;
        guardar(requestId, { scheduled_pickup_date: fecha.value });
      });
    }
  });
})();
