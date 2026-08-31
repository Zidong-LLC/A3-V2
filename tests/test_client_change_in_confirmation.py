"""ERR-099 — cambiar de cliente en la confirmación debe re-identificar, no renombrar.

El bug real (QA en vivo 2026-07-28, chat 4): el resumen mostraba "Pet Agro Colombia /
CL 78C SUR 18G 67"; el cliente escribió "El / Cliente / Soy Animal Pets" y el bot re-mostró
el resumen con el nombre nuevo y **la dirección del cliente anterior**. La sesión quedó con
el client_id, el NIT y la dirección de Pet Agro Colombia bajo el nombre de Animal Pets: la
orden se habría facturado a uno y el motorizado habría ido a la puerta del otro.

El invariante que fija este archivo: `clinic_name` no puede cambiar sin que la identidad
(client_id, tax_id, pickup_address) se re-resuelva contra la base.
"""
import pytest

from app.detectors.orden import _detect_correction_field, _CORRECTION_FIELD_KEYWORDS
from app.agent import _IDENTIFICATION_RETRY_RESET_FIELDS, _switch_client_keep_order


# ── El detector reconoce el cliente, y no lo confunde con el paciente ──────────
@pytest.mark.parametrize("text", [
    "El\nCliente\nSoy Animal Pets",          # el mensaje literal del chat real
    "quiero cambiar el cliente",
    "me equivoqué de veterinaria",
    "la clínica es otra",
    "esta orden es para la otra sede",
])
def test_corregir_el_cliente_se_detecta_como_clinic_name(text):
    assert _detect_correction_field(text) == "clinic_name"


@pytest.mark.parametrize("text, expected", [
    # "animal" y "mascota" siguen siendo del paciente cuando no se nombra al cliente.
    ("quiero cambiar el nombre del animal", "patient_name"),
    ("me equivoqué con la mascota", "patient_name"),
    ("cambia el paciente a Rocky", "patient_name"),
    # La dirección gana aunque la frase nombre a la veterinaria: es una corrección de
    # dirección, no de identidad. Por eso pickup_address va primero en la lista.
    ("cambia la dirección de la veterinaria", "pickup_address"),
    ("el domicilio de retiro de la clínica está mal", "pickup_address"),
    # El resto de los campos no se ve afectado por la entrada nueva.
    ("cambia la raza", "breed"),
    ("me equivoqué en la edad", "patient_age"),
    ("el médico solicitante es otro", "requesting_doctor"),
])
def test_los_demas_campos_no_se_desplazan(text, expected):
    assert _detect_correction_field(text) == expected


def test_clinic_name_va_antes_que_patient_name_en_la_lista():
    """El orden es load-bearing: 'Animal Pets' tiene la palabra 'animal'. Si la entrada del
    paciente quedara primero, el bug de ERR-099 vuelve."""
    fields = [field for _, field in _CORRECTION_FIELD_KEYWORDS]
    assert fields.index("clinic_name") < fields.index("patient_name")
    # Y la dirección antes que el cliente, para no robarle las correcciones de dirección.
    assert fields.index("pickup_address") < fields.index("clinic_name")


# ── El invariante de identidad ────────────────────────────────────────────────
def test_el_reset_de_identificacion_limpia_nit_y_direccion():
    """Si clinic_name se descarta, tienen que irse con él los datos que lo acompañan.
    Dejar el NIT o la dirección del cliente viejo es exactamente el bug."""
    for key in ("clinic_name", "tax_id", "pickup_address"):
        assert key in _IDENTIFICATION_RETRY_RESET_FIELDS


def test_cambiar_de_cliente_borra_la_identidad_y_conserva_la_orden():
    fields = {
        "clinic_name": "Pet Agro Colombia",
        "tax_id": "1018431256",
        "pickup_address": "CL 78C SUR 18G 67",
        "_client_found": True,
        "_address_confirmed": True,
        # lo que NO se debe perder: la orden ya armada
        "patient_name": "Titi",
        "species": "Bovino",
        "requesting_doctor": "Dr. Solano Javier",
        "exam_type": "Perfil Prequirúrgico I",
        "selected_tests": ["1405", "1404"],
        "payment_method": "contraentrega",
    }
    session = {"client_id": "24cb0026-3b78-4609-9e71-469709c984bd"}
    calls = []

    class _FakeDB:
        @staticmethod
        def clear_client_from_session(chat_id):
            calls.append(chat_id)

    import app.agent as agent
    real_db = agent.db
    agent.db = _FakeDB
    try:
        _switch_client_keep_order("chat-1", session, fields, "cambiamos de cliente")
    finally:
        agent.db = real_db

    # La identidad se fue entera, no solo el nombre.
    assert "clinic_name" not in fields
    assert "tax_id" not in fields
    assert "pickup_address" not in fields
    assert session["client_id"] is None
    assert calls == ["chat-1"]

    # La orden sobrevive: corregir un dato no reinicia el pedido (L50).
    assert fields["patient_name"] == "Titi"
    assert fields["requesting_doctor"] == "Dr. Solano Javier"
    assert fields["selected_tests"] == ["1405", "1404"]
    assert fields["payment_method"] == "contraentrega"


