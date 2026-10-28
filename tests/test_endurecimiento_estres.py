"""Lo que encontraron el estrés y las auditorías previas a la entrega (ERR-187).

Cada test fija un arreglo: rutas sin protección, webhooks que daban 500 o quedaban
abiertos, subidas sin tope, Storage en HTTP/2 compartido, cachés que guardaban un fallo,
lecturas cortadas en 1000 filas y fechas que terminaban en error 500.
"""
import re
import threading
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.main import app
from app.services import db

# Lo único que se puede abrir sin credenciales: pantallas de ingreso/salida y la raíz.
PUBLICAS = {"static", "health", "dashboard.login", "dashboard.logout", "dashboard.root", "portal.login",
            "portal.logout", "portal.home", "dashboard_sistema.login", "dashboard_sistema.logout"}


def _cliente():
    app.config["TESTING"] = True
    return app.test_client()


def _urls():
    for regla in app.url_map.iter_rules():
        if regla.endpoint in PUBLICAS:
            continue
        valores = {arg: str(uuid.uuid4()) for arg in regla.arguments}
        for metodo in sorted(regla.methods - {"HEAD", "OPTIONS"}):
            yield regla.endpoint, metodo, regla.build(valores, append_unknown=False)[1]


@pytest.mark.parametrize("endpoint,metodo,url", list(_urls()))
def test_ninguna_ruta_se_abre_sin_credenciales(endpoint, metodo, url):
    """Barrido de las ~110 rutas: sin sesión ni token, o redirige a un login o rechaza.
    Una ruta nueva sin su decorador de acceso queda pública y este test la marca."""
    with patch("app.main.process_turn") as turno, patch("app.main._debouncer.submit") as encolar:
        r = _cliente().open(url, method=metodo)
    if r.status_code in (301, 302, 303):
        assert "login" in r.headers.get("Location", ""), f"{endpoint} redirige a {r.headers.get('Location')}"
    else:
        assert r.status_code in (400, 401, 403, 404, 405, 503), f"{endpoint} {metodo} respondió {r.status_code}"
    turno.assert_not_called()
    encolar.assert_not_called()


def test_webhook_de_chatwoot_sin_secreto_configurado_no_deja_pasar(monkeypatch):
    monkeypatch.setattr("app.main.CHATWOOT_WEBHOOK_SECRET", "")
    with patch("app.main._debouncer.submit") as encolar:
        r = _cliente().post("/chatwoot/webhook", json={"event": "message_created", "message_type": "incoming",
                                                       "content": "hola", "conversation": {"id": 1}})
    assert r.status_code == 403
    encolar.assert_not_called()


@pytest.mark.parametrize("payload", [[1], "texto", {"message": {"text": "h"}},
                                     {"message": {"text": "h", "chat": "x"}}, {"message": {"chat": {"id": 1}, "text": 5}}])
