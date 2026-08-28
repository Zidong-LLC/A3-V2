"""Equipo de motorizados: crear, renombrar, dar de baja y el color que se guarda.

El color antes solo repintaba el cuadrito en pantalla y se perdía al recargar; no había
forma de crear un motorizado ni de darlo de baja desde la plataforma.
"""
from unittest.mock import patch

COURIER = {"id": "c-1", "name": "Javier", "phone": "3001234567",
           "availability": "available", "is_active": True, "color": ""}


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"


def _post(ruta, cuerpo):
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.db.update_courier", return_value=True) as editar, \
         patch("app.dashboard.db.create_courier", return_value={"id": "c-9", **COURIER}) as crear:
        respuesta = client.post(ruta, json=cuerpo)
    return respuesta, editar, crear


# ── Edición ──────────────────────────────────────────────────────────────────

def test_el_color_se_guarda():
    respuesta, editar, _ = _post("/api/dashboard/courier", {"courier_id": "c-1", "color": "#7A0D20"})
    assert respuesta.status_code == 200
    editar.assert_called_once_with("c-1", {"color": "#7a0d20"})


def test_un_color_que_no_es_color_se_rechaza():
    respuesta, editar, _ = _post("/api/dashboard/courier", {"courier_id": "c-1", "color": "rojo"})
    assert respuesta.status_code == 400
    editar.assert_not_called()


def test_se_puede_renombrar():
    respuesta, editar, _ = _post("/api/dashboard/courier", {"courier_id": "c-1", "name": "  Javier Perez "})
    assert respuesta.status_code == 200
    editar.assert_called_once_with("c-1", {"name": "Javier Perez"})


def test_el_nombre_no_puede_quedar_vacio():
    respuesta, editar, _ = _post("/api/dashboard/courier", {"courier_id": "c-1", "name": "   "})
    assert respuesta.status_code == 400
    editar.assert_not_called()


def test_se_puede_dar_de_baja_y_reactivar():
    respuesta, editar, _ = _post("/api/dashboard/courier", {"courier_id": "c-1", "is_active": False})
    assert respuesta.status_code == 200
    editar.assert_called_once_with("c-1", {"is_active": False})


def test_una_disponibilidad_inventada_se_rechaza():
    respuesta, editar, _ = _post("/api/dashboard/courier", {"courier_id": "c-1", "availability": "de vacaciones"})
    assert respuesta.status_code == 400
    editar.assert_not_called()


def test_los_campos_que_no_son_editables_no_viajan():
    """El id, las fechas o cualquier columna nueva no se tocan desde la request."""
    respuesta, editar, _ = _post("/api/dashboard/courier",
                                 {"courier_id": "c-1", "phone": "3009999999", "id": "otro", "created_at": "2020-01-01"})
    assert respuesta.status_code == 200
    editar.assert_called_once_with("c-1", {"phone": "3009999999"})


def test_sin_courier_id_no_hace_nada():
    respuesta, editar, _ = _post("/api/dashboard/courier", {"phone": "3001112222"})
    assert respuesta.status_code == 400
    editar.assert_not_called()


# ── Alta ─────────────────────────────────────────────────────────────────────

def test_se_crea_un_motorizado():
    respuesta, _, crear = _post("/api/dashboard/courier-create",
                                {"name": "Nuevo Motorizado", "phone": "3005556666", "color": "#123456"})
    assert respuesta.status_code == 200
    crear.assert_called_once_with({"name": "Nuevo Motorizado", "phone": "3005556666", "color": "#123456"})


def test_no_se_crea_sin_nombre():
    respuesta, _, crear = _post("/api/dashboard/courier-create", {"phone": "3005556666"})
    assert respuesta.status_code == 400
    crear.assert_not_called()


# ── Lo que guarda la base ────────────────────────────────────────────────────

def test_update_courier_descarta_lo_que_no_esta_permitido():
    from app.services import db as dbs
    from unittest.mock import MagicMock

    cliente = MagicMock()
    with patch.object(dbs, "_client", cliente):
        dbs.update_courier("c-1", {"name": "Ana", "id": "otro", "secreto": 1})
    enviado = cliente.table.return_value.update.call_args.args[0]
    assert enviado == {"name": "Ana"}


def test_create_courier_nace_activo_y_exige_nombre():
    from app.services import db as dbs
    from unittest.mock import MagicMock

    cliente = MagicMock()
    with patch.object(dbs, "_client", cliente):
        assert dbs.create_courier({"phone": "3001112222"}) is None       # sin nombre
        dbs.create_courier({"name": "Ana", "phone": "3001112222"})
    enviado = cliente.table.return_value.insert.call_args.args[0]
    assert enviado["is_active"] is True
    assert enviado["availability"] == "available"


# ── La pantalla ──────────────────────────────────────────────────────────────

def _contexto(**extra):
    from tests.test_dashboard import _base_context

    return _base_context(client_type_options={}, vat_regime_options={},
                         motorizados_summary={}, **extra)


def test_la_pantalla_trae_tarjetas_y_el_boton_de_alta():
    client = _get_test_client()
    _login(client)
    filas = [{**COURIER, "source": "db", "coverage_count": 2, "clients_count_from_coverage": 10,
              "localities_text": "Kennedy, Bosa", "zone_number": 3, "color": "#7a0d20",
              "color_guardado": True, "is_active": True}]
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto(couriers_rows=filas)):
        cuerpo = client.get("/motorizados").get_data(as_text=True)
    assert "courier-cards" in cuerpo
    assert "data-courier-new" in cuerpo
    assert 'data-courier-field="color"' in cuerpo
    assert 'data-courier-field="is_active"' in cuerpo
    assert "Kennedy, Bosa" in cuerpo


def test_avisa_cuando_tiene_zona_pero_ninguna_localidad():
    """Es lo que hacía figurar a un motorizado con cero clientes teniendo su zona."""
    client = _get_test_client()
    _login(client)
    filas = [{**COURIER, "source": "db", "coverage_count": 0, "clients_count_from_coverage": 0,
              "localities_text": "Sin zonas asignadas", "zone_number": 8, "color": "#7a0d20",
              "color_guardado": False, "is_active": True}]
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto(couriers_rows=filas)):
        cuerpo = client.get("/motorizados").get_data(as_text=True)
    assert "ninguna localidad asignada" in cuerpo
