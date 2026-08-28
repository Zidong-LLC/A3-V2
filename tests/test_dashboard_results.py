"""Módulo Resultados del dashboard: subida de PDF, validaciones y publicación."""
import io
from unittest.mock import patch

CLIENT_A = "11111111-1111-1111-1111-111111111111"
RESULT_ID = "33333333-3333-3333-3333-333333333333"


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login_dashboard(client):
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"


def _upload(client, pdf_bytes, **extra):
    data = {"order_number": "A3-00042", "pdf": (io.BytesIO(pdf_bytes), "informe.pdf")}
    data.update(extra)
    return client.post(
        "/resultados/subir", data=data, content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_results_page_requires_dashboard_login():
    client = _get_test_client()
    response = client.get("/resultados")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_portal_client_session_cannot_open_results_page():
    """Una veterinaria logueada al portal no accede al módulo del personal."""
    client = _get_test_client()
    with client.session_transaction() as sess:
        sess["portal_user_id"] = "user-1"
        sess["portal_client_id"] = CLIENT_A
    response = client.get("/resultados")
    assert response.status_code == 302


def test_upload_pdf_creates_result():
    client = _get_test_client()
    _login_dashboard(client)
    request_row = {"id": "r-1", "client_id": CLIENT_A, "patient_name": "Rocky",
                   "owner_name": "Ana", "exam_type": "Hemograma"}
    with patch("app.dashboard_results.portal_db.get_request_by_order_number",
               return_value=request_row), \
         patch("app.dashboard_results.storage.upload_result_pdf",
               return_value=f"{CLIENT_A}/A3-00042/x.pdf") as mock_upload, \
         patch("app.dashboard_results.portal_db.insert_lab_result",
               return_value={"id": RESULT_ID, "client_id": CLIENT_A}) as mock_insert, \
         patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        response = _upload(client, b"%PDF-1.4 contenido")
    assert response.status_code == 200
    assert mock_upload.call_args[0][0] == CLIENT_A
    inserted = mock_insert.call_args[0][0]
    assert inserted["client_id"] == CLIENT_A
    assert inserted["patient_name"] == "Rocky"
    assert inserted["uploaded_by"] == "admin"


def test_upload_rejects_non_pdf_content():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.portal_db.get_request_by_order_number",
               return_value={"id": "r-1", "client_id": CLIENT_A}), \
         patch("app.dashboard_results.storage.upload_result_pdf") as mock_upload, \
         patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        response = _upload(client, b"no es un pdf")
    assert response.status_code == 200
    assert "Archivo inválido" in response.get_data(as_text=True)
    mock_upload.assert_not_called()


def test_upload_rejects_unknown_client():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.portal_db.get_request_by_order_number",
               return_value=None), \
         patch("app.dashboard_results.find_clients_by_tax_id", return_value=[]), \
         patch("app.dashboard_results.storage.upload_result_pdf") as mock_upload, \
         patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        response = _upload(client, b"%PDF-1.4 x")
    assert response.status_code == 200
    assert "No se encontró el cliente" in response.get_data(as_text=True)
    mock_upload.assert_not_called()


def test_publish_notifies_and_sends_telegram():
    client = _get_test_client()
    _login_dashboard(client)
    result_row = {"id": RESULT_ID, "client_id": CLIENT_A, "published": False,
                  "patient_name": "Rocky", "order_number": "A3-00042",
                  "exam_name": "Hemograma", "pdf_path": "p.pdf"}
    with patch("app.dashboard_results.portal_db.get_lab_result", return_value=result_row), \
         patch("app.dashboard_results.portal_db.publish_lab_result",
               return_value={**result_row, "published": True}), \
         patch("app.dashboard_results.portal_db.insert_notification") as mock_notif, \
         patch("app.dashboard_results.portal_db.telegram_chat_for_client",
               return_value="12345"), \
         patch("app.dashboard_results.telegram.send_message") as mock_tg:
        response = client.post(f"/resultados/{RESULT_ID}/publicar")
    assert response.status_code == 302
    assert mock_notif.call_args[0][0] == CLIENT_A
    assert mock_notif.call_args[0][1] == "result_published"
    assert mock_tg.call_args[0][0] == "12345"


