"""
Regresión ERR-051 (QA adversarial contra BD real, 2026-07-05): seis hallazgos con una
causa común — el análisis capturado como texto libre nunca se resolvía contra el catálogo.

QA-1  'Coprológico $23k' registrado (precio real: $12.000) → precio inventado en la orden.
QA-2  'si, correcta' + datos en bloque + 'contraentrega' → re-preguntaba la dirección
      recién confirmada y pisaba todo lo capturado (atajo de pago fuera de turno).
QA-3  edad '2' sin unidad → el modelo registró '2 años' inventando la unidad.
QA-5  el modelo capturó 'Perfil Senior Canino V' ($130.000) que el cliente nunca nombró.
QA-5b 'el parcial de orina' cotizado como PTT + Cortisol (fuzzy multi-término en precios).
QA-6  'quiero cuadro hemático y creatinina, ¿cuánto sale?' → respondía el precio pero
      perdía la elección.
QA-7  payloads de órdenes con code null / price 0 (consecuencia de QA-1).
"""
from unittest.mock import patch

from app import agent

COPRO = {"code": "1701", "name": "Coprológico", "price": 12000, "category": "Parasitología"}
CUADRO = {"code": "1101", "name": "Cuadro Hemático Completo", "price": 14000, "category": "Hematología"}
URO_TESTS = [
    {"code": "1507", "name": "Cortisol en Orina", "price": 33000, "category": "Uroanálisis"},
    {"code": "1601", "name": "Parcial de Orina (14 parámetros)", "price": 16000, "category": "Uroanálisis"},
]


def _route_resp(fields):
    return agent._base_route_response("...", dict(fields))


def _lookup(items):
    out, seen = [], set()
    for item in items:
        key = agent._catalog_item_key(item)
        if not key:
            continue
        for row in [COPRO, CUADRO] + URO_TESTS:
            name_key = agent._catalog_item_key(row["name"])
            if (key == str(row["code"]) or key == name_key or key in name_key) \
                    and row["code"] not in seen:
                out.append(row)
                seen.add(row["code"])
                break
    return out


# ── QA-1 / QA-7: análisis suelto se estructura y el precio sale del catálogo ─────


def test_loose_exam_with_invented_price_resolves_to_catalog():
    ai = _route_resp({"exam_type": "Coprológico $23k"})
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_lookup):
        out = agent._enforce_loose_exam_catalog_resolution(ai, {})
    f = out["captured_fields"]
    assert f["selected_tests"] == ["1701"]
    assert f["exam_type"] == "1701 Coprológico"
    assert "$23" not in f["exam_type"]


def test_loose_exam_without_price_also_resolves():
    ai = _route_resp({"exam_type": "Cuadro Hemático"})
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_lookup):
        out = agent._enforce_loose_exam_catalog_resolution(ai, {})
    assert out["captured_fields"]["selected_tests"] == ["1101"]


def test_loose_exam_unresolved_keeps_text_without_price():
    """Sin match único: no inventa nada, pero el precio escrito se descarta."""
    ai = _route_resp({"exam_type": "Química sanguínea especial $99k"})
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]):
        out = agent._enforce_loose_exam_catalog_resolution(ai, {})
    f = out["captured_fields"]
    assert "$99" not in (f["exam_type"] or "")
    assert not f.get("selected_tests")


def test_loose_exam_untouched_when_profile_base_or_structure_exists():
    for extra in ({"_selected_profile_code": "152"}, {"selected_tests": ["1101"]},
                  {"_diagnostic_label": "RENAL"}):
        fields = {"exam_type": "Coprológico $23k", **extra}
        ai = _route_resp(fields)
        out = agent._enforce_loose_exam_catalog_resolution(ai, {})
        assert out["captured_fields"]["exam_type"] == "Coprológico $23k"


