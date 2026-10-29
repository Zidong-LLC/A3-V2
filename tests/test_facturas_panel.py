"""El panel mostraba «$0 este mes»: el cache de Alegra estaba congelado en el 26/08 (ERR-191).

Ahora el cron horario lo refresca (últimos 60 días, en un hilo), las métricas leen solo los
últimos 13 meses ordenados y se guardan 5 minutos para no repetir ~16 consultas por carga.
"""
from datetime import date
from unittest.mock import patch

from app import facturas_panel
from app.facturas_panel import sincronizar_en_segundo_plano as sincronizar_real


def test_desde_cubre_el_anio_y_los_12_meses_del_grafico():
    assert facturas_panel.desde_hoy(date(2026, 10, 29)) == "2025-10-01"
    assert facturas_panel.desde_hoy(date(2026, 1, 15)) == "2025-01-01"


def test_recientes_guarda_cinco_minutos_y_se_descarta_al_sincronizar():
    facturas_panel.invalidar()
    with patch("app.facturas_panel.db.list_all_cached_invoices", return_value=[{"total": 1}]) as leer:
        assert facturas_panel.recientes("total") == [{"total": 1}]
        facturas_panel.recientes("total")
        assert leer.call_count == 1
        assert leer.call_args.kwargs["desde"] == facturas_panel.desde_hoy()
        facturas_panel.invalidar()
        facturas_panel.recientes("total")
        assert leer.call_count == 2
    facturas_panel.invalidar()


def test_la_sync_para_al_pasar_la_fecha_desde():
    paginas = [[{"id": str(i), "date": "2026-10-20"} for i in range(30)],
               [{"id": str(30 + i), "date": "2026-08-01"} for i in range(30)],
               [{"id": str(60 + i), "date": "2026-07-01"} for i in range(30)]]
    from app.dashboard import _sync_invoices_from_alegra

    with patch("app.dashboard.alegra.list_invoices", side_effect=paginas) as listar, \
         patch("app.dashboard._invoice_event_index", return_value={}), \
         patch("app.dashboard.billing.invoice_to_row", side_effect=lambda f, **k: f), \
         patch("app.dashboard._invoice_cache_payload", side_effect=lambda fila, cruda: fila), \
         patch("app.dashboard.db.upsert_invoices_cache", side_effect=len):
        resultado = _sync_invoices_from_alegra(max_pages=10, desde="2026-09-01")

    assert listar.call_count == 2  # la segunda página ya trae agosto: no pide la tercera
    assert resultado == {"synced": 60, "errors": []}


def test_sin_alegra_no_lanza_nada(monkeypatch):
    monkeypatch.setattr("app.config.ALEGRA_ENABLED", False)
    assert sincronizar_real() == "alegra_deshabilitado"


def test_no_se_pisan_dos_sincronizaciones(monkeypatch):
    monkeypatch.setattr("app.config.ALEGRA_ENABLED", True)
    facturas_panel._sync_en_curso.acquire()
    try:
        assert sincronizar_real() == "en_curso"
    finally:
        facturas_panel._sync_en_curso.release()


def test_la_sync_lanzada_pide_los_ultimos_60_dias_y_refresca_el_panel(monkeypatch):
    monkeypatch.setattr("app.config.ALEGRA_ENABLED", True)
    with patch("app.dashboard._sync_invoices_from_alegra", return_value={"synced": 5, "errors": []}) as sync, \
         patch("app.facturas_panel.invalidar") as invalidar, \
         patch("app.facturas_panel.threading.Thread") as hilo:
        assert sincronizar_real() == "lanzada"
        hilo.call_args.kwargs["target"]()  # corre el hilo acá, sin esperar

    assert sync.call_args.kwargs["max_pages"] == 1000
    assert sync.call_args.kwargs["desde"] >= "2026-08-01"
    invalidar.assert_called_once()
    assert not facturas_panel._sync_en_curso.locked()


def test_el_cron_horario_dispara_la_sync_de_facturas(monkeypatch):
    from app.main import app

    monkeypatch.setattr("app.config.ANARVET_ENABLED", False)
    with patch("app.facturas_panel.sincronizar_en_segundo_plano", return_value="lanzada") as sync:
        r = app.test_client().post("/api/platform/anarvet/sync", headers={"X-Platform-Token": "test-platform-token"})

    sync.assert_called_once()
    assert r.get_json()["facturas"] == "lanzada"