def test_publish_survives_telegram_failure():
    client = _get_test_client()
    _login_dashboard(client)
    result_row = {"id": RESULT_ID, "client_id": CLIENT_A, "published": False,
                  "patient_name": "Rocky", "order_number": "A3-00042",
                  "exam_name": "Hemograma", "pdf_path": "p.pdf"}
    with patch("app.dashboard_results.portal_db.get_lab_result", return_value=result_row), \
         patch("app.dashboard_results.portal_db.publish_lab_result",
               return_value={**result_row, "published": True}), \
         patch("app.dashboard_results.portal_db.insert_notification"), \
         patch("app.dashboard_results.portal_db.telegram_chat_for_client",
               side_effect=RuntimeError("red caída")):
        response = client.post(f"/resultados/{RESULT_ID}/publicar")
    assert response.status_code == 302


def test_pdf_redirects_to_signed_url():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.portal_db.get_lab_result",
               return_value={"id": RESULT_ID, "pdf_path": "p.pdf"}), \
         patch("app.dashboard_results.storage.result_signed_url",
               return_value="https://signed.example/p.pdf"):
        response = client.get(f"/resultados/{RESULT_ID}/pdf")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://signed.example/p.pdf"


# ── Deshacer: despublicar y eliminar (ficha del cliente, 2026-08-27) ─────────────
# El caso caro es el informe compartido con la veterinaria equivocada: hasta ahora no
# había marcha atrás. Al despublicar se borra también el aviso, porque si no el cliente
# ve una notificación que lleva a un informe que ya no puede abrir.

def test_despublicar_saca_el_informe_del_portal_y_borra_el_aviso():
    client = _get_test_client()
    _login_dashboard(client)
    llamadas = {}

    def fake_unpublish(result_id):
        llamadas["unpublish"] = result_id
        return {"id": result_id, "published": False}

    with patch("app.services.portal_db.get_lab_result",
               return_value={"id": RESULT_ID, "published": True, "client_id": CLIENT_A}), \
         patch("app.services.portal_db.unpublish_lab_result", side_effect=fake_unpublish):
        response = client.post(f"/resultados/{RESULT_ID}/dejar-de-compartir",
                               data={"volver_a": CLIENT_A})

    assert llamadas["unpublish"] == RESULT_ID
    assert response.status_code == 302
    assert f"/clientes/{CLIENT_A}" in response.headers["Location"], "vuelve a la ficha del cliente"


def test_despublicar_un_informe_que_no_estaba_compartido_no_hace_nada():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.services.portal_db.get_lab_result",
               return_value={"id": RESULT_ID, "published": False}), \
         patch("app.services.portal_db.unpublish_lab_result") as unpublish:
        client.post(f"/resultados/{RESULT_ID}/dejar-de-compartir")
    unpublish.assert_not_called()


def test_eliminar_borra_el_archivo_y_la_fila():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.services.portal_db.get_lab_result",
               return_value={"id": RESULT_ID, "pdf_path": "cli/orden/x.pdf"}), \
         patch("app.services.storage.delete_result_pdf") as borrar_archivo, \
         patch("app.services.portal_db.delete_lab_result") as borrar_fila:
        client.post(f"/resultados/{RESULT_ID}/eliminar", data={"volver_a": CLIENT_A})
    borrar_archivo.assert_called_once_with("cli/orden/x.pdf")
    borrar_fila.assert_called_once_with(RESULT_ID)


def test_si_el_archivo_ya_no_esta_igual_se_borra_el_informe():
    """El bucket puede haber perdido el archivo; lo que importa es dejar de publicarlo."""
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.services.portal_db.get_lab_result",
               return_value={"id": RESULT_ID, "pdf_path": "cli/orden/x.pdf"}), \
         patch("app.services.storage.delete_result_pdf", side_effect=RuntimeError("404")), \
         patch("app.services.portal_db.delete_lab_result") as borrar_fila:
        response = client.post(f"/resultados/{RESULT_ID}/eliminar")
    borrar_fila.assert_called_once_with(RESULT_ID)
    assert response.status_code == 302


