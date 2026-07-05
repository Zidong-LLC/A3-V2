# Contrato del flujo conversacional — A3 Laboratorio Veterinario

> **Propósito:** este documento es la fuente única de verdad sobre QUÉ pasos del flujo
> están APROBADOS por el cliente y NO se deben tocar. Antes de modificar cualquier paso,
> Claude debe avisar ("voy a tocar X, por esto") y esperar OK explícito. Si un paso está
> marcado ✅ APROBADO, no se modifica salvo pedido directo del usuario.
>
> **Regla de oro:** un paso aprobado no se rediseña como efecto colateral de arreglar otro.
> Si arreglar un bug obliga a tocar un paso aprobado, PARAR y avisar primero.

**Última actualización:** 2026-06-22
**Rama:** `fix/agente-robustez-multiorden`

---

## Leyenda de estado

| Símbolo | Significado |
|---|---|
| ✅ APROBADO | El usuario confirmó que funciona bien. No tocar. |
| ⚠️ A CORREGIR | El usuario reportó que funciona mal. Hay que arreglarlo (avisando antes). |
| 🔴 REGRESIÓN | Funcionaba y se rompió en una edición reciente. Revertir/arreglar con prioridad. |
| ⏳ POR CONFIRMAR | Falta que el usuario diga si está bien o mal. |

---

## Mapa de fases

```
fase_0_bienvenida → fase_1_clasificacion → fase_2_recogida_datos
   → fase_4_confirmacion (CONFIRMATION_PHASE) → fase_6_cierre  (contraentrega)
                                              → fase_7_escalado (pago en línea / cliente nuevo / pagos)
```

---

## Bloques del flujo

### B1 · Bienvenida y clasificación de intención
- **Qué hace:** saluda como A3 (tono colombiano cercano), ofrece las 4 opciones y clasifica
  qué quiere el usuario (recogida / resultados / pagos / cliente nuevo).
- **Dónde:** `WELCOME_MESSAGE`, `process_turn` (fase_0 → fase_1).
- **Estado:** ✅ APROBADO (usuario, 2026-06-22) — andaba bien; falta re-verificar en el último test.

### B2 · Identificación del cliente (por nombre o NIT)
- **Qué hace:** pide NIT o nombre, busca en la base, y si hay varias coincidencias muestra
  una lista seleccionable (número / ordinal "la primera" / nombre). Resuelve la selección
  de forma determinística (`_select_client_match`).
- **Dónde:** `_apply_identification_fallbacks`, `_select_client_match`, bloque
  `_client_match_options` en `process_turn`.
- **Regla de negocio:** identificar al cliente ANTES de registrar cualquier solicitud.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22)

### B3 · Cliente no registrado → escala a Recepción
- **Qué hace:** si no está en la base, el bot NUNCA da de alta; escala a una persona.
- **Dónde:** `_apply_handoff_guardrails` (intent `new_client`).
- **Regla de negocio:** el alta de cliente siempre la hace una persona.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22)

### B4 · Recolección de datos de la orden de recogida
- **Qué hace:** pide en orden los campos faltantes: dirección de retiro, médico solicitante,
  paciente (nombre, especie, raza, sexo, edad), propietario, observaciones, análisis/perfil,
  forma de pago. Pregunta de a un dato por turno.
- **Dónde:** `_ROUTE_REQUIRED_FIELDS`, `_missing_route_field`,
  `_enforce_first_missing_after_progress`, `_merge_existing_route_fields`.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22)

### B5 · Confirmación de dirección de retiro
- **Qué hace:** si el cliente tiene dirección registrada, la propone y pide confirmar
  ("¿esa dirección está bien?"). Acepta confirmaciones coloquiales ("sí", "esa", "sisi").
- **Dónde:** `_confirms_address`, `_address_confirmation_pending`.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22)

### B6 · Selección de análisis — perfil de catálogo por código/nombre
- **Qué hace:** si el usuario nombra un perfil del catálogo (p. ej. "perfil 152"), lo
  resuelve por código, guarda nombre/precio reales y avanza.
- **Dónde:** `_enforce_catalog_profile_code_selection`, `_capture_profile_menu_selection`,
  `_store_selected_profile_fields`.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22) — andaba bien; falta re-verificar en el último test.

### B7 · Selección de análisis — recomendación de perfiles por especie
- **Qué hace:** si el cliente no sabe qué pedir, pide recomendación, o responde algo vago que
  no mapea a área ni etiqueta, lista perfiles de la especie con código y precio, seleccionables.
- **Dónde:** `_enforce_profile_recommendation_help`, `_enforce_analysis_help_fallback`,
  `_format_profile_recommendation`, `_profile_menu_options`.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22). Restaurado + reforzado 2026-06-22 (RESUELTO-016):
  el catch-all garantiza lista seleccionable real aunque el modelo no capture el término.

### B8 · Selección de análisis — etiqueta diagnóstica y perfil personalizado
- **Qué hace:** entiende necesidades clínicas genéricas ("función renal") y arma un perfil a
  medida con análisis individuales del catálogo, mostrando precios y total.
