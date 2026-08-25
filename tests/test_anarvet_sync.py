"""Espejo Anarvet (Fase 1, decisión 013): mapeo de filas, sync y endpoints.

No tocan la red: fn_reporte_examenes y Supabase se mockean con monkeypatch
(mismo patrón que test_alegra_billing). La validación real contra el servidor
de Anarvet se hace con tools/scripts/anarvet_smoke.py, no aquí.
"""
from datetime import date

import pytest

from app import anarvet_sync
from app.anarvet_sync import _row_to_mirror, sync_results
from app.services.anarvet import AnarvetError


def _fila_reporte(**overrides) -> dict:
    base = {
        "fechasolicitud": date(2026, 8, 19),
        "codigo": "20091064",
        "cod_cliente": "04",
        "nombre_cliente": "Animal Club",
        "nombre_propietario": "David  Victorino ",
        "nombre": "Zoe ",
        "especie": "Canino",
        "raza": "MESTIZO",
        "nacio": date(2025, 8, 19),
        "genero": "H",
        "usu_validador": "KEIDYS REYES RIOS\n",
        "examenes": "H4",
        "analito_cod": "080",
        "analito": "Leucocitos",
        "resultado": "8.94",
        "fec_val": date(2026, 8, 19),
    }
    base.update(overrides)
    return base


# --------------------------- _row_to_mirror ---------------------------

def test_row_to_mirror_renombra_y_normaliza():
    fila = _row_to_mirror(_fila_reporte())
    assert fila["mascota"] == "Zoe"                       # "nombre" renombrada y sin espacios
    assert fila["examen_cod"] == "H4"                     # "examenes" renombrada
    assert fila["usu_validador"] == "KEIDYS REYES RIOS"   # \n colgante fuera
    assert fila["fecha_solicitud"] == "2026-08-19"        # date → ISO para el JSON
    assert fila["fec_val"] == "2026-08-19"
    assert fila["resultado"] == "8.94"
    assert fila["raw"]["nombre"] == "Zoe"


def test_dedup_key_estable_ante_revalidacion():
    """Mismo analito con resultado/fec_val distintos → misma clave (upsert actualiza)."""
    original = _row_to_mirror(_fila_reporte())
    revalidada = _row_to_mirror(_fila_reporte(resultado="9.10", fec_val=date(2026, 8, 21)))
    assert original["dedup_key"] == revalidada["dedup_key"]
    distinta = _row_to_mirror(_fila_reporte(analito_cod="081"))
    assert distinta["dedup_key"] != original["dedup_key"]


def test_fila_sin_componentes_de_clave_se_descarta():
    fila = _row_to_mirror({"resultado": "8.94", "analito": "Leucocitos"})
    assert fila is None


# --------------------------- sync_results ---------------------------

@pytest.fixture
def db_mock(monkeypatch):
    registro = {"upserts": [], "codes": {}}
    monkeypatch.setattr(anarvet_sync.db, "upsert_anarvet_results",
                        lambda rows: registro["upserts"].append(rows) or len(rows))
    monkeypatch.setattr(anarvet_sync.db, "register_anarvet_client_codes",
                        lambda codes: registro["codes"].update(codes) or len(codes))
    monkeypatch.setattr(anarvet_sync.db, "list_anarvet_client_map", lambda status=None: [])
    return registro


def test_sync_cuenta_filas_y_codigos(monkeypatch, db_mock):
    report = [_fila_reporte(), _fila_reporte(analito_cod="081"), _fila_reporte(cod_cliente="403", codigo="X1")]
    monkeypatch.setattr(anarvet_sync.anarvet, "fetch_report", lambda d, h: report)
    r = sync_results("2026-08-19", "2026-08-20")
    assert r["synced"] == 3
    assert r["client_codes_seen"] == 2
    assert r["new_client_codes"] == 2
    assert r["errors"] == []
    assert set(db_mock["codes"]) == {"04", "403"}


def test_sync_colapsa_duplicados_del_mismo_lote(monkeypatch, db_mock):
    """Dos filas con la misma clave en un lote harían fallar el upsert de Postgres:
    se colapsan en memoria (última gana) y se reporta el conteo."""
    report = [_fila_reporte(resultado="8.94"), _fila_reporte(resultado="9.99")]
    monkeypatch.setattr(anarvet_sync.anarvet, "fetch_report", lambda d, h: report)
    r = sync_results("2026-08-19", "2026-08-20")
    assert r["synced"] == 1
    assert r["collapsed"] == 1
    assert db_mock["upserts"][0][0]["resultado"] == "9.99"


def test_sync_acumula_error_de_red_sin_reventar(monkeypatch, db_mock):
    def boom(d, h):
        raise AnarvetError("timeout")
    monkeypatch.setattr(anarvet_sync.anarvet, "fetch_report", boom)
    r = sync_results("2026-08-19", "2026-08-20")
    assert r["synced"] == 0
    assert r["errors"] == ["timeout"]


