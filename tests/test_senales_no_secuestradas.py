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
