"""Arreglos del flujo que salieron del estrés del 28/10 (ERR-187), con OK del usuario."""
import threading
import time
from unittest.mock import patch

from app import agent, orders, pedidos_abandonados


def test_el_cierre_deterministico_del_pedido_guarda_una_sola_vez_el_mensaje():
    sesion = {"client_id": "c1", "phase_current": "fase_6_cierre",
              "captured_fields": {"_pedido_id": "p1", "_order_registered": True}}
    guardados = []
    cierre = {"reply": "Listo, cerramos el pedido.", "phase": "fase_6_cierre", "intent": "route_scheduling",
              "captured_fields": {}, "pending_intents": []}
    with patch.object(agent.db, "get_or_create_session", return_value=sesion), \
         patch.object(agent.db, "get_recent_messages", return_value=[{"role": "bot", "content": "¿Pago?"}]), \
         patch.object(agent.db, "save_message", side_effect=lambda c, t, r: guardados.append((r, t))), \
         patch.object(agent.db, "update_session"), \
         patch.object(agent, "_sweep_stale_pedidos"), \
         patch.object(agent, "_close_pedido_turn", return_value=cierre):
        agent.process_turn("chat-1", "contraentrega")
    assert [t for r, t in guardados if r == "user"] == ["contraentrega"]


def test_dos_barridos_a_la_vez_avisan_una_sola_vez():
    """El cron y el turno de un cliente en el mismo proceso: antes, aviso doble."""
    avisos = []

    def avisar(pedido, n):
        time.sleep(0.2)
        avisos.append(pedido["id"])
        return True

    pedido = {"id": "p1", "external_chat_id": "chat-1"}
    with patch.object(pedidos_abandonados.db, "list_stale_pedidos", return_value=[pedido]), \
         patch.object(pedidos_abandonados.db, "list_pedido_requests", return_value=[{"order_number": "A3-1"}]), \
         patch.object(pedidos_abandonados.db, "close_pedido"), \
         patch.object(pedidos_abandonados.db, "limpiar_pedido_de_sesion"), \
         patch.object(pedidos_abandonados, "_avisar", side_effect=avisar):
        hilos = [threading.Thread(target=pedidos_abandonados.cerrar_abandonados) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
    assert avisos == ["p1"]


def test_repetir_un_analisis_ya_incluido_no_dice_que_lo_agrega():
    hemograma = {"code": "1101", "name": "Cuadro Hemático Completo", "price": 14000}
    sodio = {"code": "1405", "name": "Sodio", "price": 12000}
    assert orders._texto_agrego([hemograma], []) == "1101-Cuadro Hemático Completo $14.000 ya está incluido en la orden."
    texto = orders._texto_agrego([hemograma, sodio], [sodio])
    assert texto.startswith("Listo, agrego 1405-Sodio") and "1101-Cuadro Hemático Completo $14.000 ya está incluido" in texto


def test_la_promesa_de_mostrar_el_area_se_cumple_al_confirmar_la_direccion():
    opciones = [{"code": "1601", "name": "Parcial de Orina", "price": 16000}]
    ai = {"reply": "Perfecto, anotado. ¿Cuál es el médico solicitante?",
          "captured_fields": {"_area_tras_direccion": "quiero un análisis de orina", "_address_confirmed": True}}
    with patch.object(agent.db, "find_tests_by_area", return_value=("Uroanálisis", opciones)):
        agent._cumplir_promesa_de_area(ai)
    assert "1601" in ai["reply"] and "médico" not in ai["reply"]
    assert "_area_tras_direccion" not in ai["captured_fields"]
    assert ai["captured_fields"]["_test_menu_options"]


def test_la_promesa_espera_mientras_la_direccion_sigue_pendiente():
    ai = {"reply": "¿Me confirmas la dirección?",
          "captured_fields": {"_area_tras_direccion": "orina", "_address_confirmation_pending": True}}
    agent._cumplir_promesa_de_area(ai)
    assert ai["captured_fields"]["_area_tras_direccion"] == "orina"


def test_un_dato_dado_fuera_de_orden_se_nombra_en_vez_de_repetir_identica_la_pregunta():
    """QA8: a la fecha respondió una observación; el bot contestaba lo mismo de antes."""
    pregunta = "Perfecto, lo anoto. ¿Qué día tomaron la muestra?"
    ai = {"reply": pregunta, "captured_fields": {"observations": "medio urgente"}}
    agent._acusar_dato_fuera_de_orden(ai, [{"role": "bot", "content": pregunta}], ["observations"])
    assert ai["reply"] == "Listo, anoto la observación. ¿Qué día tomaron la muestra?"


def test_si_la_respuesta_ya_es_distinta_no_se_toca():
    ai = {"reply": "Anoté la observación. ¿Qué día tomaron la muestra?", "captured_fields": {}}
    agent._acusar_dato_fuera_de_orden(ai, [{"role": "bot", "content": "¿Qué día tomaron la muestra?"}], ["observations"])
    assert ai["reply"] == "Anoté la observación. ¿Qué día tomaron la muestra?"


def test_si_otro_paso_ya_mostro_las_opciones_del_area_no_se_repiten():
    """Guion V con el modelo real: el menú de orina ya venía en la respuesta y salía dos veces."""
    opciones = [{"code": "1601", "name": "Parcial de Orina", "price": 16000}]
    menu = "Para uroanálisis tenemos estas opciones:\n1. 1601 Parcial de Orina ($16.000)"
    ai = {"reply": menu, "captured_fields": {"_area_tras_direccion": "quiero un análisis de orina"}}
    with patch.object(agent.db, "find_tests_by_area", return_value=("Uroanálisis", opciones)):
        agent._cumplir_promesa_de_area(ai)
    assert ai["reply"] == menu


def test_cancelar_otro_dia_no_es_pedir_otra_orden():
    """«cancelá todo el pedido, lo hacemos otro día» abría OTRA orden ('otro' + 'pedido')."""
    from app.detectors.analisis import _explicitly_wants_another_order as quiere_otra

    assert quiere_otra("Sabés qué, cancelá todo el pedido, lo hacemos otro día.") is False
    assert quiere_otra("lo hacemos otro día, mejor") is False
    assert quiere_otra("otra orden para otro paciente") is True
    assert quiere_otra("quiero hacer otro pedido") is True
