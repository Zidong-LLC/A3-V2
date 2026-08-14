"""
Parte B (pedido del usuario, 2026-06-22): antes del resumen final, ofrecer agregar otro
análisis/perfil o personalizar, y repetir tras cada agregado hasta que el cliente siga al
pago. Debe tener salida robusta (no bucle). Ver RESUELTO-017.
"""
from unittest.mock import patch

from app import agent
from app.config import PEDIDOS_ENABLED
from app.flow import extra_analysis_offer
from tests.helpers_pedidos import assert_advances_after_decline

GLUCOSA = {"code": "1316", "name": "Glucosa (Ayunas)", "price": 12000, "category": "Química"}

COMPLETE = {
    "_client_found": True,
    "clinic_name": "Animal Pets",
    "pickup_address": "DG 51A SUR 61B-03",
    "requesting_doctor": "Dr Gastón",
    "patient_name": "Greta",
    "species": "Canino",
    "breed": "Bulldog",
    "sex": "Hembra",
    "patient_age": "3 años",
    "owner_name": "Jose",
    "observations": "sin observaciones",
    "exam_type": "Perfil Prequirúrgico I",
    "_selected_profile_code": "152",
    "_selected_profile_name": "Perfil Prequirúrgico I",
    "_selected_profile_price": 24000,
}
SESSION = {"client_id": "c1"}


def test_offers_extra_analysis_when_only_payment_missing():
    fields = dict(COMPLETE)
    out = agent._analysis_settled_response(SESSION, fields, "Listo, registro X.")
    assert fields["_offering_extra_analysis"] is True
    assert extra_analysis_offer() in out["reply"]


def test_proceed_detection():
    for t in ("no", "así está bien", "no, seguimos con el pago", "listo", "ya", "contraentrega"):
        assert agent._wants_to_proceed_to_payment(t) is True
    for t in ("agregale glucosa", "quitale la creatinina", "otro perfil"):
        assert agent._wants_to_proceed_to_payment(t) is False


def test_answer_decline_closes_the_offer():
    """Declinar la oferta cierra el carril. A dónde va después depende del flujo: sin pedidos
    lo siguiente es la forma de pago; con pedidos (decisión 011) el pago es del PEDIDO y se
    pregunta al cerrarlo, así que la orden pasa a su CONFIRMACIÓN.

    Este carril devolvía PAYMENT_METHOD_QUESTION sin mirar el flag: por eso el bot seguía
    pidiendo la forma de pago orden por orden con pedidos encendidos (testeo 2026-08-14)."""
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    out = agent._handle_extra_analysis_answer(SESSION, fields, "no, así está bien")
    assert fields.get("_offering_extra_analysis") is None
    if PEDIDOS_ENABLED:
        assert "pago" not in out["reply"].lower()
        assert out["phase"] == agent.CONFIRMATION_PHASE
        assert "¿Confirmas estos datos?" in out["reply"]
    else:
        assert out["reply"] == agent.PAYMENT_METHOD_QUESTION


def test_answer_payment_method_returns_none_to_let_pipeline_capture():
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    out = agent._handle_extra_analysis_answer(SESSION, fields, "contraentrega")
    assert out is None
    assert fields.get("_offering_extra_analysis") is None


def test_answer_named_test_adds_and_reoffers():
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[GLUCOSA]), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])):
        out = agent._handle_extra_analysis_answer(SESSION, fields, "agregale glucosa")
    assert fields["selected_tests"] == ["1316"]
    assert fields["_offering_extra_analysis"] is True  # se vuelve a ofrecer
    assert "agrego" in out["reply"].lower()
    assert extra_analysis_offer() in out["reply"]


def test_generic_area_term_does_not_autoadd():
    """ERR-053 (residual, reportado en vivo): 'Análisis sanguíneos' NUNCA debe agregar
    'Gases sanguíneos Plus' ($90k) a ciegas. Un término de área vaga no resuelve a un test:
    no agrega nada y pregunta/ofrece cuál."""
    from tests.test_catalog_resolution import CATALOG
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    with patch.object(agent.db, "list_catalog_tests", return_value=CATALOG):
        out = agent._handle_extra_analysis_answer(SESSION, fields, "Análisis sanguíneos")
    assert not agent._as_text_items(fields.get("selected_tests"))   # no autoagrega nada
    assert "1408" not in (out.get("reply") or "")                   # no sugiere el test caro
    assert "?" in (out.get("reply") or "")                          # pide precisión


def test_named_exact_test_still_adds_via_resolver():
    """El camino feliz sigue: un análisis nombrado inequívocamente se agrega directo."""
    from tests.test_catalog_resolution import CATALOG
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    with patch.object(agent.db, "list_catalog_tests", return_value=CATALOG):
        out = agent._handle_extra_analysis_answer(SESSION, fields, "un coprológico")
    assert agent._as_text_items(fields.get("selected_tests")) == ["1701"]
    assert "agrego" in out["reply"].lower()


def test_answer_bare_yes_asks_which():
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])):
        out = agent._handle_extra_analysis_answer(SESSION, fields, "sí, dale")
    assert fields.get("_awaiting_additional_test") == "add"
    assert "Qué análisis quieres agregar" in out["reply"]


def test_new_order_resets_offer_flag():
    assert "_offering_extra_analysis" in agent._ORDER_RESET_FIELDS