def test_deshacer_exige_sesion_del_dashboard():
    client = _get_test_client()
    for ruta in (f"/resultados/{RESULT_ID}/dejar-de-compartir", f"/resultados/{RESULT_ID}/eliminar"):
        response = client.post(ruta)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ── Ficha del cliente y su buscador ──────────────────────────────────────────────

def test_la_ficha_del_cliente_exige_sesion():
    client = _get_test_client()
    response = client.get(f"/clientes/{CLIENT_A}")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_el_buscador_no_dispara_consulta_con_menos_de_dos_letras():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.services.db.search_clients_for_dashboard") as buscar:
        response = client.get("/clientes/buscar?q=a")
    assert response.get_json() == {"resultados": []}
    buscar.assert_not_called()


def test_el_buscador_devuelve_nombre_nit_y_zona():
    client = _get_test_client()
    _login_dashboard(client)
    fila = {"id": CLIENT_A, "clinic_name": "Zoomascotas", "tax_id": "80733389",
            "zone": "Sur", "is_active": True}
    with patch("app.dashboard_client.db.search_clients_for_dashboard", return_value=[fila]):
        datos = client.get("/clientes/buscar?q=zoomas").get_json()
    assert datos["resultados"] == [
        {"id": CLIENT_A, "nombre": "Zoomascotas", "nit": "80733389", "zona": "Sur", "activo": True}
    ]


# ── Carga de varios informes de una vez (2026-08-28) ─────────────────────────

def _upload_many(client, archivos, **extra):
    """archivos: lista de (bytes, nombre). Cada uno con su fila de datos."""
    data = {"client_id": CLIENT_A, "pdf": [(io.BytesIO(b), n) for b, n in archivos]}
    data.update(extra)
    return client.post("/resultados/subir", data=data,
                       content_type="multipart/form-data", follow_redirects=True)


def test_upload_multiple_crea_un_resultado_por_archivo():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.get_client_by_id", return_value={"id": CLIENT_A}), \
         patch("app.dashboard_results.storage.upload_result_pdf", return_value="ruta.pdf"), \
         patch("app.dashboard_results.portal_db.insert_lab_result",
               side_effect=lambda f: {"id": RESULT_ID, **f}) as insert, \
         patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        response = _upload_many(
            client,
            [(b"%PDF-1.4 uno", "a.pdf"), (b"%PDF-1.4 dos", "b.pdf")],
            patient_name_0="Firulais", order_number_0="A3-00042",
            patient_name_1="Michi", order_number_1="A3-00043",
        )
    assert response.status_code == 200
    assert insert.call_count == 2
    pacientes = [c.args[0]["patient_name"] for c in insert.call_args_list]
    ordenes = [c.args[0]["order_number"] for c in insert.call_args_list]
    assert pacientes == ["Firulais", "Michi"]
    assert ordenes == ["A3-00042", "A3-00043"]


def test_upload_multiple_un_archivo_malo_no_cancela_los_otros():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.get_client_by_id", return_value={"id": CLIENT_A}), \
         patch("app.dashboard_results.storage.upload_result_pdf", return_value="ruta.pdf"), \
         patch("app.dashboard_results.portal_db.insert_lab_result",
               side_effect=lambda f: {"id": RESULT_ID, **f}) as insert, \
         patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        response = _upload_many(
            client, [(b"esto no es un pdf", "malo.pdf"), (b"%PDF-1.4 bueno", "bueno.pdf")],
            patient_name_0="Firulais", patient_name_1="Michi",
        )
    cuerpo = response.get_data(as_text=True)
    assert insert.call_count == 1
    assert insert.call_args.args[0]["patient_name"] == "Michi"
    assert "malo.pdf" in cuerpo


