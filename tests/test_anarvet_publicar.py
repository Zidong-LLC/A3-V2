"""Publicar un informe de Anarvet en el portal del cliente (Fase 2).

A3 lo pidió el 21/08: que la veterinaria vea sus resultados sin llamar al laboratorio. El
mecanismo de publicación ya existía para los PDFs que el personal sube a mano; lo único
nuevo es convertir el informe del espejo en un archivo.

Lo decide una persona, no el sync: nada llega al cliente sin que alguien lo mire.
"""
from unittest.mock import patch

import pytest

from app import dashboard_anarvet as danarvet
from app.services.pdf import PdfUnavailable

INFORME = [
    {"codigo": "20091534", "fecha_solicitud": "2026-08-24", "cod_cliente": "75",
     "mascota": "Nala", "nombre_propietario": "Andrés Cárdenas",
     "nombre_cliente": "Emergencias Veterinarias", "especie": "Canino", "raza": "GOLDEN",
     "genero": "H", "nacio": "2022-06-24", "examen_cod": "H4", "analito_cod": "002",
     "analito": "Hemoglobina", "resultado": "15.2", "usu_validador": "bact", "fec_val": "2026-08-25"},
]
MAPA = [{"cod_cliente": "75", "client_id": "cli-evi", "nombre_cliente": "Emergencias Veterinarias"}]


@pytest.fixture(autouse=True)
def anarvet_encendido(monkeypatch):
    monkeypatch.setattr(danarvet, "ANARVET_ENABLED", True)


def _client():
    from app.main import app

    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "admin"
    return c


def _publicar(**overrides):
    """Ejecuta la publicación con todo mockeado; `overrides` cambia una pieza."""
    conf = {
        "informe": list(INFORME),
        "mapa": list(MAPA),
        "ya_publicados": [],
        "pdf": b"%PDF-1.4 falso",
        "insert": {"id": "res-1", "client_id": "cli-evi", "patient_name": "Nala",
                   "order_number": "20091534", "exam_name": "Cuadro hemático"},
    }
    conf.update(overrides)
    notificados = []
    with patch.object(danarvet.db, "get_anarvet_informe", return_value=conf["informe"]), \
         patch.object(danarvet.db, "list_anarvet_client_map", return_value=conf["mapa"]), \
         patch("app.services.portal_db.list_lab_results", return_value=conf["ya_publicados"]), \
         patch("app.services.portal_db.insert_lab_result", return_value=conf["insert"]), \
         patch("app.services.storage.upload_result_pdf", return_value="cli-evi/20091534/x.pdf"), \
         patch("app.services.pdf.html_to_pdf", **conf.get("pdf_kwargs", {"return_value": conf["pdf"]})), \
         patch("app.dashboard_results._publish_and_notify", side_effect=notificados.append):
        resp = _client().post("/resultados/anarvet/20091534/2026-08-24/publicar")
    return resp, notificados


def test_publica_y_avisa_al_cliente():
    resp, notificados = _publicar()
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    assert len(notificados) == 1, "el cliente tiene que enterarse"
    assert notificados[0]["id"] == "res-1"


def test_no_publica_si_la_veterinaria_no_esta_emparejada():
    """Sin mapeo no hay dueño: publicarlo sería adivinar de quién es el resultado."""
    resp, notificados = _publicar(mapa=[])
    assert resp.status_code == 409
    assert "emparejada" in resp.get_json()["error"]
    assert not notificados


def test_no_publica_dos_veces_el_mismo_informe():
    resp, notificados = _publicar(ya_publicados=[{"id": "res-previo"}])
    assert resp.status_code == 409
    assert resp.get_json()["result_id"] == "res-previo"
    assert not notificados


def test_sin_generador_de_pdf_explica_que_hacer_en_vez_de_fallar_feo():
    """El personal sigue teniendo el botón de imprimir: se le dice el camino alternativo."""
    resp, notificados = _publicar(pdf_kwargs={"side_effect": PdfUnavailable("no hay navegador")})
    assert resp.status_code == 503
    datos = resp.get_json()
    assert "Imprimir" in datos["accion"]
    assert not notificados


def test_un_informe_inexistente_da_404():
    resp, _ = _publicar(informe=[])
    assert resp.status_code == 404


def test_la_publicacion_pide_login():
    from app.main import app

    app.config["TESTING"] = True
    resp = app.test_client().post("/resultados/anarvet/1/2026-01-01/publicar")
    assert resp.status_code in (301, 302)


def test_guarda_el_codigo_de_anarvet_como_numero_de_orden():
    """Es lo que hace idempotente la publicación sin agregar una columna: los códigos de
    Anarvet son de 8 dígitos y no chocan con los nuestros (A3-2026-XXX)."""
    capturado = {}
    with patch.object(danarvet.db, "get_anarvet_informe", return_value=list(INFORME)), \
         patch.object(danarvet.db, "list_anarvet_client_map", return_value=list(MAPA)), \
         patch("app.services.portal_db.list_lab_results", return_value=[]), \
         patch("app.services.portal_db.insert_lab_result",
               side_effect=lambda d: capturado.update(d) or {"id": "r", "client_id": d["client_id"]}), \
         patch("app.services.storage.upload_result_pdf", return_value="p.pdf"), \
         patch("app.services.pdf.html_to_pdf", return_value=b"%PDF"), \
         patch("app.dashboard_results._publish_and_notify"):
        _client().post("/resultados/anarvet/20091534/2026-08-24/publicar")

    assert capturado["order_number"] == "20091534"
    assert capturado["client_id"] == "cli-evi"
    assert capturado["patient_name"] == "Nala"
    assert "Cuadro hemático" in capturado["exam_name"]   # nombre legible, no el código H4
