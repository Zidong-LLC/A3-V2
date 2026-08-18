"""Descuentos por volumen editables (Fase 3 plataforma).

Endpoint con el patrón de tests/test_catalog_edit.py (monkeypatch sobre
dash.db) y el cache/fallback de app/pricing.py con providers controlados.
"""
import pytest

import app.dashboard as dash
from app import pricing, rules


@pytest.fixture()
def web(monkeypatch):
    from app.main import app

    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "tester"
    registro = {"replaced": None, "audit": [], "invalidated": 0}
    monkeypatch.setattr(dash.db, "list_discount_tiers", lambda: [{"min_tests": 2, "pct": 0.12}])
    monkeypatch.setattr(
        dash.db, "replace_discount_tiers",
        lambda tiers, updated_by: registro.update(replaced=(tiers, updated_by)) or tiers,
    )
    monkeypatch.setattr(
        dash.db, "log_catalog_change",
        lambda tabla, code, antes, despues, por: registro["audit"].append((tabla, code, antes, despues, por)),
    )
    monkeypatch.setattr(
        dash.pricing, "invalidate_discount_tiers_cache",
        lambda: registro.update(invalidated=registro["invalidated"] + 1),
    )
    return client, registro


def _post(client, tiers):
    return client.post("/api/dashboard/discount-tiers", json={"tiers": tiers})


# ── Endpoint ──────────────────────────────────────────────────────────────────

def test_requires_login():
    from app.main import app

    app.config["TESTING"] = True
    response = app.test_client().post("/api/dashboard/discount-tiers", json={"tiers": []})
    assert response.status_code == 302


def test_valid_tiers_replace_audit_and_invalidate(web):
    client, registro = web
    response = _post(client, [{"min_tests": 2, "pct": 0.10}, {"min_tests": 5, "pct": 0.15}])
    assert response.status_code == 200
    tiers, updated_by = registro["replaced"]
    assert tiers == [{"min_tests": 2, "pct": 0.10}, {"min_tests": 5, "pct": 0.15}]
    assert updated_by == "tester"
    assert registro["audit"][0][0] == "discount_tiers"
    assert registro["invalidated"] == 1


@pytest.mark.parametrize("tiers", [
    [],                                                        # vacío
    [{"min_tests": 1, "pct": 0.1}],                            # mínimo < 2
    [{"min_tests": 2, "pct": 0.95}],                           # pct > 0.9
    [{"min_tests": 2, "pct": "doce"}],                         # pct no numérico
    [{"min_tests": 2, "pct": 0.1}, {"min_tests": 2, "pct": 0.2}],   # mínimo repetido
    [{"min_tests": 5, "pct": 0.1}, {"min_tests": 2, "pct": 0.2}],   # desordenado
    [{"min_tests": 2, "pct": 0.2}, {"min_tests": 5, "pct": 0.1}],   # pct decreciente
])
def test_invalid_tiers_return_400(web, tiers):
    client, registro = web
    assert _post(client, tiers).status_code == 400
    assert registro["replaced"] is None
    assert registro["invalidated"] == 0


def test_db_failure_returns_503(web, monkeypatch):
    client, registro = web

    def boom(tiers, updated_by):
        raise RuntimeError("supabase caído")

    monkeypatch.setattr(dash.db, "replace_discount_tiers", boom)
    assert _post(client, [{"min_tests": 2, "pct": 0.1}]).status_code == 503
    assert registro["invalidated"] == 0


# ── pricing: cache y fallback ────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_pricing_cache():
    pricing.invalidate_discount_tiers_cache()
    yield
    pricing.invalidate_discount_tiers_cache()
    rules.set_discount_tiers_provider(pricing.get_discount_tiers)


def test_pricing_reads_table_and_caches(monkeypatch):
    calls = {"n": 0}

    def fake_list():
        calls["n"] += 1
        return [{"min_tests": 2, "pct": 0.5}]

    from app.services import db

    monkeypatch.setattr(db, "list_discount_tiers", fake_list)
    assert pricing.get_discount_tiers() == [(2, 0.5)]
    assert pricing.get_discount_tiers() == [(2, 0.5)]
    assert calls["n"] == 1  # segunda llamada dentro del TTL: sin query

    pricing.invalidate_discount_tiers_cache()
    pricing.get_discount_tiers()
    assert calls["n"] == 2  # invalidar fuerza la recarga


def test_pricing_falls_back_to_config_when_db_fails(monkeypatch):
    from app.config import DISCOUNT_TIERS
    from app.services import db

    def boom():
        raise RuntimeError("sin red")

    monkeypatch.setattr(db, "list_discount_tiers", boom)
    assert pricing.get_discount_tiers() == list(DISCOUNT_TIERS)


def test_pricing_falls_back_when_table_empty(monkeypatch):
    from app.config import DISCOUNT_TIERS
    from app.services import db

    monkeypatch.setattr(db, "list_discount_tiers", lambda: [])
    assert pricing.get_discount_tiers() == list(DISCOUNT_TIERS)


# ── rules: provider inyectado, firma intacta ─────────────────────────────────

def test_calculate_discount_uses_provider_tiers():
    rules.set_discount_tiers_provider(lambda: [(2, 0.5)])
    try:
        assert rules.calculate_discount(2, 10000) == 5000
    finally:
        rules.set_discount_tiers_provider(pricing.get_discount_tiers)


def test_calculate_discount_without_provider_matches_config():
    rules.set_discount_tiers_provider(None)
    try:
        # Comportamiento histórico: tramo de 2 pruebas = 12%.
        assert rules.calculate_discount(2, 10000) == 1200
    finally:
        rules.set_discount_tiers_provider(pricing.get_discount_tiers)