def test_upload_multiple_publica_todos_si_se_pide_compartir():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.get_client_by_id", return_value={"id": CLIENT_A}), \
         patch("app.dashboard_results.storage.upload_result_pdf", return_value="ruta.pdf"), \
         patch("app.dashboard_results.portal_db.insert_lab_result",
               side_effect=lambda f: {"id": RESULT_ID, **f}), \
         patch("app.dashboard_results._publish_and_notify") as publish, \
         patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        _upload_many(client, [(b"%PDF-1.4 a", "a.pdf"), (b"%PDF-1.4 b", "b.pdf")], publish_now="1")
    assert publish.call_count == 2


# ── Las dos pestañas: informes de A3 y espejo de Anarvet ─────────────────────

INFORME_ESPEJO = {"codigo": "20091939", "fecha_solicitud": "2026-08-25",
                  "nombre_cliente": "Petusos", "mascota": "Mandarino",
                  "nombre_propietario": "Yina Reyes", "especie": "Felino", "raza": "CRIOLLO",
                  "examen_codigos": "H4", "analitos": 22, "analitos_validados": 0,
                  "ultima_validacion": None, "cod_cliente": "1234"}


def test_por_defecto_abre_la_pestana_de_informes_de_a3():
    """El uso diario es cargar y compartir informes; el espejo es consulta."""
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]), \
         patch("app.dashboard_results.db.list_anarvet_informes") as espejo:
        cuerpo = client.get("/resultados").get_data(as_text=True)
    assert "Subir informe de resultados" in cuerpo
    assert "Historial de resultados emitidos" in cuerpo
    espejo.assert_not_called()  # no se consulta el espejo para mostrar la otra pestaña


def test_la_pestana_del_espejo_trae_los_informes_de_anarvet():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.db.list_anarvet_informes",
               return_value=([INFORME_ESPEJO], 1)) as espejo, \
         patch("app.dashboard_results.portal_db.list_lab_results") as historial:
        cuerpo = client.get("/resultados?vista=anarvet").get_data(as_text=True)
    assert "Mandarino" in cuerpo and "Petusos" in cuerpo
    espejo.assert_called_once()
    historial.assert_not_called()  # ni el historial para mostrar el espejo


def test_una_vista_inventada_cae_en_la_de_informes():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        cuerpo = client.get("/resultados?vista=cualquiera").get_data(as_text=True)
    assert "Subir informe de resultados" in cuerpo


def test_el_espejo_pagina_de_a_cincuenta():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.db.list_anarvet_informes",
               return_value=([INFORME_ESPEJO], 120)) as espejo:
        cuerpo = client.get("/resultados?vista=anarvet&page=2").get_data(as_text=True)
    assert espejo.call_args.kwargs == {"page": 2, "per_page": 50}
    assert "120 informe" in cuerpo


def test_una_pagina_invalida_no_rompe_la_pantalla():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.db.list_anarvet_informes",
               return_value=([], 0)) as espejo:
        respuesta = client.get("/resultados?vista=anarvet&page=cero")
    assert respuesta.status_code == 200
    assert espejo.call_args.kwargs["page"] == 1


def test_el_historial_deja_revertir_y_eliminar_sin_ir_a_la_ficha():
    """Compartir con la veterinaria equivocada se corrige donde se subió el informe."""
    client = _get_test_client()
    _login_dashboard(client)
    compartido = {"id": RESULT_ID, "client_id": CLIENT_A, "patient_name": "Rocky",
                  "published": True, "clients": {"clinic_name": "Vet Prueba"}}
    with patch("app.dashboard_results.portal_db.list_lab_results", return_value=[compartido]):
        cuerpo = client.get("/resultados").get_data(as_text=True)
    assert f"/resultados/{RESULT_ID}/dejar-de-compartir" in cuerpo
    assert f"/resultados/{RESULT_ID}/eliminar" in cuerpo
    assert f"/resultados/{RESULT_ID}/publicar" not in cuerpo  # ya está compartido
