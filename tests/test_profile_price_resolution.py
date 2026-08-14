"""
Regresión: resolver el precio base de un perfil del catálogo capturado como texto.

Caso real (orden A3-2026-062, gato): el `exam_type` quedó como "152-Perfil Prequirúrgico I"
(código + nombre juntos) sin `_selected_profile_code`. El backstop resolvía por nombre, pero
`find_catalog_profile("152-Perfil Prequirúrgico I")` no matchea la cadena combinada y por
nombre suelto devolvía un perfil equivocado ($90k en vez de $24k). Resultado: la orden cerró
con precio $0 → resumen incorrecto, evento persistido en $0 y SIN factura en Alegra
(`build_invoice_lines` descarta líneas con precio 0). Debe resolverse por el CÓDIGO que ya
trae el `exam_type` (fuente determinística del precio). Ver tasks/errores-soluciones.md ERR-041.
"""
from unittest.mock import patch

from app import agent
from app.config import PEDIDOS_ENABLED

PROFILE_152 = {
    "code": "152", "name": "Perfil Prequirúrgico I", "species": "ambos",
    "description": "Cuadro Hemático, ALT, Creatinina", "price": 24000,
}
PROFILE_151 = {
    "code": "151", "name": "Perfil General", "species": "ambos",
    "description": "Cuadro Hemático, Parcial de Orina, Coprológico", "price": 32000,
}
GLUCOSA = {"code": "0201", "name": "Glucosa", "price": 18000, "category": "Química"}


def _assert_payment_step_outcome(out):
    """Qué hace el paso de pago después de que el perfil quedó fijo.

    Lo que estos casos protegen es el paso ANTERIOR: que el perfil quede confirmado y que no
    se reabra el catálogo. Lo que el pago haga a continuación depende del flag, y las DOS
    ramas son correctas: sin pedidos empuja la pregunta; con pedidos (decisión 011)
    `payment_method` ya no es campo de la orden y el paso cede, porque el pago se pregunta
    una sola vez al cerrar el pedido."""
    reply = out["reply"].lower()
    if PEDIDOS_ENABLED:
        assert "pago" not in reply, "con pedidos el pago se pregunta al cerrar el pedido, no acá"
    else:
        assert "pago" in reply
# Perfil que el match por NOMBRE devolvía por error (mismo prefijo "Perfil Prequirúrgico").
PROFILE_161_WRONG = {
    "code": "161", "name": "Perfil Prequirúrgico X", "species": "ambos",
    "description": "...", "price": 90000,
}


def _resolve(exam_type, species="Felino"):
    fields = {"exam_type": exam_type, "species": species}
    by_codes = lambda codes, esp=None: [PROFILE_152] if "152" in [str(c) for c in codes] else []
    # find_catalog_profile (por nombre) devolvería el perfil EQUIVOCADO: el fix no debe usarlo
    # cuando hay código.
    with patch.object(agent.db, "get_catalog_profiles_by_codes", side_effect=by_codes), \
         patch.object(agent.db, "find_catalog_profile", return_value=PROFILE_161_WRONG):
        agent._resolve_profile_base_if_missing(fields)
    return fields


def test_combined_code_name_resolves_by_code_not_name():
    """'152-Perfil Prequirúrgico I' resuelve al 152 ($24k) por código, NO al 161 ($90k)
    que daría el match por nombre."""
    fields = _resolve("152-Perfil Prequirúrgico I")
    assert fields["_selected_profile_code"] == "152"
    assert fields["_selected_profile_price"] == 24000
    assert fields["_selected_profile_name"] == "Perfil Prequirúrgico I"


def test_already_resolved_is_left_untouched():
    """Si ya hay código de perfil, el backstop no lo toca."""
    fields = {"exam_type": "152-Perfil Prequirúrgico I", "species": "Felino",
              "_selected_profile_code": "999", "_selected_profile_price": 50000}
    with patch.object(agent.db, "get_catalog_profiles_by_codes", return_value=[PROFILE_152]):
        agent._resolve_profile_base_if_missing(fields)
    assert fields["_selected_profile_code"] == "999"


