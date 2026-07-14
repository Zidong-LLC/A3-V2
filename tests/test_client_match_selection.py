"""
Lógica determinista de cambio de SEDE dentro de una orden (ERR-038 y afines).

La SELECCIÓN de una opción de la lista de coincidencias de cliente (elegir "la primera",
"la de los andes", un ordinal, una afirmación con coincidencia única, etc.) dependía de
CÓMO clasifica el modelo el mensaje. Probar eso fingiendo la respuesta del LLM no detecta
el bug real —el modelo en vivo clasifica distinto a como el mock supone—, así que esa
cobertura vive en el modelo real: `tools/scripts/validate_flows.py` y los QA adversariales.

Acá queda la lógica PURA que sí es determinista: al cambiar de sede se descarta la
identificación/dirección pero se conserva el resto de la orden (paciente, análisis, etc.).
"""
from unittest.mock import patch


def test_branch_switch_keeps_patient_and_analysis():
    """'esta orden es para la otra sede' descarta solo la identificación/dirección pero
    conserva el paciente, el análisis, el médico y el pago (no reinicia la orden entera)."""
    from app import agent as ag
    session = {"chat_id": "c1", "client_id": "client-A"}
    fields = {
        "clinic_name": "Puppy Export Centro Mayor", "tax_id": "901780420",
        "pickup_address": "Calle 38", "_client_found": True, "_address_confirmed": True,
        "patient_name": "Nayara", "species": "Felino", "sex": "Hembra", "patient_age": "4 años",
        "requesting_doctor": "Ramirez", "owner_name": "Pedro",
        "selected_tests": ["1316"], "payment_method": "contraentrega",
    }
    with patch("app.services.db.clear_client_from_session"):
        out = ag._switch_branch_keep_order("c1", session, dict(fields))
    f = out["captured_fields"]
    # Identificación y dirección: descartadas.
    assert not f.get("clinic_name") and not f.get("tax_id") and not f.get("pickup_address")
    # Datos de la orden: se mantienen.
    assert f.get("patient_name") == "Nayara" and f.get("species") == "Felino"
    assert ag._as_text_items(f.get("selected_tests")) == ["1316"]
    assert f.get("requesting_doctor") == "Ramirez" and f.get("payment_method") == "contraentrega"
