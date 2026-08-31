# Tareas — A3 Laboratorio Veterinario V2

---

## Refactor de raíz FASE 2: la IA entiende la oración (2026-08-21) — EN CURSO

Plan aprobado: `~/.claude/plans/lively-swimming-popcorn.md`. Pedido del usuario: que el
agente entienda la oración completa (typos, sin tildes, cualquier fraseo) y dejar de
parchear listas de tokens. Retoma ABIERTO-003/ERR-011 con el molde C1/C2/C3 ya validado.
Metas: `PRE_LLM_RETURNS_BASELINE` 44→≤14, `known_dead` vacío, validate_flows ≥18-20/24.

- [x] **Etapa 0 — PUNTO DE GUARDADO**: 4 commits temáticos locales (ea89c8e visual,
      e898759 fixes ERR-139…143, 8c4d47e catálogo 022, 70c27bd docs) + tag
      `punto-guardado-agente-2026-08-21` en 70c27bd + suite 859 verde sobre el tag
- [x] **Etapa N — Normalización de tildes**: `tokenize` normaliza SIEMPRE (ñ→n incluida,
      consistente en ambos lados); 7 entradas tilde-only completadas con su par llano;
      invariante nuevo `test_ningun_vocabulario_depende_de_tildes` (introspección de 17
      módulos). Suite 860 passed
- [x] **Etapa 2 — Confirmación y oferta señal-primero**: stable-confirm (5 returns),
      correcciones en confirmación (3) y la oferta (1) degradados a handlers post-modelo;
      `_handle_extra_analysis_answer` recibe `signal` (correction cede, negate/farewell
      cierran, affirm pregunta cuál). Baseline 44→35. Tests:
      test_etapa2_senal_confirmacion.py (8). Suite 868 passed
- [x] **Etapa 3 — Fase terminal y memoria**: post-cierre completo (despedida, saludo,
      lateral, "quedamos atentos", negativa, reptiles) + smalltalk + "el de siempre" en
      handlers post-modelo; `same_as_previous` REVIVIDA (known_dead vacío — ya sin tope
      de 6 tokens cuando la señal viene); "otra orden" terminal absorbida por C1 con red
      ampliada. Baseline 35→24. Tests: test_etapa3_terminal_memoria.py (6). Suite 874
- [ ] **Etapa 4 — Pre-identificación y catálogo**: 4a (info servicio/laterales/muestrario),
      4b (ramas lingüísticas de mixtos restantes)
- [ ] **Checkpoints con modelo real** (validate_flows, SOLO con OK del usuario): al cerrar
      Etapa 2 y Etapa 4, comparar contra baseline 18-20/24
- [ ] **Registro**: ABIERTO-003/ERR-011 actualizados por etapa; prueba en vivo final

---

## Catálogo completo + fixes del test en vivo (2026-08-21) — EN CURSO

Plan aprobado: `~/.claude/plans/lively-swimming-popcorn.md`. Del test en vivo del usuario
(chat EVI, 15:16–15:39): el 1903 SÍ existe (PDF pág. 9, Convenio SERVIPAT) — el seed
original nunca cargó las págs. 9 y 18-27. Decisiones: SERVIPAT+LMV entran ya; Mascolab
espera precio de A3 (doble precio); especie cruzada NO es bug (pedido del cliente).

- [x] **Fase 1 — Catálogo**: migración 022 EJECUTADA con OK del usuario (2026-08-21,
      status 201): 24/24 insertados, total 159→183, el 1903 resuelve por
      `get_tests_by_codes_or_names`. Seed 002 sincronizado;
      `docs/catalogo-mascolab-pendiente.md` con erratas 2407/2061 para A3
- [x] **Fix 1 — ERR-139 contaminación de análisis entre órdenes (DINERO)**: marca
      `_analysis_inherited`; declaración reemplaza, "agregale" suma; `_extra_profiles`
      sumado a la frontera de orden (tests: test_inherited_analysis_replacement.py)
- [x] **Fix 2 — ERR-140 código inexistente avisado**: `_unknown_catalog_codes` en oferta
      y confirmación, caso mixto incluido (tests: test_unknown_catalog_code.py)
- [x] **Fix 3 — ERR-142 fraseos de cierre**: "la dejamos así", "avanzamos", par dejar+así,
      exención del tope de 6 SOLO sin "pago" (protege ERR-093)
      (tests: test_close_offer_phrases.py)
- [x] **Fix 4 — ERR-141 carril quitar/cambiar**: `_remove_order_items_by_code` + swap
      sacar+poner en un turno + código pelado responde a "¿qué quitar?"
      (tests: test_remove_swap_in_confirmation.py)
- [x] **Fix 5 — ERR-143 "No ese sácalo" anafórico**: clíticos en tokens de quitar +
      detector `_is_anaphoric_removal` + resolución del referente (1 ítem → quita;
      varios → pregunta con lista); "saca el 653" por código ahora también en la oferta
      (tests: test_anaphoric_removal.py, 11)
- [x] **Registro**: ERR-139…143 en errores-soluciones.md; suite 859 passed, 0 regresiones;
      ERR-082 re-caracterizado (latencia local medida: mediana 0.2s — el problema es del
      entorno Render, no del agente)

---

## Lavado de cara visual — estilo ZIDONG OS (2026-08-18) — EN CURSO

