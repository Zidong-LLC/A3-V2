/* Perfiles personalizados guardados: buscar y renombrar.
 *
 * Con 44 perfiles y creciendo, la lista corrida no se lee: se agrupan por veterinaria y
 * se pueden filtrar. Renombrar pasa por /api/dashboard/rename-custom-profile.
 */
(function () {
  var buscador = document.querySelector("[data-profiles-search]");
  var contador = document.querySelector("[data-profiles-count]");
  var vacio = document.querySelector("[data-profiles-empty]");

  function plano(v) {
    return String(v || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  if (buscador) {
    buscador.addEventListener("input", function () {
      var palabras = plano(buscador.value).trim().split(/\s+/).filter(Boolean);
      var visibles = 0;
      document.querySelectorAll(".custom-profile-card").forEach(function (card) {
        var texto = plano(card.dataset.search);
        var entra = palabras.every(function (p) { return texto.indexOf(p) !== -1; });
        card.hidden = !entra;
        if (entra) visibles++;
      });
      // Un grupo sin perfiles a la vista se esconde entero, con su encabezado.
      document.querySelectorAll("[data-profiles-group]").forEach(function (grupo) {
        var quedan = [...grupo.querySelectorAll(".custom-profile-card")].some(function (c) { return !c.hidden; });
        grupo.hidden = !quedan;
      });
      if (contador) contador.textContent = visibles + " de " + document.querySelectorAll(".custom-profile-card").length;
      if (vacio) vacio.hidden = visibles > 0;
    });
    buscador.dispatchEvent(new Event("input"));
  }

  // Renombrar en linea: el titulo se vuelve un campo editable. Nada de window.prompt —
  // los entornos de test y los bloqueadores de dialogos lo cierran solos (ERR-173).
  document.querySelectorAll("[data-rename-profile]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      var card = boton.closest(".custom-profile-card");
      var titulo = card.querySelector("[data-profile-name]");
      var flag = card.querySelector("[data-profile-flag]");
      if (card.querySelector("[data-rename-input]")) return; // ya esta en edicion

      var input = document.createElement("input");
      input.type = "text";
      input.value = titulo.textContent.trim();
      input.className = "cell-input";
      input.setAttribute("data-rename-input", "");
      titulo.hidden = true;
      titulo.after(input);
      input.focus();
      input.select();

      function cerrar() {
        // Quitar el input dispara su blur: se desarma antes para que
        // cancelar (Escape) no termine guardando.
        input.removeEventListener("blur", alPerderFoco);
        input.remove();
        titulo.hidden = false;
      }
      function guardar() {
        var nuevo = input.value.trim();
        if (!nuevo) { flag.textContent = "El nombre no puede quedar vacio"; return; }
        cerrar();
        if (nuevo === titulo.textContent.trim()) return;
        enviar(nuevo);
      }
      function alPerderFoco() { guardar(); }
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); guardar(); }
        if (e.key === "Escape") cerrar();
      });
      input.addEventListener("blur", alPerderFoco);
    });

    function enviar(nuevo) {
      var card = boton.closest(".custom-profile-card");
      var titulo = card.querySelector("[data-profile-name]");
      var flag = card.querySelector("[data-profile-flag]");
      flag.textContent = "Guardando…";
      fetch("/api/dashboard/rename-custom-profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: boton.dataset.renameProfile, name: nuevo }),
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.d.error || "No se pudo renombrar");
          titulo.textContent = nuevo;
          card.dataset.search = plano(nuevo + " " + (card.closest("[data-profiles-group]") || {}).dataset.client);
          flag.textContent = "Guardado";
          setTimeout(function () { flag.textContent = ""; }, 2000);
        })
        .catch(function (e) { flag.textContent = e.message; });
    }
  });
})();
