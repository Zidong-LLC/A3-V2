"""Panel de sistema (/sistema, 2026-10-26): acceso aparte de la plataforma, métricas puras y
registro de eventos desde los avisos, el modelo y los turnos."""
from unittest.mock import MagicMock, patch

import pytest

from app import alerts, sistema
from app.main import app
from app.services import ai, system_db

DATOS = {"salud": {"supabase": {"status": "ok", "latency_ms": 120}, "chatwoot": {"status": "error", "error": "caído"}},
         "errores": {"total": 1, "por_componente": {"openai": 1}, "por_dia": {"26/10": 1},
                     "ultimos": [{"created_at": "2026-10-26T10:00:00", "component": "openai", "message": "APIError: 429",
                                  "context": "turno", "details": {"rastro": ["app/agent.py:1"]}}]},
         "turnos": {"total": 3, "fallidos": 1, "p50_s": 12.0, "p95_s": 20.0, "por_canal": {"telegram": 3}, "chats": 2},
         "llm": {"llamadas": 4, "tokens_entrada": 12000, "tokens_salida": 800, "tokens_por_dia": {"26/10": 12800}},
         "conversaciones": {"conversaciones_7d": 2, "activas_24h": 1, "por_canal": {"telegram": 2}, "por_fase": {},
                            "escaladas": {}, "bloqueadas": 0, "mensajes_7d": 9, "mensajes_cliente_7d": 5,
                            "mensajes_por_dia": {}, "ordenes_7d": 1, "ordenes_por_canal": {"telegram": 1}},
         "traspaso": [{"clave": "render", "nombre": "Render (servidor)", "estado": "activo", "detalle": "plan standard",
                       "usd": 25.0, "fuente": "plan leído por la API de Render", "manual": False},
                      {"clave": "chatwoot", "nombre": "Chatwoot (VPS / EasyPanel)", "estado": "activo", "detalle": "",
                       "usd": 0.0, "fuente": "cargado a mano", "manual": True, "nota": ""}],
         "openai": {"disponible": False, "motivo": "Falta OPENAI_ADMIN_KEY"}, "total_mes": 25.0, "dias": 7}


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr("app.dashboard_sistema._datos", lambda: DATOS)
    return app.test_client()


