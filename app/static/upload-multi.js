/* Carga de varios informes de una vez.
 *
 * Al elegir más de un PDF, el formulario cambia de forma: los campos sueltos
 * (paciente, orden, análisis) se apagan y aparece UNA FILA POR ARCHIVO, con sus
 * propios campos `paciente_0`, `order_number_0`… que el backend lee por índice.
 * Con un solo archivo no cambia nada: el formulario de siempre.
 *
 * Del nombre del archivo se precarga lo que se pueda adivinar (un "A3-00042" va
 * al número de orden, el resto al paciente). Es una ayuda, no una regla: todo
 * queda editable antes de guardar.
 */
(function () {
  var ORDEN = /A3[-\s]?(\d{3,6})/i;

  function desdeNombre(nombre) {
    var limpio = nombre.replace(/\.pdf$/i, "").replace(/[_]+/g, " ").trim();
    var orden = "";
    var match = limpio.match(ORDEN);
    if (match) {
      orden = "A3-" + match[1];
      limpio = limpio.replace(match[0], "").replace(/^[\s\-–—]+|[\s\-–—]+$/g, "");
    }
    return { orden: orden, paciente: limpio };
  }

  function celda(nombre, indice, valor, placeholder) {
    var input = document.createElement("input");
    input.type = "text";
    input.className = "cell-input";
    input.name = nombre + "_" + indice;
    input.value = valor || "";
    input.placeholder = placeholder || "";
    var td = document.createElement("td");
    td.appendChild(input);
    return td;
  }

  function armarFilas(form, archivos) {
    var tabla = form.querySelector(".upload-multi");
    tabla.innerHTML = "";
    if (archivos.length < 2) {
      tabla.hidden = true;
      apagarCamposSueltos(form, false);
      return;
    }

    var titulo = document.createElement("p");
    titulo.className = "muted-text";
    titulo.textContent = archivos.length + " informes. Revisa los datos de cada uno antes de subir.";
    tabla.appendChild(titulo);

    var tablaHtml = document.createElement("table");
    tablaHtml.innerHTML =
      "<thead><tr><th>Archivo</th><th>Paciente</th><th>Nº de orden</th><th>Análisis</th></tr></thead>";
    var cuerpo = document.createElement("tbody");
    for (var i = 0; i < archivos.length; i++) {
      var pistas = desdeNombre(archivos[i].name);
      var fila = document.createElement("tr");
      var nombreTd = document.createElement("td");
      nombreTd.className = "muted-text";
      nombreTd.textContent = archivos[i].name;
      fila.appendChild(nombreTd);
      fila.appendChild(celda("patient_name", i, pistas.paciente, "Paciente"));
      fila.appendChild(celda("order_number", i, pistas.orden, "A3-00042"));
      fila.appendChild(celda("exam_name", i, "", "Hemograma…"));
      cuerpo.appendChild(fila);
    }
    tablaHtml.appendChild(cuerpo);

    var envoltorio = document.createElement("div");
    envoltorio.className = "table-wrap";
    envoltorio.appendChild(tablaHtml);
    tabla.appendChild(envoltorio);
    tabla.hidden = false;
    apagarCamposSueltos(form, true);
  }

  function apagarCamposSueltos(form, apagar) {
    ["order_number", "patient_name", "owner_name", "exam_name"].forEach(function (nombre) {
      var campo = form.querySelector('[name="' + nombre + '"]');
      if (!campo) return;
      campo.disabled = apagar;
      var etiqueta = campo.closest("label");
      // display:none y no [hidden]: el CSS del formulario le da display:flex a los
      // label y ganaba sobre el atributo, así que los campos seguían a la vista.
      if (etiqueta) etiqueta.style.display = apagar ? "none" : "";
    });
  }

  document.querySelectorAll("form.portal-upload-form").forEach(function (form) {
    var entrada = form.querySelector('input[type="file"][name="pdf"]');
    if (!entrada) return;
    entrada.multiple = true;
    if (!form.querySelector(".upload-multi")) {
      var contenedor = document.createElement("div");
      contenedor.className = "upload-multi";
      contenedor.hidden = true;
      entrada.closest(".form-grid").insertAdjacentElement("afterend", contenedor);
    }
    entrada.addEventListener("change", function () {
      armarFilas(form, Array.prototype.slice.call(entrada.files || []));
    });
  });
})();
