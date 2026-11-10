"""Carga de informes en tanda (pedido de A3, 10/11): veterinaria obligatoria, un PDF por
envío con respuesta JSON, un solo aviso por chat al final y la red de seguridad que frena
el informe de otra veterinaria (por la orden o por el NIT impreso)."""
import io
from unittest.mock import patch

from tests.test_informe_pdf import _pdf_con_texto

CLIENT_A = "11111111-1111-1111-1111-111111111111"
CLIENT_B = "22222222-2222-2222-2222-222222222222"
RESULT_ID = "33333333-3333-3333-3333-333333333333"
VARVET = {"id": CLIENT_A, "clinic_name": "Varvet", "tax_id": "901915997"}


def _cliente_logueado():
    from app.main import app

    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"
    return client


def _subir_uno(client, pdf=b"%PDF-1.4 contenido", **extra):
    """Lo que manda upload-lote.js: un archivo, sus datos en el índice 0 y respuesta JSON."""
    data = {"client_id": CLIENT_A, "respuesta": "json", "pdf": (io.BytesIO(pdf), "Skay.pdf")}
    data.update(extra)
    return client.post("/resultados/subir", data=data, content_type="multipart/form-data")


def _parches(cliente=VARVET, orden=None):
    return (
        patch("app.dashboard_results.get_client_by_id", return_value=cliente),
        patch("app.dashboard_results.portal_db.get_request_by_order_number", return_value=orden),
        patch("app.dashboard_results.storage.upload_result_pdf", return_value="ruta.pdf"),
        patch("app.dashboard_results.portal_db.insert_lab_result",
              side_effect=lambda f: {"id": RESULT_ID, **f}),
    )


def test_la_tanda_responde_json_y_no_avisa_por_chat_informe_por_informe():
    client = _cliente_logueado()
    p_cli, p_ord, p_up, p_ins = _parches()
    with p_cli, p_ord, p_up, p_ins as insert, \
         patch("app.dashboard_results.portal_db.publish_lab_result", return_value={"id": RESULT_ID}), \
         patch("app.dashboard_results.portal_db.insert_notification") as aviso_portal, \
         patch("app.dashboard_results.portal_db.chat_for_client") as chat:
        response = _subir_uno(client, publish_now="1", patient_name_0="Skay")
    assert response.status_code == 200
    assert response.get_json() == {"subidos": 1, "errores": []}
    assert insert.call_args.args[0]["patient_name"] == "Skay"
    aviso_portal.assert_called_once()  # el aviso dentro del portal sale igual, por informe
    chat.assert_not_called()           # el del chat sale UNO al final (avisar-lote)


def test_una_orden_de_otra_veterinaria_no_se_sube():
    client = _cliente_logueado()
    p_cli, p_ord, p_up, p_ins = _parches(orden={"id": "r-9", "client_id": CLIENT_B})
    with p_cli, p_ord, p_up as upload, p_ins as insert:
        response = _subir_uno(client, order_number_0="A3-2026-013")
    errores = response.get_json()["errores"]
    assert response.get_json()["subidos"] == 0
    assert "es de otra veterinaria" in errores[0]
    upload.assert_not_called()
    insert.assert_not_called()


def test_una_orden_de_la_misma_veterinaria_queda_atada_al_informe():
    client = _cliente_logueado()
    orden = {"id": "r-13", "client_id": CLIENT_A, "patient_name": "Kookie", "exam_type": "Coprológico"}
    p_cli, p_ord, p_up, p_ins = _parches(orden=orden)
    with p_cli, p_ord, p_up, p_ins as insert:
        _subir_uno(client, order_number_0="A3-2026-013")
    fila = insert.call_args.args[0]
    assert fila["request_id"] == "r-13"
    assert fila["patient_name"] == "Kookie"
    assert fila["exam_name"] == "Coprológico"


def test_un_pdf_con_el_nit_de_otra_veterinaria_no_se_sube():
    client = _cliente_logueado()
    hocicos = {"id": CLIENT_A, "clinic_name": "Hocicos", "tax_id": "830123456-1"}
    p_cli, p_ord, p_up, p_ins = _parches(cliente=hocicos)
    with p_cli, p_ord, p_up as upload, p_ins as insert:
        response = _subir_uno(client, pdf=_pdf_con_texto("901915997-3Nit Varvet"))
    assert "NIT 901915997" in response.get_json()["errores"][0]
    upload.assert_not_called()
    insert.assert_not_called()


def test_un_pdf_con_el_nit_de_la_veterinaria_elegida_se_sube():
    client = _cliente_logueado()
    p_cli, p_ord, p_up, p_ins = _parches()
    with p_cli, p_ord, p_up as upload, p_ins:
        response = _subir_uno(client, pdf=_pdf_con_texto("901915997-3Nit Varvet"))
    assert response.get_json() == {"subidos": 1, "errores": []}
    upload.assert_called_once()


def test_avisar_lote_manda_un_solo_mensaje_con_la_cantidad():
    client = _cliente_logueado()
    with patch("app.dashboard_results.get_client_by_id", return_value=VARVET), \
         patch("app.dashboard_results.portal_db.chat_for_client", return_value=("55", "whatsapp")), \
         patch("app.dashboard_results.chatwoot.send_message") as enviar:
        response = client.post("/resultados/avisar-lote", data={"client_id": CLIENT_A, "cantidad": "37"})
    assert response.status_code == 200
    enviar.assert_called_once()
    assert enviar.call_args.args[0] == "55"
    assert "37 resultados nuevos" in enviar.call_args.args[1]


def test_avisar_lote_rechaza_datos_invalidos():
    client = _cliente_logueado()
    with patch("app.dashboard_results.get_client_by_id", return_value=None), \
         patch("app.dashboard_results.chatwoot.send_message") as enviar:
        sin_cliente = client.post("/resultados/avisar-lote", data={"client_id": CLIENT_A, "cantidad": "3"})
    with patch("app.dashboard_results.get_client_by_id", return_value=VARVET):
        sin_cantidad = client.post("/resultados/avisar-lote", data={"client_id": CLIENT_A, "cantidad": "x"})
    assert sin_cliente.status_code == 400
    assert sin_cantidad.status_code == 400
    enviar.assert_not_called()


def test_avisar_lote_exige_sesion_del_dashboard():
    from app.main import app

    app.config["TESTING"] = True
    response = app.test_client().post("/resultados/avisar-lote", data={"client_id": CLIENT_A, "cantidad": "2"})
    assert response.status_code == 302


def test_el_formulario_pide_veterinaria_y_comparte_por_defecto():
    client = _cliente_logueado()
    with patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        html = client.get("/resultados").get_data(as_text=True)
    assert 'name="publish_now" value="1" checked' in html
    assert 'name="client_id" value="" data-vet-id' in html
    assert 'id="elegir-vet"' in html
    assert "upload-lote.js" in html
    assert 'name="tax_id"' not in html  # el destino ya no se escribe a mano
