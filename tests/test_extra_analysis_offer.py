"""
Parte B (pedido del usuario, 2026-06-22): antes del resumen final, ofrecer agregar otro
análisis/perfil o personalizar, y repetir tras cada agregado hasta que el cliente siga al
pago. Debe tener salida robusta (no bucle). Ver RESUELTO-017.
"""
from unittest.mock import patch

from app import agent

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
    assert "agregar otro análisis" in out["reply"]
    assert "seguimos con el pago" in out["reply"]


def test_proceed_detection():
    for t in ("no", "así está bien", "no, seguimos con el pago", "listo", "ya", "contraentrega"):
        assert agent._wants_to_proceed_to_payment(t) is True
    for t in ("agregale glucosa", "quitale la creatinina", "otro perfil"):
        assert agent._wants_to_proceed_to_payment(t) is False


def test_answer_decline_goes_to_payment():
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    out = agent._handle_extra_analysis_answer(SESSION, fields, "no, así está bien")
    assert fields.get("_offering_extra_analysis") is None
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
    assert "seguimos con el pago" in out["reply"]


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
    merced del modelo (a veces saltaba al pago). Ahora el menú pegado se descarta y la oferta
    sale determinística. Lógica pura sobre el estado real, sin fingir la respuesta del modelo."""
    base = {k: v for k, v in COMPLETE.items()
            if k not in ("exam_type", "_selected_profile_code",
                         "_selected_profile_name", "_selected_profile_price")}
    fields = dict(base)
    fields["selected_tests"] = ["1404", "1405"]                 # Potasio + Sodio recién capturados
    # sin exam_type (el modelo puso solo selected_tests) → antes salía "Listo, queda None."
    fields["_profile_menu_options"] = [{"code": "152", "name": "Perfil Prequirúrgico I",
                                        "price": 24000}]         # menú PEGADO del turno anterior
    ai = {"intent": "route_scheduling", "reply": agent.PAYMENT_METHOD_QUESTION,
          "captured_fields": fields}
    out = agent._enforce_extra_analysis_offer(SESSION, ai, base)
    assert fields.get("_profile_menu_options") is None          # el menú pegado se descarta
    assert fields.get("_offering_extra_analysis") is True       # y se ofrece agregar otro
    assert "agregar otro análisis" in out["reply"]
    assert "None" not in out["reply"]                           # sin "queda None" cuando no hay nombre
