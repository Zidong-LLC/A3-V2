"""Informe de resultados imprimible — Anarvet Fase 2 (pedido de A3, llamada del 21/08).

*"Si un cliente llama por teléfono y no tiene acceso, que la persona humana lo descargue
y se lo envíe por WhatsApp."*

Anarvet no entrega PDF (decisión 013): el documento lo componemos nosotros con los datos
del espejo. Se imprime desde el navegador, igual que la orden de servicio.
"""
from unittest.mock import patch

import pytest

from app import dashboard_anarvet as danarvet
from app.dashboard_anarvet import _edad, _es_observacion


@pytest.fixture(autouse=True)
def anarvet_encendido(monkeypatch):
    """conftest deja el flag en false (para que /health y el sync no toquen Anarvet);
    esta sección solo existe con el flag encendido."""
    monkeypatch.setattr(danarvet, "ANARVET_ENABLED", True)

INFORME = [
    {"codigo": "20090826", "fecha_solicitud": "2026-08-18", "mascota": "Chimuela",
     "especie": "Felino", "raza": "MESTIZO", "genero": "H", "nacio": "2020-02-18",
     "nombre_propietario": "María Espinosa", "nombre_cliente": "Dra. Marisol Sánchez",
     "examen_cod": "H4", "analito_cod": "001", "analito": "Hemoglobina",
     "resultado": "13.8", "usu_validador": "bacterióloga", "fec_val": "2026-08-18"},
    {"codigo": "20090826", "fecha_solicitud": "2026-08-18", "mascota": "Chimuela",
     "especie": "Felino", "raza": "MESTIZO", "genero": "H", "nacio": "2020-02-18",
     "nombre_propietario": "María Espinosa", "nombre_cliente": "Dra. Marisol Sánchez",
     "examen_cod": "URE", "analito_cod": "004", "analito": "UREA",
     "resultado": "147.08", "usu_validador": "bacterióloga", "fec_val": "2026-08-18"},
    {"codigo": "20090826", "fecha_solicitud": "2026-08-18", "mascota": "Chimuela",
     "especie": "Felino", "raza": "MESTIZO", "genero": "H", "nacio": "2020-02-18",
     "nombre_propietario": "María Espinosa", "nombre_cliente": "Dra. Marisol Sánchez",
     "examen_cod": "URE", "analito_cod": "999", "analito": "OBSERVACIONES",
     "resultado": "Correlacionar con el cuadro clínico.", "usu_validador": "bacterióloga",
     "fec_val": "2026-08-18"},
]


def _client_logueado():
    from app.main import app

    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "admin"
    return c


def _html():
    c = _client_logueado()
    with patch("app.dashboard_anarvet.db.get_anarvet_informe", return_value=list(INFORME)):
        resp = c.get("/resultados/anarvet/20090826/2026-08-18/imprimir")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_pide_login(monkeypatch):
    from app.main import app

    app.config["TESTING"] = True
    resp = app.test_client().get("/resultados/anarvet/20090826/2026-08-18/imprimir")
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


def test_informe_inexistente_da_404():
    c = _client_logueado()
    with patch("app.dashboard_anarvet.db.get_anarvet_informe", return_value=[]):
        assert c.get("/resultados/anarvet/nada/2026-01-01/imprimir").status_code == 404


def test_el_documento_identifica_paciente_y_solicitante():
    html = _html()
    assert "Chimuela" in html and "Felino" in html
    assert "María Espinosa" in html          # propietario
    assert "Dra. Marisol Sánchez" in html    # veterinaria solicitante
    assert "20090826" in html                # número de informe
    assert "A3 Laboratorio" in html


def test_los_examenes_salen_con_nombre_legible():
    """Anarvet solo entrega el código corto ('H4'); el documento muestra qué es.
    Cuando el analito ya se llama igual que su examen ('UREA' en el examen URE) no se
    repite: la línea diría 'UREA · Urea'."""
    html = _html()
    assert "Cuadro hemático" in html      # contexto del analito Hemoglobina, del examen H4
    assert "UREA · Urea" not in html


def test_un_examen_de_un_solo_valor_nombra_lo_que_se_midio():
    """Con un analito suelto, el documento dice 'Hemoglobina 13.8' y deja el examen como
    contexto. Titularlo 'Cuadro hemático 13.8' haría pasar el valor de un analito por el
    resultado de todo el examen."""
    html = _html()
    assert "Otros exámenes" in html
    assert "Hemoglobina" in html and "13.8" in html
    assert "UREA" in html and "147.08" in html


def test_la_observacion_no_se_muestra_como_un_resultado_medido():
    """El reporte mezcla el comentario del profesional entre los analitos, como una fila
    más. En el documento va aparte: no es un valor."""
    html = _html()
    assert "Correlacionar con el cuadro clínico." in html
    assert "Observaciones del laboratorio" in html
    # Y no queda como fila de la tabla de resultados.
    assert "<td>OBSERVACIONES</td>" not in html


def test_firma_al_validador_real_cuando_existe():
    html = _html()
    assert "bacterióloga" in html
    assert "Profesional responsable" not in html


def test_sin_validador_la_firma_queda_generica():
    sin_validar = [dict(f, usu_validador=None, fec_val=None) for f in INFORME]
    c = _client_logueado()
    with patch("app.dashboard_anarvet.db.get_anarvet_informe", return_value=sin_validar):
        html = c.get("/resultados/anarvet/20090826/2026-08-18/imprimir").get_data(as_text=True)
    assert "Profesional responsable" in html


def test_edad_al_momento_de_la_solicitud():
    assert _edad("2020-02-18", "2026-08-18") == "6 años y 6 meses"
    assert _edad("2026-05-18", "2026-08-18") == "3 meses"
    assert _edad("2025-08-18", "2026-08-18") == "1 año"
    # Sin fecha de nacimiento no se inventa una edad.
    assert _edad(None, "2026-08-18") == ""
    assert _edad("2026-12-01", "2026-08-18") == ""


def test_deteccion_de_observaciones():
    assert _es_observacion({"analito": "OBSERVACIONES"})
    assert _es_observacion({"analito": " comentario "})
    assert not _es_observacion({"analito": "Hemoglobina"})


def test_no_repite_el_nombre_cuando_analito_y_examen_dicen_lo_mismo():
    """'BUN · Nitrógeno ureico (BUN)' y 'ALT · ALT (GPT)' dicen dos veces lo mismo."""
    from app.dashboard_anarvet import _contexto

    assert _contexto("BUN", "Nitrógeno ureico (BUN)") == ""
    assert _contexto("ALT", "ALT (GPT)") == ""
    assert _contexto("Creatinina", "Creatinina") == ""
    # Cuando el examen SÍ aporta contexto, se conserva:
    assert _contexto("Hemoglobina", "Cuadro hemático") == "Cuadro hemático"