def test_custom_profile_is_not_resolved():
    """Un perfil armado desde cero ('Perfil personalizado') no es del catálogo: no se resuelve."""
    fields = {"exam_type": "Perfil personalizado (3 análisis)", "species": "Felino"}
    with patch.object(agent.db, "get_catalog_profiles_by_codes", return_value=[PROFILE_152]):
        agent._resolve_profile_base_if_missing(fields)
    assert fields.get("_selected_profile_code") is None


def test_invoice_lines_have_price_after_resolution():
    """Tras resolver, las líneas de factura tienen precio (>0) → Alegra sí factura."""
    from app import billing
    fields = _resolve("152-Perfil Prequirúrgico I")
    profile_payload = {
        "base_profile": {
            "code": fields["_selected_profile_code"],
            "name": fields["_selected_profile_name"],
            "price": fields["_selected_profile_price"],
        },
        "added_tests": [],
        "removed_tests": [],
    }
    lines = billing.build_invoice_lines(profile_payload)
    assert lines and any(ln["price"] > 0 for ln in lines)
    assert sum(ln["price"] for ln in lines) == 24000


def test_summary_puts_catalog_profile_price_on_analysis_line_without_duplicate_base():
    fields = {
        "clinic_name": "Veterinaria San Roque",
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo",
        "patient_name": "Greta",
        "species": "Canino",
        "breed": "Bulldog",
        "sex": "Hembra",
        "patient_age": "7 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "payment_method": "pago en línea",
        "exam_type": "151-Perfil General",
        "_selected_profile_code": "151",
        "_selected_profile_name": "Perfil General",
        "_selected_profile_price": 32000,
    }

    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]):
        summary = agent._route_confirmation_summary(fields)

    # El CÓDIGO va adelante, igual que en "Perfiles adicionales" y en la orden impresa: es
    # como el cliente que pidió "el perfil 151" verifica que quedó ese y no otro.
    assert "- Análisis: 151 Perfil General — $32.000" in summary
    assert "- Perfil base:" not in summary
    assert "- Valor estimado: $32.000" in summary


def test_confirmation_adds_analysis_to_profile_instead_of_closing_order():
    fields = {
        "clinic_name": "Veterinaria San Roque",
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo",
        "patient_name": "Greta",
        "species": "Canino",
        "breed": "Bulldog",
        "sex": "Hembra",
        "patient_age": "7 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "payment_method": "contraentrega",
        "exam_type": "151-Perfil General",
        "_selected_profile_code": "151",
        "_selected_profile_name": "Perfil General",
        "_selected_profile_price": 32000,
    }
    ai_response = agent._base_route_response("Quedó registrado", dict(fields))

    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=lambda items: [GLUCOSA] if items else []):
        out = agent._enforce_confirmation_step(
            {"client_id": "client-1"},
            ai_response,
            ai_response["captured_fields"],
            agent.CONFIRMATION_PHASE,
            "sí, pero agrégale glucosa",
        )

    assert out["phase"] == agent.CONFIRMATION_PHASE
    assert out["captured_fields"]["selected_tests"] == ["0201"]
    assert "- Agregados: 0201-Glucosa $18.000" in out["reply"]
    assert "¿Confirmas estos datos?" in out["reply"]
    assert "Quedó registrado" not in out["reply"]


def test_confirmation_asks_which_analysis_when_addition_is_unspecified():
    fields = {
        "clinic_name": "Veterinaria San Roque",
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo",
        "patient_name": "Greta",
        "species": "Canino",
        "breed": "Bulldog",
        "sex": "Hembra",
        "patient_age": "7 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "payment_method": "contraentrega",
        "exam_type": "151-Perfil General",
        "_selected_profile_code": "151",
        "_selected_profile_name": "Perfil General",
        "_selected_profile_price": 32000,
    }
    ai_response = agent._base_route_response("Quedó registrado", dict(fields))

    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]):
        out = agent._enforce_confirmation_step(
            {"client_id": "client-1"},
            ai_response,
            ai_response["captured_fields"],
            agent.CONFIRMATION_PHASE,
            "sí, pero agregale otro análisis",
        )

    assert out["phase"] == agent.CONFIRMATION_PHASE
    assert out["captured_fields"]["_awaiting_additional_test"] == "add"
    assert "¿Qué análisis quieres agregar?" in out["reply"]
    assert "Quedó registrado" not in out["reply"]