def test_loose_exam_with_two_tests_resolves_both():
    """QA run 3: 'Cuadro Hemático Completo , Creatinina' como texto dejaba el payload
    en $0; cada ítem resoluble 1:1 se estructura en selected_tests."""
    creat = {"code": "1309", "name": "Creatinina", "price": 12000, "category": "Química"}

    def lookup(items):
        out = []
        for item in items:
            key = agent._catalog_item_key(item)
            for row in (CUADRO, creat):
                if key and key in agent._catalog_item_key(row["name"]):
                    out.append(row)
                    break
        return out

    ai = _route_resp({"exam_type": "Cuadro Hemático Completo , Creatinina"})
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=lookup):
        out = agent._enforce_loose_exam_catalog_resolution(ai, {})
    f = out["captured_fields"]
    assert f["selected_tests"] == ["1101", "1309"]
    assert "personalizado" in f["exam_type"].lower()


def test_strip_price_preserves_names_with_numbers():
    assert agent._strip_price_text("Parcial de Orina (14 parámetros)") == \
        "Parcial de Orina (14 parámetros)"
    assert agent._strip_price_text("Coprológico $23k") == "Coprológico"
    assert agent._strip_price_text("Cuadro Hemático $14.000") == "Cuadro Hemático"


# ── Re-test: la descripción del perfil NO se duplica como agregados ──────────────


def test_profile_description_items_are_not_added_as_extras():
    """Re-test QA (A3-2026-116): el modelo re-escribió exam_type con la descripción
    ('Perfil Parasitológico II: Coprológico y Coproscópico') y el invariante sumaba
    esos análisis YA INCLUIDOS como agregados ($23.000 → $50.000 al cerrar)."""
    fields = {
        "exam_type": "Perfil Parasitológico II: Coprológico y Coproscópico $23k",
        "_selected_profile_code": "102",
        "_selected_profile_name": "Perfil Parasitológico II",
        "_selected_profile_price": 23000,
        "_selected_profile_description": "Coprológico y Coproscópico",
        "selected_tests": [],
    }
    ai = _route_resp(fields)
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_lookup):
        out = agent._enforce_profile_exam_type_integrity(ai)
    f = out["captured_fields"]
    assert f["exam_type"] == "Perfil Parasitológico II"
    assert agent._as_text_items(f.get("selected_tests")) == []   # nada duplicado


def test_true_addition_outside_description_still_lands():
    """El caso legítimo de ERR-050 sigue funcionando: un agregado que NO está en la
    descripción del perfil sí va a selected_tests."""
    fields = {
        "exam_type": "Perfil Prequirúrgico I + Parcial de Orina (14 parámetros)",
        "_selected_profile_code": "152",
        "_selected_profile_name": "Perfil Prequirúrgico I",
        "_selected_profile_price": 24000,
        "_selected_profile_description": "Cuadro Hemático, ALT, Creatinina",
        "selected_tests": [],
    }
    ai = _route_resp(fields)
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_lookup):
        out = agent._enforce_profile_exam_type_integrity(ai)
    f = out["captured_fields"]
    assert agent._as_text_items(f.get("selected_tests")) == ["1601"]


# ── QA-5: exam_type sin anclaje en lo que dijo el cliente se descarta ────────────


def test_hallucinated_profile_is_discarded_and_reasked():
    history = [
        {"role": "user", "content": "necesito un perfil prequirurgico para Rocco"},
        {"role": "bot", "content": "¿Quieres dejar alguna observación?"},
    ]
    ai = _route_resp({"exam_type": "Perfil Senior Canino V"})
    ai["reply"] = "Antes de cerrar, ¿cómo prefieres el pago?"
    out = agent._enforce_exam_type_grounding(ai, {}, "Sin observaciones.", history)
    f = out["captured_fields"]
    assert f["exam_type"] is None
    assert "análisis" in out["reply"].lower() or "perfil" in out["reply"].lower()


