"""Sync incremental del espejo Anarvet (Fase 2).

Antes pedía siempre "los últimos 7 días" a ciegas, sin mirar qué tenía ya el espejo:
traía de más cuando estaba al día, y dejaba huecos si nadie apretaba el botón por más de
una semana. Ahora arranca donde terminó lo anterior.
"""
from datetime import date
from unittest.mock import patch

from app import anarvet_sync
from app.anarvet_sync import DEFAULT_SYNC_DAYS, _desde_incremental

HOY = date(2026, 8, 25)


def test_arranca_donde_quedo_el_espejo():
    with patch.object(anarvet_sync.db, "max_anarvet_fecha_solicitud", return_value="2026-08-24"):
        assert _desde_incremental(HOY) == "2026-08-22"  # 24 menos 2 de solapamiento


def test_re_pide_unos_dias_para_las_validaciones_tardias():
    """Un analito puede validarse días después de la solicitud. El upsert por dedup_key
    hace que repetir esos días sea gratis: reescribe, no duplica."""
    with patch.object(anarvet_sync.db, "max_anarvet_fecha_solicitud", return_value="2026-08-20"):
        assert _desde_incremental(HOY) == "2026-08-18"


def test_con_el_espejo_vacio_usa_el_rango_por_defecto():
    with patch.object(anarvet_sync.db, "max_anarvet_fecha_solicitud", return_value=None):
        assert _desde_incremental(HOY) == str(date(2026, 8, 25 - DEFAULT_SYNC_DAYS))


def test_si_la_consulta_falla_no_rompe_el_sync():
    """Mejor sincronizar de más que no sincronizar."""
    with patch.object(anarvet_sync.db, "max_anarvet_fecha_solicitud",
                      side_effect=RuntimeError("supabase caído")):
        assert _desde_incremental(HOY) == str(date(2026, 8, 25 - DEFAULT_SYNC_DAYS))


def test_una_fecha_corrupta_no_rompe_el_sync():
    with patch.object(anarvet_sync.db, "max_anarvet_fecha_solicitud", return_value="ayer"):
        assert _desde_incremental(HOY) == str(date(2026, 8, 25 - DEFAULT_SYNC_DAYS))


def test_nunca_arranca_despues_de_hoy():
    """Si el espejo tuviera una fecha futura, pedir un rango invertido sería un error."""
    with patch.object(anarvet_sync.db, "max_anarvet_fecha_solicitud", return_value="2027-01-01"):
        assert _desde_incremental(HOY) == str(HOY)


# ── Endpoint para el cron ────────────────────────────────────────────────────────

def _client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def test_el_endpoint_del_cron_exige_token(monkeypatch):
    from app import platform_api

    monkeypatch.setattr(platform_api, "PLATFORM_API_TOKEN", "secreto")
    assert _client().post("/api/platform/anarvet/sync").status_code == 401


def test_sin_token_configurado_la_api_queda_cerrada(monkeypatch):
    """Fail-closed: es la regla de esta API desde el hallazgo H1 del QA."""
    from app import platform_api

    monkeypatch.setattr(platform_api, "PLATFORM_API_TOKEN", "")
    assert _client().post("/api/platform/anarvet/sync").status_code == 503


def test_el_cron_sincroniza_y_devuelve_el_resumen(monkeypatch):
    from app import platform_api

    monkeypatch.setattr(platform_api, "PLATFORM_API_TOKEN", "secreto")
    monkeypatch.setattr("app.config.ANARVET_ENABLED", True, raising=False)
    resumen = {"synced": 120, "skipped": 0, "collapsed": 3,
               "range": {"desde": "2026-08-22", "hasta": "2026-08-25"}, "errors": []}
    with patch("app.anarvet_sync.sync_results", return_value=resumen) as sync:
        resp = _client().post("/api/platform/anarvet/sync",
                              headers={"X-Platform-Token": "secreto"})
    assert resp.status_code == 200
    assert resp.get_json()["synced"] == 120
    # Sin cuerpo, sincroniza incremental: no le pasa fechas.
    assert sync.call_args.kwargs == {"desde": None, "hasta": None}


def test_un_sync_con_errores_parciales_avisa_con_207(monkeypatch):
    from app import platform_api

    monkeypatch.setattr(platform_api, "PLATFORM_API_TOKEN", "secreto")
    monkeypatch.setattr("app.config.ANARVET_ENABLED", True, raising=False)
    with patch("app.anarvet_sync.sync_results",
               return_value={"synced": 10, "errors": ["lote 2 falló"]}):
        resp = _client().post("/api/platform/anarvet/sync",
                              headers={"X-Platform-Token": "secreto"})
    assert resp.status_code == 207
    assert resp.get_json()["ok"] is False


def test_anarvet_caido_no_tumba_el_endpoint(monkeypatch):
    from app import platform_api

    monkeypatch.setattr(platform_api, "PLATFORM_API_TOKEN", "secreto")
    monkeypatch.setattr("app.config.ANARVET_ENABLED", True, raising=False)
    with patch("app.anarvet_sync.sync_results", side_effect=RuntimeError("connection refused")):
        resp = _client().post("/api/platform/anarvet/sync",
                              headers={"X-Platform-Token": "secreto"})
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "anarvet_unavailable"
