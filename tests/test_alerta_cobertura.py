"""«Cobertura pendiente» dice QUÉ zonas y QUÉ clientes (reporte del usuario, 2026-10-29).

Antes la alerta decía «5 localidad(es) con clientes sin motorizado» y no había forma de
saber cuáles. Ahora nombra las zonas y lista los clientes activos sin motorizado propio,
cada uno con enlace a su ficha, más un acceso a Motorizados para asignar la zona.
"""
from unittest.mock import patch

from app.dashboard import _alerta_cobertura, _build_motorizados_context


def _fila(code, nombre, clientes, asignada=False):
    return {"locality_code": code, "locality_name": nombre, "clients_count": clientes, "is_assigned": asignada}


def _cliente(cid, nombre, activo=True, courier=None):
    return {"id": cid, "clinic_name": nombre, "is_active": activo,
            "client_courier_assignment": [{"courier_id": courier}] if courier else []}


def test_nombra_las_zonas_de_mayor_a_menor_y_lista_solo_los_que_faltan():
    filas = [_fila("cota", "Cota", 2), _fila("soacha", "Soacha", 3),
             _fila("kennedy", "Kennedy", 9, asignada=True), _fila("funza", "Funza", 0)]
    por_zona = {
        "soacha": [_cliente("s1", "Con motorizado", courier="c1"), _cliente("s2", "Sin motorizado"),
                   _cliente("s3", "Inactiva", activo=False)],
        "cota": [_cliente("c1", "Talento Canes")],
        "kennedy": [_cliente("k1", "Cubierta por la zona")],
    }

    alerta = _alerta_cobertura(filas, por_zona)

    assert alerta["detail"] == "Soacha (3 clientes) y Cota (2 clientes) no tienen motorizado asignado a la zona."
    assert [c["id"] for c in alerta["clientes"]] == ["s2", "c1"]
    assert alerta["clientes"][0] == {"id": "s2", "nombre": "Sin motorizado", "zona": "Soacha"}
    assert alerta["accion"]["url"] == "/motorizados"


def test_una_sola_zona_en_singular():
    alerta = _alerta_cobertura([_fila("funza", "Funza", 1)], {})

    assert alerta["detail"] == "Funza (1 cliente) no tiene motorizado asignado a la zona."
    assert alerta["clientes"] == []


def test_el_contexto_de_motorizados_arma_la_alerta_con_los_clientes_del_municipio():
    clientes = [
        {"id": "a", "clinic_name": "Wavet", "city": "Soacha", "is_active": True, "client_courier_assignment": []},
        {"id": "b", "clinic_name": "Vet propia", "city": "Soacha", "is_active": True,
         "client_courier_assignment": [{"courier_id": "c9"}]},
    ]
    soacha = {"code": "soacha", "name": "Soacha", "is_active": True, "lat": 4.58, "lng": -74.21}
    with patch("app.dashboard.db.list_couriers", return_value=[]), \
         patch("app.dashboard.db.list_courier_locality_coverage", return_value=[]), \
         patch("app.dashboard.db.list_territorial_zones", return_value=[]), \
         patch("app.dashboard.db.list_territorial_neighborhoods", return_value=[]), \
         patch("app.dashboard.maestros_db.list_municipios", return_value=[soacha]):
        contexto = _build_motorizados_context(clientes)

    alerta = next(a for a in contexto["motorizados_alerts"] if a["title"] == "Cobertura pendiente")
    assert "Soacha (2 clientes)" in alerta["detail"]
    assert alerta["clientes"] == [{"id": "a", "nombre": "Wavet", "zona": "Soacha"}]


def test_la_plantilla_enlaza_cada_ficha_y_escapa_el_nombre():
    from app.main import app

    alerta = {"level": "warning", "title": "Cobertura pendiente", "detail": "Soacha (1 cliente) no tiene…",
              "clientes": [{"id": "abc-123", "nombre": "<b>Wavet</b>", "zona": "Soacha"}],
              "accion": {"texto": "Asignar la zona en Motorizados", "url": "/motorizados"}}
    with app.test_request_context():
        html = app.jinja_env.get_template("_alerta_operativa.html").render(alert=alerta)

    assert 'href="/clientes/abc-123"' in html
    assert 'href="/motorizados"' in html
    assert "&lt;b&gt;Wavet&lt;/b&gt;" in html and "<b>Wavet</b>" not in html


def test_las_demas_alertas_se_ven_como_antes():
    from app.main import app

    with app.test_request_context():
        html = app.jinja_env.get_template("_alerta_operativa.html").render(
            alert={"level": "error", "title": "Sin motorizados", "detail": "no hay activos."})

    assert "<strong>Sin motorizados:</strong> no hay activos." in html
    assert "<details" not in html and "<a " not in html