def test_no_queda_nombre_nuevo_con_direccion_vieja():
    """La forma exacta del bug: nombre de un cliente + dirección de otro conviviendo."""
    fields = {
        "clinic_name": "Pet Agro Colombia",
        "tax_id": "1018431256",
        "pickup_address": "CL 78C SUR 18G 67",
        "patient_name": "Titi",
    }
    session = {"client_id": None}
    import app.agent as agent
    real_db = agent.db
    agent.db = type("_D", (), {"clear_client_from_session": staticmethod(lambda c: None)})
    try:
        _switch_client_keep_order("chat-1", session, fields, "cambiamos")
    finally:
        agent.db = real_db

    tiene_nombre = bool(fields.get("clinic_name"))
    tiene_direccion = bool(fields.get("pickup_address"))
    assert not (tiene_nombre and tiene_direccion), (
        "clinic_name y pickup_address quedaron juntos tras cambiar de cliente: "
        "es el cruce de identidad de ERR-099"
    )


# ── Decisión 2026-08-31 (pedido de A3, llamada 7): el cliente maestro se BLOQUEA ─
# Con una orden en curso o un pedido abierto, cambiar de veterinaria se rechaza con un
# mensaje claro y NADA se toca (ni campos ni client_id). Solo procede sin nada cargado.
from unittest.mock import patch

from app.agent import _restart_identification_for_new_client


def _sesion(client_id="cli-A", fase="fase_2_recogida_datos"):
    return {"client_id": client_id, "phase_current": fase, "external_chat_id": "chat-1"}


def test_con_orden_en_curso_el_cambio_de_cliente_se_bloquea():
    fields = {"clinic_name": "Pet Agro Colombia", "tax_id": "1018431256",
              "pickup_address": "CL 78C SUR 18G 67", "patient_name": "Rocky"}
    session = _sesion()
    with patch("app.agent.db.get_open_pedido", return_value=None), \
         patch("app.agent.db.clear_client_from_session") as limpiar:
        r = _restart_identification_for_new_client("chat-1", session, fields)
    assert "no puedo cambiar el cliente" in r["reply"]
    assert "Pet Agro Colombia" in r["reply"]
    limpiar.assert_not_called()                      # la identidad no se toca
    assert session["client_id"] == "cli-A"
    assert fields["tax_id"] == "1018431256"          # nada se descarta
    assert fields["pickup_address"] == "CL 78C SUR 18G 67"


def test_con_pedido_abierto_tambien_se_bloquea_aunque_no_haya_orden_cargada():
    """La orden anterior ya se registró en el pedido: cambiar de cliente ahora asociaría
    la orden siguiente al pedido (y la factura) de la veterinaria equivocada."""
    fields = {"clinic_name": "Pet Agro Colombia", "_order_registered": True}
    session = _sesion(fase="fase_6_cierre")
    with patch("app.agent.db.get_open_pedido", return_value={"id": "p-1", "status": "abierto"}), \
         patch("app.agent.db.clear_client_from_session") as limpiar:
        r = _restart_identification_for_new_client("chat-1", session, fields)
    assert "no puedo cambiar el cliente" in r["reply"]
    limpiar.assert_not_called()
    assert session["client_id"] == "cli-A"


def test_sin_nada_cargado_el_cambio_procede_como_siempre():
    fields = {"clinic_name": "Pet Agro Colombia", "tax_id": "1018431256"}
    session = _sesion()
    with patch("app.agent.db.get_open_pedido", return_value=None), \
         patch("app.agent.db.clear_client_from_session") as limpiar:
        r = _restart_identification_for_new_client("chat-1", session, fields)
    assert "verificar" in r["reply"].lower()
    limpiar.assert_called_once()
    assert session["client_id"] is None
    assert not fields.get("tax_id")                  # la identidad vieja se descarta