def test_grounded_exam_from_current_message_passes():
    ai = _route_resp({"exam_type": "Coprológico"})
    out = agent._enforce_exam_type_grounding(ai, {}, "necesito un coprologico por fa", [])
    assert out["captured_fields"]["exam_type"] == "Coprológico"


def test_grounded_exam_from_history_passes():
    history = [{"role": "user", "content": "quiero una glucosa para mi paciente"}]
    ai = _route_resp({"exam_type": "Glucosa"})
    out = agent._enforce_exam_type_grounding(ai, {}, "sin observaciones", history)
    assert out["captured_fields"]["exam_type"] == "Glucosa"


def test_grounding_skips_menu_selections_and_snapshots():
    # Selección desde menú mostrado: el exam no aparece textual en el mensaje y es válido.
    prev = {"_test_menu_options": [dict(CUADRO)]}
    ai = _route_resp({"exam_type": "Cuadro Hemático Completo"})
    out = agent._enforce_exam_type_grounding(ai, prev, "el 1", [])
    assert out["captured_fields"]["exam_type"] == "Cuadro Hemático Completo"
    # Reoferta de la orden anterior ("el mismo de la vez pasada").
    prev2 = {"_prev_order_snapshot": {"exam_type": "Cuadro Hemático Completo"}}
    ai2 = _route_resp({"exam_type": "Cuadro Hemático Completo"})
    out2 = agent._enforce_exam_type_grounding(ai2, prev2, "el mismo de siempre", [])
    assert out2["captured_fields"]["exam_type"] == "Cuadro Hemático Completo"


# ── QA-5b: precio por área, sin fuzzy multi-término ──────────────────────────────


def test_price_answer_area_mention_lists_area_options():
    fields = {"_selected_profile_code": "152", "_selected_profile_name": "Perfil Prequirúrgico I",
              "_selected_profile_price": 24000, "species": "Canino"}
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(agent.db, "find_tests_by_area", return_value=("Uroanálisis", URO_TESTS)):
        answer = agent._catalog_price_answer(fields, "¿cuánto queda el total con el parcial de orina incluido?")
    assert answer is not None
    assert "1601" in answer                      # lista el área real
    assert "PTT" not in answer                   # no inventa por fuzzy
    assert fields.get("_test_menu_adds_to_profile") is True  # la selección posterior SUMA


def test_price_answer_single_test_still_works():
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_lookup), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])):
        answer = agent._catalog_price_answer({}, "¿cuánto sale el coprológico?")
    assert answer is not None and "12,000" in answer


# ── QA-6: pedido + consulta de precio en el mismo mensaje ────────────────────────


def test_expresses_order_request_detection():
    assert agent._expresses_order_request("Quiero cuadro hemático y creatinina juntos. ¿Cuánto sale el total? Confirmo.")
    assert not agent._expresses_order_request("¿cuánto sale un cuadro hemático?")
    assert not agent._expresses_order_request("quiero saber cuánto sale la creatinina")


# ── QA-3: edad sin unidad no se asume ────────────────────────────────────────────


def test_age_unit_invented_by_model_is_stripped():
    ai = _route_resp({"patient_age": "2 años"})
    out = agent._enforce_age_unit_grounding(ai, {}, "luna, gata siames, hembra, 2, dra sofia")
    assert out["captured_fields"]["patient_age"] == "2"


def test_age_with_unit_from_client_is_kept():
    ai = _route_resp({"patient_age": "2 años"})
    out = agent._enforce_age_unit_grounding(ai, {}, "tiene 2 años")
    assert out["captured_fields"]["patient_age"] == "2 años"


def test_greeting_dia_does_not_count_as_age_unit():
    """'buen dia' en el saludo no cuenta como unidad de edad: 'hembra, 2' del historial
    con '2 años' del modelo se recorta igual (escape del run 3 de QA)."""
    history = [{"role": "user", "content": "hola, buen dia, como va todo? necesito un coprologico para luna, gata siames, hembra, 2"}]
    ai = _route_resp({"patient_age": "2 años"})
    out = agent._enforce_age_unit_grounding(ai, {}, "si, correcta.", history)
    assert out["captured_fields"]["patient_age"] == "2"


