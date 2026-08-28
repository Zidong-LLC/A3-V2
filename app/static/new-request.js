/* Carga manual de una orden: elegir cliente, sede y varios perfiles y análisis.
 *
 * Dos cosas que el formulario no hacía y en la operación real hacen falta:
 * 1) al elegir la veterinaria, la dirección de retiro se completa sola, y si esa
 *    veterinaria tiene varias sedes con el mismo NIT se puede elegir cuál;
 * 2) una orden lleva VARIOS perfiles y varios análisis para el mismo paciente, así
 *    que se eligen con casillas buscables y se ve la lista de lo elegido.
 */
(function () {
  // ── Cliente, dirección y sedes ─────────────────────────────────────────────
  var selectCliente = document.querySelector('select[name="client_id"]');
  var direccion = document.querySelector("[data-pickup-address]");
  var pista = document.querySelector("[data-address-hint]");
  var campoSede = document.querySelector("[data-sede-field]");
  var selectSede = document.querySelector("[data-sede-select]");

  function sedesDelNit(nit) {
    if (!nit) return [];
    return [...selectCliente.options].filter(function (o) {
      return o.value && o.dataset.taxId === nit;
    });
  }

  function aplicarSede(opcion) {
    if (!opcion) return;
    direccion.value = opcion.dataset.address || "";
    pista.textContent = opcion.dataset.address
      ? "Direccion registrada de " + opcion.dataset.clinic
      : "Esta sede no tiene direccion registrada: escribila a mano";
  }

  if (selectCliente && direccion) {
    selectCliente.addEventListener("change", function () {
      var elegida = selectCliente.options[selectCliente.selectedIndex];
      aplicarSede(elegida);

      var hermanas = sedesDelNit(elegida.dataset.taxId);
      if (hermanas.length > 1) {
        selectSede.innerHTML = "";
        hermanas.forEach(function (o) {
          var op = document.createElement("option");
          op.value = o.value;
          op.textContent = o.dataset.clinic + (o.dataset.address ? " · " + o.dataset.address : " · sin direccion");
          op.selected = o.value === elegida.value;
          selectSede.appendChild(op);
        });
        campoSede.hidden = false;
      } else {
        campoSede.hidden = true;
      }
    });
  }

  if (selectSede) {
    // Elegir otra sede cambia el cliente de la orden, no solo la dirección: la
    // factura y el motorizado salen de la sede que atiende.
    selectSede.addEventListener("change", function () {
      selectCliente.value = selectSede.value;
      aplicarSede(selectCliente.options[selectCliente.selectedIndex]);
    });
  }

  // ── Perfiles y análisis ────────────────────────────────────────────────────
  var chips = document.querySelector("[data-picker-chips]");
  var elegidos = document.querySelector("[data-picker-chosen]");

  function repintarElegidos() {
    if (!chips) return;
    var marcados = document.querySelectorAll(".catalog-item input:checked");
    chips.innerHTML = "";
    marcados.forEach(function (input) {
      var nombre = input.parentElement.querySelector("strong").textContent;
      var li = document.createElement("li");
      li.className = "catalog-chip" + (input.name === "profile_codes" ? " es-perfil" : "");
      li.textContent = nombre;
      var quitar = document.createElement("button");
      quitar.type = "button";
      quitar.setAttribute("aria-label", "Quitar " + nombre);
      quitar.textContent = "×";
      quitar.addEventListener("click", function () {
        input.checked = false;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
      li.appendChild(quitar);
      chips.appendChild(li);
    });
    elegidos.hidden = marcados.length === 0;
  }

  // Sin tildes en los dos lados: "hepatico" tiene que encontrar "Perfil Hepático".
  function sinTildes(texto) {
    return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  document.querySelectorAll("[data-picker]").forEach(function (caja) {
    var buscador = caja.querySelector("[data-picker-search]");
    var lista = caja.querySelector("[data-picker-list]");
    var contador = caja.querySelector("[data-picker-count]");
    var items = [...lista.querySelectorAll(".catalog-item")];

    function contar() {
      var n = caja.querySelectorAll("input:checked").length;
      contador.textContent = n + (n === 1 ? " elegido" : " elegidos");
      contador.classList.toggle("on", n > 0);
    }

    buscador.addEventListener("input", function () {
      var q = sinTildes(buscador.value.trim());
      items.forEach(function (item) {
        // Lo ya marcado no se esconde nunca: si desaparece al buscar, parece que se
        // perdió lo que se había elegido.
        var visible = !q || sinTildes(item.dataset.text).indexOf(q) !== -1 || item.querySelector("input").checked;
        item.hidden = !visible;
      });
    });

    lista.addEventListener("change", function () {
      contar();
      repintarElegidos();
    });
    contar();
  });

  repintarElegidos();
})();