- **Dónde:** `_enforce_diagnostic_label_help`, `find_diagnostic_label`,
  `_capture_test_menu_selection`, `calculate_custom_profile_total`.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22) — andaba bien; falta re-verificar en el último test.

### B9 · Personalización del perfil base (agregar / quitar pruebas)
- **Qué hace:** sobre un perfil base elegido, permite "agregale X" / "sacale Y" sin empezar
  de cero, recalculando el total. Si el cliente pregunta por opciones de un ÁREA mientras ajusta
  ("qué análisis de orina tienen"), lista esas opciones y las suma al perfil base al elegir.
- **Dónde:** `_enforce_profile_detail_step`, `_enforce_profile_customization_changes`,
  `_profile_customizing`, `calculate_profile_adjusted_total`, `_area_options_for_profile_addition`,
  `_capture_menu_addition_to_profile`, `_add_tests_to_order`, `_enforce_profile_exam_type_integrity`.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22). Extensión 2026-06-22 (RESUELTO-014): pregunta
  por área durante el ajuste ya no se traba — pendiente re-prueba conversacional del usuario.
- **Extensión 2026-07-04 (ERR-050), garantías nuevas con perfil elegido:**
  1. Intención de AGREGAR ("agregale un análisis más") nunca lleva al menú de recomendación
     de perfiles; abre el ajuste del perfil base y pregunta cuál.
  2. Mención de un ÁREA en el pedido (pregunta O afirmación: "agregale un análisis de orina")
     → menú de esa área marcado para AGREGAR; jamás se resuelve el área a un test suelto por
     parecido de nombre.
  3. INVARIANTE: todo agregado vive en `selected_tests` (código y precio reales); con perfil
     base, `exam_type` es exactamente el nombre del perfil (lo anotado como texto libre se
     resuelve a la estructura o se descarta). El resumen y el total salen SIEMPRE de la
     estructura — un agregado no puede perderse del valor estimado.
  4. Una pregunta de catálogo con análisis en curso no pisa la orden (menú marcado AGREGAR).

### B9.5 · Oferta de agregar otro análisis antes del resumen
- **Qué hace:** una vez fijado el análisis y cuando solo falta el pago, ofrece "¿agregar otro
  análisis o perfil, o personalizar? Si ya está, seguimos con el pago". Se repite tras CADA
  agregado hasta que el cliente decida seguir. Acepta nombrar un análisis, pedir opciones por
  área (suma al perfil), pedir recomendación, o dar el método de pago directo (salta al resumen).
- **Dónde:** `_analysis_settled_response`, `_handle_extra_analysis_answer`,
  `_enforce_extra_analysis_offer`, `_wants_to_proceed_to_payment`, `EXTRA_ANALYSIS_OFFER`,
  flag `_offering_extra_analysis`.
- **Estado:** ✅ IMPLEMENTADO Y VERIFICADO (2026-06-22, RESUELTO-017) — pedido del usuario;
  pendiente aprobación visual. Salida robusta para no reabrir el bucle histórico.

### B10 · Resumen de la orden y confirmación (fase_4_confirmacion)
- **Qué hace:** con la orden completa, muestra SIEMPRE un resumen determinístico
  (veterinaria, dirección, médico, paciente, propietario, análisis con precio,
  observaciones, forma de pago) y pide "¿Confirmas? (Sí / Corregir)".
- **Dónde:** `_enforce_confirmation_step`, `_route_confirmation_summary`,
  `_order_summary_lines`.
- **Estado del resumen en general:** ⏳ POR CONFIRMAR por el usuario.
- **Puntos reportados como mal por el usuario:**
  - ✅ CORREGIDO TÉCNICAMENTE (2026-06-22, RESUELTO-012) — perfiles de catálogo muestran el
    precio en la línea `- Análisis: X — $Y COP`.
  - ✅ CORREGIDO TÉCNICAMENTE (2026-06-22, RESUELTO-012) — ya no se duplica el perfil como
    `- Análisis: X` + `- Perfil base: X ($Y)`.

### B11 · Agregar otro análisis durante la confirmación
- **Qué hace (deseado):** si en la confirmación el usuario dice "sí, pero agregale otro
  análisis", el bot NO debe cerrar; debe preguntar qué agregar, sumarlo y re-mostrar el
  resumen.
- **Dónde:** guardas en `_enforce_confirmation_step` + Sección 7.0 de `process_turn`
  (`_awaiting_additional_test`).