def test_telegram_con_payload_malformado_responde_200_y_no_procesa(payload):
    with patch("app.main._debouncer.submit") as encolar:
        r = _cliente().post("/webhooks/telegram", json=payload,
                            headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"})
    assert r.status_code == 200
    encolar.assert_not_called()


@pytest.mark.parametrize("payload", [[1], "texto", {"event": "message_created", "message_type": "incoming",
                                                    "content": "hola", "conversation": "x"}])
def test_chatwoot_con_payload_malformado_responde_200_y_no_procesa(monkeypatch, payload):
    monkeypatch.setattr("app.main.CHATWOOT_WEBHOOK_SECRET", "s")
    with patch("app.main._debouncer.submit") as encolar:
        r = _cliente().post("/chatwoot/webhook?token=s", json=payload)
    assert r.status_code == 200
    encolar.assert_not_called()


def test_una_subida_gigante_sin_sesion_se_corta_con_413():
    assert app.config["MAX_CONTENT_LENGTH"] == 64 * 1024 * 1024
    r = _cliente().post("/portal/login", data=b"x" * (65 * 1024 * 1024),
                        content_type="application/x-www-form-urlencoded")
    assert r.status_code == 413


def test_storage_no_usa_http2_compartido():
    """Mismo corte que ERR-176, pero en los PDF de resultados."""
    storage = db._client.storage
    assert storage.session is storage._client
    assert storage.session._transport._pool._http2 is False


def test_si_la_carga_de_razas_falla_el_turno_siguiente_reintenta(monkeypatch):
    from app import breeds

    llamadas = []

    def carga():
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("timeout justo después del deploy")
        return [{"name": "Pastor Alemán", "species": "Canino"}]

    monkeypatch.setattr(breeds, "_fetch_rows", carga)
    breeds._load.cache_clear()
    try:
        assert breeds.resolve_breed("pastor aleman").status == breeds.NONE  # falla, no lanza
        assert breeds.resolve_breed("pastor aleman").status == breeds.EXACT  # reintentó
    finally:
        breeds._load.cache_clear()


def test_limite_de_intentos_del_portal_aguanta_hilos_simultaneos(monkeypatch):
    from app.portal import auth

    auth._login_attempts.clear()
    auth._login_attempts["1.2.3.4"] = auth.deque([0.0] * 10)  # intentos ya vencidos
    errores = []

    def intento():
        try:
            auth._rate_limited("1.2.3.4")
        except Exception as exc:  # noqa: BLE001
            errores.append(exc)

    hilos = [threading.Thread(target=intento) for _ in range(50)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []
    auth._login_attempts.clear()


def _tabla_falsa(total: int):
    filas = [{"id": i} for i in range(total)]
    consulta = MagicMock()
    for metodo in ("select", "order", "eq", "gte"):
        getattr(consulta, metodo).return_value = consulta

    def rango(desde, hasta):
        r = MagicMock()
        r.execute.return_value.data = filas[desde:min(hasta + 1, desde + 1000)]
        return r
    consulta.range.side_effect = rango
    cliente = MagicMock()
    cliente.table.return_value = consulta
    return cliente


def test_motorizados_reciben_todos_los_barrios_no_mil():
    with patch.object(db, "_client", _tabla_falsa(1649)):
        assert len(db.list_territorial_neighborhoods()) == 1649


def test_panel_de_sistema_no_se_corta_en_mil_eventos():
    from app.services import system_db

    with patch.object(system_db, "_client", _tabla_falsa(2300)):
        assert len(system_db.eventos("turn")) == 2300


def test_exportar_facturas_trae_todas_y_no_mil(monkeypatch):
    from app import dashboard

    facturas = [{"number": f"F{i}"} for i in range(1200)]
    monkeypatch.setattr(db, "list_cached_invoices", lambda f, page=1, per_page=25:
                        (facturas[(page - 1) * per_page:page * per_page], len(facturas)))
    filas, total = dashboard._todas_las_facturas({})
    assert len(filas) == total == 1200


def test_portal_ignora_fechas_que_no_son_fechas():
    from app.services import portal_db

    assert portal_db._fecha("2026-10-28") == "2026-10-28"
    for basura in ("x)(", "2026-10-28)", "", None, "28/10/2026"):
        assert portal_db._fecha(basura) is None


def test_datos_del_personal_se_escapan_antes_de_ir_a_innerhtml():
    """XSS almacenado: un motorizado o cliente con nombre `<img onerror=...>` corría código
    en la sesión del administrador (mapa de motorizados, buscador de resultados)."""
    plantillas = Path(__file__).resolve().parents[1] / "app" / "templates"
    resultados = (plantillas / "dashboard_results.html").read_text(encoding="utf-8")
    mapa = (plantillas / "dashboard.html").read_text(encoding="utf-8")
    alta = (plantillas / "new_client.html").read_text(encoding="utf-8")
    assert "'<strong>' + f.nombre" not in resultados
    assert not re.search(r"'<strong>' \+ p\.locality_name", mapa)
    assert "+ n + '</span>'" not in mapa
    assert "${row.courier_name}" not in alta


def test_informes_de_anarvet_se_leen_de_la_vista_materializada_y_caen_a_la_comun():
    """La vista común se corta a los 8 s (ERR-187). Sin la migración 037 aplicada todavía,
    la pantalla no puede quedar rota: cae a la vista de siempre una sola vez."""
    pedidas = []

    def listar(tabla, filters, page, per_page):
        pedidas.append(tabla)
        if tabla == "anarvet_informes_mat":
            raise RuntimeError("{'code': 'PGRST205', 'message': 'Could not find the table'}")
        return [{"codigo": "1"}], 1

    with patch.object(db, "_listar_informes", side_effect=listar), \
         patch.dict(db._TABLA_INFORMES, {"nombre": "anarvet_informes_mat"}):
        assert db.list_anarvet_informes({}) == ([{"codigo": "1"}], 1)
        assert db.list_anarvet_informes({}) == ([{"codigo": "1"}], 1)
    assert pedidas == ["anarvet_informes_mat", "anarvet_informes", "anarvet_informes"]


def test_el_sync_refresca_los_informes_precalculados_cuando_trae_filas(monkeypatch):
    from app import anarvet_sync

    monkeypatch.setattr(anarvet_sync.anarvet, "fetch_report", lambda d, h: [{"x": 1}])
    monkeypatch.setattr(anarvet_sync, "_row_to_mirror", lambda raw: {"dedup_key": "k", "cod_cliente": "7"})
    monkeypatch.setattr(db, "upsert_anarvet_results", lambda lote: len(lote))
    monkeypatch.setattr(db, "list_anarvet_client_map", lambda: [])
    monkeypatch.setattr(db, "register_anarvet_client_codes", lambda codes: None)
    refrescos = []
    monkeypatch.setattr(db, "refrescar_anarvet_informes", lambda: refrescos.append(1))
    anarvet_sync.sync_results("2026-10-27", "2026-10-28")
    assert refrescos == [1]