Plan aprobado: `~/.claude/plans/lively-swimming-popcorn.md`. Decisiones del usuario:
acento **monocromo blanco fiel** (#f5f5f7, el naranja deja de ser acento), alcance
completo (dashboard + portal + logins), kit portado del original
`ZIDONG LLC OS/platform/app/assets/css/main.css`. `service_order_print.html` y la isla
clara `.service-order-sheet` NO se tocan; colores semánticos (danger/ok/status badges)
se conservan. Solo CSS/templates/JS visual — cero lógica Python.

- [x] **Fase A — Kit**: `app/static/os-kit.css` (tokens, springs `linear()`, clases `os-*`,
      orbes, reduced-motion) + `app/static/os-fx.js` (spotlight + blur-text vanilla)
- [x] **Fase B — Piel**: retokenizar `app.css` (alias de variables viejas → escalera
      `--os-space-*`), barrido de ~60 naranjas/grises hardcodeados, canvas flotante,
      sidebar oscuro con blur, receta zd-card, inputs/tablas/tabs/drawers
- [x] **Fase C — Movimiento**: clases `os-scene`/`os-stagger`/`os-lift-card` +
      `[data-spotlight]`/`[data-blur-text]` en dashboard.html; charts ApexCharts a
      monocromo (dashboard.js v6)
- [x] **Fase D — Resto de vistas**: dashboard_results, new_client, login staff
      (dashboard.css reescrito), portal/base + portal/login (portal.css)
- [x] **Fase E — Verificación y registro**

**Resultados (2026-08-18):** piel completa portada del main.css original de ZIDONG OS.
Suite completa: 824 passed, 4 skipped, 1 xfailed — 0 regresiones. Verificación visual
con Flask local + Edge headless (login por requests con CSRF): capturas de login, Panel
Ejecutivo, Muestras (kanban + tabs), Facturación y Motorizados — todas con el look
Linear/Circle (canvas flotante, sidebar con blur, acento blanco, orbes). Colores
semánticos intactos: pipeline por estado, paleta de motorizados, badge naranja
"en ruta", verde dinero (--zd-chart) en sparklines/totales; isla clara
`.service-order-sheet` y `service_order_print.html` sin tocar. 1 fix descubierto en la
verificación: las tablas anchas propagaban su min-width y rompían el borde del canvas —
resuelto con `min-width:0` en los ítems del grid del canvas (app.css, sección "Piel
ZIDONG OS"). Bumps: os-kit.css v1, app.css v8, portal.css v2, dashboard.css v2,
dashboard.js v6, os-fx.js v1 (+ se agregó `?v=` donde faltaba: new_client y logins).
Sin commit (pendiente de OK del usuario). Artefacto conocido del headless: con
virtual-time el blur-text puede capturarse a mitad de animación; en navegador real no
pasa (verificado en Muestras/Clientes/Facturación/Motorizados).

---

## Plataforma al 100% — 4 features (2026-08-18) — EN CURSO

Plan aprobado: `~/.claude/plans/wise-petting-wren.md`. Alcance decidido por el usuario:
descuentos editables, TAT/tendencias, asignación automática por zona, y login del portal
por **nombre de veterinaria + NIT** (reemplaza email/contraseña de Supabase Auth, nunca
configurado). Módulos de alcance agregado quedan afuera (material de negociación con A3).
1 commit local por fase, sin push.

- [x] **Fase 1 — Login portal veterinaria + NIT** (commit 839f9b7, 787 passed): reescribir `app/portal/auth.py` y
      `login.html`; eliminar `services/portal_auth.py` y `create_portal_user.py`; alias
      `client_name_matches` en db.py; conftest fuerza `PORTAL_DEMO_MODE=false`; reescribir
      `tests/test_portal_auth.py` (multi-sede, anti fuerza bruta, rate limit)
- [x] **Fase 2 — Auto-asignación por zona** (commit 09bbba8, 800 passed): `app/zone_routing.py` puro +
      `_auto_assign_courier` en db.py (persiste `assigned_by='auto_zone'`) + bugfix
      confirm-suggestions (dashboard.js:237) + `tests/test_zone_auto_assignment.py`
- [x] **Fase 3 — Descuentos editables** (commit 16ceca2, 815 passed; migración 021 SIN ejecutar en Supabase — pedir OK): migración 021 `discount_tiers` (avisar antes de
      ejecutar en Supabase) + `app/pricing.py` (cache TTL 60 s, fallback a constante) +
      provider en rules.py + endpoint/UI patrón catálogo + `tests/test_discount_tiers.py`
- [x] **Fase 4 — TAT y tendencias** (commit 52c3e2b, 824 passed; smoke /dashboard y /muestras OK)

**Resultados (2026-08-18):** 4 fases completas en 4 commits locales (839f9b7, 09bbba8,
16ceca2, 52c3e2b). Suite: 783 → 824 passed (41 tests nuevos), 0 regresiones; los 6
fallos por red pre-existentes de test_portal_auth/test_dashboard quedaron resueltos por
el fix del conftest. 2 bugs adyacentes reparados (confirm-suggestions 404 silencioso;
savePrefs de widgets rechazado por falta de `order`). Migración 021 EJECUTADA con OK del
usuario (2026-08-18, vía apply_supabase_migration.py, status 201): 14 tramos sembrados,
verificado en solo lectura que pricing lee la tabla y calculate_discount da idéntico
(12% para 2 pruebas). PENDIENTE: smoke manual en vivo — login del portal con NIT real
multi-sede, edición de tramos → cotización del agente, y fila `auto_zone` tras una
orden de un cliente sin asignación.

---

## Fix: ERR-080/081/082 — chat real 10, errores no registrados (2026-07-22) — EN CURSO

Plan aprobado: `~/.claude/plans/pod-s-detectar-qu-pas-replicated-cosmos.md`.
Del QA en vivo del 2026-07-21 (chat 10) quedaron 3 errores sin registrar además de
ERR-077/078/079: el "Si" final cayó en bucle y la orden nunca se registró
(`request_id=None`), la identidad quedó cruzada entre dos clientes (La Uribe con la
dirección del Centro Médico Veterinario), y el batch "1/1/2" solo atendió el último.

- [x] ERR-080: limpiar `_awaiting_additional_test` al mostrar el resumen + resolver
      perfiles al agregar en confirmación (`app/enforcers/confirmacion.py`)
- [x] ERR-080: tests `tests/test_confirmation_close_not_looped.py` (5 passed)
- [x] ERR-081: re-identificar cliente cuando responde con nombre de sede a la pregunta
      de dirección (`app/agent.py`, bloque de dirección)
- [x] ERR-081: tests `tests/test_address_reject_with_clinic_name.py` (4 passed)
- [x] ERR-082: registrar en bitácora (batch + latencia; sin cambio de código)
- [x] Suite completa verde + bitácora ERR-080/081/082 + lección L55

**Resultados (2026-07-22):** 483 passed, 2 skipped, 1 xfailed. Los 6 fallos restantes son
`test_dashboard`/`test_portal_auth` por red (`httpx.ConnectError`), pre-existentes.
Verificado con stash que el subconjunto del agente pasa 425/425 sin los tests nuevos → cero
regresiones. PENDIENTE: validación con modelo real (`validate_flows.py`/Telegram) replicando
el chat 10 punta a punta (junto con la de ERR-077/078/079, que sigue pendiente) y la
investigación de latencia de ERR-082.

---

## Refactor de raíz: atacar la causa core, no la fascia (2026-07-07) — EN CURSO

Plan aprobado: `~/.claude/plans/podemos-hacer-podemos-hacer-lively-waterfall.md`.
Diagnóstico: 70 bugs, ~90% parches localizados; los mismos escenarios reparados 5-6 veces.
Causa raíz (3 caras): (1) intención por listas de tokens, (2) resolución de catálogo por
string-matching duplicada (dinero), (3) máquina de estados implícita (~41 flags). Orden
elegido: **empezar por catálogo/dinero**, con **red de tests primero**.

**Fase 0 — Red de seguridad — HECHA**
- [x] `tests/test_catalog_resolution.py`: ejercita la resolución REAL (catálogo inyectado en
      `db._client`). 6 verde + el residual "sanguíneos"→Gases sanguíneos Plus como `xfail`
      estricto (se vuelve verde en Fase 1).
- [x] `tests/test_money_invariants.py`: harness end-to-end sobre `process_turn` (resolución de
      catálogo real dentro del turno) + invariantes reutilizables I1 (códigos válidos),
      I2 (sin precio inventado en exam_type), I4 (total = cálculo por códigos).
- [x] Suite: 180 passed, 1 xfailed (sin contar portal/dashboard, que fallan por red).

**Fase 1 — Resolvedor de catálogo unívoco — EJE COMPLETO (192 passed, 1 xfailed)**
- [x] `app/catalog.py`: `resolve_tests` puro (EXACT agrega / AMBIGUOUS ofrece / NONE pregunta).
- [x] Integrado en `_handle_extra_analysis_answer` → residual "sanguíneos" resuelto (ofrece, no agrega).
- [x] `_enforce_loose_exam_catalog_resolution` y `_enforce_multiple_tests_capture` migrados a `resolve_tests`.
- [x] Validador I1 `_enforce_selected_tests_are_catalog_codes` (red dura antes de registrar).
- [ ] Deuda (xfail estricto): retirar `get_tests_by_codes_or_names` de bajo nivel al migrar precios/remove.

**Fase 2 — Comprensión por IA — ARRANCADA (punto crítico)**
- [x] Cierre de orden migrado a `user_intent_signal` (`_confirms_order_now`): cierra confirmaciones fuera de lista.
- [ ] Resto de detectores: acoplados a Fase 3 (viven en la cascada PRE-LLM, sin señal disponible). Ver ABIERTO-003.

**Fase 3 — CIERRE 2026-07-18 (tandas A/B/C, plan `snug-dancing-tiger`)**
- [x] **3.4a — 21/21 enforcers en `app/enforcers/`** (commits `cee8ec7`+`f5e9a5f`): la capa de
      helpers de respuesta salió de agent.py (`app/laterales.py` NUEVO + text/menus/orders) y
      los 2 enforcers finales viven en `enforcers/confirmacion.py` y `enforcers/resultados.py`.
      agent.py: 3.582 → 3.181 líneas; ya no define ningún `_enforce_*`. Lint de referencias
      extendido a laterales.py. PENDIENTE (Tanda D, sesión aparte): partir `process_turn` en
      `app/turno/` — después de que el reorden C repose en vivo.
- [x] **3.2 — FSM en modo BLOQUEO de estado** (commit `86f7183`): `FSM_ENFORCE=true` en `.env`
      local; `heal()` probado end-to-end en el embudo (`_persist_turn` → `db.update_session`
      recibe el estado reparado). Flags fantasma NO se dropean en runtime (typo = fallo de
      suite: `test_catalog_covers_flags_used_in_whole_app` cubre app/**). Transiciones
      ilegales quedan en DETECCIÓN (grafo descriptivo). [ ] Flip del default en `config.py`
      tras la prueba en vivo del usuario con el enforce activo.
- [x] **3.3 — REORDEN pre-LLM completo** (commits `5fe8737`/`9c86290`/`ba5ee3a`): los 3 atajos
      de INTENCIÓN por tokens se degradaron a sus handlers post-modelo señal-primero con
      tokens de RED y guards portados: C1 otra-orden (+_stable_confirm_pending), C2 cambio
      cliente/sede (+rama sede, base prev_captured con menús limpios), C3 no-registrado
      (+bypass ERR-037 en el atajo de servicio). Trade-off aceptado: +1 llamada LLM en esos
      turnos raros (~1-3 s sobre el debounce de 5 s). Señales sin consumidor propio —
      `same_as_previous`, `farewell`, `cancel`, `provides_requested_data` — quedan cubiertas
      por otras vías (memoria pre-LLM, fases terminales, message_mode=cancellation, captura
      normal); documentado, sin acción.
- Validación: suite 325 passed (6 fallos de red ajenos); `validate_flows.py` (modelo real)
  18-20/24 — los flujos con problemas NO son regresión: A falla igual en el commit BASE
  (verificado con worktree en `784b799`) y F/M/M2/S/T varían entre corridas (flakiness del
  modelo); B/K/L/T (las áreas del reorden) pasan. [ ] Prueba en vivo del usuario.

**Fase 3 — histórico (estado previo al cierre)**
- [x] `app/state.py` ya tenía la FSM documentada (`Phase`, `LEGAL_TRANSITIONS`, `is_legal_transition`)
      y las invariantes de estado (`assert_valid`, `unknown_flags`).
- [x] `agent._observe_state_health` conectado al embudo `_persist_turn`: tras cada turno loggea
      (warning) las TRES señales de raíz de los bucles (clusters 3 y 6), SIN bloquear ni cambiar
      el flujo: (1) banderas incoherentes ("pegadas", `assert_valid`), (2) flags fantasma/typos
      (`unknown_flags`), (3) transiciones de fase fuera del grafo (`is_legal_transition`). La fase
      de entrada se pasa vía `ContextVar` de alcance de turno (sin drillear los ~20 return).
      5 tests nuevos en `test_state.py`. Suite: 280 passed, 1 xfailed (6 fallos de red ajenos).
- [ ] Paso 3.2 (BLOQUEO real de la transición/estado): recién cuando los logs en vivo confirmen
      que las señales de detección no dan falsos positivos. Validar en vivo primero.
- [~] Paso 3.4 (partir el monolito) — DETECTORES COMPLETOS como paquete (2026-07-16):
      - [x] `app/messages.py`: 22 textos fijos del agente.
      - [x] Paquete `app/detectors/` por tema (basico/perfil/direccion/orden/cliente, todos
            <200 líneas; `__init__` re-exporta = superficie de import idéntica): 30 detectores
            puros + su vocabulario movidos en 7 tandas verificadas.
      - agent.py: 5.729 → 5.485 líneas. Suite verde en cada tanda (290 passed al cierre).
      - [ ] Resto del 3.4: los 23 enforcers `_enforce_*` (NO son puros: llaman db y se
            encadenan) → moverlos por responsabilidad en sesión dedicada, con validación viva.
- [~] Paso 3.3 — señal→ACCIÓN (2026-07-17): `change_client` y `another_order` ya tienen
      manejador de acción post-modelo (mismas acciones determinísticas que los tokens:
      conservar orden / _begin_followup_order). change_client verificado EN VIVO con fraseo
      nuevo. `same_as_previous`/`farewell`/`cancel`: sin consumidor propio pero cubiertas por
      otras vías (memoria pre-LLM, fases terminales, message_mode=cancellation) — revisar si
      la prueba en vivo muestra huecos. Falta: reorden pre-LLM completo (sesión dedicada).
- [~] Paso 3.4 enforcers — ARRANCADO: paquete `app/enforcers/` (dinero.py: validador I1)
      + `as_text_items` movido a app/text.py. Los 22 restantes dependen de la capa de
      helpers de respuesta de agent.py: moverla primero (sesión dedicada).
- [ ] (histórico) Paso 3.3: los sitios POST-LLM ya son señal-primero
      (cierre, dirección, pago-corrección, handoff, sede, coincidencia única). Lo que FALTA
      es el REORDEN del pipeline: los detectores de cambio-de-cliente/otra-orden/etc. corren
      PRE-LLM (agent.py ~4600-5100), donde la señal no existe aún. Mover esas ramas a
      después del modelo = cirugía mayor → sesión dedicada con QA real entre pasos.
- Nota 3.2: logs del observador LIMPIOS en todas las pruebas en vivo del 2026-07-16 (cero
  falsas alarmas). El bloqueo duro queda diferido: los estados pegados encontrados
  (ERR-060/061) se arreglaron determinísticamente en su origen, mejor que bloquear.

> **Próximo paso: validación en vivo** del eje catálogo + cierre por señal antes de encarar Fase 3.

**Fases 2-3 (esbozadas):** completar comprensión por IA (Etapas 2-4 de ERR-011); formalizar FSM.

---

## Fix: ERR-051 — QA adversarial contra BD real (2026-07-05) — EN VERIFICACIÓN

**Metodología nueva:** batería de 10 personas-IA adversariales contra `process_turn` +
Supabase REAL (clientes/NITs/catálogo verdaderos), juez-IA + lectura manual de cada
transcripción, `ALEGRA_ENABLED=false`, spies para capturar/limpiar lo creado, y
`create_pending_client_review` bloqueada. Runner en scratchpad de la sesión.

**Hallazgos (7):** precio inventado en orden registrada (Coprológico $23k vs $12.000);
payloads de análisis suelto con code null/price 0; perfil de $130.000 capturado sin que
el cliente lo nombrara; "parcial de orina" cotizado como PTT+Cortisol; elección + precio
en el mismo mensaje perdía la elección; confirmación de dirección + datos en bloque +
pago pisada por el atajo de pago fuera de turno; edad sin unidad asumida como años.

**Fixes (app/agent.py):**
- [x] A. `_enforce_loose_exam_catalog_resolution` + `_strip_price_text`: análisis suelto
      SIEMPRE estructurado contra catálogo; cifras del modelo descartadas; categoría de
      perfiles → menú de armados (nunca al resumen sin precio).
- [x] B. `_enforce_exam_type_grounding`: exam_type nuevo sin anclaje en lo dicho por el
      cliente se descarta y se re-pregunta.
- [x] C. `_catalog_price_answer`: mensaje completo → área (opciones reales con precios,
      menú marcado AGREGAR si hay orden en curso) → términos como último fallback.
- [x] D. `_expresses_order_request`: pedido + precio en un mensaje captura la elección.
- [x] E. Atajo de pago fuera de turno: resuelve la dirección pendiente del mismo mensaje
      y no pisa turnos con datos en bloque.
- [x] F. `_enforce_age_unit_grounding`: unidad de edad no dicha por el cliente (mensaje
      o historial) → se guarda solo el número y se re-pregunta.
- [x] Ajustes post-re-test: descripción del perfil no se duplica como agregados
      ($23k→$50k); categoría al menú; tokens "confirmame"; edad por historial.
- [x] Tests: `tests/test_qa_realista_guardrails.py` (18) — suite 190 passed
      (4 dashboard preexistentes).
- [x] Verificación adversarial final: caotico_typos BIEN ($12.000 real estructurado),
      precios BIEN, perfil_agregado con dinero perfecto (155 · $36.000 · parcial de orina
      incluido; FAIL del juez solo por comunicación). Limpieza verificada (0 residuos).
- [x] Ajustes finales: "buen día" no cuenta como unidad de edad; multi-análisis en texto
      se estructura 1:1. Suite 192 passed.
- [x] Docs: ERR-051 en bitácora, lección L49.

**Pendiente:** re-prueba del usuario por Telegram (reiniciar Flask local) y residuo menor
de comunicación (explicitar qué incluye el perfil elegido) anotado como ABIERTO en ERR-051.

---

## Fix: ERR-050 — agregar análisis a un perfil elegido (prueba real 2026-07-04, chat 4) — COMPLETADO

**Problema (5 síntomas en la conversación real):** con el perfil 152 elegido, (1) "agregarle
un análisis más" mostraba perfiles Cachorros; (2) la insistencia repetía el mismo menú;
(3) "un análisis de orina" agregaba Cortisol ($33k) por fuzzy-match sin confirmar;
(4) "¿qué análisis de orina hacen?" daba un muestrario mixto que BORRABA la orden en curso;
(5) el agregado final quedó como texto en exam_type y el resumen cobró $24.000 en vez de $40.000.

**Solución (invariante + ruteo, aprobada por el usuario vía prompt):**
- [x] Invariante `_enforce_profile_exam_type_integrity`: agregados SIEMPRE en selected_tests;
      exam_type = nombre exacto del perfil; texto libre se resuelve a estructura o se descarta;
      exam_type vacío con perfil activo se restaura (mata el paso atrás post-pago).
- [x] Ruteo: agregar → ajuste del perfil (nunca menú de recomendación); área en afirmativo →
      menú del área (`require_question=False`, también en confirmación); pregunta de catálogo
      con análisis en curso no pisa la orden; lookup mensaje-completo primero; selección de
      menú tolera palabras alrededor (nombre sin paréntesis, mín. 5 chars); reemplazo total
      limpia el perfil base viejo.
- [x] Menor: concordancia de género (`_FIELD_GRAMMAR`) en "el mismo" + R19 del prompt.
- [x] Tests: `tests/test_profile_addition_invariant.py` (11 nuevos); suite 172 passed
      (4 fallos de test_dashboard preexistentes).
- [x] Modelo real (`ALEGRA_ENABLED=false`): caso X nuevo OK end-to-end (resumen con
      "Agregados: 1603-Urocultivo $52k / Valor estimado: $76,000 COP"); vecinos
      A/G/H/Q/R/U/W OK. El caso V es flaky por no-determinismo del modelo (preexistente,
      alterna OK/PROBLEMAS con código idéntico).
- [x] Docs: ERR-050 en errores-soluciones.md, B9/B11 del contrato, lección L48.

**Pendiente:** re-prueba conversacional del usuario por Telegram (Flask hay que reiniciarlo
para cargar este código).

---

## Fix: ERR-046 + ERR-047 (confirmación pendiente y selección de coincidencia) — COMPLETADO

**ERR-047 (ex ABIERTO-004):** "sí, esa está bien" ante la lista de coincidencia única no
seleccionaba al cliente y la identificación se descarrilaba. Fix: con 1 sola opción, una
afirmación la selecciona — `user_intent_signal == "affirm"` como fuente primaria, tokens
como fallback; no aplica si dice ser cliente nuevo. 4 tests nuevos en
`tests/test_client_match_selection.py`.

**ERR-046 (señalado por el usuario):** con la confirmación de dirección pendiente, una
respuesta esquiva ("quiero un análisis de orina") la daba por confirmada en silencio.
Fix (criterio del usuario: responder a lo que dijo, conservar el dato, re-preguntar lo
pendiente): el progreso solo cuenta turnos anteriores; otra dirección en el mensaje vale
como corrección; en cualquier otro caso el pipeline responde al mensaje y AL FINAL del
turno se re-pregunta la dirección (inyección post-guardrails para que un menú no la pise).
4 tests nuevos en `tests/test_address_pending_reask.py` + caso V en validate_flows.

**Verificación:** suite unitaria 122 passed; modelo real `validate_flows.py` con
`ALEGRA_ENABLED=false`: A, G, H, Q, R, U y V todos OK. Lección L47 en `tasks/lessons.md`.

---

## Fix: perfiles armados por categoría ignorados (prueba 2026-07-03, chat 4) — COMPLETADO

**Problema (prueba real de hoy):** cliente pidió "perfil prequirúrgico" y el bot:
(1) recomendó perfiles genéricos por especie (Cachorros para una perra de 2 años) aunque
el catálogo tiene 11 perfiles Prequirúrgicos armados (152–162); (2) con la etiqueta
PREQUIRURGICO activa, ante "¿No tienes perfiles armados?" re-preguntó la especie ya
capturada; (3) "Ya te dije q especie es" terminó saltando al pago con
`exam_type="PREQUIRURGICO CANINO"` (inexistente en catálogo, sin análisis ni valor).

**Plan:**
- [x] 1. `db.py`: nueva `list_catalog_profiles_matching_category(text, species, limit)` —
      matching por categoría normalizada (sin tildes/espacios), defensiva, con la
      lógica de filtrado en función pura testeable (`filter_profiles_by_category_mention`).
- [x] 2. `agent.py`: helper `_category_profiles_menu_response(fields, text)` que arma el
      menú seleccionable (`_profile_menu_options`) con los perfiles de la categoría
      nombrada, limpiando análisis previo y `_diagnostic_label`.
- [x] 3. Conectarlo (categoría primero, especie como fallback) en: rama pre-AI de
      recomendación, `_enforce_profile_recommendation_help`, `_enforce_diagnostic_label_help`
      (perfiles armados antes que pruebas sueltas) y `_diagnostic_label_profile_turn`
      (etiqueta activa + pide perfiles armados, detector `_asks_for_armed_profiles`).
      NOTA: NO se tocó `_handle_extra_analysis_answer` (paso 3) para limitar el radio
      del cambio; ahí sigue el menú por especie.
- [x] 4. Tests de regresión: `tests/test_category_profile_menu.py` (7 nuevos) + patch de
      la nueva función en `tests/test_analysis_options_restore.py`.
- [x] 5. Suite completa: 151 passed. Los 4 fallos de `test_dashboard.py`
      (`exec_alerts_count`) son preexistentes — verificado con git stash.
- [x] 6. ERR-045 registrado en `tasks/errores-soluciones.md`.

**Resultados:** verificado contra el catálogo real (solo lectura): el mensaje exacto de la
prueba fallida ("Cual me recomiendas pre quirúrgico q perfil tienen?") ahora devuelve el
menú con los 11 perfiles Prequirúrgicos (152–162) con precios reales, y "¿No tienes
perfiles armados?" con la etiqueta activa responde el menú sin re-preguntar la especie.
Validación con modelo REAL (caso U nuevo en `tools/scripts/validate_flows.py`, con
`ALEGRA_ENABLED=false` para no tocar Alegra): OK end-to-end — menú de armados, "el 1"
registra 701 con $24.000, resumen con valor estimado y orden cerrada. Q y R siguen OK.
Hallazgo colateral PREEXISTENTE (reproducido con git stash, no causado por este fix):
"sí, esa está bien" no selecciona la coincidencia única de cliente → registrado como
ABIERTO-004, fix propuesto pendiente de OK (toca el paso de identificación).
Pendiente: prueba conversacional real del usuario end-to-end.

---

## Módulo "Facturación" (Alegra) — Completado (falta aplicar migración 014)

**Objetivo:** centro de consulta de facturas de Alegra dentro del dashboard (Fase 4 de la
decisión 009, read-only), adaptado a Colombia/DIAN. Plan en
`C:\Users\Artel\.claude\plans\hidden-leaping-eclipse.md`.

**Decisiones del usuario:** sin roles (login admin actual) · arquitectura híbrida (tabla
cache + lectura directa para el detalle) · consulta + acciones con bloqueo de envío/emisión
en pruebas.

**Cambios realizados:**
- [x] `app/services/alegra.py`: `list_invoices`, `get_invoice`, `get_invoice_pdf_url` (solo lectura).
- [x] `app/billing.py`: `invoice_to_row()` (mapeo puro Alegra→fila) + tests en `tests/test_alegra_billing.py`.
- [x] Migración `db/migrations/014_invoices_cache.sql` (tabla `invoices_cache`, no toca esquema existente).
- [x] `app/services/db.py`: `upsert_invoices_cache`, `list_cached_invoices`, `list_all_cached_invoices`, `get_cached_invoice`.
- [x] `app/config.py` + `.env.example`: flag `ALEGRA_PRODUCTION` (false=pruebas → acciones de envío bloqueadas).
- [x] `app/dashboard.py`: ruta `/facturacion`, contexto (KPIs/métricas/paginación/filtros), endpoints
      `GET /api/dashboard/invoices`, `GET .../invoices/<id>` (read-through), `POST .../invoices/sync`,
      `GET .../invoices/export` (CSV/Excel).
- [x] UI: ítem en sidebar, pestaña con KPIs, filtros, buscador, orden por columna, paginación,
      tabla con **columnas configurables** (reusa `columns-config.js`), modal de detalle.
- [x] `app/static/invoices.js` (sync, export, orden, paginación, copiar, detalle) + estilos en `app.css`.

**Pendiente:**
- [ ] Aplicar `014_invoices_cache.sql` en Supabase. Sin esto, el módulo carga vacío con gracia
      ("No hay facturas en cache") — nada se rompe.
- [ ] Validar `alegra.list_invoices/get_invoice` contra la cuenta de pruebas con un smoke (solo lectura).

**Verificación hecha:** `pytest` (147 pasan) · render `/facturacion` 200 con test client (estado
vacío correcto) · rutas registradas · `node --check` y parseo Jinja OK.

**Guardrails respetados:** solo lectura; ninguna emisión/envío; IDs Alegra↔orden vía evento
`alegra_invoiced` en `request_events`; acciones de reenvío/XML deshabilitadas en pruebas.

---

## Personalización de columnas en tablas del CRM — Completado (falta aplicar migración)

**Objetivo:** que cada usuario elija qué columnas ver/ocultar y su orden, en todas las tablas
del dashboard, de forma reutilizable y persistente entre sesiones y dispositivos.

**Estado de partida:** la funcionalidad ya existía casi completa (sin commitear) en
`app/static/columns-config.js`, con atributos `data-column`/`data-mandatory` en los `<th>` y
botones "Columnas" en 6 tablas. Persistía solo en `localStorage` (por navegador).

**Decisión del usuario:** persistencia **híbrida** (localStorage instantáneo + servidor para
sincronizar entre dispositivos).

**Cambios realizados:**
- [x] Fix bug HTML: fragmento basura en el `<thead>` de la tabla de clientes
      (`app/templates/dashboard.html`) que rompía el encabezado.
- [x] Migración `db/migrations/013_dashboard_column_prefs.sql` (tabla `dashboard_column_prefs`,
      PK `user_key,table_id`, `prefs jsonb`).
- [x] `db.list_column_prefs()` y `db.upsert_column_prefs()` en `app/services/db.py`.
- [x] Endpoints GET/POST `/api/dashboard/column-prefs` en `app/dashboard.py` (mismo patrón
      JSON que el resto; exentos de CSRF por no usar `request.form`).
- [x] `columns-config.js`: sincronización híbrida (debounce POST al guardar, GET al cargar que
      sobrescribe lo local) + arreglo del cierre del panel al hacer clic afuera. Cache `?v=3`.

**Pendiente para que funcione el lado servidor:**
- [ ] Aplicar la migración `013` en el SQL Editor de Supabase (sin esto, el GET/POST devuelven
      error y el sistema cae con gracia a solo-localStorage; nada se rompe).

**Verificación:** levantar el dashboard, abrir cada tabla → botón "Columnas" abre panel lateral;
marcar/desmarcar actualiza al instante; buscador filtra; mostrar/ocultar/restablecer funcionan;
drag & drop reordena; recargar conserva la config. Tras aplicar la migración, cambiar de equipo
debe traer la misma configuración.

---

## Bug: agregar otro análisis/perfil se traba (chat 4 real) — En curso

Reportado por el usuario y reproducido en el historial real (`external_chat_id=4`):
1. **Intención compuesta ignorada:** "quiero el perfil 152 al cual le quiero agregar un
   analisis extra" → el bot captura el perfil y salta al pago, descartando el "agregar".
2. **Pregunta de catálogo durante el ajuste se traba:** estando en personalización/confirmación,
   "que analisis de orina tienen" → el bot repite el resumen sin listar opciones de orina.
   El usuario quedó sin respuesta.

Causa raíz: durante el ajuste de un perfil, el código solo resuelve nombre/código EXACTO de
análisis; una pregunta abierta por área no llega a `find_tests_by_area` y cae al resumen.

Plan (mínimo, avisado y aprobado por el usuario):
- [x] Helper `_area_options_for_profile_addition`: ante pregunta por área durante el ajuste,
      muestra el menú de esa área marcado para AGREGAR al perfil base (`_test_menu_adds_to_profile`).
- [x] `_enforce_profile_customization_changes`: si llega una pregunta por área, mostrar el menú.
- [x] `_confirmation_analysis_adjustment`: si no resuelve test exacto, intentar opciones por área.
- [x] Selección de menú en `process_turn`: si `_test_menu_adds_to_profile`, AGREGAR al
      perfil en vez de reemplazar (`_capture_menu_addition_to_profile`).
- [x] Fix intención compuesta: en `_enforce_catalog_profile_code_selection`, si el mismo mensaje
      pide agregar, tras fijar el perfil preguntar qué análisis agregar.
- [x] Tests de regresión (`tests/test_add_analysis_during_adjustment.py`, 5 casos).
- [x] Registrar en `errores-soluciones.md` (RESUELTO-014) y actualizar el contrato (B9/B11).

**Resultado:** suite 126/126 verde. Verificado contra base real (`find_tests_by_area` →
7 análisis de Uroanálisis; perfil 152 = $24.000). Pendiente: que el usuario reinicie el Flask
local y re-pruebe la conversación (el historial del chat 4 era de código anterior).

---

## Integración de Alegra (facturación electrónica DIAN) — Por fases — En curso

Decisión [009](../docs/decisions/009-alegra-integracion-por-fases.md) (supersede la 008).
Plan completo en el archivo de plan aprobado. Cubre las 4 capacidades (facturación DIAN,
link de pago en chat, consulta de facturas/saldo, sync de clientes), por fases. Se prueba
PRIMERO con una cuenta nueva detrás de `ALEGRA_ENABLED`; migrar a la del cliente = cambiar
solo `.env`.

### Fase 0 — Credenciales y feature flag ✅ COMPLETA
- [x] `config.py`: `ALEGRA_ENABLED` (default false), `ALEGRA_EMAIL`, `ALEGRA_API_TOKEN`, `ALEGRA_BASE_URL`.
- [x] `.env.example`: bloque Alegra documentado.
- [x] `docs/decisions/009-alegra-integracion-por-fases.md` (supersede 008).
- [x] `scripts/alegra_smoke.py`: ping de conectividad + get_or_create de contacto demo.

### Fase 1 — Cliente API + sync de contactos (backend) — Base validada
- [x] `app/services/alegra.py`: cliente Basic auth aislado, `ping`, `find_contact_by_nit`,
      `get_or_create_contact`. urllib (igual que chatwoot.py), errores re-lanzados como `AlegraError`.
- [x] Validado contra API real (cuenta Colombia, `applicationVersion="colombia"`):
      conectividad, lectura y **alta de contacto con NIT** OK. El NIT se guarda y la búsqueda
      lo encuentra → idempotencia confirmada (ver RESUELTO-009). Formato: `identificationObject`
      (NIT) + `regime` + `kindOfPerson`.
- [ ] Hook de sync: al identificar cliente, `get_or_create_contact` por NIT y guardar
      `alegra_contact_id` en `request_events.event_payload` (bajo `ALEGRA_ENABLED`).
      → Toca `agent.py`/`db.py`; siguiente paso.

### Fase 2 — Facturación (backend) — Base API validada
- [x] `app/services/alegra.py`: `find_item_by_reference`, `get_or_create_item` (idempotente
      por código), `create_invoice` (borrador por defecto). Validado contra cuenta Colombia:
      ítem idempotente, factura con total correcto (2×35000=70000), status `draft`.
- [x] Confirmado: la cuenta de pruebas tiene numeración de factura de venta `id=1`
      `electronic=false` → se factura en borrador/no-electrónico ahora; la emisión DIAN real
      (timbrado) se valida con la cuenta del cliente que sí tiene facturación electrónica.
- [x] Mapeo catálogo → ítems Alegra: `app/billing.py` (`build_invoice_lines` puro +
      `invoice_order`). El total cuadra con `price_adjustment.total` del event_payload
      (base ajustado por removidas + agregadas como líneas). `create_request` ahora devuelve
      `event_payload` (cambio aditivo) para no reconstruir la lógica de catálogo.
- [x] Hook al cerrar orden `route_scheduling`: `agent._try_invoice_in_alegra` tras
      `db.create_request`, bajo `ALEGRA_ENABLED`. Sync de contacto + factura borrador; guarda
      IDs como evento `alegra_invoiced` (sin tocar esquema Supabase). try/except: si Alegra
      falla, loggea y NO rompe el cierre ni la recogida.
- [x] Tests: `tests/test_alegra_billing.py` (7) — build_invoice_lines + hook (éxito, fallo
      no rompe, orden sin perfil no factura). Suite 84/84.
- [x] Validado end-to-end contra cuenta Colombia real: hook → factura con total correcto
      (95000) → evento guardado. Decisión del usuario: facturar TODA orden, automático.
- [ ] PENDIENTE emisión DIAN real (cuenta del cliente): IVA de análisis, régimen por cliente,
      numeración electrónica. Hoy se factura en borrador/no-electrónico.

### Fases 3–4 — Pendientes
- [ ] Fase 3: link de pago en chat para `pago_linea` (requiere activar pagos electrónicos / Mercado Pago).
- [ ] Fase 4: consulta de facturas/saldo (read-only) dentro del intent `accounting`.

---

## Bucle de especie/typos + fallback robótico (caso Luciano) ✅ COMPLETA

Bug reportado: pidiendo la especie, el cliente responde "Kanino"/"Kany"; el modelo
no lo captura, repregunta idéntico, y el anti-bucle lo reemplaza por la frase
robótica "Para avanzar, dime el dato que tengas a mano o escribe 'hablar con
alguien'…". Causa: `_rephrased_repeated_question` no tenía branch para especie
(ni sexo ni pago) → caía al genérico feo; y "Kanino" no se recuperaba de raíz.

Arreglo (preciso, sin tocar el umbral del anti-bucle):
- [x] `agent.py` `_rephrased_repeated_question`: branches cálidos para especie, sexo
      y pago; genérico final sin "hablar con alguien" seco.
- [x] `agent.py` `_recover_enumerated_answer` + `_RECOVERABLE_SPECIES`/`_RECOVERABLE_SEX`:
      recupera variantes/typos de los campos enumerados ANTES del anti-bucle.
      `_avoid_redundant_route_field_question` corrige el reply al siguiente campo.
- [x] `prompt.py`: PASO 3 especie (capturar variante / confirmar ambiguo) + R5b
      (nunca repetir pregunta idéntica; confirmar u ofrecer opciones).
- [x] Capa de coherencia afinada: detector `_looks_off_topic_smalltalk` ahora cubre
      conectores ("y", "ah", "pero"…) y frases sociales ("cómo vas", "qué más"), y se
      quitó la optimización que saltaba el verificador (hacía que el off-topic saliera
      con tono seco en vez de cálido). Off-topic → SIEMPRE reencauce cálido.
- [x] Tests: typo de especie se recupera y avanza a raza; typo de sexo → Macho;
      repregunta de especie/pago da opciones cálidas; off-topic con conectores → cálido.
- [x] Verificado: py_compile OK; suite 206 passed.

### Resultados (validado contra el modelo REAL, gpt-5.4-mini)
Script `tools/scripts/validate_coherence.py` (db mockeada, `ai.generate_turn` real):
- "Kanino" → "registro canino. ¿Cuál es la raza?" (Canino). Sin bucle.
- "es un gatito" → Felino.
- "Kany" (ambiguo) → "¿Te refieres a canino?" (el modelo confirma).
- "jaja, ¿y cómo vas?" (off-topic) → "Jajaja, bien por acá, gracias. ¿Me compartes
  el nombre del médico solicitante?" (cálido, no captura basura).
- "masho" → Macho, avanza.
El bug original (frase robótica "hablar con alguien" / bucle) quedó cerrado. Ver L20.

---

## Capa de coherencia en el flujo de datos del paciente ✅ COMPLETA

Problema: cuando el cliente no sigue los pasos (pido el médico/edad y responde
"hola, ¿cómo estás?" u otra cosa), la coherencia estaba 100% delegada al prompt
del LLM (sección "Coherencia antes de capturar" + R22/R23). El LLM a veces igual
capturaba basura. El flujo de cliente nuevo ya tenía una red de seguridad real
(`interpret_nc_step`), pero el flujo principal de datos del paciente no.

Decisión de diseño (confirmada con el usuario):
- Híbrido, replicando el patrón ya existente: chequeo barato determinista primero,
  verificador-LLM corto SOLO cuando la respuesta huele a off-topic. No agrega una
  segunda llamada en cada turno.
- Tono de reencauce: humano y cálido, breve (colombiano), no robótico.

Pasos:
- [x] `ai.py`: `interpret_route_field(question, user_message)` — gemelo de
      `interpret_nc_step`, devuelve `{action: save|clarify, value, reply}`.
- [x] `agent.py`: `_enforce_field_coherence(...)` + `_looks_off_topic_smalltalk`
      (normaliza acentos) + `_COHERENCE_GUARDED_FIELDS`. Solo actúa en
      route_scheduling con cliente identificado, fuera de fases terminales y del
      armado de perfil. Si el modelo ya manejó bien el off-topic (no capturó nada
      nuevo y su reply repregunta el mismo dato), no gasta la llamada extra.
- [x] Insertado tras `_clarify_captured_field`, antes de confirmación/cierre (frena
      antes de crear cualquier request).
- [x] Tests: off-topic se reencauza y NO captura; respuesta válida no gasta llamada
      extra; modelo que ya repreguntó no gasta llamada extra.
- [x] Verificado: py_compile OK; `test_agent_flows` 112 passed; suite 202 passed.

### Resultados
- Campos cubiertos: requesting_doctor, patient_name, species, breed, sex,
  patient_age, owner_name. Quedan fuera exam_type (lo gobierna catálogo/perfil) y
  cliente/dirección/pago/observaciones (tienen manejo dedicado).
- La red de seguridad solo se activa ante señales claras de off-topic (saludo,
  small talk, pregunta social), así no encarece el caso común.

---

## Forma de pago dentro de ruta activa ✅ COMPLETA

Bug detectado durante `validate_flows.py`: si el bot estaba pidiendo la forma de
pago, el modelo podía clasificar "pago en línea" como `accounting` y crear una
solicitud incompleta, o si el usuario decía "pago en línea" antes del turno de
pago podía descarrilar el campo faltante.

Arreglo:
- [x] `agent.py`: `_payment_method_from_text` normaliza `contraentrega` y
      `pago_linea` desde texto del usuario.
- [x] Si la ruta activa está esperando `payment_method`, se fuerza
      `intent=route_scheduling` y se muestra confirmación editable antes de crear
      la orden.
- [x] Si todavía falta otro campo, una forma de pago fuera de turno no cierra ni
      escala: se vuelve a preguntar el campo faltante.
- [x] Tests: pago clasificado erróneamente como contabilidad dentro de ruta y pago
      dicho antes del turno de pago.

### Resultados
- `pytest tests/test_agent_flows.py tests/test_db_identification.py` → 134 passed.
- `python tools/scripts/validate_flows.py` → 6/6 flujos OK con modelo real.

---

## Memoria del cliente + manejo de off-topic ✅ COMPLETA

Objetivo: que el agente recuerde datos estables del cliente a lo largo de la
conversación y los reofrezca con confirmación ("el mismo de siempre"), y que
responda con naturalidad a mensajes fuera de alcance sin abandonar el flujo.

Decisiones de diseño:
- Solo se recuerdan datos ESTABLES del cliente: `pickup_address`,
  `requesting_doctor`, `payment_method`. Los datos del paciente NO se recuerdan
  entre órdenes (riesgo de arrastre). Teléfono fuera (R11).
- Se persiste en `captured_fields._client_memory` (JSON existente, sin tocar
  Supabase). Sobrevive solo porque empieza con `_` (agent.py:2043-2046).
- La confirmación conversacional y el off-topic los maneja el LLM con reglas de
  prompt + memoria inyectada al contexto. NO se construye máquina de estados nueva.

Pasos:
- [x] `agent.py`: constante `_CLIENT_MEMORY_FIELDS`.
- [x] `agent.py` (`_persist_turn`): `_remember_client_fields` vuelca los campos estables a `_client_memory`.
- [x] `agent.py` (`process_turn`): arma `session["_client_memory_hint"]` antes de llamar al modelo.
- [x] `ai.py`: inyecta el hint de memoria en `state_parts`.
- [x] `prompt.py`: R21 (reofrecer dato estable recordado + confirmar) y R22 (off-topic: declinar breve + retomar flujo).
- [x] Verificar: `py_compile` OK; suite `tests/` 199 passed (2 fallos preexistentes y ajenos: cargan un Excel de otra máquina).
- [x] Prueba local con modelo real: `validate_flows.py` reofrece "el de siempre" como médico solicitante y continúa al paciente.

### Resultados
- Memoria persistente sin tocar Supabase ni el JSON schema (vive en `captured_fields._client_memory`).
- El LLM maneja la confirmación conversacional y el off-topic vía R21/R22 — sin máquina de estados nueva.
- El atajo determinista del otro dev (`_resolve_same_as_previous`, misma sesión) sigue intacto y no colisiona: corto plazo = atajo; largo plazo = LLM con memoria inyectada.
- Verificación final: tests determinísticos de memoria + `validate_flows.py` 6/6 OK con modelo real.

---

## Desplegar análisis por área/muestra (ej. "orina") ✅ COMPLETA

Bug: al pedir "análisis de orina" el bot no despliega opciones y cae en "Para
avanzar necesito el análisis o perfil exacto". Causa: "orina" no es perfil ni
etiqueta diagnóstica; es la categoría "Uroanálisis" / sample "Orina Fresca" de
los análisis individuales (`catalog_tests`), que el bot no consulta al elegir
examen. Las 3 búsquedas (find_catalog_profiles/profile/diagnostic_label) dan vacío.

Solución (elegida: completa, generaliza a todas las áreas):
- [x] `db.find_tests_by_area(query, species)`: matchea la query contra categoría
      o sample de `catalog_tests` y devuelve (área, tests). Resuelve orina vía sample.
      Defensiva (try/except → None,[] si la BD no responde).
- [x] `agent._test_area_suggestion_reply` + `_enforce_test_category_help`: réplica
      de `_enforce_diagnostic_label_help`. Despliega los análisis del área y arranca
      selección (selected_tests=[]), reusando el flujo de perfil personalizado.
      Usa el término del usuario en el mensaje (no la categoría interna).
- [x] Insertado en el pipeline después de `_enforce_catalog_profile_help`.
- [x] Guard "exam_type nuevo" (compara con prev_captured): solo evalúa el área en
      el turno donde se menciona el examen → evita I/O y re-disparos en pasos posteriores.
- [x] Verificado: py_compile + suite 199 passed + simulación end-to-end con "orina".
- [x] Tests agregados: enforcement de área en `agent.py` y matching por `sample` en `db.find_tests_by_area`.

### Resultados
- "quiero un análisis de orina" ahora despliega las 7 opciones de Uroanálisis con precio.
- Regresión detectada y corregida: sin el guard de "exam_type nuevo", el enforcement
  hacía I/O en cada turno y rompía 30 tests (ConnectError). Ver L17.

---

## Perfiles por necesidad diagnóstica (etiquetas) ✅ COMPLETA
Integra el sheet de etiquetas: cuando el cliente pide un perfil por motivo clínico, el sistema sugiere las pruebas y arma un perfil personalizado (con descuento por volumen).
- [x] Datos: `tools/data/diagnostic_labels.json` (31 etiquetas, 66 pruebas; códigos cruzan 100% con `catalog_tests`).
- [x] Migración `012_diagnostic_labels.sql`: tabla `diagnostic_label_tests (label, test_code)`.
- [x] Script `tools/scripts/import_diagnostic_labels.py` (idempotente, lee el JSON).
- [x] `db.py`: `list_diagnostic_labels`, `find_diagnostic_label`, `get_tests_for_label` (defensivas si la tabla no existe aún).
- [x] `agent.py`: `_enforce_diagnostic_label_help` sugiere pruebas y arranca perfil personalizado (`selected_tests=[]`); prioridad a perfiles de catálogo con precio fijo. Etiquetas inyectadas al contexto. Prompt con regla.
- [x] Tests: matching normalizado de etiqueta + sugerencia en el flujo. Suite verde (186).
- ⚠️ Pasos manuales en Supabase: aplicar migración `012` y luego `python tools/scripts/import_diagnostic_labels.py`.

---

## Alineación con spec v4.3 — Plan por fases (pendiente de aprobación)

### Alcance acordado
HACER: #2 (parcial), #3, #6, #8, #9, #10, #12, #13, #14, #15, #16, #17.
OMITIR por ahora: #1 (WhatsApp), #4 (consulta resultados), #5 (notificaciones), #7 (correo), #11 (foto/OCR).

### Decisiones tomadas
- Descuentos (#15): estructura de tramos parametrizable en `config.py`, valores vacíos → sigue 0.
- N° de orden (#16): reinicia por año → `A3-2026-001`.
- Pago en línea (#6): registra la orden + deriva a contabilidad ("te contactan en X min").
- Cliente final (#2): se detecta y se BLOQUEA la sesión; el agente deja de responder.

---

### FASE 1 — Ajustes de captura (bajo riesgo) ✅ COMPLETA
Archivos: `prompt.py`, `agent.py`, `schema.py`, `db.py`
- [x] #8 Quitar teléfono: eliminado `clinic_phone` del schema, de las tuplas de campos, del prompt, de los fallbacks y del resumen. El teléfono de la orden impresa se toma del cliente (`_client_phone` desde BD) vía `_service_order_event_payload`.
- [x] #9 Exámenes al final: orden ahora Médico → Paciente → Especie → Raza → Sexo → Edad → Propietario → Observaciones → **Exámenes** (en `prompt.py` y `_ROUTE_ORDER_FIELDS_BEFORE_PAYMENT`).
- [x] #10 Regla de edad: prompt con ejemplos; `_age_has_unit` + `_missing_route_field` tratan la edad sin unidad como faltante para repreguntar.
- [x] #17 Ortografía forzada: `_normalize_name_fields()`/`_titlecase_value()` aplican Mayúscula inicial a clinic_name, patient_name, species, breed, owner_name, requesting_doctor. No toca exam_type ni observations.
- Resultado: `tests/` verde (86 en test_agent_flows).

### FASE 2 — Menú y confirmación de cierre ✅ COMPLETA
Archivos: `prompt.py`, `agent.py`
- [x] #3 Menú numerado (Etapa 3): el `WELCOME_MESSAGE` ahora ofrece `1 Programar · 2 Resultados · 3 Pagos · 4 Otro` y el prompt mapea la respuesta numérica al intent (1→route, 2→results, 3→accounting, 4→unknown/derivar).
- [x] #12 Confirmación editable: nueva `_enforce_confirmation_step` intercepta el cierre y muestra el resumen "Antes de registrar… ¿Confirmas? (Sí / Corregir)" en `fase_4_confirmacion` sin registrar. Al confirmar, el pipeline cierra (fase_6/fase_7) y crea la request. "Corregir <campo>" se resuelve con short-circuit determinista (`_detect_correction_field`/`_clear_field_for_correction`) que limpia el campo y lo repregunta. Refactor: `_order_summary_lines` (compartido cierre/confirmación), `_finalize_request` y `_persist_turn`.
- Resultado: suite verde (176 pasan). Se reescribieron los tests de cierre al flujo de 2 turnos y se añadieron tests del mecanismo de corrección.

### FASE 3 — Pago en línea ✅ COMPLETA
Archivos: `schema.py`, `prompt.py`, `agent.py`, `dashboard.py`
- [x] #6 `payment_method` enum ahora `["contraentrega", "pago_linea"]` (reemplaza "contado"). `pago_linea` → registra la orden con su N°, `requires_handoff=true`, `handoff_area=contabilidad`, y reply `PAYMENT_ONLINE_HANDOFF_MESSAGE` ("contabilidad te contactará en breve para enviarte el link… la recogida sigue programada"). Ajustados `_enforce_payment_step`, `_apply_handoff_guardrails`, `PAYMENT_METHOD_QUESTION`, prompt PASO 4 y reglas de negocio. Etiquetas legibles (`PAYMENT_METHOD_LABELS`) en el dashboard/print.
- Resultado: suite verde (176 pasan). Nuevo `test_route_with_pago_linea_sets_accounting_handoff_and_creates_request`; tests de pago y dashboard actualizados.

### FASE 4 — Identificación ✅ COMPLETA
Archivos: `agent.py`, `db.py`, `main.py`, `prompt.py`
- [x] #2 Bloqueo de cliente final: al detectar `_is_final_user_text` se marca `captured_fields._blocked` y se persiste. `process_turn` retorna `None` si la sesión está bloqueada; `main.py` (telegram y chatwoot) no envía nada cuando el reply es `None`.
- [x] #13 Sucursales: nuevo `db.find_clients_by_tax_id` devuelve todas las sedes con ese NIT. Si hay >1 → se listan con `_client_match_options` y `_client_match_options_reply` detecta sedes del mismo cliente ("¿Desde cuál sede solicitas?"). Selección por número. Corregido el descarte de opciones para no perder las sedes cuando el NIT viene preservado.
- [x] #14 Cliente nuevo: regla vigente del chatbot = escalar inmediatamente a operaciones/recepción sin capturar datos en chat. El alta y la revisión pendiente se gestionan desde la plataforma/dashboard, no desde Telegram. Las sesiones legacy que ya estaban en Flujo B se siguen atendiendo para no dejarlas colgadas.
- Resultado: suite verde (181 pasan en ese momento). Tests de identificación migrados a `find_clients_by_tax_id`; el comportamiento vigente queda documentado en `tasks/errores-soluciones.md`.

### FASE 5 — Negocio / datos ✅ COMPLETA
Archivos: `config.py`, `rules.py`, `prompt.py`, nueva migración `011`
- [x] #15 Descuentos parametrizables: `DISCOUNT_TIERS: list[tuple[int, float]] = []` en `config.py`; `calculate_discount` aplica el porcentaje del mayor tramo alcanzado. Vacío → 0 (sin cambios de comportamiento hasta tener la tabla real).
- [x] #16 N° orden anual: migración `011_order_number_yearly.sql` con `order_number_counters` + función `next_order_number()` que genera `A3-<año>-<seq 3 díg>` reiniciando por año (zona America/Bogota) y cambia el DEFAULT de la columna. `create_request` ya lee el valor generado (sin cambio de código, defensivo). R17 del prompt actualizada al formato `A3-2026-001`.
- ⚠️ La migración `011` debe aplicarse manualmente en el SQL Editor de Supabase.
- Resultado: suite verde (183 pasan). Nuevos tests de `calculate_discount` (tramos vacíos y configurados).

### Verificación
- Correr `tests/` tras cada fase y actualizar los tests afectados (test_agent_flows, test_db_identification).
- Demostrar cada fase con un flujo de ejemplo antes de marcar completa.

---

## Número de orden legible (A3-00042) — Plan, pendiente de aprobación

### Objetivo
Al cerrar una orden de servicio, generar un número legible y secuencial
(`A3-00042`), guardarlo asociado al pedido en `requests`, mostrarlo al cliente
en el cierre y poder dárselo si lo pide por chat. El AI NUNCA inventa el número.

### Decisiones
- Formato: `A3-00042` (prefijo + secuencial continuo, 5 dígitos, sin año).
- Consulta por chat: devuelve la ÚLTIMA orden del cliente identificado.
- Migración DDL: la aplica el usuario en el SQL Editor de Supabase (no hay
  `SUPABASE_ACCESS_TOKEN` en `.env`).

### Diseño
1. **`db/migrations/010_order_number.sql`** (aplicar en Supabase):
   - `CREATE SEQUENCE request_order_seq`
   - `ALTER TABLE requests ADD COLUMN order_number text UNIQUE DEFAULT
     ('A3-' || lpad(nextval(...),5,'0'))` → cada INSERT genera el número solo.
2. **`app/services/db.py`**:
   - `create_request` devuelve `{request_id, order_number}` (lee el campo que la
     BD generó por DEFAULT). Defensivo: si la columna no existe → `order_number=None`.
   - `get_last_order_for_client(client_id)` → última request con su número.
3. **`app/agent.py`**:
   - Crear la request ANTES de armar el reply de cierre, capturar `order_number`
     y añadir "Número de orden: A3-00042" al mensaje (defensivo si es None).
   - Heurística `_is_order_number_query()` + short-circuit: si el cliente
     identificado pregunta su número, responder con el real de la BD (sin AI).
4. **`app/prompt.py`**: regla R17 — nunca inventar números de orden.
5. **Tests**: cierre incluye el número; consulta devuelve el número; la heurística
   no se dispara con "crear otra orden".

### Compatibilidad
- El cierre de órdenes es defensivo: si la migración aún no se aplicó, el insert
  no cambia y simplemente no se muestra número (no rompe producción).

### Items
- [x] Migración `010_order_number.sql`
- [x] `db.py`: create_request devuelve número + get_last_order_for_client + list_requests trae order_number (select defensivo `*`)
- [x] `agent.py`: número en cierre + consulta por chat (`_is_order_number_query` short-circuit)
- [x] `prompt.py`: R17
- [x] `dashboard.py`: order_number en service_order_rows, sample lanes y operation center
- [x] templates: dashboard.html (ficha) + service_order_print.html (título y cuerpo)
- [x] Tests + verificación: 176 passed (5 nuevos)

### Resultado (2026-06-01)
Número de orden `A3-00042` implementado punta a punta. El cliente lo recibe al
cerrar la orden y puede pedirlo por chat ("¿cuál es el número de mi orden?"); el
dashboard lo muestra en la ficha, la vista de impresión y el seguimiento de
muestras. Defensivo: si la migración no está aplicada, no rompe (no muestra número).
Sin fallos del agente en esa verificación.

**PENDIENTE DEL USUARIO:** aplicar `db/migrations/010_order_number.sql` en el SQL
Editor de Supabase (no hay SUPABASE_ACCESS_TOKEN para aplicarla por script).

---

## Mensaje "déjame revisar los registros" antes del lookup de cliente — En curso

### Objetivo
Cuando el usuario da NIT o nombre de veterinaria y el bot va a buscarlo en la BD,
mandar primero un mensaje intermedio ("Permíteme un momentico mientras reviso
nuestros registros 🔍") con indicador de "escribiendo…" y pausa de ~1.5s, antes de
decir si está registrado o no.

### Diseño
- `process_turn` recibe callback opcional `on_progress(msg)` (default None) → no
  rompe firma ni tests existentes.
- El agente llama `on_progress(...)` UNA sola vez, justo antes de tocar la BD para
  la primera búsqueda de cliente por NIT/nombre.
- El webhook (main.py) implementa `on_progress`: manda el mensaje, activa "escribiendo…"
  y espera ~1.5s. Respeta separación de capas (agent no importa telegram/chatwoot).
- El mensaje de progreso es efímero: NO se persiste en conversation_messages.

### Items
- [x] `app/services/telegram.py`: `send_typing(chat_id)` → sendChatAction typing
- [x] `app/services/chatwoot.py`: `send_typing(conversation_id)` → toggle_typing_status on
- [x] `app/agent.py`: constante + param `on_progress` + llamada antes del lookup
- [x] `app/main.py`: `on_progress` en ambos webhooks
- [x] Verificar: 171 passed (2 tests nuevos del callback) + Flask reiniciado y /health OK

### Resultado (2026-06-01)
Implementado con callback `on_progress`. El agente avisa "Permíteme un momentico
mientras reviso nuestros registros 🔍", activa "escribiendo…" y espera 1.5s antes
de confirmar si el cliente está registrado. Tests: 171 passed.

---

## Agente Conversacional — Completado

### Core (Bloques 1–4)
- [x] `schema.py` → 10 campos, intents en inglés, 8 fases nombradas, message_mode, pending_intents, confidence
- [x] `prompt.py` → system prompt limpio, sin JSON embebido
- [x] `rules.py` → INTENT_TO_SERVICE_AREA + TERMINAL_PHASES
- [x] `db.py` → get_or_create_session, update_session, create_request alineados con modelo real
- [x] `agent.py` → pending_intents entre turnos, transición a fase terminal
- [x] `ai.py` → recibe pending_intents, filtra campos internos

### Tests obligatorios — 11/11 ✓
- [x] Test 1: cliente con motorizado asignado → solicitud `assigned`
- [x] Test 2: cliente sin motorizado → `error_pending_assignment` + evento en `request_events`
- [x] Test 3: cliente nuevo → `fase_7_escalado` inmediato, sin recolectar datos
- [x] Test 4: solicitud post-17:30 → `scheduled_pickup_date` = siguiente día hábil
- [x] Test 5: múltiples intenciones en un mensaje → ambas procesadas en orden correcto
- [x] Test 6: usuario repite sin dar dato → agente ofrece opciones en vez de preguntar de nuevo
- [x] Test 7: usuario cancela solicitud en curso → cancelación confirmada, flujo limpio
- [x] Test 8: conversación interrumpida y retomada → sin saludo, continúa donde estaba
- [x] Test 9: gestión de pagos → derivación inmediata a contabilidad
- [x] Test 10: alta de cliente nuevo → derivación inmediata a operaciones
- [x] Test 11: toda solicitud de ruta → priority siempre "normal" en BD

### Modificaciones V2.1 (llamadas con cliente)
- [x] Preguntas conversacionales, una por turno (no formulario)
- [x] Búsqueda progresiva de cliente: NIT → nombre → escalada
- [x] Forma de pago: contado vs contraentrega (PASO 4 del flujo)
- [x] Recolección conversacional: exam_type → patient_name → species (patient_age/owner_name opcionales)
- [x] "Crear tu perfil": selected_tests, catálogo individual, cálculo de subtotal/total
- [x] Chat permanece abierto: solo cierra con despedida explícita del usuario
- [x] Notificación del motorizado al cerrar orden (`agent.py` → append a reply)
- [x] Múltiples órdenes en misma sesión: reset de campos de orden al retomar desde fase terminal

---

## Agente Conversacional — Pendiente

### Tests nuevos (V2.1)
- [x] Múltiples órdenes en misma sesión: segunda orden con cliente ya identificado
- [x] "Crear tu perfil": seleccionar análisis individuales, ver subtotal calculado
- [x] Notificación de motorizado: mensaje incluido en cierre de orden

---

## Plataforma Interna — Pendiente (NO es el agente conversacional)

Estas funciones se implementarán en la plataforma de gestión, no en el chatbot.

- [ ] **Descuentos por cantidad**: `calculate_discount()` en `rules.py` es placeholder (retorna 0). Las reglas de descuento las define el cliente y se configuran desde la plataforma. La BD las persiste; el agente solo las lee.
- [ ] **Asignación por zonas geográficas**: hoy el agente asigna por `client_courier_assignment` (tabla por cliente). La asignación por zona requiere la tabla de zonas que define el cliente; se gestiona desde la plataforma.
- [ ] **Integración ANARVET**: consulta de estado de análisis. La plataforma expone el estado; el agente lo consumirá vía endpoint interno cuando esté disponible.
- [ ] **Gestión de zonas y motoristas**: calendario de repartidores, asignación manual de override, edición de zonas.
- [ ] **Dashboard y reportes**: órdenes por día, por motorista, por zona, perfiles más solicitados.
- [ ] **Gestión de clientes**: alta manual, edición de datos, vinculación a zona.
- [ ] **Gestión de portafolio**: cargar nuevo catálogo, editar precios, definir perfiles predefinidos.

### Información pendiente del cliente (bloquea algunas de las anteriores)
- [ ] Números de teléfono para escalar contabilidad/pagos y PQRs
- [ ] Definición de zonas geográficas (número, descripción, motorista asignado)
- [ ] Tabla de descuentos por cantidad de parámetros
- [ ] Estructura de perfiles predefinidos en el catálogo
- [ ] API ANARVET: endpoint, autenticación, datos expuestos
- [ ] **PRÓXIMA REUNIÓN — Mascolab (PCR)**: cada ítem tiene DOS precios (Punto Final,
      el menor, y Tiempo Real, el mayor) y el catálogo admite uno solo. ¿Cuál cotiza el
      bot, o el médico elige la técnica en el chat? Sin esta respuesta las págs. 19-27
      del PDF no se cargan a la base (decisión 2026-08-21). De paso confirmar las 2
      erratas del PDF (código 2407 duplicado y 2061 duplicado). Detalle completo y
      tabla con ambos precios: `docs/catalogo-mascolab-pendiente.md`

---

## Resultados

**2026-04-27** — Bloques 1-4 completados.
**2026-04-30** — Tests obligatorios validados: 11/11 completados.
**2026-05-01** — Flujo de búsqueda progresiva + forma de pago cerrados para V2.1.
**2026-05-03** — Separación plataforma vs. agente documentada. Notificación de motorizado y múltiples órdenes en sesión implementadas en `agent.py`.
**2026-05-11** — Tests V2.1 pendientes cubiertos y suite validada: 64/64.
**2026-05-11** — Alta manual de clientes en dashboard afinada: validación de formulario, motorizado sugerido y contexto de motorizados cubiertos por tests. Suite validada: 68/68.
**2026-05-15** — Zonas territoriales A3 estructuradas: `data/barrios_zonas_a3.csv`, `app/territory.py`, migración `006_territorial_zones.sql` y scripts de carga. Supabase actual: 8 motorizados verificados y 282 asignaciones cliente→motorizado cargadas. Pendiente aplicar migración con credencial admin SQL para subir 1649 barrios.
**2026-05-15** — Alta manual de cliente ahora sugiere motorizado automaticamente por barrio/localidad/zona, con override manual del operador. Endpoint `GET /api/dashboard/courier-suggestion` y guardado de `courier_suggestion` en revisión. Suite validada: 83/83.
**2026-05-15** — Autocompletado de barrios agregado en alta manual: `GET /api/dashboard/neighborhood-search`, autollenado de localidad/zona y sugerencia de motorizado. Suite validada: 84/84.
**2026-06-13** — Allegra queda fuera de alcance por ahora: eliminados scripts/tests activos que dependían de Excel externo. `pytest` completo queda verde (214 passed). Auditoría Supabase read-only: core/catálogo/órdenes/etiquetas OK; tablas territoriales de migración `006` aún no están en Supabase (warning no bloqueante para el bot principal).
**2026-05-15** — Flujo de migracion territorial cerrado: script `apply_supabase_migration.py` para aplicar DDL con `SUPABASE_ACCESS_TOKEN`, seed territorial idempotente y runbook actualizado. Service role key no permite crear tablas.
**2026-05-15** — Proyecto autosuficiente con `.env` local protegido por `.gitignore`; seeds corren sin rutas antiguas. Operacion territorial funcional con fallback interno hasta que existan tablas territoriales en Supabase.
**2026-05-15** — Centro Operativo Diario agregado en `/operacion`: KPIs de rutas, aprobaciones, muestras abiertas, alertas, rutas por gestionar y clientes nuevos. Suite validada: 85/85.
**2026-05-15** — Agenda por motorizado agregada dentro de `/operacion`, agrupando rutas activas por mensajero y columna `Sin asignar`. Suite validada: 86/86.
**2026-05-24** — Orden de servicio conversacional alineada al PDF oficial: datos completos antes de pago/cierre, persistencia en `request_events.event_payload.service_order`, vista Supabase `service_orders` preparada y PDF guardado en `docs/forms/orden-de-servicio-2025.pdf`. Suite validada: 131/131.
**2026-05-24** — Plataforma muestra ordenes de servicio del agente en `/operacion` y `/muestras`, con ficha visual tipo formulario y tarjetas derivadas en proceso de muestras. Suite validada: 133/133.
**2026-05-24** — Agregada vista imprimible de orden de servicio en `/ordenes-servicio/<request_id>/imprimir`, accesible desde las fichas como `Imprimir PDF` para imprimir o guardar desde el navegador. Suite validada: 134/134.
**2026-05-24** — Flujo multiorden ajustado: al cerrar una orden el agente pregunta si necesita otra para otro paciente/animal; respuesta afirmativa inicia nueva orden sin reidentificar cliente y respuesta negativa cierra la conversacion. Suite validada: 137/137.

**2026-06-13** — Memoria entre órdenes mejorada + captura de varios análisis sin bucle. (1) Al crear una orden de seguimiento el agente reusa los datos estables (médico, dirección, pago) de la orden anterior y los confirma en bloque (`_carry_over_stable_fields` + flag `_stable_confirm_pending`), en vez de repreguntarlos en blanco; el reconocimiento de "el mismo" se amplió y ahora cae a `_client_memory` aunque no haya snapshot (resolución determinística sin AI). (2) Nuevo guardrail `_enforce_multiple_tests_capture`: si el cliente pide varios análisis en un mensaje y cada ítem mapea 1:1 al catálogo, los registra como perfil personalizado sin repreguntar el tipo (evita bucle); si hay ambigüedad, deja el flujo normal. Prompt R24 agregada. Suite validada: 221/221 + 6/6 flujos con modelo real.

**2026-06-13** — Tres mejoras de robustez del agente (ordenado y sin loops): (#1) backstop determinístico `_enforce_custom_profile_close`: el perfil personalizado armado desde cero se cierra y fija `exam_type` cuando el cliente lo pide, sin depender del modelo (evita el bucle "¿agregás otro o cerramos?"). (#6) Eliminado el "Flujo B" muerto de cliente nuevo (`_start_new_client_capture`, `_handle_new_client_capture`, `_save_new_client_pending`, constantes `_nc_*`/`NEW_CLIENT_*`, `ai.interpret_nc_step`): nunca se invocaba y contradecía la regla "el bot nunca registra cliente nuevo"; sesiones viejas con `_nc_capturing` se auto-sanan y escalan por el flujo normal. (#3) Resume determinístico de intenciones: "resultados + recogida" en un mensaje ya no pierde la ruta — entrega el mensaje fijo de resultados y retoma la recogida en el mismo turno (`_enforce_results_message`). Suite: 222/222 + 6/6 flujos con modelo real.

**2026-07-06** — Portal Web implementado (decisión 010): blueprint `/portal` con dos roles vía Supabase Auth (GoTrue, `app_metadata.portal_role` + `client_id`; alta solo por `tools/scripts/create_portal_user.py`). Staff: buscar/subir/publicar/descargar resultados PDF (bucket privado `lab-results`, signed URLs 5 min); compartir = publicar + notificación + aviso Telegram. Cliente: solicitar retiro (reutiliza `db.create_request` intacto: corte 17:30, motorizado determinista, order_number), historial con estados, resultados publicados propios, notificaciones y perfil solo lectura. Aislamiento estricto por `session["portal_client_id"]`. Dashboard y flujo conversacional intactos (main.py solo registra el blueprint). Migración `015_portal_results_notifications.sql` lista — PENDIENTE aplicarla (requiere `SUPABASE_ACCESS_TOKEN` o SQL Editor) y agregar `SUPABASE_ANON_KEY` al `.env`. Suite: 214 passed + 19 tests nuevos del portal (los 4 fallos de `test_dashboard.py` son preexistentes en HEAD).

**2026-07-06 (revisión)** — El usuario definió que el Portal Web es SOLO para clientes veterinarias: el personal ya tiene su plataforma (dashboard). Se eliminó la vista staff del portal (`app/portal/staff.py`, template y tests) y la carga/publicación de resultados se movió al dashboard como blueprint separado `app/dashboard_results.py` (ruta `/resultados`, usa la sesión/login del dashboard existente; `dashboard.py` NO se modificó — solo se agregó el enlace «Resultados» al menú de `dashboard.html` con OK explícito). Login del portal ahora solo acepta cuentas con `portal_role=client`; `create_portal_user.py` simplificado a solo clientes. Decisión 010 actualizada. Suite: 215 passed (los 4 fallos de `test_dashboard.py` son preexistentes).

**2026-07-06 (limpieza CRM)** — Borradas del CRM operativo las pestañas Flujo, Análisis y Aprobaciones (solo visualización read-only las dos primeras). Aprobaciones era la única vía para aprobar/rechazar clientes nuevos (activa cliente + asigna motorizado + auditoría) — antes de borrarla se movieron los botones Aprobar/Rechazar a la tabla de Clientes (nueva columna "Aprobación", visible solo si `row.pending_request_id` existe, mismo endpoint `POST /aprobaciones/decision`). Redirects de `new_client_page` y `approval_decision` ahora apuntan a `/clientes`; el aviso `notice`/`notice_type` se movió a un bloque global (ya no dependía de una pestaña). `_build_client_rows` recibe `pending_request_by_client` construido en `build_dashboard_context` reusando `db.list_pending_client_reviews` (sin doble consulta). Tests actualizados en `test_dashboard.py` (nuevo assert: Aprobar/Rechazar en /clientes + 404 en rutas eliminadas). Suite: 215 passed (los 4 fallos de siempre son preexistentes, no relacionados).

**2026-07-20** — Catálogo de RAZAS del cliente incorporado (323 razas / 14 especies, del Excel "Lista de Especies con Raza"). Antes `breed` era texto libre sin catálogo: lo único que le pasaba era un `capitalize()` por palabra que rompía tildes y camelCase, y nada relacionaba raza con especie. Ahora: tabla nueva `catalog_breeds` (migración `016` + seed `003`, 332 filas / 323 keys únicos, generada por `tools/scripts/build_breeds_seed.py`); `app/breeds.py` la lee UNA vez por proceso (`lru_cache`) y resuelve EXACT/AMBIGUOUS/NONE; `agent._recover_breed_and_species` normaliza la grafía ("pastor aleman" → `Pastor Alemán`) e infiere la especie cuando la raza pertenece a una sola ("Holstein" → Bovino), ahorrando la pregunta. **Las 8 razas ambiguas** (Criollo, Mestizo, Angora, Hampshire, Abisinio, Cruce, Siberiano, Unica) y **las 9 que son palabras de especie** (Conejo, Ave, Gallina, Canario, Cerdo, Cebú, Chinchilla, Degú, Axolote) NUNCA infieren: delegan en `species.py`. Fuzzy más estricto que el de clientes (ratio 0.87 desde 6 letras + margen 0.05) porque el mínimo de 4 de `db.py` confundía `boer`(Caprino) con `boxer`(Canino) @0.889. Nomenclatura: manda el código (Excel `Aviar/Lagomorfo/Cobayo/Hámster/Reptiles` → `Ave/Conejo/Roedor/Reptil`), el mapeo vive solo en el script. Las 5 exóticas (Erizo, Chinchilla, Sugar Glider, Degú, Axolote) se agregaron a `ANIMAL_DOMAIN` como especies propias — seguro para precios porque `catalog.py:199` solo filtra por especie en canino/felino. `flow.py` NO se tocó: una raza desconocida ("tobiano", "no sé") no bloquea nada. Suite: 401 passed + 70 tests nuevos (los 6 fallos de dashboard/portal son preexistentes por red). Flujos con modelo real: 21/26 — los 2 nuevos (Y raza infiere especie, Z raza ambigua sigue preguntando) en verde, y los 5 en rojo (A, F, M2, S, T) fallan idénticos en el baseline sin estos cambios.

**2026-07-20 (contactos, cartera y territorial)** — Los dos Excel restantes NO eran "datos por cargar": una importación previa ya los había ingresado (`clients_a3_professionals` traía 1.828 filas y entre sus `source_sheet` está `Alegra - Terceros`). El valor estaba en el vínculo y la calidad. **(A) Facturación:** se encontró un defecto real — `_client_email` estaba declarado en `state.py:74` y leído en `agent.py:1928`, pero NADIE lo escribía, así que todo contacto creado en Alegra iba SIN correo (y en facturación electrónica el correo es por donde la DIAN entrega la factura). Causa: `clients` no tenía columna de correo. Migración `017_clients_email.sql` (rompe deliberadamente la convención de no tocar `clients` de las decisiones 006/009: `clients_a3_knowledge` se indexa por nombre normalizado y el agente nunca la lee, así que era el único camino al flujo real). `tools/scripts/import_alegra_emails.py` cruza por NIT reusando `db._nit_candidates()` y cargó 218 filas / 197 clientes. Aclaración del usuario: varias sedes con el mismo NIT son la MISMA veterinaria y Alegra crea un contacto por NIT, así que el correo se carga en todas las sedes (antes se descartaban 53 por "ambiguas"). Cableado en `_store_client_context` + `email` agregado a los 3 selects explícitos de cliente. **(E) Territorial:** la migración `006` nunca se había aplicado desde mayo — `territorial_zones`/`territorial_neighborhoods`/`courier_locality_coverage` no existían y `app/territory.py` venía funcionando con el CSV como fallback, por eso nadie lo notó. Aplicada + seed: 8 zonas y 1.649 barrios, cero discrepancias contra el CSV. Además la `005` estaba aplicada A MEDIAS: faltaban `courier_locality_coverage` y 12 columnas de knowledge (entre ellas `electronic_invoicing` y `billing_email`); es idempotente, se aplicó completa. **(C) Calidad:** 241 de 1.083 valores del campo `email` de knowledge no eran correos (`"N/A"` x225, `"vet"`, hasta un nombre de persona); `clean_knowledge_emails.py` rescató 4 que traían el correo entre ruido y vació 237 → 846 válidos, 0 basura. Y se arregló un bug preexistente: `email` no estaba en `allowed_profile_fields` (`dashboard.py:1841`), así que el input existía y el endpoint devolvía 400 — el campo era imposible de corregir a mano. **(B) Cartera:** decisión del usuario — solo agregar y enriquecer, NUNCA dar de baja (la ausencia en una planilla no prueba nada y el match por nombre es débil). El matcher difuso (`db._name_match_score`, el mismo que usa el agente) subió los reconocidos de 397 a 443 sobre 664. De las 221 realmente nuevas: 4 con NIT → `clients` (is_active=False) + cola de aprobación; 217 solo con nombre → ficha en knowledge. Más 314 fichas para clínicas que ya eran clientes pero no tenían fila en knowledge (sin esa ficha no se les pueden cargar médicos: FK). **Clientes activos 654 antes y después.** **(D) Médicos:** `clients_a3_professionals` estaba muerta — `affiliation_rows` se pasaba al contexto como `[]` y NINGÚN template lo consumía (variable vestigial, eliminada). Nueva `db.list_client_professionals()`, agrupación por `clinic_key` en `_build_client_rows` y columna "Medicos" desplegable en la tabla de clientes, incluida en el buscador. Cargados 872 pares → 2.700 médicos. Suite: 411 passed + 11 tests nuevos (los 6 fallos de dashboard/portal son preexistentes por red, verificado con `git stash`). **El flujo conversacional no se tocó**: `flow.py`, `breeds.py`, `prompt.py`, `schema.py`, `detectors/` y `enforcers/` sin cambios; en `agent.py` solo 4 líneas en `_store_client_context`.

**2026-07-20 (auditoría de integridad)** — A pedido del usuario se verificó que las cargas no duplicaran ni pisaran datos previos. Nuevo `tools/scripts/audit_data_integrity.py` (SOLO LECTURA, sale con código 1 si hay problemas): distingue lo legítimo (varias sedes con el mismo NIT, una clínica con muchos médicos, un médico en varias clínicas) de lo que no (mismo nombre repetido, mismo NIT + mismo nombre, médico repetido en la misma clínica, huérfanos, correos/NIT inválidos). **Resultado en clientes y fichas: limpio** — 0 nombres repetidos, 0 teléfonos repetidos, 20 NITs multi-sede todos distinguibles por nombre, 197/197 correos válidos en `clients`, 850/850 en knowledge, `clinic_key` sin duplicados, 0 médicos huérfanos, 0 altas pendientes activas. **Bug encontrado y corregido en la carga de médicos:** `import_doctors.py` comparaba contra el `professional_key` guardado, pero las importaciones viejas lo escribieron con espacios y a veces con el número de tarjeta pegado ("jesus antonio correa orozco 4173 0") mientras el script usaba `_normalize_lookup_key` (guiones bajos) — el chequeo de existencia nunca los encontraba y **se crearon 24 filas duplicadas**. Se corrigió el script para comparar por NOMBRE normalizado y se borraron las 24 filas redundantes (2.700 → 2.676); re-corrido queda idempotente (910 ya cargados, 0 a insertar) y la auditoría confirma 0 duplicados atribuibles a esta carga. **Hallazgos PREEXISTENTES (no de esta carga, sin resolver):** (1) 488 pares clínica-médico duplicados, 414 de ellos por una doble carga histórica de la misma planilla (`Clientes` + `Copia de Clientes`) — son 537 filas redundantes que podrían borrarse sin perder ningún médico; (2) 13 clientes sin NIT, creados en marzo/mayo/junio, entre ellos `Dra Helen Dayana Villalobos Bonilla` que tiene **su propio nombre en el campo `tax_id`** (la misma ficha que tenía el nombre en el campo `email`); (3) 1 médico sin nombre, de la hoja `Clientes`.

**2026-07-20 (deduplicación de médicos preexistentes)** — Con OK del usuario se limpiaron las filas redundantes históricas de `clients_a3_professionals` (originadas en dobles cargas de las mismas planillas: `Clientes` + `Copia de Clientes` explicaban 414 de 488 casos). Nuevo `tools/scripts/dedupe_professionals.py` con `--dry-run` por defecto. Antes de borrar se detectó que las copias NO son idénticas: 7 pares tenían el número de tarjeta en una fila y no en la otra, y 23 tenían el nombre escrito distinto (con y sin tildes). Regla de conservación: se queda la fila (1) que tiene tarjeta, (2) con la grafía más completa —tildes—, (3) la más antigua por `synced_at`. Dos invariantes se verifican simuladas antes de escribir y reales después, y el script aborta si alguna falla: **el conjunto de pares (clínica, médico) debe ser idéntico** y **ninguna tarjeta puede perderse**. Resultado: 532 filas borradas (2.676 → 2.144), pares intactos 2.138 → 2.138, tarjetas 874 → 874. Pares duplicados: 488 → 2. **Los 2 restantes NO se tocaron a propósito**: tienen tarjetas en conflicto real (`adryvete` / Adriana Marcela Higuera: 43562 vs 43652, dígitos transpuestos; `animal consult` / Lizeth Paola Garzon: 333354 vs 33354) — elegir una sería inventar un dato, requieren decisión humana. **Pendientes preexistentes que siguen abiertos:** 13 clientes sin NIT (uno, `Dra Helen Dayana Villalobos Bonilla`, tiene su propio nombre en el campo `tax_id`), 1 médico sin nombre de la hoja `Clientes`, y los 2 conflictos de tarjeta.

**2026-07-20 (verificación integral + fix del límite de 500 clientes)** — Antes de commitear se verificó cada superficie contra el entorno real: **agente** 21-22/26 flujos con modelo real (idéntico al baseline; los rojos A/F/M2/S/T son los preexistentes documentados); **dashboard** `/`, `/clientes`, `/operacion`, `/muestras`, `/resultados`, `/facturacion` todos 200, con la columna nueva de médicos renderizando; **portal** las 6 rutas reales (`/portal/`, `/mis/solicitudes`, `/mis/solicitudes/nueva`, `/mis/resultados`, `/mis/notificaciones`, `/mis/perfil`) 200 en `PORTAL_DEMO_MODE` — OJO: el login real de clientes NO se probó porque falta `SUPABASE_ANON_KEY` en `.env`; **Alegra** conectado y autenticado (GET /contacts y GET /invoices OK, 4 contactos y 3 facturas todas en `draft`, guardrail respetado, no se creó ni modificó nada). **Bug preexistente encontrado y corregido:** `db.list_clients_with_assignment` se llamaba con `limit=500` sobre 804 clientes, así que el dashboard no mostraba a los 304 que caían después de la "L" por orden alfabético — y con ellos quedaban invisibles 2 de las 4 altas pendientes, que recepción no podía aprobar. La función ahora pagina de a 1000 (tope por request de Supabase) con `limit` como cota, y los 2 call sites de `dashboard.py` usan el default. Verificado end-to-end: 804 clientes distintos alcanzables por el paginador (15 por página, 54 páginas), los 4 botones Aprobar presentes, 279 celdas con médicos y 388 correos renderizados; `/clientes` tarda 5,4s y la query 1,07s. Dos tests nuevos: uno de que las 804 filas se construyen, otro que la query pide varias tandas cuando hay más de 1000 filas. Suite: 413 passed (los 6 fallos de dashboard/portal siguen siendo preexistentes por red).

**2026-07-20 (QA adversarial de razas/especies — 2 bugs cazados y resueltos)** — Se corrió un QA de estrés contra el MODELO REAL con el catálogo REAL de razas: `validate_flows.py` ahora carga las 332 filas de `catalog_breeds` desde Supabase (`_load_real_breeds`, con fallback a una muestra mínima si no hay red) en vez del mock de 6 razas, porque los casos que importan —las 8 ambiguas, las que chocan con palabras de especie, el par boer/boxer— solo existen en el catálogo completo. Se agregaron 6 flujos adversariales (QA1-QA6). **El catálogo aguantó todo lo que se le tiró:** QA2 "conejo" respondido a la pregunta de raza → `Pelusa (Conejo, Holland Lop, Hembra, 1 año)`; QA5 typo "doverman" → `Rocky (Canino, Doberman, Macho, 4 años)`; QA6 paciente completo en un mensaje → `Rocky (Canino, Pastor Alemán, Macho, 4 años)`; QA4 especie declarada Felino + raza bovina Holstein → `Michi (Felino, Holstein, Hembra, 3 años)`, es decir NO pisó la especie que dio el cliente. **Dos bugs preexistentes cazados y resueltos con OK del usuario:** ERR-074 ("no sé la raza" trababa la orden en bucle infinito — el más frecuente, afecta mestizos y rescatados) y ERR-075 (paciente llamado "Toro" nunca se capturaba). Ambos son la misma falla estructural: un campo obligatorio que el modelo decide no llenar y que `_enforce_first_missing_after_progress` re-pide sin fin, sin salida de emergencia. Detalle que costó el primer intento del ERR-074: `_detect_which_field_is_being_asked` hace match por substring y evalúa "especie" ANTES que "raza", así que un cierre como "anoto Axolote como especie. ¿Cuál es la raza del paciente?" resolvía a `species` y el guard no disparaba; se cambió a `_reply_asks_for_route_field(..., "breed")`, que exige la frase completa. Nuevo `tests/test_unknown_field_answers.py` (24 tests). Suite: 437 passed. **Queda abierto** el residual de QA1 (tres correcciones de raza encadenadas), que es la clase ya documentada en `docs/estado-agente-qa.md` — corrección con el valor nuevo en el mismo mensaje, pendiente de la reorganización de `process_turn`.

**2026-07-21 (QA real del usuario: 3 hallazgos)** — (1) **Bug propio, grave y repetido**: `list_client_professionals` usaba `.limit(5000)` sin paginar y Supabase corta cada request en 1000 → devolvía 1000 de 1554 filas EN SILENCIO, así que los médicos del último tramo no se encontraban nunca. El usuario lo cazó con "Paola Andrea Celis" (era `Paola Andrea Cardenas Celis`, de Animals Box, que sí es cliente activo y cuyo score de match era 1.4 — todo daba positivo pero la función devolvía []). Es EXACTAMENTE el mismo error de `limit=500` sobre 804 clientes que se había arreglado horas antes en la misma sesión; se repitió al escribir la función nueva. Se corrigió con paginación de a 1000 en `list_client_professionals` (1000→1554) y en `list_a3_knowledge_index` (1000→1427, al dashboard le faltaban 427 fichas sin ningún error visible). Test de regresión parametrizado que falla si alguna vuelve a truncar. (2) **ERR-074 ampliado**: el guard de "no sé la raza" no reconocía negar que TENGA raza ("Ni tiene raza", "no tiene raza", "ninguna", "sin determinar") — en el QA real funcionó por suerte porque el modelo capturó `breed='Sin Raza'` solo. Se ampliaron los fraseos, verificando que NO se coman razas reales (`mestizo`, `criollo`, `angora`, `boer`, `holstein` siguen guardándose como raza). (3) **R29 nueva en el prompt (con OK del usuario)**: al confirmar un dato normalizado el bot nombra el valor CANÓNICO, no la palabra del cliente. El usuario dijo "es una cabra" y el bot respondía "anoto Cabra como especie" aunque internamente guardaba `species='Caprino'` correctamente — el dato estaba bien pero no había forma de verificarlo en el momento. Verificado con MODELO REAL: ahora responde "Perfecto, anoto Caprino como especie y Hembra como sexo". Nuevo flujo E2E QA7. Suite: 446 passed. Flujos de raza: 8/9 (el único rojo, QA1 con tres correcciones encadenadas, es la clase ya documentada en `docs/estado-agente-qa.md`).

**2026-07-21 (ERR-076 de raíz: la regla general, no el caso puntual)** — El usuario objetó que el primer arreglo era puntual ("la idea era una solución general aplicada a la lógica, no a la palabra puntual"). Tenía razón y se comprobó: el mismo bug existía en el camino de ÁREA. Medido: `"un análisis de orina, sodio y potasio"` → tras el pedido mixto `selected_tests=['1405','1404']`, tras elegir del menú `['1601']` — sodio y potasio borrados. Causa de fondo: `_capture_test_menu_selection` (agent.py:549) hacía SIEMPRE `fields["selected_tests"] = [t["code"] for t in selected]`, o sea reemplazo incondicional. **Regla general implementada:** elegir de un menú REEMPLAZA si el menú fue una elección desde cero, pero AGREGA si el menú se abrió como residuo de un pedido mixto. La señal es DE DÓNDE VINO el menú (`_mixed_request_text`), no qué palabra se pidió — vale para áreas, categorías de perfiles y cualquier menú futuro, sin nada codificado sobre "prequirúrgico" ni "orina". Verificado en ambas direcciones: mixto `['1405','1404'] → ['1405','1404','1601']` (agrega); desde cero `['9999'] → ['1601']` (reemplaza). También se cazó un bug del propio fix (riesgo R3 del plan): al reaplicar el pedido original tras elegir el perfil se RE-ENCOLABA el término ya resuelto y el guard de cierre trababa la orden pidiendo algo ya elegido. **Nuevo flujo QA9** que mide SOLO el pedido mixto: QA8 arranca con una frase real enredada ("es una cabra que se llama a Luisa") que el modelo a veces no descompone, y cuando falla el flujo ni llega al turno de análisis — medía dos cosas a la vez y oscilaba. QA9: 3/3 corridas OK. Suite: 458 passed.

---

## 2026-08-24 — Checkpoint modelo real del refactor (harness reparado)

**Diagnóstico del 9/35:** la corrida del checkpoint (Etapas 0-3) salió 9/35 pero NO por el
refactor: `validate_flows.py` quedó pre-pedidos (decisión 011). `create_request` mockeado
sin `pedido_id` → TypeError en el cierre de casi todos los guiones; las funciones de
pedidos no mockeadas golpeaban Supabase real (uuid inválido — verificado: no escribió nada,
tabla `pedidos` limpia). Las transcripciones muestran el flujo conversacional impecable.

- [x] `create_request` acepta `pedido_id` y guarda **deepcopy** (la referencia viva se
      vaciaba con `_reset_order_fields` tras el cierre → falso negativo en QA8/QA9)
- [x] Pedidos in-memory en `_PATCHES`: create/get_open/get/close/mark_invoiced/
      profiles/requests/stale (estado en `_state["pedidos"]`)
- [x] Smoke QA9: 1/1 OK — commit `1349225`
- [x] Corrida completa 35 guiones: **22/35 OK**
- [x] Contraste de los 13 fallidos sobre el tag `punto-guardado-agente-2026-08-21`
      (worktree + harness reparado): el BASE da 3/13 OK con **10 fallos idénticos**
      (A, B, F, G, M, M2, T-bucle, U, QA1 → preexistentes, no regresión)
- [x] **Única regresión real: guion X** — la señal `correction` sin red secuestraba
      "quiero agregarle un analisis de orina al perfil" en el handler 2a, borraba
      exam_type y se comía turnos (0 órdenes). Fix commit `ddb4cb2` (+ test); re-validado
      con modelo real: el flujo endereza (menú de área, agregado 1601, resumen con
      Agregados) y los issues restantes son los MISMOS del BASE (deuda ERR-050 parcial)
- [x] V, QA2, QA4: repros mecánicos idénticos en ambos árboles → flakiness del modelo
      sobre debilidades compartidas, no regresión
- Anotados (compartidos con el BASE, no tocar sin OK): (1) "sí, confirmo" ambiguo tras
  la oferta del pedido cae al vacío (QA2/QA4); (2) la frontera multiorden dispara con
  "necesito un perfil renal para un paciente" sin orden previa (G); (3) el handoff
  anti-bucle en preventa crea una solicitud (T); (4) los checks del guion A siguen
  desfasados del contrato de pedidos (el cierre ya ocurre en el turno del pago)

**Veredicto del checkpoint:** el refactor de comprensión (Etapas 0-3) NO empeoró el
agente — mismos fallos que el BASE + 1 regresión cazada y corregida. Suite: 875 passed.


---

## 2026-08-24 — Etapa 4a del refactor de comprensión (catálogo y laterales)

- [x] Carriles 14 (info pre-identificación), 15 (precio), 16 (lateral operativa),
      17 (muestrario), 21 (recomendación) y 22 (etiqueta diagnóstica) movidos JUNTOS
      (ERR-072) a un handler post-modelo ANTES de la frontera de orden — misma
      precedencia que pre-LLM; gates con entry_intent. Commit `16463bd`.
- [x] `PRE_LLM_RETURNS_BASELINE` 24 → **13** — meta del plan (≤14) CUMPLIDA.
      `known_dead` ya estaba vacío desde la Etapa 3. Suite: **879 passed**.
- [x] 4 tests de mecánica nuevos (`test_etapa4_laterales_catalogo.py`); harness con
      `client_id` parametrizable.
- **Decisión 4b (registrada):** los carriles restantes (nº de orden, cliente final,
  opciones 2/4/reconsiderar del menú de bienvenida, "dije/dicho" con lista en
  pantalla) deciden por ESTADO + dato exacto — el criterio del propio plan los deja
  pre-LLM, como los menús 18/19. Argumentado en la nota del baseline.
- [ ] **Checkpoint con modelo real al cierre de Etapa 4** (validate_flows 35 guiones,
      ~$0.4-1.4) — SOLO con OK explícito del usuario (regla de tokens).
- [ ] Prueba en vivo del usuario por Telegram (reiniciar Flask antes: el proceso de
      fondo corre código pre-refactor).


---

## 2026-08-24 — Tanda pre-lanzamiento: cerrar los fallos restantes del checkpoint (OK del usuario)

Pedido: ajustar todos los errores que quedaron para lanzar al público; check final con
modelo real al terminar (autorizado).

- [x] 1. "sí, confirmo" ambiguo tras la oferta del pedido cae al vacío (QA2/QA4/A/F/U):
      con `_pedido_offer_pending` + afirmación pelada → re-pregunta determinística
      (¿otra orden o cerramos? forma de pago)
- [x] 2. M/M2: corrección post-cierre ("corrige el paciente: ahora se llama Rocky")
      responde "¿Qué análisis o perfil desean?" y la corrección se pierde
- [x] 3. G: la frontera multiorden dispara "¡Con gusto cargamos otra!" con "necesito un
      perfil renal para un paciente" SIN orden previa cargada
- [x] 4. T: el handoff anti-bucle en preventa crea una solicitud sin cliente identificado
- [x] 5. B: tras derivar cliente nuevo, respuestas duplicadas y silencio sin `_blocked`
- [x] 6. U: perfil elegido del menú por categoría queda sin código/precio real
- [x] 7. QA1: bucle de correcciones encadenadas de raza (residual documentado)
- [x] 8. F: revisar check "pago en línea no derivó a contabilidad"
- [x] 9. Checks del guion A al contrato de pedidos (harness, no producto)
- [x] **Check final: 35/35 flujos OK con modelo real** (corrida completa 33/35 +
      O y X en verde tras los últimos fixes; récord — el baseline histórico era
      18-20/24). Rondas en commits `38d7ef1`, `2391b8f`, `f952a66` y el fix de O.
      Ronda 2: escalera del re-ask (2ª afirmación → pago), silencio de cliente
      nuevo blindado ('sí' pelado no reabre), categoría por mención de perfil (W),
      corrección post-cierre robusta contra re-emisiones del historial (M2),
      re-preguntas de dirección (V), identificación (T) y comprensión (O) que
      alternan fraseo — nunca la misma plantilla dos veces seguidas.
- Resueltos en commits `38d7ef1` (1-2) y `2391b8f` (3-9). Suite 891 passed.
  Detalle: ítem 1 = _pedido_offer_pending sobrevive al reset B12 + re-pregunta
  determinística (3a y enforcer); ítem 2 = update_request_order_fields (UPDATE columnas
  + evento 'corrected') con flujo corregir→confirmar→aplicar; ítem 5 = era el CHECK
  (el silencio reversible ERR-088 funciona — repro mecánico con silencio en 3/3);
  ítems 8-9 y parte del 5 eran checks pre-pedidos, actualizados al contrato vigente.


---

## 2026-08-24 — Repro del test en vivo contra el código nuevo (pedido del usuario)

- [x] Conversación real del 21/08 recuperada de la BD y reproducida (5 pasadas)
- [x] Los 4 fallos del test original: RESUELTOS en la repro (bucle de la oferta,
      952+1903 juntos, heredado no secuestra, 1903 existe con precio)
- [x] 3 bugs de dinero nuevos cazados y corregidos (ERR-146)
- [x] Resultado final: 3/3 órdenes registradas (Joy con 952 + 1903, $90.000 íntegros
      + agregado), pedido listo para el pago
- [ ] Prueba en vivo del usuario por Telegram (reiniciar Flask antes)

---

## 2026-08-25 — Integración Anarvet Fase 1: espejo de solo lectura (decisión 013)

Credenciales entregadas por Anarvet (PostgreSQL, usuario restringido a
fn_reporte_examenes). Alcance aprobado: conexión + espejo en Supabase + sync manual
+ mapeo de clientes. El flujo conversacional del chat NO se tocó.

- [x] Config `ANARVET_*` con flag (default off) + `.env.example` + psycopg 3.2.9
- [x] `app/services/anarvet.py` — conexión read-only con timeouts (patrón alegra.py)
- [x] `tools/scripts/anarvet_smoke.py` — corrido contra el servidor real: tipos
      confirmados (todas las fechas `date`), ~3.900 analitos/día, SIN TLS
- [x] Migración 023 aplicada: `anarvet_results` + `anarvet_client_map` (RLS on)
- [x] `app/anarvet_sync.py` — sync con dedupe sha1 + lotes de 500; verificado con
      datos reales: 7.694 filas de 2 días, re-sync idempotente (0 duplicados)
- [x] Endpoints dashboard: sync / listar mapeo / asignar a mano + botón en Resultados
- [x] Matching por nombre (`anarvet_map_clients.py`): 84/103 auto (82%), 15 ambiguos
      y 4 sin match quedaron pending para asignación manual
- [x] Health check `anarvet` no crítico (ping real 1.3s; disabled con flag off)
- [x] Tests: `tests/test_anarvet_sync.py` (14) — suite completa 911 passed
- [x] Docs: decisión 013, deploy skill/runbook, CLAUDE.md/AGENTS.md
- [ ] Deploy a Render con flag OFF → encender y probar sync desde Render (riesgo IP)
- [ ] Revisar 2 mapeos auto sospechosos: cod 828 ('...San Francisco' → 'Centro
      Medico Veterinario') y cod 882 ('Danimal Planet Sede Roma' → 'Danimal Planet')
- [ ] Pedir TLS a Anarvet (hoy el tráfico va en claro)

Resultado: espejo operativo end-to-end en local. Fase 2 (consulta de resultados por
chat + PDF propio) queda para su propio plan con OK explícito.


---

## 2026-08-25 — Catálogo completo: cobertura y resolución por nombre (pedido del usuario)

Pedido tras la llamada 9: ordenar bien el catálogo, que no falte ningún producto y que
todo se detecte tanto por código como por nombre.

- [x] Tabla canónica del PDF "A3 - Catálogo 2025" (págs. 3-18) transcrita y versionada
      en `tools/scripts/audit_catalogo_pdf.py`
- [x] Cruce contra seeds: **316/316 códigos, precios idénticos** — sin faltantes
- [x] Cruce contra Supabase vivo (solo lectura): 183 tests + 133 perfiles, todo OK
- [x] Resolubilidad fila por fila (código + nombre + fraseo con muletillas): 4 huecos
      encontrados y corregidos (romanos XI/XII; muletillas 'me haces') — ERR-147
- [x] Verificado el caso de la llamada 9: 'citología' ofrece el 1903 del convenio
- [x] Invariante permanente: `test_cobertura_catalogo_seed.py` (317 casos, sin red)
- [x] Suite **1238 passed**
- [ ] **Mascolab** (págs. 19-27, 60 ítems): bloqueado por A3 — doble precio Punto Final /
      Tiempo Real, más 2 erratas de código (2407, 2061). Ver `docs/catalogo-mascolab-pendiente.md`
- [ ] **Anotado, requiere OK:** con `exam_type` fijado y sin oferta activa el modelo no
      recibe el catálogo (`agent.py:3371-3410`). Tocarlo roza la regla "perfil cerrado →
      avanzar a paciente" del flujo aprobado
- [x] **Segunda vuelta — cómo pide el veterinario** (ERR-147b): siglas del propio nombre
      (BUN, LDH, PIF, TVT, 4DX), jerga del gremio (hemograma, parvo, toxo, ionograma),
      'materia fecal' ya no agrega Tripsina, y el convenio no gana callado sobre la
      prueba propia de A3. Suite 1245 passed
- [ ] **Migración 025 pendiente de OK**: restaura "o Moquillo Canino" en los nombres del
      2004 y 2017 (el PDF lo trae, el seed lo recortó). Solo texto; sin precios ni códigos


---

## 2026-08-25 — Pendientes de la llamada 9 (OK del usuario)

- [x] **Fecha de toma de muestra en el chat** (ERR-148): posición 9, entre propietario y
      análisis; no bloquea; PDF corregido; contrato B4 re-aprobado. Suite 1255
- [x] **Repositorio publicado**: 117 commits a origin/fix/agente-robustez-multiorden
      (el remoto estaba en el 8 de junio). Nota: el repo se movió a Zidong-LLC — la URL
      del remote sigue apuntando a Zidong-IA y GitHub redirige
- [x] **Sección "Nueva orden" en el dashboard** (ERR-149): /solicitudes/nueva con menú
      y botón propios; resolve_catalog_selection movida a app/orders.py (una sola regla de
      dinero para portal y dashboard); verificada contra la base real sin escribir. Suite 1261
- [x] **Migración 026 APLICADA** (2026-08-25, status 201): la vista `service_orders` expone
      `sample_taken_date`. Las órdenes viejas devuelven NULL — nunca se preguntó
- [x] **Migración 025 APLICADA** (2026-08-25, status 201): el 2004 y el 2017 recuperaron el
      "o Moquillo Canino" del PDF. Verificado en vivo: 'moquillo' ya ofrece el de A3
      ($45.000) junto al del convenio ($124.000) en vez de cobrar el caro en silencio
- [x] **Remoto corregido** a https://github.com/Zidong-LLC/A3-V2.git


---

## 2026-08-25 — Anarvet Fase 2 (en curso)

Conexión revisada antes de empezar: ping 1.31s, 11.546 analitos en 3 días, credenciales OK.

- [x] **1/4 · Informe propio descargable** (ERR-150): plantilla A4 con identidad A3, nombres
      de examen legibles, observaciones fuera de la tabla, edad calculada y firma del
      validador real. Botón en el detalle y en el listado. Suite 1270
- [x] **2/4 · Publicar el resultado al portal** (ERR-155): PDF en el servidor con
      Playwright, reusando el publicar+notificar existente. Verificado end-to-end con un
      informe real de 93 analitos
- [x] **3/4 · Pantalla de mapeo de clientes** (ERR-151): 80 emparejados solos, informes
      con dueño de 58% a 87%. Quedan 20 para decisión humana, 8 de ellos por clientes
      DUPLICADOS en la base de A3
- [x] **4/4 · Sync incremental + endpoint para cron** (ERR-154): arranca donde quedó el
      espejo, no en 7 días ciegos. Verificado real: 11.665 analitos sin errores
- [ ] **A pedirle a Anarvet**: unidades y valores de referencia por analito, y el nombre
      largo del examen — sin eso el informe no es clínicamente completo. Además: función de
      ESTADO (hoy solo devuelve analitos ya validados), TLS y whitelist de IPs de Render


---

## 2026-08-25 — Anarvet Fase 2 COMPLETA

Los cuatro frentes cerrados (ERR-150 a ERR-155). Suite **1317 passed**.

- [ ] **Encender en producción**: cambiar el runtime de Render a Docker, desplegar con
      `PDF_ENABLED=false`, verificar `/health` y recién ahí encenderlo
- [ ] **Programar el cron** que llame a `POST /api/platform/anarvet/sync`
- [ ] **Resolver los 20 mapeos** que quedan en la pantalla nueva (8 son duplicados que A3
      debería unificar en su base)
- [ ] **A pedirle a Anarvet**: unidades y valores de referencia por analito (sin eso el
      informe no es clínicamente completo), por qué Albúmina y Proteínas nunca llevan
      validación, TLS y whitelist de IPs de Render
- [ ] **A decidir con A3**: desde qué fecha quieren ver resultados en el portal — el espejo
      hoy cubre una semana y traer el historial es repetir el sync por tramos

---

## Retema a la identidad A3 — plataforma y portal (2026-08-27) — EN CURSO

Plan aprobado: `~/.claude/plans/okey-mira-podriamos-adaptar-linear-tulip.md`. Pedido del
usuario: que la interfaz deje el oscuro monocromo y adopte la estética de las plantillas de
Nuxt con los colores de `https://a3laboratorio.co/`. Solo capa de presentación: ni lógica
Python, ni rutas, ni el flujo conversacional.

Identidad verificada en el sitio del cliente: marca `#7a0d20` (vinotinto del logo, y color
primario de su tema Divi), tipografías Nunito Sans / Open Sans, logo `A3` blanco sobre
círculo vinotinto. Decisiones del usuario: vinotinto de acento sobre neutros (no barra
lateral vinotinta), tema claro único, Nunito Sans, y maqueta aprobada antes de tocar código.

- [x] **Fase 1 — Maqueta de referencia**: `mockups/v1-nuxt.html` retemado a la identidad A3
      (portal de clientes) y `mockups/v4-dashboard-a3.html` nuevo (dashboard interno con
      kpi-card, filter-bar, cols-btn, approval-notice, service-order-sheet). Ambas usan los
      nombres de clase REALES del proyecto, así sirven de referencia 1:1 al retemar app.css.
      Publicadas como Artifacts. **Pendiente: visto bueno del usuario.**
- [x] **Fase 2 — Tokens**: `:root` de os-kit.css a paleta clara con los nombres `--os-space-*`
      intactos; acento `#7a0d20`; tokens nuevos `--os-space-hover/field/inset/tint/on-accent`
- [x] **Fase 3 — Barrido de hardcodes**: los 36 `rgba(255,255,255,…)` de app.css clasificados
      por rol (campo / hover / superficie tonal / marca) + 4 de dashboard.css + 3 de
      portal.css; sombras negras aligeradas; halo del spotlight a vinotinto; orbes apagados
      (`.os-shell-ambient{display:none}`), el markup queda intacto
- [x] **Fase 4 — Forma**: radios 14→10 / 10→6, `.card-head` y `.filter-bar` con tono propio,
      `.crm-main` al gris del lienzo, sidebar blanca, `th` con fondo y corte, `.menu-link.active`
      en tinte + texto vinotinto. **Estados corregidos**: había inventado nombres
      (`status-programada`…); los reales de `REQUEST_STATUS_LABELS` son received/assigned/
      on_route/picked_up/in_lab/processed/sent/cancelled/error_pending_assignment — los 9
      cubiertos y los 4 que tenían texto claro sobre tinte oscuro, corregidos
- [ ] **Fase 5 — Tipografía**: se mantiene Public Sans (decisión del usuario 2026-08-27: la
      estética de Nuxt queda intacta, solo cambia la paleta). Nada que tocar.
- [x] **Verificación**: 16 pantallas recorridas con Playwright sobre Flask local (11 del CRM
      + 5 del portal), todas responden; contraste medido con getComputedStyle: todos los
      textos ≥4.5:1 (el más bajo, `.hello-label`, 4.79:1); `rgba(255,255,255` en cero en los
      4 CSS; suite **1327 passed, 4 skipped, 1 xfailed**; las vistas de impresión llevan
      `<style>` propio y no dependen del tema
- [ ] **Pendiente ajeno al retema**: `/solicitudes/nueva` paso 3 tiene los rótulos «Análisis
      sueltos» y «Observaciones» encimados y el `select multiple` desbordado. **Verificado que
      ya ocurría con el tema oscuro** (captura comparativa), no es regresión. Requiere OK del
      usuario por tocar una plantilla del flujo de carga manual

---

## Paso a datos reales: Alegra del cliente, cartera, FE y Mascolab (2026-08-27) — EN CURSO

Plan aprobado: `~/.claude/plans/okey-mira-podriamos-adaptar-linear-tulip.md`. Cierre de la
etapa de pruebas: credenciales reales de Alegra, limpieza de lo transaccional, cartera en
portal y admin, factura electrónica vs Consumidor Final, PDF desde la ficha del cliente y
convenio Mascolab.

- [x] **Fase 0 — Respaldo y limpieza**: `tools/scripts/backup_transaccional.py` (81 filas a
      `data/backups/transaccional-20260827-103300/`) y `limpiar_transaccional.py --confirmar`.
      Borradas 8 tablas transaccionales + numeración reiniciada. **Intactos**: 992 clientes,
      183+133 catálogo, 332 razas, 8 motorizados, 320 asignaciones, 44 perfiles, 27.102
      Anarvet. Hallazgo: `requests.pedido_id` → `pedidos` obliga a borrar requests ANTES que
      pedidos (el orden inicial fallaba por FK)
- [x] **Fase 1 — Alegra real (solo borradores)**: `.env` → cuenta del cliente,
      `ALEGRA_COUNTRY=colombia`, `ALEGRA_PRODUCTION=false`. Verificado en solo lectura:
      empresa «A3 LABORATORIO CLINICO VETERINARIO SAS», NIT 900296338, Colombia, Responsable
      de IVA; el catálogo y los contactos YA estaban cargados en su cuenta; 660 facturas
      (126 open / 534 closed). Guardrail y CLAUDE.md reescritos: cuenta real, jamás DIAN
- [x] **Fase 2 — Factura electrónica vs Consumidor Final**: migración 028
      (`clients.electronic_invoice` + `invoice_note`); `import_factura_electronica.py` marcó
      **39 clientes** desde el Excel (los 29 «NO» del Excel, varios con sedes que comparten
      NIT). `billing.invoice_target` decide destino y nota; `alegra.create_invoice` acepta
      `anotation`. **Hallazgo**: ya existía `clients_a3_knowledge.electronic_invoicing` con
      UI y filtro pero **vacía en las 1427 fichas** — se reusó esa UI apuntándola a la
      columna real de `clients` en vez de crear un campo duplicado. 5 tests nuevos
- [x] **Fase 3 — Cartera**: migración 029 (`balance`, `total_paid` en `invoices_cache`);
      `db.list_cartera/cartera_totales/cartera_por_cliente`; vista en Facturación (KPIs +
      cartera por cliente con mora) y **nueva página del portal** `/portal/mis/cuenta`
      (`app/portal/client_cartera.py`). Datos reales: **$103.9M facturado, $80.2M cobrado,
      $20.9M por cobrar, 49 clientes con saldo**. Filtro `money` registrado en Jinja
- [x] **Fase 4 — PDF desde la ficha del cliente**: `_resolve_client` acepta `client_id`
      explícito (el NIT no sirve: hay sedes que lo comparten, ERR-157); enlace «Subir PDF»
      en cada fila de Clientes y precarga del destino. Probado de punta a punta: se subió,
      publicó, notificó y se limpió el rastro (incluido el bucket)
- [x] **Fase 5 — Mascolab**: `build_mascolab_migration.py` cruza el Excel con los precios de
      `docs/catalogo-mascolab-pendiente.md` → migración 030 con **122 entradas** (30 perfiles
      + 92 análisis): código base = Punto Final, `-1` = Tiempo Real, con la técnica en el
      nombre para poder cotizarlas por separado. El 2461 entró con la tarifa general
      ($157.000/$224.000) por decisión del usuario. Catálogo: 275 análisis + 163 perfiles
- [ ] **Pendiente de OK del usuario**: probar el camino de ESCRITURA en Alegra (crear un
      borrador real de punta a punta). La regla dura exige avisar antes: cada borrador queda
      en la cuenta del contador de A3
- [x] **Auditoría del catálogo nuevo** (`A3 - Catalogo 2025 (3) (4).pdf`): script nuevo
      `tools/scripts/audit_catalogo_pdf_vs_base.py` (lee el PDF y compara contra la BASE
      viva, no contra los seeds como el `audit_catalogo_pdf.py` existente).
      **Resultado: 311 códigos leídos, CERO precios distintos y CERO códigos del PDF que
      falten en la base.** Los 5 que el parser no pudo leer (1601, 1606, 2063, 2216, 2217)
      se verificaron a mano contra el PDF: también coinciden. **El catálogo nuevo no cambia
      ningún precio.**
      Aprendizajes del parseo, que costaron dos versiones del script: el PDF mezcla dos
      formatos de precio (`85.000$` y `$ 85.000`); las tablas de análisis solo se leen bien
      con `extraction_mode="layout"` y las de perfiles solo con la extracción normal (en
      layout salen desarmadas); y emparejar código→precio «por cercanía» produce disparates
      —la primera versión leyó el código 2301 como un precio de $2.301—, así que se lee
      estrictamente por línea y lo que no se puede leer se reporta en vez de adivinarse

---

## Portal del cliente fuera del modo demostración (2026-08-27) — COMPLETADO

Pedido: que el portal deje de ser demo y cada veterinaria entre con **nombre de la clínica +
NIT** y vea solo lo suyo. **Hallazgo: ya estaba construido y probado** (login real en
`app/portal/auth.py` desde el 2026-08-18, con 10 tests). El modo demo lo tapaba con un `if`.

- [x] `PORTAL_DEMO_MODE=false`. El código de demo queda, apagado (decisión del usuario)
- [x] Hueco que dejaba la demo: `session.portal_email` («demo@a3test.com») se borra en el
      login real, así que el menú lateral y «Correo de acceso» del perfil quedaban **vacíos**.
      Ahora la sesión guarda `portal_clinic_name`; el menú muestra la sede y el perfil, el
      correo real de `clients` + cómo se accede
- [x] `tools/scripts/export_clientes_sin_nit.py` → `data/clientes-sin-nit-20260827.csv` con
      los **161 activos sin NIT** (19% de 842) que no pueden entrar. Es el mismo dato que
      falta para facturarles
- [x] Verificación e2e contra clientes reales: sin sesión redirige al login; login correcto;
      nombre ajeno al NIT rechazado; NIT inexistente con el mismo mensaje; **NIT con dos sedes
      ofrece elegir y re-valida**; logout corta el acceso. **Aislamiento comprobado contra la
      base**: «Ama Tu Mascota» ve 6 facturas y 4 pendientes, «Zoomascotas Veraguas» 19 y 8
- [x] Suite **1332 passed**; decisión 010 actualizada
- Nota: durante las pruebas el **rate limit se disparó solo** (10 intentos/5 min por IP) y
      bloqueó mi propia batería. Funcionó como debía; se reinició Flask para limpiarlo
- [x] **PDF para A3** con las 161 (`tools/scripts/pdf_clientes_sin_nit.py` →
      `data/veterinarias-sin-nit.pdf`, 6 páginas). Al armarlo apareció el porqué: **154 de las
      161 entraron el 22/07 desde «Clientes y Doctores A3.xlsx»**, que solo traía nombre y
      médico — de ahí que no tengan NIT, ni teléfono real (son de relleno, 5700000xxxxx) ni
      dirección. El PDF cruza ese Excel para devolver el médico de cada una (157 de 161) y
      ordena por prioridad: primero las 8 con actividad real (informes en Anarvet, motorizado
      o dirección), que son las que hoy operan sin poder entrar al portal
- [x] **Herramienta para futuras listas de A3** (pedido del usuario, 27/08):
      `snapshot_clientes.py` (foto del padrón) + `conciliar_clientes.py` (compara una lista
      nueva contra la base: nuevos / datos que completa / ausentes) +
      `docs/runbooks/actualizar-padron-clientes.md`. Lee .xlsx y .csv y reconoce las columnas
      por alias; cruza por NIT y, si no hay, por nombre con `client_name_matches` — el mismo
      criterio del agente y del portal. **No escribe en la base**: deja 3 CSV para decidir.
      Probada con dos listas reales: la de Alegra (cubre 32%) y la de Clientes y Doctores
      (74%). Aviso incorporado: **si la lista cubre <60% del padrón, los «ausentes» NO son
      bajas** — sin eso, la de Alegra sugería dar de baja a 570 clientes activos.
      Hallazgo útil: la lista de Alegra aporta el NIT de «Club Animals» Marruecos y Venecia,
      dos de los 161 que hoy no pueden entrar al portal

---

## Ficha de la veterinaria en la plataforma (2026-08-27) — COMPLETADO

Pedido del usuario: poder **buscar y seleccionar la veterinaria** y ver su resumen —informes
subidos, solicitudes y qué falta cobrar— en un solo lugar. Nace de los 5 problemas detectados
en la pantalla de Resultados.

- [x] **Buscador de veterinaria** en Resultados: escribe nombre o NIT y abre la ficha.
      `db.search_clients_for_dashboard` (una consulta con `or_`, activos primero) +
      `GET /clientes/buscar` (JSON) + autocompletar sin dependencias
- [x] **Ficha del cliente** `GET /clientes/<id>` en **blueprint nuevo**
      `app/dashboard_client.py` (patrón de dashboard_results/anarvet: no agranda dashboard.py).
      Muestra KPIs, datos, subida con el destino ya resuelto, informes, solicitudes y estado
      de cuenta. Reusa `portal_db.list_client_requests/list_lab_results` y el `db.list_cartera`
      de hoy
- [x] **Deshacer, que era el problema más caro**: `POST /resultados/<id>/dejar-de-compartir`
      y `POST /resultados/<id>/eliminar`. Antes no había marcha atrás para un informe
      compartido con la veterinaria equivocada
- [x] **Compartir viene marcado** en la ficha: el caso normal deja de requerir acordarse
- [x] Las acciones **vuelven a donde estaba el usuario** (helper `_volver`)
- [x] 8 tests nuevos. Suite **1340 passed**

**Dos bugs que aparecieron al verificar, no antes:**
1. Al **dejar de compartir**, el aviso le quedaba al cliente apuntando a un informe que ya no
   podía abrir. Ahora `unpublish_lab_result` borra también la notificación.
2. `storage.delete_result_pdf` **nunca se había creado**: el `try/except` de `delete_result`
   se tragaba el `AttributeError` y **el archivo quedaba huérfano en el bucket** mientras la
   fila sí se borraba. Lo destapó un test, no la prueba manual — que había dado «OK».
   Se limpiaron 3 archivos huérfanos.

Pendiente menor de los 5 originales: **la carga sigue siendo de a un archivo**.

---

## Decisiones de alcance del 2026-08-28 (llamada con el usuario)

Recorte y confirmación de alcance sobre el balance del 25/08. Detalle y motivo en
`Auditoria Alcance/13-decisiones-alcance-2026-08-28.md`.

- [x] **Mascolab (migración 030): ya está aplicada en Supabase** — verificado contra la base
      viva, no contra el archivo: 30 perfiles + 92 análisis con categoría `Mascolab - Punto
      Final` / `Mascolab - Tiempo Real`, los 122 códigos de la migración presentes, cero
      faltantes. Catálogo total: 163 perfiles + 275 análisis. **El frente de catálogo y
      precios queda cerrado.**
- [x] **FUERA DE ALCANCE (decisión del usuario)**: adjuntos y fotos en el chat (el agente es
      de texto y no se contrató otra cosa); inventario en Alegra (Alegra ya descuenta las
      unidades al facturar, no hay nada que construir); pasarela de pago (cancelada, el pago
      se deriva a una persona); unidades y valores de referencia por analito de Anarvet (el
      documento lo carga el cliente, nosotros mostramos la información como llega hoy);
      historial anterior a la conexión con Anarvet (el espejo arranca donde nos conectamos).
- [x] **Roles: solo dos** — personal interno de A3 (todos con el usuario administrador) y
      cliente final en el portal. **El motorizado no se loguea a nada.** Elimina la tabla de
      usuarios y el rol de mensajero del pendiente.
- [x] **Consulta de resultados por chat — HECHA** (ERR-159, OK del usuario 28/08). El agente
      busca los resultados publicados del cliente por paciente o número de orden y manda el
      PDF por Telegram o Chatwoot. Piezas nuevas: `multipart.py`, `send_document` en los dos
      canales, `results_lookup.py`, `results_delivery.py`. Bloque B15 del contrato reescrito.
      16 tests nuevos, suite 1356. **Falta probarlo con un chat real de Telegram**
- [x] **Validación del médico veterinario: FUERA DE ALCANCE** (decisión del usuario 28/08).
      El agente sigue anotando el nombre que le den sin comprobar que esté registrado
- [x] **Los 17 mapeos de Anarvet: en manos de A3** (decisión del usuario 28/08). No se escribe
      nada en la base hasta que A3 conteste `docs/anarvet-consulta-clientes.html`. 88 informes
      quedan sin mostrarse mientras tanto
- [x] **Calendario de mensajeros: ENTRA COMPLETO** (decisión del usuario 28/08), con
      reasignación y reprogramación de recogidas desde la plataforma
- [x] **Resultados por chat: el agente manda el PDF por el chat** (decisión del usuario 28/08),
      no un enlace al portal. Obliga a agregar envío de documentos en Telegram y Chatwoot
- [ ] **Bloquear el cambio de cliente maestro**: se prueba antes de decidir, no se cierra hoy

---

## Tres pendientes de plataforma (2026-08-28) — COMPLETADOS

Detalle en `tasks/errores-soluciones.md` (ERR-160). Decisiones del usuario tomadas antes de
escribir: una fila por archivo, agenda semana por mensajero, y las tres cargas por CSV.

- [x] **Varios PDF de una vez** en la ficha del cliente y en Resultados: una fila por archivo
      con paciente, orden y análisis, precargados desde el nombre del archivo. Que uno falle
      no cancela los demás. 3 tests
- [x] **Agenda de recogidas** `/agenda`: fila por motorizado, columna por día, reasignar y
      reprogramar desde cada tarjeta. Reusa `/api/dashboard/request-operation` (validación y
      auditoría ya existentes). 10 tests
- [x] **Cargas por CSV** `/cargas`: precios, clientes y portafolio, siempre con vista previa
      antes de escribir y revalidación contra la base al confirmar. 18 tests
- [x] Suite **1387 passed**. Verificado en el navegador contra datos reales, con el rastro
      borrado en cada prueba

---

## Publicación del código y migraciones (2026-08-28) — COMPLETADO

- [x] **Migraciones 023 a 030: ya estaban aplicadas** en la base real. Verificado en solo
      lectura, una por una: tablas del espejo de Anarvet, vistas `anarvet_informes` y
      `service_orders` con fecha de toma, `clients.electronic_invoice`, `invoices_cache.balance`,
      los nombres del PDF y los 92 análisis de Mascolab. **Hay un solo proyecto de Supabase**
      (confirmado por el usuario): el de local es el mismo que usará Render
- [x] **Código publicado** (OK explícito del usuario). La rama de trabajo ya se venía
      publicando y solo le faltaban 3 commits; lo que estaba parado en el 8 de junio era
      `master`, que avanzó sin conflictos hasta el trabajo de hoy. `origin/master` quedó en
      `944e53f`, a cero de diferencia con local
- [ ] **Falta el despliegue**: Render todavía no corre este código. Runbook en
      `docs/runbooks/deploy.md` (runtime Docker, variables, primer arranque con el PDF apagado)

---

## Búsqueda de clientes arreglada (2026-08-28) — COMPLETADO

Reporte del usuario: buscar «animal pet» no encontraba al cliente entre los 992. Detalle y
causa raíz en `tasks/errores-soluciones.md` (ERR-161).

- [x] `app/client_filters.py`: búsqueda por todas las palabras en cualquier orden, sin tildes,
      sobre los mismos campos que muestra la fila; más los cuatro filtros
- [x] Se filtra ANTES de paginar (`_render_dashboard`), no en el navegador sobre 15 filas
- [x] La barra pasó a formulario GET; la paginación conserva búsqueda y filtros; el contador
      informa el total encontrado
- [x] Sugerencias mientras se escribe, reusando `GET /clientes/buscar`; las inactivas van
      marcadas (decisión del usuario)
- [x] `db.search_clients_for_dashboard`: espacios repetidos y palabras en otro orden
- [x] 17 tests nuevos. Suite **1420 passed**. Verificado en el navegador contra los 992 reales
- [ ] **Pendiente aparte**: la pantalla de Clientes tarda ~7 s porque el contexto arma todo el
      dashboard en cada request. Es previo a este cambio

---

## Vista de ejemplo: se usó para revisar el diseño y se retiró (2026-08-28)

Pedido del usuario: ver cómo quedaban las pantallas con movimiento y, una vez revisadas,
**sacar todos los datos falsos de la plataforma**.

- [x] Se revisaron con datos de ejemplo: Solicitudes, Pedidos (con órdenes de varios perfiles y
      hasta siete análisis, el peor caso) y la Agenda de motorizados (14 recogidas repartidas
      entre los 8 motorizados reales, con dos sin asignar)
- [x] **Retirado todo**: `app/demo_data.py` y sus tests, el `?demo=1` de Solicitudes, Pedidos y
      Agenda, y también el **modo demo de Muestras que existía desde antes**
      (`_demo_sample_process_lanes`, la marca `is_demo` de las tarjetas y su aviso)
- [x] Verificado en el navegador: ninguna de las ocho rutas muestra datos inventados, ni
      siquiera agregando `?demo=1`, que ya no hace nada. Suite **1460 passed**
- **Queda a propósito**: `PORTAL_DEMO_MODE` en el portal del cliente, apagado desde el 27/08 por
  decisión del usuario («el código de demo queda, apagado»). No genera datos falsos: entra al
  portal con un cliente real sin pedir credenciales, y hoy está en `false`

---

## Decisiones del usuario (2026-08-31)

- [x] **Unidades y valores de referencia de Anarvet: DESCARTADO para siempre.** Anarvet no va a
      compartir esa métrica. Por eso los informes NO se generan en nuestra plataforma: el equipo
      de A3 sube a mano el PDF que produce Anarvet (circuito de Resultados, ya funcionando).
      Se retira el pendiente «pedir unidades/valores de referencia a Anarvet».
- [x] **Mascolab doble precio: YA ESTABA RESUELTO** como el usuario lo pidió hoy (decisión
      original del 27/08, migración 030 aplicada): cada prueba PCR está DOS veces en el
      catálogo — «(Punto Final)» y «(Tiempo Real)» — cada una con su precio; el médico elige
      la técnica al pedir. 30 perfiles + 92 análisis verificados en la base.
- [x] **PDF de consulta para A3 generado**: `data/anarvet-consulta-20260831.pdf` — los 17
      códigos de Anarvet sin emparejar (3.658 informes esperando dueño), cada uno con sus
      candidatos para marcar con X. Antes se corrió el automatch: emparejó 22 solos.
- [x] Bajas por lista v3: si un cliente desaparece entre una entrega y la siguiente, es baja
      (criterio del usuario, aplicado a los 2 casos con cero movimiento verificado).

---

## Auditoría total pre-lanzamiento (2026-08-31) — plan aprobado

Cruce de 10 llamadas + 13 docs de alcance + bitácora contra el código real.
Plan completo en la conversación; secuencia acordada con A3 (llamada 9):
ajustes → Anarvet → WhatsApp → lanzamiento → semana de testeo.

- [ ] 1. Verificaciones dudosas: bug 1903 Citología, comando reset, PDF contraentrega, ERR-095
- [ ] 2. Los 3 tapones de WhatsApp (entry_channel, aviso de resultados, firma del webhook)
- [ ] 3. Seguridad: /setup-webhook, DASHBOARD_ADMIN_PASSWORD=admin123, PLATFORM_API_TOKEN
      en Render, rotar SERVICE_ROLE_KEY, revisar SUPABASE_ANON_KEY
- [ ] 4. ERR-099 (decisión del usuario) + estrés multi-orden ERR-117/118 + ERR-113
- [ ] 5. Decisiones con el usuario: aviso al motorizado, alertas por tiempo, descuentos del
      bot, números contabilidad/PQR, panel de cubos
- [ ] 6. Acta a A3 (prometida 2 veces) + 3 capturas a Adriana + enviar PDF de mapeos
- [ ] 7. Deploy Render + webhooks + cron + prueba Telegram real + semana de testeo
- [ ] 8. Documentación al día (CLAUDE.md, README, contrato, bitácora, ADRs)

- [x] **Estilo visual: CERRADO** (2026-08-31). Las capturas se le enviaron a Adriana y A3
      eligió el estilo actual de la plataforma: lo que está hoy ES la versión final visual.
      Se retira el pendiente de la llamada 9 y el «visto bueno de Fase 1» del retema.