- **Estado:** ✅ CORREGIDO TÉCNICAMENTE (2026-06-22, RESUELTO-013) — pendiente aprobación
  visual del usuario. El guard corre antes del cierre determinístico y mantiene
  `fase_4_confirmacion`. Extensión RESUELTO-014: si en vez de nombrar el análisis el usuario
  pregunta por un área ("qué análisis de orina tienen"), se listan las opciones para agregar.
  Extensión ERR-050 (2026-07-04): la mención de área también aplica en AFIRMATIVO ("agregale
  un análisis de orina") — va al menú del área antes que cualquier match difuso por nombre.

### B12 · Corrección de datos en la confirmación
- **Qué hace:** si el usuario pide cambiar un dato ("cambiá el médico"), limpia ese campo,
  repregunta y re-muestra el resumen, manteniendo la fase de confirmación.
- **Dónde:** Sección 7.1 de `process_turn`, `_detect_correction_field`,
  `_clear_field_for_correction`, `_correction_pending`.
- **Estado:** ⏳ POR CONFIRMAR

### B13 · Cierre de la orden y forma de pago
- **Qué hace:**
  - **Contraentrega** → `fase_6_cierre`: registra la orden, genera N° (A3-2026-001) y asigna
    el motorizado determinista.
  - **Pago en línea** → `fase_7_escalado`: registra la orden igual y escala a Contabilidad
    para enviar el link.
- **Dónde:** `_enforce_payment_step`, `_enforce_confirmation_step` (cierre determinístico),
  `_finalize_request`, `PAYMENT_ONLINE_HANDOFF_MESSAGE`.
- **Regla de negocio:** pagos siempre escalan a Contabilidad.
- **Estado:** ✅ APROBADO / regresión RESUELTA (2026-06-22). Tras revertir los 3 cambios,
  verificado con modelo real (validate_flows 20/20 + repro perfil-por-código): "pago en
  línea" muestra el resumen (fase_4) y el cierre escala a Contabilidad recién al confirmar.
- ~~🔴 REGRESIÓN ACTIVA~~ → RESUELTA (revert de los 3 cambios). Detalle histórico:
  - Al elegir "pago en línea", el bot **escala a Contabilidad SIN mostrar antes el resumen**
    de confirmación.
  - Los campos del paciente (especie, raza, sexo, nombre, edad, médico) **quedan en NULL**
    tras el turno del perfil + pago.
  - El bot reinicia la recolección preguntando "¿Cuál es el médico solicitante?".
  - **Causa probable:** los tres cambios encadenados de la última sesión
    (`_order_summary_lines`, guarda de `_wants_partial_analysis_change` en
    `_enforce_confirmation_step`, y la Sección 7.0 `_awaiting_additional_test`).
  - **Decisión (usuario, 2026-06-22):** revertir los 3 cambios y dejar el cierre como
    estaba (resumen → confirmación → cierre). Re-implementar B11 después, mínimo y avisando.

### B14 · Multi-orden (otra orden en la misma conversación)
- **Qué hace:** tras registrar una orden, si el usuario pide "otra orden", arrastra datos
  estables del cliente (dirección, médico, pago) y limpia los datos del paciente anterior.
  Permite cambiar de cliente.
- **Dónde:** `_begin_followup_order`, `_prev_order_snapshot`, `_restart_identification_for_new_client`,
  bloques de fase terminal en `process_turn`.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22) — andaba bien; falta re-verificar en el último test.

### B15 · Opción 2 · Consultar resultados
- **Qué hace:** informa que aún no está disponible por este medio (en integración).
- **Dónde:** `_enforce_results_message`.
- **Estado:** ⏳ POR CONFIRMAR

### B16 · Opción 3 · Pagos → Contabilidad
- **Qué hace:** deriva siempre a Contabilidad.
- **Dónde:** `_apply_handoff_guardrails` (intent `accounting`).
- **Estado:** ✅ APROBADO (usuario, 2026-06-22)

### B17 · Preguntas laterales (precio, tiempos de recogida, especies)
- **Qué hace:** responde dudas operativas o de precio en medio del flujo y retoma el dato
  pendiente sin perder el hilo.
- **Dónde:** `_operational_side_question_answer`, `_catalog_price_answer`,
  `_resume_route_after_lateral_turn`.
- **Estado:** ✅ APROBADO (usuario, 2026-06-22) — andaba bien; falta re-verificar en el último test.

### B18 · Facturación en Alegra (borrador, cuenta de pruebas)
- **Qué hace:** al cerrar una orden, intenta crear un borrador en Alegra. Complementario:
  cualquier fallo se loggea y no rompe el cierre.
- **Dónde:** `_try_invoice_in_alegra`, `app/billing.py`, `app/services/alegra.py`.
- **Regla de negocio dura:** TODO es prueba; solo borradores en cuenta de pruebas; nunca
  emitir facturas reales a la DIAN; avisar antes de escribir en Alegra.
- **Estado:** ⏳ POR CONFIRMAR (fuera de la queja actual de flujo conversacional)

---

## Pendientes priorizados

1. 🔴 **B13 — Revertir los 3 cambios y restaurar el cierre que funcionaba** (resumen →
   confirmación → cierre). _En curso._
2. ⏳ **B10 — Precios y estructura del resumen** corregido técnicamente; pendiente aprobación
   visual del usuario.
3. ⏳ **B11 — Agregar otro análisis durante la confirmación** corregido técnicamente; pendiente
   aprobación visual del usuario.

> Nada de los bloques marcados ✅ APROBADO se toca para resolver estos pendientes. Si hace
> falta, se avisa primero.
