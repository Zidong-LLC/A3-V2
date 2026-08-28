"""Consulta de resultados por chat (paso 3.4a): búsqueda, respuesta y entrega del PDF."""
from unittest.mock import patch

from app.enforcers.resultados import DELIVER_KEY, _enforce_results_message
from app.results_lookup import build_response, order_number_in, pdf_filename

CLIENT = "11111111-1111-1111-1111-111111111111"
OTRO_CLIENTE = "22222222-2222-2222-2222-222222222222"


def _result(rid="r1", patient="Firulais", exam="Hemograma", order="A3-00042"):
    return {
        "id": rid, "client_id": CLIENT, "published": True, "pdf_path": f"{CLIENT}/{rid}.pdf",
        "patient_name": patient, "exam_name": exam, "order_number": order,
    }


def _results_turn(patient=None):
    return {
        "intent": "results", "captured_fields": {"patient_name": patient} if patient else {},
        "pending_intents": [], "reply": "", "phase": "fase_6_cierre",
    }


# ── Búsqueda y armado de la respuesta ────────────────────────────────────────

def test_order_number_in_reconoce_la_orden_legible():
    assert order_number_in("me pasas el A3-00042 por favor") == "A3-00042"
    assert order_number_in("hola, cómo va todo") is None


def test_un_solo_resultado_se_manda_directo():
    with patch("app.results_lookup.portal_db.list_lab_results", return_value=[_result()]):
        text, deliver = build_response(CLIENT, "Firulais", None)
    assert deliver == ["r1"]
    assert "Firulais" in text


def test_varios_resultados_pocos_se_mandan_todos():
    found = [_result("r1"), _result("r2", exam="Química")]
    with patch("app.results_lookup.portal_db.list_lab_results", return_value=found):
        text, deliver = build_response(CLIENT, "Firulais", None)
    assert deliver == ["r1", "r2"]
    assert "2 resultados" in text


def test_demasiados_resultados_se_listan_y_no_se_mandan():
    found = [_result(f"r{i}", patient=f"Paciente {i}") for i in range(6)]
    with patch("app.results_lookup.portal_db.list_lab_results", return_value=found):
        text, deliver = build_response(CLIENT, None, None)
    assert deliver == []
    assert "Cuál te mando" in text


def test_sin_coincidencia_ofrece_los_ultimos_del_cliente():
    def fake(filters, client_id=None, only_published=False, limit=100):
        return [] if filters.get("patient") else [_result()]

    with patch("app.results_lookup.portal_db.list_lab_results", side_effect=fake):
        text, deliver = build_response(CLIENT, "Michi", None)
    assert deliver == []
    assert "No encuentro un resultado cargado para Michi" in text
    assert "Firulais" in text


def test_cliente_sin_resultados_recibe_aviso_y_no_promete_nada():
    with patch("app.results_lookup.portal_db.list_lab_results", return_value=[]):
        text, deliver = build_response(CLIENT, None, None)
    assert deliver == []
    assert "no tengo resultados publicados" in text


def test_nombre_del_pdf_es_legible_y_sin_caracteres_raros():
    assert pdf_filename(_result(patient="Firulais/Gómez")) == "Resultado - FirulaisGómez - Hemograma.pdf"


# ── Enforcer del paso 3.4a ───────────────────────────────────────────────────

def test_sin_cliente_identificado_pide_la_clinica_y_no_busca():
    with patch("app.results_lookup.portal_db.list_lab_results") as query:
        response = _enforce_results_message({}, _results_turn("Firulais"), "resultado de Firulais")
    query.assert_not_called()
    assert "veterinaria o el NIT" in response["reply"]
    assert DELIVER_KEY not in response["captured_fields"]


def test_con_cliente_identificado_marca_el_pdf_para_entrega():
    with patch("app.results_lookup.portal_db.list_lab_results", return_value=[_result()]):
        response = _enforce_results_message(
            {"client_id": CLIENT}, _results_turn("Firulais"), "el resultado de Firulais"
        )
    assert response["captured_fields"][DELIVER_KEY] == ["r1"]
    assert "Firulais" in response["reply"]