def test_confirmation_closes_on_affirm_signal_outside_token_list():
    """Etapa 2 (comprensión por IA): una confirmación FUERA de la lista de tokens
    ('me sirve así, avancemos con eso') cierra la orden cuando la IA marca
    user_intent_signal=affirm. El fallback de tokens queda intacto para cuando no hay señal."""
    fields = {
        "clinic_name": "Veterinaria San Roque", "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo", "patient_name": "Greta", "species": "Canino",
        "breed": "Bulldog", "sex": "Hembra", "patient_age": "7 años", "owner_name": "Pedro",
        "observations": "sin observaciones", "payment_method": "contraentrega",
        "exam_type": "151-Perfil General", "_selected_profile_code": "151",
        "_selected_profile_name": "Perfil General", "_selected_profile_price": 32000,
    }
    msg = "me sirve así, avancemos con eso"
    assert not agent._is_order_confirmation(msg)   # NO está en la lista de tokens
    ai_response = agent._base_route_response("...", dict(fields))
    ai_response["user_intent_signal"] = "affirm"
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(agent.db, "get_tests_by_codes", return_value=[]):
        out = agent._enforce_confirmation_step(
            {"client_id": "client-1"}, ai_response, ai_response["captured_fields"],
            agent.CONFIRMATION_PHASE, msg,
        )
    assert out["phase"] == "fase_6_cierre"


def test_profile_code_selection_wins_over_diagnostic_label():
    """'perfil 151' debe registrar el perfil cerrado, no abrir el flujo de perfil GENERAL."""
    session = {"client_id": "client-1"}
    fields = {
        "_client_found": True,
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo",
        "patient_name": "Greta",
        "species": "Canino",
        "breed": "Bulldog",
        "sex": "Hembra",
        "patient_age": "7 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "exam_type": "Perfil General",
        "_diagnostic_label": "GENERAL",
        "selected_tests": [],
        "removed_tests": [],
    }
    ai_response = agent._base_route_response(
        "Para un perfil General suelo sugerir estas pruebas. ¿Cuáles quieres incluir?",
        fields,
    )

    with patch.object(agent.db, "get_catalog_profiles_by_codes", return_value=[PROFILE_151]):
        out = agent._enforce_catalog_profile_code_selection(session, ai_response, "perfil 151")

    assert out["captured_fields"]["_selected_profile_code"] == "151"
    assert out["captured_fields"]["_selected_profile_price"] == 32000
    assert out["captured_fields"].get("_diagnostic_label") is None
    assert "151 Perfil General" in out["reply"]
    assert "Cuáles quieres incluir" not in out["reply"]
    _assert_payment_step_outcome(out)


def test_selected_profile_can_be_customized_before_payment():
    """Tras elegir un perfil cerrado, 'agrégale glucosa' debe personalizarlo, no saltar a pago."""
    session = {"client_id": "client-1"}
    fields = {
        "_client_found": True,
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo",
        "patient_name": "Greta",
        "species": "Canino",
        "breed": "Bulldog",
        "sex": "Hembra",
        "patient_age": "7 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "exam_type": "Perfil General",
        "_selected_profile_code": "151",
        "_selected_profile_name": "Perfil General",
        "_selected_profile_price": 32000,
        "_profile_detail_offered": True,
    }
    ai_response = agent._base_route_response("agrégale glucosa", fields)

    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[GLUCOSA]):
        out = agent._enforce_profile_detail_step(session, ai_response, fields, "agrégale glucosa")
    out = agent._enforce_payment_step(session, out, out["captured_fields"])

    assert out["captured_fields"]["_profile_customizing"] is True
    assert out["captured_fields"]["selected_tests"] == ["0201"]
    assert "Glucosa" in out["reply"]
    assert "pago" not in out["reply"].lower()


