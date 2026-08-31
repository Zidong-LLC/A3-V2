"""
Tests unitarios de lógica pura (rules.py) — sin I/O, sin mocks de servicios.
Cubre casos 4 y partes de 1, 2, 9, 10 del bootstrap sección 12.
"""
import pytest
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo

BOG = ZoneInfo("America/Bogota")


def _dt(hour: int, minute: int, weekday_offset: int = 0) -> datetime:
    """Crea un datetime en hora Bogotá para el próximo lunes + offset."""
    from datetime import timedelta
    # Lunes fijo de referencia
    base = date(2026, 4, 27)  # lunes
    d = base + timedelta(days=weekday_offset)
    local = datetime(d.year, d.month, d.day, hour, minute, tzinfo=BOG)
    return local.astimezone(timezone.utc)


# ── Test 4: regla de corte horario ───────────────────────────────────────────

class TestCutoffRule:
    def test_before_cutoff_weekday(self):
        """Solicitud lunes 16:00 → recogida martes."""
        from app.rules import get_scheduled_pickup_date
        now = _dt(16, 0, weekday_offset=0)  # lunes
        result = get_scheduled_pickup_date(now)
        assert result == date(2026, 4, 28)  # martes

    def test_after_cutoff_weekday(self):
        """Solicitud lunes 18:00 → recogida miércoles (saltea martes)."""
        from app.rules import get_scheduled_pickup_date
        now = _dt(18, 0, weekday_offset=0)  # lunes
        result = get_scheduled_pickup_date(now)
        assert result == date(2026, 4, 29)  # miércoles

    def test_before_cutoff_friday(self):
        """Solicitud viernes 16:00 → recogida lunes siguiente."""
        from app.rules import get_scheduled_pickup_date
        now = _dt(16, 0, weekday_offset=4)  # viernes
        result = get_scheduled_pickup_date(now)
        assert result == date(2026, 5, 4)  # lunes siguiente

    def test_after_cutoff_friday(self):
        """Solicitud viernes 18:00 → recogida martes siguiente (salta sábado y domingo)."""
        from app.rules import get_scheduled_pickup_date
        now = _dt(18, 0, weekday_offset=4)  # viernes
        result = get_scheduled_pickup_date(now)
        assert result == date(2026, 5, 5)  # martes siguiente

    def test_exact_cutoff_is_before(self):
        """17:30 exacto cuenta como antes del corte."""
        from app.rules import get_scheduled_pickup_date
        now = _dt(17, 30, weekday_offset=0)  # lunes 17:30
        result = get_scheduled_pickup_date(now)
        assert result == date(2026, 4, 28)  # martes

    def test_before_cutoff_saturday(self):
        """Solicitud sábado 10:00 -> recogida lunes."""
        from app.rules import get_scheduled_pickup_date
        now = _dt(10, 0, weekday_offset=5)  # sábado
        result = get_scheduled_pickup_date(now)
        assert result == date(2026, 5, 4)  # lunes

    def test_after_cutoff_saturday(self):
        """Solicitud sábado 18:00 -> recogida martes."""
        from app.rules import get_scheduled_pickup_date
        now = _dt(18, 0, weekday_offset=5)  # sábado
        result = get_scheduled_pickup_date(now)
        assert result == date(2026, 5, 5)  # martes

    def test_before_cutoff_sunday(self):
        """Solicitud domingo 10:00 -> recogida lunes."""
        from app.rules import get_scheduled_pickup_date
        now = _dt(10, 0, weekday_offset=6)  # domingo
        result = get_scheduled_pickup_date(now)
        assert result == date(2026, 5, 4)  # lunes


# ── Test: INTENT_TO_SERVICE_AREA mapea correctamente ─────────────────────────

class TestIntentMapping:
    def test_all_intents_mapped(self):
        from app.rules import INTENT_TO_SERVICE_AREA
        expected = {"route_scheduling", "results", "accounting", "new_client", "unknown"}
        assert set(INTENT_TO_SERVICE_AREA.keys()) == expected

    def test_values_match_keys(self):
        from app.rules import INTENT_TO_SERVICE_AREA
        for k, v in INTENT_TO_SERVICE_AREA.items():
            assert k == v, f"Se esperaba identidad, pero {k} → {v}"


# ── Test: TERMINAL_PHASES contiene las fases correctas ───────────────────────

class TestTerminalPhases:
    def test_terminal_phases(self):
        from app.rules import TERMINAL_PHASES
        assert "fase_6_cierre" in TERMINAL_PHASES
        assert "fase_7_escalado" in TERMINAL_PHASES
        assert "fase_2_recogida_datos" not in TERMINAL_PHASES


# ── Alerta por tiempo (llamada 4; decision del usuario 2026-08-31) ───────────

def test_recogida_con_fecha_vencida_y_sin_recoger_esta_atrasada():
    from app.rules import pickup_is_overdue

    fila = {"scheduled_pickup_date": "2026-08-30", "status": "assigned"}
    assert pickup_is_overdue(fila, "2026-08-31")


def test_recogida_ya_recogida_o_al_dia_no_alerta():
    from app.rules import pickup_is_overdue

    assert not pickup_is_overdue({"scheduled_pickup_date": "2026-08-30", "status": "on_route"}, "2026-08-31")
    assert not pickup_is_overdue({"scheduled_pickup_date": "2026-08-31", "status": "assigned"}, "2026-08-31")
    assert not pickup_is_overdue({"scheduled_pickup_date": None, "status": "assigned"}, "2026-08-31")
    assert not pickup_is_overdue({"scheduled_pickup_date": "2026-08-30", "status": "in_lab"}, "2026-08-31")
