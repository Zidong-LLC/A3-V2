"""Las horas de las tablas salían en UTC: un pedido de las 10:26 se veía «15:26» (ERR-194).

Supabase guarda los timestamps en UTC; el filtro `fecha_corta` solo recortaba el texto.
Ahora convierte a la hora de Bogotá (también en el portal que ve el cliente).
"""
import pytest

from app.text import short_datetime


@pytest.mark.parametrize("valor, esperado", [
    ("2026-10-29T15:26:03.123456+00:00", "29/10 10:26"),
    ("2026-10-29T03:10:00Z", "28/10 22:10"),          # de madrugada en UTC es el día anterior acá
    ("2026-10-29T10:26:00-05:00", "29/10 10:26"),
    ("2026-10-29T15:26:03", "29/10 15:26"),           # sin zona horaria: se deja como está
    ("2026-10-29", "2026-10-29"),
    ("", "-"),
    (None, "-"),
])
def test_fecha_corta_en_hora_de_bogota(valor, esperado):
    assert short_datetime(valor) == esperado


def test_el_portal_y_el_dashboard_ya_no_recortan_fechas_a_mano():
    from pathlib import Path

    plantillas = Path(__file__).resolve().parents[1] / "app" / "templates"
    a_mano = [p.name for p in plantillas.rglob("*.html") if "[:16] | replace('T'" in p.read_text(encoding="utf-8")]
    assert a_mano == []
