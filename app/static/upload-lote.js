/* Subida de informes en tandas (pedido de A3, 10/11: suben 400–500 por día).
 *
 * Un solo envío con todos los PDFs choca con el tope del servidor (64 MB, unos 20 informes).
 * Acá cada PDF viaja en su propio envío, de a dos a la vez, con barra de progreso: que uno
 * falle no frena al resto, y al final se ve cuáles fallaron y por qué. La clínica recibe UN
 * aviso por chat con la cantidad, no uno por informe.
 *
 * Sin veterinaria elegida no se sube nada: el destino lo decide una persona, nunca la
 * plataforma. Con un solo PDF queda el envío de siempre (solo se exige la veterinaria).
 */
(function () {
  var EN_PARALELO = 2;
  var FILAS = ["patient_name", "order_number", "owner_name", "exam_name"];

  function estado(form) {
    var caja = form.querySelector(".lote-estado");
    if (!caja) {
      caja = document.createElement("div");
      caja.className = "lote-estado";
      form.appendChild(caja);
    }
    return caja;
  }

  function avisar(form, texto, error) {
    var caja = estado(form);
    caja.innerHTML = "";
    var p = document.createElement("p");
    p.className = "approval-notice " + (error ? "error" : "ok");
    p.textContent = texto;
    caja.appendChild(p);
    return caja;
  }

  // El envío de UN archivo, con los datos de su fila pasados al índice 0 que lee el servidor.
  function datosDe(form, archivo, indice) {
    var datos = new FormData(form);
    datos.delete("pdf");
    Array.from(datos.keys()).forEach(function (clave) {
      if (/_\d+$/.test(clave)) datos.delete(clave);
    });
    FILAS.forEach(function (nombre) {
      var campo = form.querySelector('[name="' + nombre + "_" + indice + '"]');
      if (campo) datos.set(nombre + "_0", campo.value);
    });
    datos.append("pdf", archivo, archivo.name);
    datos.set("respuesta", "json");
    return datos;
  }

  function enviar(url, datos) {
    return fetch(url, { method: "POST", body: datos, credentials: "same-origin",
                        headers: { Accept: "application/json" } })
      .then(function (r) {
        if (r.status === 413) throw new Error("el archivo supera el tamaño permitido");
        if (!r.ok) throw new Error("el servidor respondió " + r.status);
        return r.json().catch(function () { throw new Error("la sesión venció: volvé a entrar"); });
      });
  }

  function cargar(form, archivos) {
    var boton = form.querySelector('button[type="submit"]');
    var entrada = form.querySelector('input[type="file"][name="pdf"]');
    var compartir = form.querySelector('[name="publish_now"]');
    var total = archivos.length, hechos = 0, subidos = 0, errores = [], siguiente = 0;

    var caja = avisar(form, "Subiendo 0 de " + total + "…", false);
    var barra = document.createElement("progress");
    barra.max = total;
    barra.value = 0;
    caja.appendChild(barra);
    boton.disabled = true;
    entrada.disabled = true;
    window.onbeforeunload = function () { return "Todavía se están subiendo informes."; };

    function uno() {
      if (siguiente >= total) return Promise.resolve();
      var indice = siguiente++;
      var archivo = archivos[indice];
      return enviar(form.action, datosDe(form, archivo, indice))
        .then(function (r) {
          subidos += r.subidos || 0;
          (r.errores || []).forEach(function (e) { errores.push(archivo.name + ": " + e); });
        })
        .catch(function (e) { errores.push(archivo.name + ": no se pudo subir (" + e.message + ")"); })
        .then(function () {
          hechos++;
          barra.value = hechos;
          caja.firstChild.textContent = "Subiendo " + hechos + " de " + total + "…";
          return uno();
        });
    }

    var hilos = [];
    for (var i = 0; i < Math.min(EN_PARALELO, total); i++) hilos.push(uno());
    Promise.all(hilos).then(function () {
      var compartidos = compartir && compartir.checked;
      return (compartidos && subidos ? avisarAlCliente(form, subidos) : Promise.resolve())
        .then(function () {
          window.onbeforeunload = null;
          terminar(form, subidos, errores, compartidos);
        });
    });
  }

  // Un solo mensaje por chat a la clínica con la cantidad. Si falla, los informes igual están.
  function avisarAlCliente(form, cantidad) {
    var datos = new FormData();
    datos.set("csrf_token", form.querySelector('[name="csrf_token"]').value);
    datos.set("client_id", form.querySelector('[name="client_id"]').value);
    datos.set("cantidad", String(cantidad));
    return fetch("/resultados/avisar-lote", { method: "POST", body: datos, credentials: "same-origin" })
      .catch(function () {});
  }

  function terminar(form, subidos, errores, compartidos) {
    var caja = avisar(form, subidos + (subidos === 1 ? " informe subido" : " informes subidos") +
      (compartidos ? " y compartidos con el cliente." : " como borrador (sin compartir).") +
      (errores.length ? " " + errores.length + (errores.length === 1 ? " no se subió:" : " no se subieron:") : ""),
      errores.length > 0);
    if (errores.length) {
      var lista = document.createElement("ul");
      errores.forEach(function (e) {
        var li = document.createElement("li");
        li.textContent = e;
        lista.appendChild(li);
      });
      caja.appendChild(lista);
    }
    var listo = document.createElement("button");
    listo.type = "button";
    listo.className = "ghost-btn";
    listo.textContent = "Ver en el historial";
    listo.addEventListener("click", function () { window.location.reload(); });
    caja.appendChild(listo);
  }

  document.querySelectorAll("form[data-carga-lote]").forEach(function (form) {
    form.addEventListener("submit", function (evento) {
      var destino = form.querySelector("[data-vet-id]");
      if (!destino || !destino.value) {
        evento.preventDefault();
        avisar(form, "Elegí la veterinaria antes de subir: los informes van solo a ella.", true);
        return;
      }
      var entrada = form.querySelector('input[type="file"][name="pdf"]');
      var archivos = Array.prototype.slice.call((entrada && entrada.files) || []);
      if (archivos.length < 2) return;  // un solo PDF: el envío de siempre
      evento.preventDefault();
      cargar(form, archivos);
    });
  });
})();
