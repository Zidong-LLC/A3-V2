"""Formato de los mensajes largos del flujo de la orden (pedido de A3 tras el último test
por WhatsApp, 2026-10-29): listas de a una por línea, bloques separados con una línea en
blanco, opciones numeradas debajo de la pregunta y «continuar» en vez de «cerrar»."""
from unittest.mock import patch

from app import agent, opciones_cerradas, orders
from app.flow import estimated_total_lines
from app.messages import PEDIDO_CLOSING_PROMPT, PEDIDO_CLOSING_QUESTION, PEDIDO_OFFER_REASK
from tests.test_prueba_real_whatsapp_20261029 import CATALOGO, CHAT3_ANTES_DE_CODIGOS, turno

SESSION = {"external_chat_id": "w1", "client_id": "cli-A", "channel": "whatsapp",
           "phase_current": "fase_2_recogida_datos", "intent_current": "route_scheduling"}
TRES = [CATALOGO["1701"], CATALOGO["1702"], CATALOGO["2057"]]


def test_los_analisis_registrados_van_uno_por_linea_con_el_total_aparte():
    fields = dict(CHAT3_ANTES_DE_CODIGOS, _test_menu_options=TRES)
    fields.pop("_correction_pending")
    with patch.object(agent, "db") as db, patch.object(orders, "db") as db2:
        db.get_tests_by_codes.return_value = TRES
        db2.get_tests_by_codes.return_value = TRES
        out = agent._capture_test_menu_selection(SESSION, fields, TRES)
    reply = opciones_cerradas.agregar(out)["reply"]
    assert reply.startswith("Listo, registro:\n- 1701 Coprológico $12.000\n- 1702 Coproscópico $15.000\n"
                            "- 2057 Panleucopenia Felina (Antígeno) $55.000\n\n"
                            "Subtotal $82.000\nDescuento por volumen -$10.660\nValor estimado $71.340\n\n"
                            "¿Agregamos otro análisis a esta orden, o la dejamos así?\n\n"
                            "1. Agregar otro análisis\n2. Dejarla así")


def test_el_total_en_lineas_sin_descuento_es_una_sola_linea():
    assert estimated_total_lines({"subtotal": 12000, "discount": 0, "total": 12000}) == "Valor estimado $12.000"


def test_el_resumen_separa_la_oferta_y_la_pregunta_con_lineas_en_blanco():
    fields = dict(CHAT3_ANTES_DE_CODIGOS, selected_tests=["1701", "2057"], exam_type="Perfil personalizado (2 análisis)",
                  removed_tests=[])
    with patch.object(orders, "db") as db:
        db.get_tests_by_codes.return_value = [CATALOGO["1701"], CATALOGO["2057"]]
        resumen = orders._route_confirmation_summary(fields)
        cierre = orders._route_closure_summary(fields)
    assert resumen.endswith("\n\nSi quieres cambiar algún dato o agregar otro análisis, decímelo.\n\n¿Confirmas estos datos?")
    assert "- Valor estimado:" in resumen.split("\n\n")[0], "el total queda dentro del bloque del resumen"
    assert cierre.endswith("\n\nNuestro motorizado pasará a recoger la muestra.")


def test_las_opciones_van_separadas_de_la_pregunta_por_una_linea_en_blanco():
    out = opciones_cerradas.agregar({"reply": f"Número de orden: A3-2026-005\n\n{PEDIDO_CLOSING_PROMPT}", "captured_fields": {}})
    assert out["reply"].endswith(f"{PEDIDO_CLOSING_PROMPT}\n\n1. Otra orden para otro paciente\n2. Continuar con el pago")


def test_la_oferta_dice_continuar_y_no_cerrar():
    assert PEDIDO_CLOSING_PROMPT == "¿Deseas cargar otra orden para otro paciente, o continuamos con el pago?"
    assert PEDIDO_OFFER_REASK.endswith("o continuamos con el pago?")
    assert "cerr" not in (PEDIDO_CLOSING_PROMPT + PEDIDO_OFFER_REASK).lower()


def test_la_pregunta_del_pago_va_en_dos_lineas_con_sus_opciones():
    out = opciones_cerradas.agregar({"reply": PEDIDO_CLOSING_QUESTION, "captured_fields": {}})
    assert out["reply"] == ("Listo. Si quieres dejar una observación para el pedido, escribila.\n¿Cómo prefieres el pago?"
                            "\n\n1. Contraentrega con el motorizado\n2. Pago en línea")


def test_de_punta_a_punta_el_2_a_la_oferta_sigue_cerrando_con_el_texto_nuevo():
    """El «2» (Continuar con el pago) sigue traduciéndose y lleva a la pregunta del pago."""
    from tests.test_prueba_real_whatsapp_20261029 import CHAT1_TRAS_REGISTRAR, HIST1
    estado = dict(CHAT1_TRAS_REGISTRAR, **{opciones_cerradas.CLAVE: {
        "1": "otra orden para otro paciente", "2": "no, eso es todo, cerramos el pedido"}})
    hist = HIST1[:-1] + [{"role": "bot", "content": f"Número de orden: A3-2026-003\n\n{PEDIDO_CLOSING_PROMPT}\n\n"
                                                     "1. Otra orden para otro paciente\n2. Continuar con el pago"}]
    reply, f, _ = turno("2", "unclear", estado, "fase_6_cierre", hist)
    assert reply.startswith(PEDIDO_CLOSING_QUESTION) and f.get("_pedido_awaiting_payment")
