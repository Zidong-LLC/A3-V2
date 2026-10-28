"""Supabase corta cada request en 1000 filas: las lecturas grandes tienen que paginar."""
from unittest.mock import MagicMock, patch

from app.services import db


def _tabla_falsa(total: int, columna: str = "n"):
    """Consulta encadenable que respeta .range() como PostgREST, con tope de 1000."""
    filas = [{columna: i, "cod_cliente": str(i % 3)} for i in range(total)]
    consulta = MagicMock()
    consulta.select.return_value = consulta
    consulta.order.return_value = consulta

    def rango(desde, hasta):
        resultado = MagicMock()
        resultado.execute.return_value.data = filas[desde:min(hasta + 1, desde + 1000)]
        return resultado
    consulta.range.side_effect = rango
    cliente = MagicMock()
    cliente.table.return_value = consulta
    return cliente, consulta


def test_fetch_rows_trae_mas_de_mil_y_en_orden_cronologico():
    cliente, consulta = _tabla_falsa(2500)
    with patch.object(db, "_client", cliente):
        filas = db.fetch_rows("request_events", "n", 4000, order="created_at")
    assert len(filas) == 2500
    consulta.order.assert_called_with("created_at", desc=True)
    assert filas[0]["n"] == 2499  # la consulta viene de nuevo a viejo y se da vuelta


def test_conteo_de_informes_de_anarvet_lo_agrupa_la_base():
    """Paginar la vista daba statement timeout con 271.000 analitos (ERR-187): la
    función de la migración 037 devuelve ya agrupado, en una sola consulta."""
    cliente = MagicMock()
    cliente.rpc.return_value.execute.return_value.data = [
        {"cod_cliente": "907", "informes": 2400}, {"cod_cliente": 842, "informes": 93}]
    with patch.object(db, "_client", cliente):
        assert db.count_anarvet_informes_por_cliente() == {"907": 2400, "842": 93}
    cliente.rpc.assert_called_once_with("anarvet_informes_por_cliente")