def test_age_unchanged_from_previous_turn_is_untouched():
    ai = _route_resp({"patient_age": "5 años"})
    out = agent._enforce_age_unit_grounding(ai, {"patient_age": "5 años"}, "sin observaciones")
    assert out["captured_fields"]["patient_age"] == "5 años"


# ── QA-2: confirmación de dirección + datos en bloque + pago (turno completo) ────


def _full_ai_response(reply, captured):
    return {"reply": reply, "intent": "route_scheduling", "phase": "fase_2_recogida_datos",
            "service_area": "route_scheduling", "captured_fields": captured,
            "message_mode": "flow_progress", "user_intent_signal": "provides_requested_data",
            "requires_handoff": False, "handoff_area": None, "resume_prompt": "",
            "confidence": 1.0, "pending_intents": []}


def test_block_data_with_payment_confirms_address_and_keeps_capture():
    """El turno QA-2 real: 'si, correcta. necesito coprologico para luna... y
    contraentrega' debe confirmar la dirección, conservar TODO lo capturado y avanzar
    (antes: '¿Cuál es la dirección de retiro?' pisando el turno entero)."""
    REG = "CL 27 SUR 12-22"
    prev = {"_client_found": True, "clinic_name": "Animal Club", "tax_id": "35529523-1",
            "pickup_address": REG, "_client_address": REG,
            "_address_confirmation_pending": True, "_address_confirmed": False}
    session = {"chat_id": "t", "channel": "telegram", "client_id": "client-A",
               "phase_current": "fase_2_recogida_datos", "intent_current": "route_scheduling",
               "captured_fields": prev}
    history = [
        {"role": "user", "content": "1"},
        {"role": "bot", "content": f"Perfecto, encontramos Animal Club. Tenemos como domicilio de retiro: {REG}. ¿Es correcta?"},
    ]
    msg = ("si, correcta. necesito coprologico para luna, gata siames, hembra, 2 años, "
           "dra sofia, dueña carolina, sin observaciones y contraentrega. confirmamos?")
    ai_captured = dict(prev)
    ai_captured.update({
        "requesting_doctor": "Dra. Sofia", "patient_name": "Luna", "species": "Felino",
        "breed": "Siames", "sex": "Hembra", "patient_age": "2 años", "owner_name": "Carolina",
        "observations": "sin observaciones", "payment_method": "contraentrega",
        "exam_type": "Coprológico",
    })
    db_patches = {
        "get_or_create_session": dict(side_effect=lambda c, channel="telegram": session),
        "get_recent_messages": dict(side_effect=lambda c, limit=8: history[-limit:]),
        "save_message": dict(side_effect=lambda c, t, r: history.append({"role": r, "content": t})),
        "update_session": dict(side_effect=lambda c, ai: session.update(
            phase_current=ai["phase"], intent_current=ai["intent"], captured_fields=ai["captured_fields"])),
        "get_client_by_id": dict(return_value={"id": "client-A", "clinic_name": "Animal Club",
                                               "tax_id": "35529523-1", "phone": "300", "address": REG}),
        "get_courier_for_client": dict(return_value=None),
        "get_catalog_context": dict(return_value=""),
        "get_individual_tests_context": dict(return_value=""),
        "get_last_order_for_client": dict(return_value=None),
        "list_diagnostic_labels": dict(return_value=[]),
        "find_diagnostic_label": dict(return_value=None),
        "get_tests_for_label": dict(return_value=[]),
        "find_tests_by_area": dict(return_value=(None, [])),
        "get_tests_by_codes_or_names": dict(side_effect=_lookup),
        "get_tests_by_codes": dict(side_effect=_lookup),
        "find_catalog_profiles": dict(return_value=[]),
        "find_catalog_profile": dict(return_value=None),
        "get_catalog_profiles_by_codes": dict(return_value=[]),
        "list_catalog_profiles_for_species": dict(return_value=[]),
        "list_catalog_profiles_matching_category": dict(return_value=[]),
        "create_request": dict(return_value={"request_id": "r1", "order_number": "A3-2026-901"}),
    }
    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in db_patches.items()]
    patchers.append(patch.object(agent.ai, "generate_turn",
                                 return_value=_full_ai_response("Perfecto, lo anoto.", ai_captured)))
    for p in patchers:
        p.start()
    try:
        reply = agent.process_turn("t", msg)
    finally:
        for p in patchers:
            p.stop()

    f = session["captured_fields"]
    assert f.get("_address_confirmation_pending") is False
    assert f.get("_address_confirmed") is True
    assert f.get("pickup_address") == REG
    assert f.get("patient_name") == "Luna"
    # El coprológico quedó estructurado con el precio real del catálogo.
    assert agent._as_text_items(f.get("selected_tests")) == ["1701"]
    assert "¿Cuál es la dirección de retiro?" != (reply or "")
    # La orden completa muestra el resumen con el precio del catálogo, no inventado.
    assert "12,000" in (reply or "")
    assert "23" not in (reply or "").replace("12,000", "")


