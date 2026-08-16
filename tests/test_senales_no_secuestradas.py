"""Regresión ERR-124 (Ronda 3, confirmo_y_sigo): dos atajos secuestraban mensajes de
multi-orden por colisión de tokens — la clase que el usuario pidió erradicar ("entender el
contexto de toda la oración, no palabras puntuales").

1. "Confirmo, y sigo con la siguiente orden: … código 1101" disparaba la consulta del
   número de orden ('orden' + 'código' en la misma frase) y el bot respondía el nº de la
   orden ANTERIOR en pleno multi-orden.
2. "Ya está, son todas las órdenes" con el análisis pendiente disparaba la red de ayuda
   del catálogo (menú de recomendación de perfiles) en vez de ceder al cierre del pedido.
"""
from app.detectors.analisis import _is_order_number_query
from app.enforcers import ayudas


def test_siguiente_orden_con_codigo_no_es_consulta_de_numero():
    assert not _is_order_number_query(
        "Confirmo, y sigo con la siguiente orden: gata criolla hembra de 3 años, "
        "dueño B, código 1101.")
    assert not _is_order_number_query("sigo con la siguiente orden, codigo 1701")


def test_la_consulta_legitima_de_numero_sigue_viva():
    assert _is_order_number_query("cual es el numero de mi orden")
    assert _is_order_number_query("me pasas el número de la orden?")
    assert _is_order_number_query("el codigo de rastreo de mi pedido porfa")


def _ai(signal):
    return {
        "intent": "route_scheduling",
        "captured_fields": {"_client_found": True, "species": "Canino"},
        "reply": "respuesta del modelo",
        "user_intent_signal": signal,
    }


def test_farewell_no_dispara_el_menu_de_recomendacion():
    """'Ya está, son todas las órdenes' (farewell) con exam pendiente: la red CEDE —
    jamás responde con 'Lo que sueles pedir' + lista de perfiles."""
    for signal in ("farewell", "negate", "cancel", "another_order"):
        ai = _ai(signal)
        out = ayudas._enforce_analysis_help_fallback({"client_id": "c1"}, ai, {}, "Ya está, son todas las órdenes.", [])
        assert out is ai, f"con señal {signal} la red no debe interceptar"


def test_no_asi_esta_bien_cierra_el_pedido_aunque_el_modelo_marque_affirm():
    """ERR-128 (Ronda 6, 8 personas): a la oferta '¿otra orden… o cerramos?' el cliente dice
    'No, así está bien' y el modelo lo marca affirm (lee la conformidad) — el pedido quedaba
    abierto para siempre. La red de frases cierra, pero SOLO con la orden ya registrada."""
    from unittest.mock import patch
    from app import agent
    from app.messages import PEDIDO_CLOSING_QUESTION

    prev = {"_pedido_id": "ped-1", "_order_registered": True}
    ai = {"intent": "route_scheduling", "captured_fields": dict(prev),
          "reply": "¿Qué análisis o perfil desean?", "user_intent_signal": "affirm"}
    with patch.object(agent, "PEDIDOS_ENABLED", True):
        out = agent._enforce_open_pedido_close({"client_id": "c1"}, ai, prev, "No, así está bien.")
    assert out["reply"] == PEDIDO_CLOSING_QUESTION

    # A mitad de captura (orden NO registrada), "ya está, el dueño es Juan" NO cierra.
    prev2 = {"_pedido_id": "ped-1"}
    ai2 = {"intent": "route_scheduling", "captured_fields": dict(prev2),
           "reply": "sigo", "user_intent_signal": "provides_requested_data"}
    with patch.object(agent, "PEDIDOS_ENABLED", True):
        out2 = agent._enforce_open_pedido_close({"client_id": "c1"}, ai2, prev2, "ya está, el dueño es Juan")
    assert out2["reply"] == "sigo"


def test_direccion_escrita_gana_al_sustantivo_sucursal():
    """ERR-129 (Ronda 7, bucle infinito): 'te di la de la nueva sucursal. Calle 45 Sur
    # 12-30' — el carril de cambio de sede re-identificaba descartando la dirección
    literal. La dirección escrita por el cliente es una corrección, no otra identidad."""
    from app.agent import _user_gave_replacement_address

    msg = "la dirección está mal, te di la de la nueva sucursal. Calle 45 Sur # 12-30."
    fields = {"pickup_address": "Calle 45 Sur # 12-30"}
    prev = {"pickup_address": "DG 51A SUR 61B-03"}
    assert _user_gave_replacement_address(fields, prev, msg)
    # Sin dirección escrita en el mensaje, el cambio de sede sigue siendo cambio de sede.
    assert not _user_gave_replacement_address(
        {"pickup_address": "CL 1 # 2-3"}, prev, "mandalo a la otra sucursal")
    # La misma dirección re-capturada no es una corrección.
    assert not _user_gave_replacement_address(
        {"pickup_address": "DG 51A SUR 61B-03"}, prev, msg)
