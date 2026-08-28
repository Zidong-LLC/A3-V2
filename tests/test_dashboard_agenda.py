"""Agenda de recogidas: grilla semanal por motorizado, reasignación y reprogramación."""
from datetime import date, timedelta
from unittest.mock import patch

from app.dashboard_agenda import SIN_ASIGNAR, _lunes, armar_grilla

COURIER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COURIER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
COURIERS = [{"id": COURIER_A, "name": "Javier"}, {"id": COURIER_B, "name": "Jeeferson"}]
SEMANA = [date(2026, 8, 24) + timedelta(days=i) for i in range(6)]  # lunes 24 a sábado 29


def _pickup(dia="2026-08-24", courier=COURIER_A, **extra):
    base = {"id": "r-1", "order_number": "A3-00042", "scheduled_pickup_date": dia,
            "assigned_courier_id": courier, "clients": {"clinic_name": "Vet Prueba"},
            "couriers": {"name": "Javier"}, "status": "assigned"}
    base.update(extra)
    return base


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"


# ── La semana que se muestra ─────────────────────────────────────────────────

def test_lunes_de_la_semana_de_una_fecha_cualquiera():
    assert _lunes("2026-08-27") == date(2026, 8, 24)
    assert _lunes("2026-08-24") == date(2026, 8, 24)


def test_sin_fecha_valida_cae_en_la_semana_en_curso():
    hoy = date.today()
    assert _lunes(None) == hoy - timedelta(days=hoy.weekday())
    assert _lunes("no es fecha") == hoy - timedelta(days=hoy.weekday())


# ── La grilla ────────────────────────────────────────────────────────────────

def test_cada_recogida_cae_en_su_motorizado_y_su_dia():
    filas = armar_grilla(
        [_pickup("2026-08-24", COURIER_A), _pickup("2026-08-26", COURIER_B, id="r-2")],
        COURIERS, SEMANA,
    )
    javier = next(f for f in filas if f["id"] == COURIER_A)
    jeeferson = next(f for f in filas if f["id"] == COURIER_B)
    assert len(javier["dias"]["2026-08-24"]) == 1
    assert javier["total"] == 1
    assert len(jeeferson["dias"]["2026-08-26"]) == 1


def test_los_motorizados_sin_recogidas_igual_aparecen():
    filas = armar_grilla([], COURIERS, SEMANA)
    assert [f["nombre"] for f in filas] == ["Javier", "Jeeferson", "Sin asignar"]
    assert all(f["total"] == 0 for f in filas)


def test_una_recogida_sin_motorizado_va_a_la_fila_sin_asignar():
    filas = armar_grilla([_pickup(courier=None)], COURIERS, SEMANA)
    sin_asignar = next(f for f in filas if f["id"] == SIN_ASIGNAR)
    assert sin_asignar["total"] == 1


def test_un_motorizado_inactivo_no_esconde_su_carga():
    """Si la recogida quedó con un motorizado que ya no está activo, se ve igual:
    es justamente la que hay que reasignar."""
    filas = armar_grilla([_pickup(courier="viejo-id")], COURIERS, SEMANA)
    fila = next(f for f in filas if f["id"] == "viejo-id")
    assert fila["total"] == 1
    assert filas[-1]["id"] == SIN_ASIGNAR  # la de sin asignar sigue al final


def test_una_recogida_de_otra_semana_no_entra_en_la_grilla():
    filas = armar_grilla([_pickup("2026-09-07")], COURIERS, SEMANA)
    assert all(f["total"] == 0 for f in filas)


# ── La página ────────────────────────────────────────────────────────────────

def test_la_agenda_exige_sesion_del_dashboard():
    response = _get_test_client().get("/agenda")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_la_agenda_muestra_la_semana_pedida_con_sus_recogidas():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard_agenda.db.list_pickups_between", return_value=[_pickup()]) as consulta, \
         patch("app.dashboard_agenda.db.list_active_couriers", return_value=COURIERS):
        response = client.get("/agenda?semana=2026-08-27")
    cuerpo = response.get_data(as_text=True)
    assert response.status_code == 200
    # La semana del 27 de agosto de 2026 va del lunes 24 al domingo 30.
    consulta.assert_called_once_with("2026-08-24", "2026-08-30")
    assert "Vet Prueba" in cuerpo
    assert "Javier" in cuerpo and "Jeeferson" in cuerpo


def test_la_semana_vacia_lo_dice_en_vez_de_quedar_en_blanco():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard_agenda.db.list_pickups_between", return_value=[]), \
         patch("app.dashboard_agenda.db.list_active_couriers", return_value=COURIERS):
        cuerpo = client.get("/agenda").get_data(as_text=True)
    assert "No hay recogidas programadas" in cuerpo


def test_la_agenda_muestra_el_color_de_cada_motorizado():
    """El color elegido en Motorizados identifica al mismo mensajero en toda la
    plataforma: mapa de cobertura y agenda."""
    filas = armar_grilla([], [{"id": COURIER_A, "name": "Javier", "color": "#0e7490"},
                              {"id": COURIER_B, "name": "Jeeferson", "color": ""}], SEMANA)
    javier = next(f for f in filas if f["id"] == COURIER_A)
    jeeferson = next(f for f in filas if f["id"] == COURIER_B)
    assert javier["color"] == "#0e7490"
    assert jeeferson["color"] == ""          # sin color propio no se pinta nada
    assert filas[-1]["color"] == ""          # la fila de "sin asignar" tampoco
