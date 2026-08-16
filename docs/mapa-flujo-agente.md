# Mapa vivo del agente conversacional

> Producto de la Fase 0 de la campaña de producción (2026-08-15). Refleja el código REAL de
> hoy — si tocás el pipeline, actualizá este mapa en el mismo commit. Complementa (no
> reemplaza) `docs/contrato-flujo-conversacional.md`, que registra qué pasos están aprobados.

## 1. Anatomía de un turno (`process_turn`, app/agent.py)

```
mensaje del cliente
  │
  ├─ ATAJOS PRE-LLM (44 returns — invariante congelado en test_pipeline_invariants)
  │    · bloqueos: _blocked, particular (silencio), escalado no-reabierto (ERR-088)
  │    · saludo inicial / despedida post-terminal / consulta de nº de orden
  │    · CIERRE DETERMINÍSTICO del pedido: abierto + orden registrada + pago en el texto
  │    · barrido oportunista de pedidos abandonados (1×/10min)
  │    · carril de la oferta de análisis (_offering_extra_analysis) → _handle_extra_analysis_answer
  │    · reofrecimiento de estables (_stable_confirm_pending): confirmación PELADA responde
  │      plantilla; cualquier cosa más CEDE al modelo (L65)
  │    · corrección en confirmación (campo detectado → repregunta; "no quiero los agregados")
  │    · "el de siempre" (snapshot/memoria) · recomendación de perfiles · etiqueta diagnóstica
  │
  ├─ MODELO (ai.generate_turn — DOS call sites: principal y camino de identificación)
  │
  ├─ POST-MODELO INMEDIATO
  │    · state.carry_over (flags _*)
  │    · CANDADO DE PROVENANCIA (_candado_provenancia_tests): selected_tests solo crece por
  │      lo que el mensaje trae/nombra/menú/"el de siempre" — en AMBOS call sites del modelo
  │    · FRONTERA DE ORDEN (_order_boundary_response): "otra orden" a mitad o paciente nuevo
  │      en bloque → cierra la actual (registra) + abre la siguiente con lo ya dicho.
  │      Se resuelve FUERA del pipeline (return temprano) para que nada se cruce.
  │
  ├─ ENFORCERS EN ORDEN (agent.py ~4183-4289)
  │    results → recommendation_help → exam_type_grounding → multiple_tests_capture →
  │    selected_tests_grounding (anclaje) → catalog_profile_code_selection (perfiles por
  │    código + captura determinística de códigos de análisis sueltos) → diagnostic_label →
  │    catalog_profile_help → generic_blood → test_category → analysis_help_fallback →
  │    profile_detail → custom_profile_close → extra_analysis_offer (oferta como paso propio)
  │    → open_pedido_close (cierre señal-primero) → payment_step (cede con PEDIDOS) →
  │    profile_customization → profile_exam_type_integrity → loose_exam_resolution →
  │    age_unit_grounding → handoff_guardrails → route_closure_summary →
  │    field_coherence → comprehension_recheck (PARTE 2: incoherencia/confidence → repregunta)
  │    → first_missing_after_progress (acuse + empuje del faltante) →
  │    confirmation_step (resumen editable + cierre determinístico del "sí") →
  │    selected_tests_are_catalog_codes
  │
  ├─ _finalize_request: si el turno cierra una orden nueva → create_request + evento con
  │    payload de dinero + nº de orden + motorizado + PEDIDO_CLOSING_PROMPT; acumula
  │    _pedido_ordenes/_pedido_profiles para la factura única
  │
  └─ _persist_turn: save_message ×2 + update_session (REEMPLAZO completo de captured_fields)
```

## 2. Ciclos de vida

**ORDEN**: captura de campos (orden fijo: dirección→médico→paciente→…→análisis→observación)
→ oferta "¿agregamos otro análisis?" (paso propio) → observación → RESUMEN editable
("cambiá un dato o agregá un análisis… ¿Confirmas?") → "sí" → registro (`requests` +
`request_events.profile` con los precios) → nº A3-XXXX + motorizado.

**PEDIDO** (decisión 011): se abre con la primera orden del chat → junta N órdenes → al
terminar ("eso es todo", CUALQUIER fraseo — señal farewell/negate/cancel) → observación del
pedido + forma de pago (UNA vez) → cierre: resumen de TODAS las órdenes + total → UNA factura
borrador en Alegra → estados `abierto→cerrado→facturado`. Red: barrido tras 1h de
inactividad (cierra SIN facturar y avisa a operaciones) + cierre manual en dashboard.

**FRONTERAS** (dónde muere el estado): `_ORDER_RESET_FIELDS` al abrir orden nueva (incluye
selected_tests, perfil, menús, carril mixto — ERR-114); `_clear_field_for_correction` en
cambio total de análisis; el cierre del pedido limpia `_pedido_*`.

## 3. Estado

- **Fases**: `fase_0_bienvenida` → … → `fase_6_cierre` / `fase_7_escalado` (state.Phase).
- **Flags `_*`**: 38 catalogadas en `app/state.py` (test obliga a catalogar cada una nueva).
  Claves de dinero: `_selected_profile_code/price`, `selected_tests`, `_extra_profiles`,
  `_pedido_id/_pedido_ordenes/_pedido_profiles`, `_order_registered`.
- **Claves efímeras de respuesta** (sin `_`, mueren en el turno): `skip_request_creation`,
  `boundary_next`.

## 4. Conexiones y escrituras

| Destino | Cuándo | Función |
|---|---|---|
| `telegram_sessions` | cada turno | `update_session` (reemplazo completo) |
| `conversation_messages` | cada turno ×2 | `save_message` |
| `requests` + `request_events` | orden confirmada | `create_request` (payload `profile` = la verdad del dinero) |
| `pedidos` | 1ª orden / cierre / factura | `create_pedido`, `close_pedido`, `mark_pedido_invoiced` |
| Alegra (borrador) | cierre del pedido | `_try_invoice_pedido` → `billing.invoice_order` (nunca por orden con pedido) |
| Chatwoot/Telegram | respuesta | vía `main.py` webhooks |

Lecturas: catálogo (159 tests + perfiles), clientes (~992), razas, motorizados, memoria.

## 5. Principios que gobiernan (las lecciones pagadas)

1. **Señal-primero** (`user_intent_signal` manda, tokens de red) — un atajo determinístico
   solo responde cuando el mensaje no dice NADA más (L65, `_is_bare_confirmation`).
2. **El catálogo decide, no los verbos** (ERR-111): lo que toca dinero se resuelve contra la
   base; `names_test` es la vara del anclaje.
3. **Verificar ESTADO, no texto** (L66): el bot no afirma lo que no quedó guardado; los tests
   miran campos, no frases.
4. **Provenancia**: ninguna marca con contenido de una orden cruza su frontera (L67);
   `confidence` y `provides_requested_data` se LEEN (Parte 2) — incoherencia → repregunta.
5. **Invariantes estructurales**: los 44 returns pre-LLM y las señales del enum están
   congelados en tests que exigen justificación escrita para moverse.
```