def test_si_la_busqueda_falla_responde_el_mensaje_de_siempre():
    with patch("app.results_lookup.portal_db.list_lab_results", side_effect=RuntimeError("base caída")):
        response = _enforce_results_message({"client_id": CLIENT}, _results_turn("Firulais"), "resultado")
    assert "todavía no está disponible por este medio" in response["reply"]
    assert DELIVER_KEY not in response["captured_fields"]


def test_la_recogida_pendiente_se_retoma_con_el_resultado_en_el_mismo_turno():
    turn = _results_turn("Firulais")
    turn["pending_intents"] = ["route_scheduling"]
    with patch("app.results_lookup.portal_db.list_lab_results", return_value=[_result()]):
        response = _enforce_results_message({"client_id": CLIENT}, turn, "resultado de Firulais")
    assert response["captured_fields"][DELIVER_KEY] == ["r1"]
    assert "Mientras tanto" in response["reply"]


# ── Entrega por el canal ─────────────────────────────────────────────────────

def _session(deliver=("r1",), client_id=CLIENT):
    return {"client_id": client_id, "captured_fields": {DELIVER_KEY: list(deliver)}}


def test_entrega_manda_el_pdf_por_telegram_y_limpia_la_marca():
    from app import results_delivery

    with patch.object(results_delivery.db, "get_or_create_session", return_value=_session()), \
         patch.object(results_delivery.db, "clear_pending_result_delivery") as clear, \
         patch.object(results_delivery.portal_db, "get_lab_result", return_value=_result()), \
         patch.object(results_delivery.storage, "download_result_pdf", return_value=b"%PDF-1.4"), \
         patch.object(results_delivery.telegram, "send_document") as send:
        sent = results_delivery.deliver_pending("chat-1", channel="telegram")
    assert sent == 1
    clear.assert_called_once_with("chat-1")
    assert send.call_args[0][2] == b"%PDF-1.4"


def test_nunca_entrega_el_resultado_de_otro_cliente():
    from app import results_delivery

    ajeno = _result()
    ajeno["client_id"] = OTRO_CLIENTE
    with patch.object(results_delivery.db, "get_or_create_session", return_value=_session()), \
         patch.object(results_delivery.db, "clear_pending_result_delivery"), \
         patch.object(results_delivery.portal_db, "get_lab_result", return_value=ajeno), \
         patch.object(results_delivery.storage, "download_result_pdf") as download, \
         patch.object(results_delivery.telegram, "send_document") as send:
        sent = results_delivery.deliver_pending("chat-1", channel="telegram")
    assert sent == 0
    download.assert_not_called()
    send.assert_not_called()


def test_un_resultado_despublicado_no_se_entrega():
    from app import results_delivery

    borrador = _result()
    borrador["published"] = False
    with patch.object(results_delivery.db, "get_or_create_session", return_value=_session()), \
         patch.object(results_delivery.db, "clear_pending_result_delivery"), \
         patch.object(results_delivery.portal_db, "get_lab_result", return_value=borrador), \
         patch.object(results_delivery.telegram, "send_document") as send:
        assert results_delivery.deliver_pending("chat-1", channel="telegram") == 0
    send.assert_not_called()


def test_sin_marca_no_toca_la_base_ni_el_canal():
    from app import results_delivery

    with patch.object(results_delivery.db, "get_or_create_session", return_value={"captured_fields": {}}), \
         patch.object(results_delivery.db, "clear_pending_result_delivery") as clear, \
         patch.object(results_delivery.telegram, "send_document") as send:
        assert results_delivery.deliver_pending("chat-1") == 0
    clear.assert_not_called()
    send.assert_not_called()


def test_chatwoot_recibe_el_adjunto_por_su_propio_canal():
    from app import results_delivery

    with patch.object(results_delivery.db, "get_or_create_session", return_value=_session()), \
         patch.object(results_delivery.db, "clear_pending_result_delivery"), \
         patch.object(results_delivery.portal_db, "get_lab_result", return_value=_result()), \
         patch.object(results_delivery.storage, "download_result_pdf", return_value=b"%PDF"), \
         patch.object(results_delivery.chatwoot, "send_document") as send:
        assert results_delivery.deliver_pending("conv-9", channel="chatwoot") == 1
    send.assert_called_once()