@pytest.mark.parametrize("desde,hasta", [
    ("19-08-2026", "2026-08-20"),   # formato inválido
    ("2026-08-20", "2026-08-19"),   # rango invertido
    ("2026-01-01", "2026-08-20"),   # más de MAX_RANGE_DAYS
])
def test_sync_rechaza_rangos_invalidos(desde, hasta, db_mock):
    with pytest.raises(ValueError):
        sync_results(desde, hasta)


# --------------------------- Endpoints del dashboard ---------------------------

@pytest.fixture
def client_dashboard():
    from app.main import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["dashboard_authenticated"] = True
            s["dashboard_username"] = "tester"
        yield c


def test_endpoint_sync_flag_apagado_da_400(client_dashboard, monkeypatch):
    import app.dashboard as dash
    monkeypatch.setattr(dash, "ANARVET_ENABLED", False)
    res = client_dashboard.post("/api/dashboard/anarvet/sync", json={})
    assert res.status_code == 400


def test_endpoint_sync_sin_login_redirige():
    from app.main import app

    app.config["TESTING"] = True
    res = app.test_client().post("/api/dashboard/anarvet/sync", json={})
    assert res.status_code == 302


def test_endpoint_sync_happy_path(client_dashboard, monkeypatch):
    import app.dashboard as dash
    monkeypatch.setattr(dash, "ANARVET_ENABLED", True)
    monkeypatch.setattr(dash.anarvet_sync, "sync_results",
                        lambda d, h: {"synced": 5, "errors": [], "range": {"desde": d, "hasta": h}})
    res = client_dashboard.post("/api/dashboard/anarvet/sync", json={"desde": "2026-08-19", "hasta": "2026-08-20"})
    assert res.status_code == 200
    assert res.get_json()["synced"] == 5


def test_endpoint_sync_rango_invalido_da_400(client_dashboard, monkeypatch):
    import app.dashboard as dash

    def rechaza(d, h):
        raise ValueError("Rango invertido")
    monkeypatch.setattr(dash, "ANARVET_ENABLED", True)
    monkeypatch.setattr(dash.anarvet_sync, "sync_results", rechaza)
    res = client_dashboard.post("/api/dashboard/anarvet/sync", json={})
    assert res.status_code == 400


def test_pagina_informes_flag_apagado_da_404(client_dashboard, monkeypatch):
    import app.dashboard_anarvet as danarvet
    monkeypatch.setattr(danarvet, "ANARVET_ENABLED", False)
    assert client_dashboard.get("/resultados/anarvet").status_code == 404


def test_pagina_informes_lista_y_detalle(client_dashboard, monkeypatch):
    import app.dashboard_anarvet as danarvet
    informe = {
        "codigo": "X1", "fecha_solicitud": "2026-08-19", "cod_cliente": "04",
        "nombre_cliente": "Animal Club", "nombre_propietario": "David", "mascota": "Zoe",
        "especie": "Canino", "raza": "MESTIZO", "genero": "H", "analitos": 2,
        "examenes": 1, "examen_codigos": "H4", "ultima_validacion": "2026-08-19",
    }
    analito = {**_fila_reporte(), "mascota": "Zoe", "examen_cod": "H4",
               "fecha_solicitud": "2026-08-19", "fec_val": "2026-08-19", "nacio": "2025-08-19"}
    monkeypatch.setattr(danarvet, "ANARVET_ENABLED", True)
    monkeypatch.setattr(danarvet.db, "list_anarvet_informes", lambda f, page, per_page: ([informe], 1))
    monkeypatch.setattr(danarvet.db, "get_anarvet_informe", lambda c, f: [analito] if c == "X1" else [])

    res = client_dashboard.get("/resultados/anarvet")
    assert res.status_code == 200
    assert "Zoe" in res.get_data(as_text=True)

    res = client_dashboard.get("/resultados/anarvet/X1/2026-08-19")
    assert res.status_code == 200
    assert "Examen H4" in res.get_data(as_text=True)

    assert client_dashboard.get("/resultados/anarvet/NOEXISTE/2026-08-19").status_code == 404


def test_endpoint_assign_manual_y_none(client_dashboard, monkeypatch):
    import app.dashboard as dash
    llamadas = []
    monkeypatch.setattr(dash, "ANARVET_ENABLED", True)
    monkeypatch.setattr(dash.db, "get_client_by_id", lambda cid: {"id": cid} if cid == "uuid-ok" else None)
    monkeypatch.setattr(dash.db, "assign_anarvet_client", lambda cod, cid, src: llamadas.append((cod, cid, src)))

    res = client_dashboard.post("/api/dashboard/anarvet/clients/04/assign", json={"client_id": "uuid-ok"})
    assert res.status_code == 200
    res = client_dashboard.post("/api/dashboard/anarvet/clients/99/assign", json={"client_id": None})
    assert res.status_code == 200
    res = client_dashboard.post("/api/dashboard/anarvet/clients/04/assign", json={"client_id": "no-existe"})
    assert res.status_code == 404
    assert llamadas == [("04", "uuid-ok", "manual"), ("99", None, "none")]