# ── Desglose del descuento por volumen (reporte del usuario 2026-07-06) ──────────


def test_summary_shows_volume_discount_breakdown():
    """2 análisis ($14k + $8k) mostraban 'Valor estimado: $19,360' sin explicar el 12%
    de descuento — parecía un cálculo mal hecho. El resumen desglosa subtotal →
    descuento → total."""
    retic = {"code": "1104", "name": "Recuento de Reticulocitos", "price": 8000,
             "category": "Hematología"}

    def lookup(items):
        out = []
        for item in items:
            key = agent._catalog_item_key(str(item))
            for row in (CUADRO, retic):
                if key == str(row["code"]) or key in agent._catalog_item_key(row["name"]):
                    out.append(row)
                    break
        return out

    fields = {
        "_client_found": True, "clinic_name": "Animal Pets",
        "pickup_address": "DG 51A SUR 61B-03", "_address_confirmed": True,
        "requesting_doctor": "Dr. Prueba", "patient_name": "Pipo", "species": "Canino",
        "breed": "Chihuahua", "sex": "Macho", "patient_age": "5 años",
        "owner_name": "Luciano", "observations": "sin observaciones",
        "payment_method": "contraentrega",
        "exam_type": "Perfil personalizado (2 análisis)",
        "selected_tests": ["1101", "1104"], "removed_tests": [],
    }
    with patch.object(agent.db, "get_tests_by_codes", side_effect=lookup), \
         patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=lookup):
        summary = agent._route_confirmation_summary(fields)
    assert summary is not None
    assert "Subtotal: $22,000 COP" in summary
    assert "Descuento por volumen: -$2,640 COP" in summary
    assert "Valor estimado: $19,360 COP" in summary


def test_menu_selection_intro_shows_discount_breakdown():
    """El mensaje de registro tras elegir del menú también desglosa el descuento."""
    retic = {"code": "1104", "name": "Recuento de Reticulocitos", "price": 8000}
    text = agent._estimated_total_text(
        agent.calculate_custom_profile_total([dict(CUADRO), retic])
    )
    assert "Subtotal $22,000 COP" in text
    assert "descuento por volumen -$2,640 COP" in text
    assert "$19,360 COP" in text


def test_single_test_total_has_no_discount_breakdown():
    """Un solo análisis no tiene descuento: el texto sigue simple."""
    text = agent._estimated_total_text(agent.calculate_custom_profile_total([dict(CUADRO)]))
    assert text == "Valor estimado: $14,000 COP."