def test_el_panel_tiene_su_propio_ingreso_y_no_es_la_plataforma(client):
    assert client.get("/sistema").status_code == 302  # sin sesión del panel → a su login
    with client.session_transaction() as s:  # un admin de la plataforma tampoco entra
        s["dashboard_authenticated"], s["dashboard_role"] = True, "administrador"
    assert client.get("/sistema").headers["Location"].endswith("/sistema/login")
    assert client.post("/sistema/login", data={"username": "dev", "password": "mala"}).status_code == 200
    r = client.post("/sistema/login", data={"username": "dev", "password": "test-sistema"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/sistema")
    html = client.get("/sistema").get_data(as_text=True)
    assert "APIError: 429" in html and "Turnos fallidos" in html and "USD 25.00" in html
    assert "Servicios que se traspasan" in html and 'name="usd_chatwoot"' in html and 'name="usd_render"' not in html
    assert "menu-link" not in html  # no lleva el menú del CRM
    assert client.get("/sistema/logout").status_code == 302 and client.get("/sistema").status_code == 302


def test_el_menu_de_la_plataforma_no_muestra_sistema(client, monkeypatch):
    monkeypatch.setattr("app.services.users_db.list_users", lambda: [])
    with client.session_transaction() as s:
        s["dashboard_authenticated"], s["dashboard_role"] = True, "administrador"
    assert "Sistema" not in client.get("/usuarios").get_data(as_text=True).split("menu-list")[1].split("</nav>")[0]


def test_el_json_acepta_la_sesion_del_panel_o_el_token(client):
    assert client.get("/api/sistema/estado").status_code == 401
    assert client.get("/api/sistema/estado", headers={"X-Platform-Token": "test-platform-token"}).get_json()["turnos"]["total"] == 3
    with client.session_transaction() as s:
        s["sistema_authenticated"] = True
    assert client.get("/api/sistema/estado").status_code == 200


def test_sin_clave_configurada_el_panel_queda_cerrado(client, monkeypatch):
    monkeypatch.setattr("app.dashboard_sistema.SISTEMA_PASSWORD", "")
    assert client.get("/sistema/login").status_code == 503
    assert client.post("/sistema/login", data={"username": "dev", "password": ""}).status_code == 503


def test_cinco_claves_malas_bloquean_el_ingreso_al_panel(client):
    for _ in range(5):
        client.post("/sistema/login", data={"username": "dev", "password": "mala"})
    assert client.post("/sistema/login", data={"username": "dev", "password": "test-sistema"}).status_code == 429


def test_notify_error_deja_la_linea_en_system_events(monkeypatch):
    filas = []
    monkeypatch.setattr(system_db, "_ACTIVO", True)
    monkeypatch.setattr(system_db.threading, "Thread", lambda target, args, daemon: MagicMock(start=lambda: target(*args)))
    monkeypatch.setattr(system_db, "_insertar", lambda fila: filas.append(fila))
    try:
        raise RuntimeError("Connection error to api.openai.com")
    except RuntimeError as exc:
        alerts.notify_error("turno de Telegram", exc, "chat 1")
    assert filas and filas[0]["kind"] == "error" and filas[0]["component"] == "openai"
    assert "Connection error" in filas[0]["message"] and "turno de Telegram" in filas[0]["context"]


@pytest.mark.parametrize("contexto,exc,esperado", [
    ("envío a whatsapp", RuntimeError("x"), "whatsapp"),
    ("GET /clientes", RuntimeError("x"), "web"),
    ("turno de Telegram", RuntimeError("postgrest timeout"), "supabase"),
    ("turno de whatsapp", RuntimeError("x"), "whatsapp"),
    ("entrega de PDF", RuntimeError("x"), "pdf"),
])
def test_componente_de(contexto, exc, esperado):
    assert sistema.componente_de(contexto, exc) == esperado


def test_cada_llamada_al_modelo_registra_tokens(monkeypatch):
    registros = []
    monkeypatch.setattr(system_db, "registrar", lambda *a, **k: registros.append((a, k)))
    respuesta = MagicMock()
    respuesta.choices[0].message.content = '{"name": "Norte", "tax_id": null}'
    respuesta.usage.prompt_tokens, respuesta.usage.completion_tokens = 300, 12
    with patch.object(ai._client.chat.completions, "create", return_value=respuesta) as crear:
        assert ai.extract_client_identifier("soy de la veterinaria Norte")["name"] == "Norte"
    assert crear.call_args.kwargs["response_format"] == {"type": "json_object"}
    (kind, componente, _nivel, uso), extra = registros[0]
    assert (kind, componente, uso) == ("llm", "openai", "identificar cliente")
    assert extra["details"]["prompt_tokens"] == 300 and extra["details"]["completion_tokens"] == 12


def test_cada_turno_del_webhook_queda_medido(monkeypatch):
    registros = []
    monkeypatch.setattr("app.main.system_db.registrar", lambda *a, **k: registros.append((a, k)))
    monkeypatch.setattr("app.main.process_turn", lambda *a, **k: "hola")
    monkeypatch.setattr("app.main.telegram.send_message", lambda *a, **k: None)
    monkeypatch.setattr("app.main.deliver_pending", lambda *a, **k: 0)
    from app.main import _process_telegram
    _process_telegram("chat-1", "hola")
    (kind, componente, nivel, _msg), extra = registros[0]
    assert (kind, componente, nivel) == ("turn", "bot", "info")
    assert extra["details"]["ok"] is True and extra["details"]["channel"] == "telegram" and extra["chat_id"] == "chat-1"

    def explota(*a, **k):
        raise RuntimeError("openai caído")
    monkeypatch.setattr("app.main.process_turn", explota)
    monkeypatch.setattr("app.main.notify_error", lambda *a, **k: False)
    _process_telegram("chat-1", "hola")
    assert registros[-1][0][2] == "error" and registros[-1][1]["details"]["ok"] is False


def test_resumenes_puros():
    turnos = [{"details": {"ms": 1000, "ok": True, "channel": "telegram"}, "chat_id": "a"},
              {"details": {"ms": 30000, "ok": False, "channel": "whatsapp"}, "chat_id": "b"},
              {"details": {"ms": 2000, "ok": True, "channel": "telegram"}, "chat_id": "a"}]
    r = sistema.resumen_turnos(turnos)
    assert (r["total"], r["fallidos"], r["chats"], r["p50_s"]) == (3, 1, 2, 2.0)
    llm = sistema.resumen_llm([{"created_at": "2026-10-26T12:00:00+00:00", "details": {"prompt_tokens": 100, "completion_tokens": 10}}])
    assert llm["tokens_entrada"] == 100 and list(llm["tokens_por_dia"].values()) == [110]
    conv = sistema.resumen_conversaciones(
        [{"updated_at": "2000-01-01T00:00:00+00:00", "channel": "whatsapp", "requires_handoff": True,
          "handoff_area": "contabilidad", "captured_fields": {"_blocked": True}}],
        [{"role": "user", "created_at": "2026-10-26T12:00:00+00:00"}], [{"entry_channel": "portal"}])
    assert conv["conversaciones_7d"] == 1 and conv["activas_24h"] == 0 and conv["escaladas"] == {"contabilidad": 1}
    assert conv["bloqueadas"] == 1 and conv["ordenes_por_canal"] == {"portal": 1}


def test_gasto_openai_suma_los_dias_del_mes(monkeypatch):
    monkeypatch.setattr(sistema, "OPENAI_ADMIN_KEY", "sk-admin")
    sistema._cache_openai.update(valor=None, hasta=0)
    cuerpo = b'{"data": [{"results": [{"amount": {"value": 0.5}}]}, {"results": [{"amount": {"value": 1.25}}]}]}'
    respuesta = MagicMock(__enter__=lambda s: MagicMock(read=lambda: cuerpo), __exit__=lambda *a: False)
    with patch("app.sistema.urllib.request.urlopen", return_value=respuesta):
        assert sistema.gasto_openai_mes() == {"disponible": True, "usd": 1.75}
    sistema._cache_openai.update(valor=None, hasta=0)
    monkeypatch.setattr(sistema, "OPENAI_ADMIN_KEY", "")
    assert sistema.gasto_openai_mes()["disponible"] is False


def test_guardar_costos(client, monkeypatch):
    guardados = []
    monkeypatch.setattr(system_db, "guardar_costo", lambda s, m, n: guardados.append((s, m, n)) or True)
    with client.session_transaction() as s:
        s["sistema_authenticated"] = True
    r = client.post("/sistema/costos", data={"usd_render": "25,50", "nota_render": "Standard", "usd_x": "abc"})
    assert r.status_code == 302 and guardados == [("render", 25.5, "Standard")]


def test_el_error_guarda_el_aviso_completo_como_en_telegram(monkeypatch):
    filas = []
    monkeypatch.setattr(system_db, "_ACTIVO", True)
    monkeypatch.setattr(system_db.threading, "Thread", lambda target, args, daemon: MagicMock(start=lambda: target(*args)))
    monkeypatch.setattr(system_db, "_insertar", lambda fila: filas.append(fila))
    try:
        raise ValueError("NIT inválido")
    except ValueError as exc:
        alerts.notify_error("GET /clientes", exc, "ficha")
    texto = filas[0]["details"]["texto"]
    assert "🔴 A3 · GET /clientes" in texto and "ValueError: NIT inválido" in texto and "Versión:" in texto


def test_estado_de_render_y_supabase_por_api(monkeypatch):
    sistema._cache_servicios.clear()
    monkeypatch.setattr(sistema, "RENDER_API_KEY", "k"); monkeypatch.setattr(sistema, "RENDER_SERVICE_ID", "srv-1")
    respuestas = {"services/srv-1": {"suspended": "not_suspended", "serviceDetails": {"plan": "standard", "region": "oregon"}},
                  "deploys?limit=1": [{"deploy": {"status": "live", "finishedAt": "2026-10-26T15:00:00Z"}}],
                  "projects/ref1": {"status": "ACTIVE_HEALTHY", "region": "us-east-1", "organization_slug": "org1"},
                  "organizations/org1": {"name": "LABERIT", "plan": "free"},
                  "billing/addons": {"selected_addons": [{"variant": {"price": {"amount": 10}}}]}}
    monkeypatch.setattr(sistema, "_get_json", lambda url, h, timeout=12: next(v for k, v in respuestas.items() if url.endswith(k)))
    r = sistema.estado_render()
    assert (r["plan"], r["estado"], r["usd"], r["ultimo_deploy"]) == ("standard", "activo", 25, "2026-10-26 15:00")
    monkeypatch.setattr(sistema, "SUPABASE_ACCESS_TOKEN", "t"); monkeypatch.setattr(sistema, "SUPABASE_URL", "https://ref1.supabase.co")
    sb = sistema.estado_supabase()
    assert (sb["plan"], sb["estado"], sb["usd"]) == ("free", "ACTIVE_HEALTHY", 10)
    sistema._cache_servicios.clear()
    monkeypatch.setattr(sistema, "RENDER_API_KEY", "")
    assert sistema.estado_render()["disponible"] is False


def test_servicios_traspaso_usa_api_o_valor_a_mano(monkeypatch):
    monkeypatch.setattr(sistema, "estado_render", lambda: {"disponible": True, "plan": "standard", "estado": "activo",
                                                            "ultimo_deploy": "", "region": "oregon", "usd": 25})
    monkeypatch.setattr(sistema, "estado_supabase", lambda: {"disponible": False, "motivo": "Falta SUPABASE_ACCESS_TOKEN"})
    costos = [{"service": "supabase", "monthly_usd": 25, "note": "Pro"}, {"service": "chatwoot", "monthly_usd": 12.5, "note": "Hetzner"}]
    filas = sistema.servicios_traspaso(costos, {"disponible": True, "usd": 3.2}, {"openai": {"status": "ok"}, "chatwoot": {"status": "ok", "latency_ms": 90}},
                                       {"llamadas": 10, "tokens_entrada": 1000, "tokens_salida": 100})
    por = {f["clave"]: f for f in filas}
    assert (por["openai"]["usd"], por["openai"]["manual"]) == (3.2, False)
    assert (por["render"]["usd"], por["render"]["manual"]) == (25.0, False)
    assert (por["supabase"]["usd"], por["supabase"]["manual"]) == (25.0, True) and "SUPABASE_ACCESS_TOKEN" in por["supabase"]["detalle"]
    assert (por["chatwoot"]["usd"], por["chatwoot"]["estado"], por["chatwoot"]["nota"]) == (12.5, "activo", "Hetzner")
    assert round(sum(f["usd"] for f in filas), 2) == 65.7
