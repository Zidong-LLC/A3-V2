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

import pytest

from app import agent
from app.config import PEDIDOS_ENABLED

# Dos casos de este archivo prueban la LÓGICA DE RETROCESO *dentro* de la pregunta de pago de
# la orden ("antes de cerrar quiero agregar otro análisis" mientras el bot pregunta cómo paga).
# Con la jerarquía de pedidos (decisión 011) ese momento no existe: el pago no se pregunta por
# orden, así que `_enforce_payment_step` cede antes de llegar a esas ramas. El retroceso
# equivalente con pedidos —pedir otro análisis cuando el bot ofrece "¿otra orden o cerramos?"—
# se cubre en tests/test_pedidos_flujo.py.
solo_sin_pedidos = pytest.mark.skipif(
    PEDIDOS_ENABLED, reason="el paso de pago por orden solo existe sin PEDIDOS_ENABLED")

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


_CATALOG_ROWS = [COPRO, CUADRO] + URO_TESTS


def test_loose_exam_with_invented_price_resolves_to_catalog():
    ai = _route_resp({"exam_type": "Coprológico $23k"})
    with patch.object(agent.db, "list_catalog_tests", return_value=_CATALOG_ROWS):
        out = agent._enforce_loose_exam_catalog_resolution(ai, {})
    f = out["captured_fields"]
    assert f["selected_tests"] == ["1701"]
    assert f["exam_type"] == "1701 Coprológico"
    assert "$23" not in f["exam_type"]


def test_loose_exam_without_price_also_resolves():
    ai = _route_resp({"exam_type": "Cuadro Hemático"})
    with patch.object(agent.db, "list_catalog_tests", return_value=_CATALOG_ROWS):
        out = agent._enforce_loose_exam_catalog_resolution(ai, {})
    assert out["captured_fields"]["selected_tests"] == ["1101"]


def test_loose_exam_unresolved_keeps_text_without_price():
    """Sin match único: no inventa nada, pero el precio escrito se descarta."""
    ai = _route_resp({"exam_type": "Química sanguínea especial $99k"})
    with patch.object(agent.db, "list_catalog_tests", return_value=_CATALOG_ROWS), \
         patch.object(agent, "_category_profiles_menu_response", return_value=None):
        out = agent._enforce_loose_exam_catalog_resolution(ai, {})
    f = out["captured_fields"]
    assert "$99" not in (f["exam_type"] or "")
    assert not f.get("selected_tests")


def test_loose_exam_ambiguous_offers_options_instead_of_zero_price():
    """QA modelo real: 'una glucosa' (varias variantes reales) cerraba mostrando '$0'.
    Ahora un análisis genérico ambiguo OFRECE las opciones para elegir, sin estructurar
    a ciegas ni mostrar precio cero."""
    glucosas = [
        {"code": "1316", "name": "Glucosa (Ayunas)", "price": 12000, "category": "Química"},
        {"code": "1317", "name": "Glucosa Pre y Pos", "price": 20000, "category": "Química"},
        {"code": "1511", "name": "Insulina / Glucosa", "price": 43000, "category": "Endocrino"},
    ]
    ai = _route_resp({"exam_type": "Glucosa"})
    with patch.object(agent.db, "list_catalog_tests", return_value=glucosas):
        out = agent._enforce_loose_exam_catalog_resolution(ai, {})
    f = out["captured_fields"]
    assert f.get("_test_menu_options")                            # ofreció opciones
    assert not agent._as_text_items(f.get("selected_tests"))       # no estructuró a ciegas
    assert "$0" not in (out["reply"] or "") and "1316" in out["reply"]


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
    ai = _route_resp({"exam_type": "Cuadro Hemático Completo , Creatinina"})
    with patch.object(agent.db, "list_catalog_tests", return_value=[CUADRO, creat]):
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
         patch.object(agent.db, "list_catalog_tests", return_value=[]), \
         patch.object(agent.db, "find_tests_by_area", return_value=("Uroanálisis", URO_TESTS)):
        answer = agent._catalog_price_answer(fields, "¿cuánto queda el total con el parcial de orina incluido?")
    assert answer is not None
    assert "1601" in answer                      # lista el área real
    assert "PTT" not in answer                   # no inventa por fuzzy
    assert fields.get("_test_menu_adds_to_profile") is True  # la selección posterior SUMA


def test_price_answer_single_test_still_works():
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_lookup), \
         patch.object(agent.db, "list_catalog_tests", return_value=[COPRO, CUADRO] + URO_TESTS), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])):
        answer = agent._catalog_price_answer({}, "¿cuánto sale el coprológico?")
    assert answer is not None and "12.000" in answer


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


# QA-2 (confirmación de dirección + datos en bloque + pago en un turno completo): el
# escenario end-to-end se prueba con el MODELO REAL —fingir la respuesta del LLM no
# detecta el bug real— en tools/scripts/validate_flows.py y los QA adversariales.
# Los invariantes deterministas que ese turno debía respetar (dirección por señal,
# código del catálogo, precio real) están cubiertos por los tests de lógica pura de este
# archivo, test_money_invariants.py y test_address_pending_reask.py.