def test_customized_selected_profile_can_be_closed_then_asks_payment():
    session = {"client_id": "client-1"}
    fields = {
        "_client_found": True,
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo",
        "patient_name": "Greta",
        "species": "Canino",
        "breed": "Bulldog",
        "sex": "Hembra",
        "patient_age": "7 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "exam_type": "Perfil General",
        "_selected_profile_code": "151",
        "_selected_profile_name": "Perfil General",
        "_selected_profile_price": 32000,
        "_profile_customizing": True,
        "selected_tests": ["0201"],
        "removed_tests": [],
    }
    ai_response = agent._base_route_response("cerramos así", fields)

    out = agent._enforce_custom_profile_close(session, ai_response, fields, "cerramos así")
    out = agent._enforce_payment_step(session, out, out["captured_fields"])

    assert out["captured_fields"]["_profile_customizing"] is False
    _assert_payment_step_outcome(out)


def test_confirming_profile_detail_does_not_reopen_catalog_options():
    """'no así está bien' confirma el perfil mostrado; no debe listar otros perfiles General."""
    session = {"client_id": "client-1"}
    fields = {
        "_client_found": True,
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo",
        "patient_name": "Greta",
        "species": "Canino",
        "breed": "Bulldog",
        "sex": "Hembra",
        "patient_age": "7 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "exam_type": "Perfil General",
        "_selected_profile_code": "151",
        "_selected_profile_name": "Perfil General",
        "_selected_profile_price": 32000,
        "_profile_detail_offered": True,
    }
    ai_response = agent._base_route_response("Listo, lo dejamos así.", fields)

    with patch.object(agent.db, "find_catalog_profiles", side_effect=AssertionError("no rebuscar")):
        out = agent._enforce_catalog_profile_help(session, ai_response, "no asi esta bien", [])
    out = agent._enforce_profile_detail_step(session, out, out["captured_fields"], "no asi esta bien")
    out = agent._enforce_payment_step(session, out, out["captured_fields"])

    assert out["captured_fields"]["_profile_detail_confirmed"] is True
    assert "combinaciones" not in out["reply"].lower()
    _assert_payment_step_outcome(out)


def test_profile_detail_confirmation_uses_intent_signal_not_exact_words():
    session = {"client_id": "client-1"}
    fields = {
        "_client_found": True,
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo",
        "patient_name": "Greta",
        "species": "Canino",
        "breed": "Bulldog",
        "sex": "Hembra",
        "patient_age": "7 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "exam_type": "Perfil General",
        "_selected_profile_code": "151",
        "_selected_profile_name": "Perfil General",
        "_selected_profile_price": 32000,
        "_profile_detail_offered": True,
    }
    ai_response = agent._base_route_response("Tal cual, lo dejo así.", fields)
    ai_response["user_intent_signal"] = "affirm"

    out = agent._enforce_profile_detail_step(session, ai_response, fields, "tal cual")
    out = agent._enforce_payment_step(session, out, out["captured_fields"])

    assert out["captured_fields"]["_profile_detail_confirmed"] is True
    _assert_payment_step_outcome(out)


def test_negated_customization_signal_keeps_profile_as_is():
    """'No quiero agregar nada' contiene 'agregar', pero semánticamente deja el perfil igual."""
    session = {"client_id": "client-1"}
    fields = {
        "_client_found": True,
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Dr. Araujo",
        "patient_name": "Greta",
        "species": "Canino",
        "breed": "Bulldog",
        "sex": "Hembra",
        "patient_age": "7 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "exam_type": "Perfil General",
        "_selected_profile_code": "151",
        "_selected_profile_name": "Perfil General",
        "_selected_profile_price": 32000,
        "_profile_detail_offered": True,
    }
    ai_response = agent._base_route_response("Listo, lo dejo sin cambios.", fields)
    ai_response["user_intent_signal"] = "negate"

    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]):
        out = agent._enforce_profile_detail_step(session, ai_response, fields, "no quiero agregar nada")
    out = agent._enforce_payment_step(session, out, out["captured_fields"])

    assert out["captured_fields"].get("_profile_customizing") is not True
    assert out["captured_fields"]["_profile_detail_confirmed"] is True
    _assert_payment_step_outcome(out)
