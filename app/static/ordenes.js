/* Pedidos: eliminar una orden o quitarle un análisis (pedido de A3, 2026-11-09).
 * El servidor decide si se puede (muestras o resultados en el laboratorio, pago en línea
 * aprobado o factura emitida lo frenan) y guarda el respaldo antes de tocar. Acá solo se
 * pregunta, se muestra el motivo si no se pudo y se avisa lo que hay que revisar. */
(function () {
  function enviar(url, cuerpo) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) })
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || "No se pudo completar"); return d; }); });
  }
  function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function plata(n) { return "$" + Number(n || 0).toLocaleString("es-CO"); }
  function avisar(avisos) { if (avisos && avisos.length) window.alert(avisos.join("\n\n")); }
  function marcar(fila, texto) {
    var flag = fila && fila.querySelector("[data-orden-flag]");
    if (flag) { flag.textContent = texto; flag.style.color = "var(--danger)"; }
  }

  function pintarLineas(fila, requestId, datos) {
    var caja = document.createElement("tr");
    caja.setAttribute("data-orden-lineas-caja", requestId);
    caja.setAttribute("data-cols-tagged", "1");
    var items = (datos.lines || []).map(function (l, i) {
      var boton = datos.lines.length > 1
        ? ' <button type="button" class="reject-btn" data-linea-quitar="' + i + '" data-linea-code="' + esc(l.code) + '" data-linea-nombre="' + esc(l.name) + '">Quitar</button>'
        : "";
      return "<li>" + esc(l.tipo) + " · " + esc(l.code) + " " + esc(l.name) + " · <strong>" + plata(l.price) + "</strong>" + boton + "</li>";
    }).join("");
    var nota = !datos.lines.length
      ? "Esta orden no tiene análisis con precio para quitar."
      : datos.lines.length === 1 ? "Es el único análisis: para sacarlo, elimina la orden." : "Total: " + plata(datos.total);
    caja.innerHTML = '<td colspan="20"><strong>Análisis de la orden ' + esc(datos.order_number || "") + "</strong><ul>" + items + '</ul><small class="muted-text">' + esc(nota) + "</small></td>";
    fila.insertAdjacentElement("afterend", caja);
    caja.addEventListener("click", function (e) {
      var boton = e.target.closest("[data-linea-quitar]");
      if (!boton) return;
      if (!window.confirm("¿Quitar «" + boton.dataset.lineaNombre + "» de la orden? El total se recalcula y el cambio queda en el historial.")) return;
      boton.disabled = true;
      enviar("/api/dashboard/order-line-delete", { request_id: requestId, index: Number(boton.dataset.lineaQuitar), code: boton.dataset.lineaCode })
        .then(function (d) { avisar(d.avisos); window.location.reload(); })
        .catch(function (err) { boton.disabled = false; marcar(fila, err.message); });
    });
  }

  function banderaPedido(pedidoId, texto, mal) {
    var flag = document.querySelector('[data-pedido-flag="' + pedidoId + '"]');
    if (flag) { flag.textContent = texto; flag.style.color = mal ? "var(--danger)" : ""; }
    else if (mal) window.alert(texto);
  }

  // Link de pago en línea: devuelve el vigente o crea uno, y lo deja copiado.
  document.addEventListener("click", function (e) {
    var pago = e.target.closest("[data-pago-link]");
    if (!pago) return;
    pago.disabled = true;
    enviar("/api/dashboard/pedido-pago-link", { pedido_id: pago.dataset.pagoLink })
      .then(function (d) {
        var listo = function () { pago.textContent = "Link copiado"; pago.disabled = false; };
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(d.url).then(listo, function () { window.prompt("Link de pago del pedido:", d.url); listo(); });
        else { window.prompt("Link de pago del pedido:", d.url); listo(); }
      })
      .catch(function (err) { pago.disabled = false; window.alert(err.message); });
  });

  // Emitir a la DIAN: no se deshace, así que se confirma dos veces y con el pedido a la vista.
  document.addEventListener("click", function (e) {
    var emitir = e.target.closest("[data-pedido-emitir]");
    if (!emitir) return;
    var cual = "el pedido " + emitir.dataset.pedidoNumero + " de " + emitir.dataset.pedidoCliente;
    if (!window.confirm("Vas a EMITIR ante la DIAN la factura de " + cual + ".\n\nUna factura emitida no se puede deshacer: solo se corrige con una nota crédito en Alegra.\n\n¿Ya revisaste el borrador?")) return;
    if (!window.confirm("Última confirmación: ¿emitir la factura de " + cual + "?")) return;
    emitir.disabled = true;
    banderaPedido(emitir.dataset.pedidoEmitir, "Emitiendo…", false);
    enviar("/api/dashboard/pedido-emitir", { pedido_id: emitir.dataset.pedidoEmitir })
      .then(function (d) { banderaPedido(emitir.dataset.pedidoEmitir, "Emitida " + (d.numero || ""), false); setTimeout(function () { window.location.reload(); }, 1500); })
      .catch(function (err) { emitir.disabled = false; banderaPedido(emitir.dataset.pedidoEmitir, err.message, true); });
  });

  document.addEventListener("click", function (e) {
    var ver = e.target.closest("[data-orden-lineas]");
    if (ver) {
      var fila = ver.closest("tr");
      var abierta = document.querySelector('[data-orden-lineas-caja="' + ver.dataset.ordenLineas + '"]');
      if (abierta) { abierta.remove(); return; }
      fetch("/api/dashboard/order-lines?request_id=" + encodeURIComponent(ver.dataset.ordenLineas))
        .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || "No se pudo leer la orden"); return d; }); })
        .then(function (d) { pintarLineas(fila, ver.dataset.ordenLineas, d); })
        .catch(function (err) { marcar(fila, err.message); });
      return;
    }
    var borrar = e.target.closest("[data-orden-eliminar]");
    if (!borrar) return;
    var filaOrden = borrar.closest("tr");
    var cual = "la orden " + (borrar.dataset.ordenNumero || "") + (borrar.dataset.ordenPaciente ? " (" + borrar.dataset.ordenPaciente + ")" : "");
    if (!window.confirm("¿Eliminar " + cual + "? Se borra de la plataforma y queda un respaldo en el historial. No se toca nada en Alegra.")) return;
    borrar.disabled = true;
    enviar("/api/dashboard/order-delete", { request_id: borrar.dataset.ordenEliminar })
      .then(function (d) { avisar(d.avisos); window.location.reload(); })
      .catch(function (err) { borrar.disabled = false; marcar(filaOrden, err.message); });
  });
})();