# ── Desglose del descuento por volumen (reporte del usuario 2026-07-06) ──────────


def test_summary_shows_volume_discount_breakdown():
    """2 análisis ($14k + $8k) mostraban 'Valor estimado: $19.360' sin explicar el 12%
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
        "owner_name": "Luciano", "sample_taken_date": "hoy", "observations": "sin observaciones",
        "payment_method": "contraentrega",
        "exam_type": "Perfil personalizado (2 análisis)",
        "selected_tests": ["1101", "1104"], "removed_tests": [],
    }
    with patch.object(agent.db, "get_tests_by_codes", side_effect=lookup), \
         patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=lookup):
        summary = agent._route_confirmation_summary(fields)
    assert summary is not None
    assert "Subtotal: $22.000" in summary
    assert "Descuento por volumen: -$2.640" in summary
    assert "Valor estimado: $19.360" in summary


def test_menu_selection_intro_shows_discount_breakdown():
    """El mensaje de registro tras elegir del menú también desglosa el descuento."""
    retic = {"code": "1104", "name": "Recuento de Reticulocitos", "price": 8000}
    text = agent._estimated_total_text(
        agent.calculate_custom_profile_total([dict(CUADRO), retic])
    )
    assert "Subtotal $22.000" in text
    assert "descuento por volumen -$2.640" in text
    assert "$19.360" in text


def test_single_test_total_has_no_discount_breakdown():
    """Un solo análisis no tiene descuento: el texto sigue simple."""
    text = agent._estimated_total_text(agent.calculate_custom_profile_total([dict(CUADRO)]))
    assert text == "Valor estimado: $14.000."


# ── Prueba real chat 4 (2026-07-08): tres fallos del 20% restante ────────────────


def test_new_test_menu_discards_stale_profile_menu():
    """BUG menú pegado de PERFILES: pidió 'prueba de orina' (menú de análisis nuevo) con el
    menú de perfiles prequirúrgicos viejo aún vivo; el '1' registró '152 Perfil Prequirúrgico I'
    pisando el perfil personalizado. Mostrar un menú de análisis DESCARTA el de perfiles."""
    fields = {"_profile_menu_options": [{"code": "152", "name": "Perfil Prequirúrgico I", "price": 24000}]}
    agent._store_test_menu_options(fields, URO_TESTS)
    assert not fields.get("_profile_menu_options")          # menú viejo descartado
    assert fields.get("_test_menu_options")                 # menú nuevo activo
    # Y la inversa: mostrar perfiles descarta el menú de análisis.
    fields2 = {"_test_menu_options": [{"code": "1601", "name": "Parcial de Orina", "price": 16000}],
               "_test_menu_adds_to_profile": True}
    agent._store_profile_menu_options(fields2, [{"code": "152", "name": "Perfil Prequirúrgico I", "price": 24000}])
    assert not fields2.get("_test_menu_options") and not fields2.get("_test_menu_adds_to_profile")


@solo_sin_pedidos
def test_payment_question_does_not_override_add_analysis_request():
    """'antes de cerrar quiero agregar otro análisis' cuando el bot pregunta el pago NO debe
    ser pisado re-preguntando el pago: se reabre el paso de agregado."""
    fields = {"_client_found": True, "clinic_name": "X", "pickup_address": "Y",
              "requesting_doctor": "Dr", "patient_name": "Messi", "species": "Caprino",
              "breed": "Arida", "sex": "Hembra", "patient_age": "9 años", "owner_name": "Matias", "sample_taken_date": "hoy",
              "sample_taken_date": "hoy",
              "observations": "sin observaciones", "exam_type": "Perfil personalizado (3 análisis)",
              "selected_tests": ["1101", "1404", "1405"]}
    ai = _route_resp(fields)
    out = agent._enforce_payment_step({"client_id": "c1"}, ai, ai["captured_fields"],
                                      "antes de cerrar quiero agregar otro analisis")
    assert "agregar" in out["reply"].lower() and "pago" not in out["reply"].lower()
    assert out["captured_fields"].get("_awaiting_additional_test") == "add"
    # Sin ese pedido, el paso de pago sigue normal.
    ai2 = _route_resp(fields)
    out2 = agent._enforce_payment_step({"client_id": "c1"}, ai2, ai2["captured_fields"], "listo")
    assert out2["reply"] == agent.PAYMENT_METHOD_QUESTION


def test_reference_phrase_captured_as_doctor_is_discarded():
    """'el que ya te dije' capturado LITERAL como requesting_doctor ('El Que Ya Te Dije')
    se descarta para que el pipeline re-pregunte; un nombre real pasa limpio."""
    f = {"requesting_doctor": "El Que Ya Te Dije", "owner_name": "el de siempre"}
    agent._reject_reference_phrases_as_names(f, {})
    assert f["requesting_doctor"] is None and f["owner_name"] is None
    ok = {"requesting_doctor": "Sr Juan", "patient_name": "Messi"}
    agent._reject_reference_phrases_as_names(ok, {})
    assert ok["requesting_doctor"] == "Sr Juan" and ok["patient_name"] == "Messi"
    # Un valor que NO cambió este turno no se toca (aunque sea raro).
    prev = {"requesting_doctor": "El Que Ya Te Dije"}
    same = dict(prev)
    agent._reject_reference_phrases_as_names(same, prev)
    assert same["requesting_doctor"] == "El Que Ya Te Dije"


# ── L50: la LÓGICA de los fallos, no la palabra (corrección del usuario 2026-07-11) ──


@solo_sin_pedidos
def test_step_push_yields_to_correction_signal():
    """LÓGICA DE RETROCESO: el empuje del paso de pago CEDE ante la señal semántica de
    corrección del modelo — cualquier fraseo de 'volver atrás' (agregar análisis, cambiar
    un dato) mientras se pregunta el pago, sin depender de palabras."""
    fields = {"_client_found": True, "clinic_name": "X", "pickup_address": "Y",
              "requesting_doctor": "Dr", "patient_name": "Messi", "species": "Caprino",
              "breed": "Arida", "sex": "Hembra", "patient_age": "9 años", "owner_name": "Matias", "sample_taken_date": "hoy",
              "sample_taken_date": "hoy",
              "observations": "sin observaciones", "exam_type": "Perfil personalizado (3 análisis)",
              "selected_tests": ["1101", "1404", "1405"]}
    ai = _route_resp(fields)
    ai["user_intent_signal"] = "correction"
    ai["reply"] = "Claro, dime qué quieres ajustar."
    out = agent._enforce_payment_step({"client_id": "c1"}, ai, ai["captured_fields"],
                                      "cualquier fraseo de cambio que el modelo entendió")
    assert out["reply"] == "Claro, dime qué quieres ajustar."   # el empuje cedió
    # Sin señal de corrección, el paso de pago sigue empujando normal.
    ai2 = _route_resp(fields)
    ai2["user_intent_signal"] = "provides_requested_data"
    out2 = agent._enforce_payment_step({"client_id": "c1"}, ai2, ai2["captured_fields"], "ok")
    assert out2["reply"] == agent.PAYMENT_METHOD_QUESTION


def test_change_client_mid_order_keeps_the_order():
    """Decision 2026-08-31 (pedido de A3, llamada 7): con la orden EN CURSO el cliente
    maestro se BLOQUEA — nada se descarta y el bot pide cerrar el pedido primero."""
    fields = {"clinic_name": "Danimal Planet", "tax_id": "9001", "pickup_address": "CL 59",
              "_client_found": True, "_address_confirmed": True,
              "requesting_doctor": "Sr Juan", "patient_name": "Messi", "species": "Caprino",
              "breed": "Arida", "sex": "Hembra", "patient_age": "9 años", "owner_name": "Matias", "sample_taken_date": "hoy",
              "sample_taken_date": "hoy",
              "observations": "sin observaciones", "payment_method": "pago_linea",
              "selected_tests": ["1101", "1404", "1405"],
              "exam_type": "Perfil personalizado (3 análisis)"}
    session = {"chat_id": "c", "client_id": "cli-1", "phase_current": "fase_4_confirmacion"}
    with patch("app.services.db.get_open_pedido", return_value=None),          patch("app.services.db.clear_client_from_session"):
        out = agent._restart_identification_for_new_client("c", session, dict(fields))
    f = out["captured_fields"]
    # Identidad y direccion: INTACTAS (el cambio se bloquea, no se re-verifica nada).
    assert f.get("clinic_name") and f.get("pickup_address")
    assert "no puedo cambiar el cliente" in out["reply"]
    # La orden: intacta.
    assert f.get("requesting_doctor") == "Sr Juan" and f.get("patient_name") == "Messi"
    assert agent._as_text_items(f.get("selected_tests")) == ["1101", "1404", "1405"]
    assert f.get("payment_method") == "pago_linea"


def test_change_client_after_registered_order_resets():
    """Con la orden anterior YA REGISTRADA (fase terminal), 'otra orden para otro cliente'
    sí parte de cero: es un pedido nuevo."""
    fields = {"clinic_name": "X", "_order_registered": True,
              "requesting_doctor": "Dr", "patient_name": "Toby",
              "selected_tests": ["1101"], "exam_type": "1101 Cuadro Hemático"}
    session = {"chat_id": "c", "client_id": "cli-1", "phase_current": "fase_6_cierre"}
    with patch("app.services.db.clear_client_from_session"):
        out = agent._restart_identification_for_new_client("c", session, dict(fields))
    f = out["captured_fields"]
    assert not f.get("patient_name") and not agent._as_text_items(f.get("selected_tests"))