def test_stuck_profile_menu_does_not_block_extra_offer():
    """Regresión turno-15 (chat real 2026-07-14): el menú de perfiles armados queda PEGADO al
    pasar de 'elegir armado' a 'armar a medida'; en el turno siguiente, con los análisis ya
    capturados, ese menú obsoleto inhibía _enforce_extra_analysis_offer y la oferta quedaba a
    merced del modelo (a veces saltaba al pago). Un menú pegado viene ARRASTRADO del turno
    anterior (idéntico en prev): se descarta y la oferta sale determinística. Lógica pura
    sobre el estado real, sin fingir la respuesta del modelo."""
    stuck_menu = [{"code": "152", "name": "Perfil Prequirúrgico I", "price": 24000}]
    base = {k: v for k, v in COMPLETE.items()
            if k not in ("exam_type", "_selected_profile_code",
                         "_selected_profile_name", "_selected_profile_price")}
    base["_profile_menu_options"] = stuck_menu                  # ya estaba en el turno anterior
    fields = dict(base)
    fields["selected_tests"] = ["1404", "1405"]                 # Potasio + Sodio recién capturados
    # sin exam_type (el modelo puso solo selected_tests) → antes salía "Listo, queda None."
    ai = {"intent": "route_scheduling", "reply": agent.PAYMENT_METHOD_QUESTION,
          "captured_fields": fields}
    with patch.object(agent.db, "get_tests_by_codes", return_value=[]):
        out = agent._enforce_extra_analysis_offer(SESSION, ai, base)
    assert fields.get("_profile_menu_options") is None          # el menú pegado se descarta
    assert fields.get("_offering_extra_analysis") is True       # y se ofrece agregar otro
    assert extra_analysis_offer() in out["reply"]
    assert "None" not in out["reply"]                           # sin "queda None" cuando no hay nombre


def test_fresh_menu_set_this_turn_is_respected():
    """Un menú puesto EN ESTE turno (no estaba en prev — p. ej. el menú de área del grounding
    de 'orina') es una pregunta legítima al cliente: no se descarta ni se pisa con la oferta."""
    base = {k: v for k, v in COMPLETE.items()
            if k not in ("exam_type", "_selected_profile_code",
                         "_selected_profile_name", "_selected_profile_price")}
    fields = dict(base)
    fields["selected_tests"] = ["1404", "1405"]
    fields["_test_menu_options"] = [{"code": "1601", "name": "Parcial de Orina", "price": 16000}]
    fields["_test_menu_adds_to_profile"] = True
    ai = {"intent": "route_scheduling", "reply": "Para orina tenemos estas opciones: ...",
          "captured_fields": fields}
    out = agent._enforce_extra_analysis_offer(SESSION, ai, base)
    assert fields.get("_test_menu_options")                     # el menú fresco sigue vivo
    assert fields.get("_test_menu_adds_to_profile") is True
    assert out["reply"] == "Para orina tenemos estas opciones: ..."   # no lo pisó la oferta


def test_offer_intro_shows_new_tests_with_prices():
    """Reporte 2026-07-16: 'potasio y sodio' se anotaban sin decir el precio. Cuando el turno
    captura códigos nuevos (sin perfil base), el intro muestra ítems con precio y el total."""
    POTASIO = {"code": "1404", "name": "Potasio", "price": 12000}
    SODIO = {"code": "1405", "name": "Sodio", "price": 12000}
    base = {k: v for k, v in COMPLETE.items()
            if k not in ("exam_type", "_selected_profile_code",
                         "_selected_profile_name", "_selected_profile_price")}
    fields = dict(base)
    fields["selected_tests"] = ["1404", "1405"]
    ai = {"intent": "route_scheduling", "reply": agent.PAYMENT_METHOD_QUESTION,
          "captured_fields": fields}
    with patch.object(agent.db, "get_tests_by_codes", return_value=[POTASIO, SODIO]):
        out = agent._enforce_extra_analysis_offer(SESSION, ai, base)
    assert "Potasio $12.000" in out["reply"] and "Sodio $12.000" in out["reply"]
    assert extra_analysis_offer() in out["reply"]


# ── ERR-093 — frase ambigua sobre el pago: preguntar, no adivinar ────────────────
# QA en vivo 2026-07-27 (chat 1): el cliente escribió "No seguimos con el pago, te estoy
# diciendo" y el bot RE-MOSTRÓ el menú de perfiles desde cero, tirando el avance. El atajo
# que va al pago exige <=6 tokens y esa frase tiene 8, así que caía por la cascada.

def test_ambiguous_payment_phrase_asks_instead_of_reshowing_menu():
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    out = agent._handle_extra_analysis_answer(
        SESSION, fields, "No seguimos con el pago, te estoy diciendo")
    assert out is not None
    assert out["reply"] == agent.EXTRA_ANALYSIS_AMBIGUOUS_QUESTION
    # No debe re-ofrecer el menú de perfiles ni perder lo ya elegido.
    assert "Panel" not in out["reply"] and "1." not in out["reply"]
    assert fields["_selected_profile_code"] == "152"
    # Sigue en la oferta: el cliente todavía no decidió.
    assert fields.get("_offering_extra_analysis") is True


def test_short_proceed_phrases_still_go_straight_to_payment():
    """El fix no debe entorpecer el camino normal: las frases cortas siguen derecho."""
    for text in ("no, así está bien", "listo", "no", "ya"):
        fields = dict(COMPLETE, _offering_extra_analysis=True)
        out = agent._handle_extra_analysis_answer(SESSION, fields, text)
        assert_advances_after_decline(out, text)


def test_ambiguous_phrase_naming_an_analysis_is_not_hijacked():
    """Si nombra un análisis concreto la intención es clara: se agrega, no se repregunta."""
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[GLUCOSA]), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])):
        out = agent._handle_extra_analysis_answer(
            SESSION, fields, "agregale una glucosa antes de seguir con el pago")
    assert out["reply"] != agent.EXTRA_ANALYSIS_AMBIGUOUS_QUESTION
    assert "1316" in (fields.get("selected_tests") or [])
