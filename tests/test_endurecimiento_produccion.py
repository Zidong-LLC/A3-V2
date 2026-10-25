"""Endurecimiento previo a la salida a producción (auditoría 2026-10-25).

Timeouts y mensajes largos en los transportes, borrador explícito en Alegra, tope duro
del debounce sin bloquear el webhook, y pantallas que no se caen por un PDF borrado."""
import threading
import time
from unittest.mock import MagicMock, patch

from app.services import alegra, debounce, storage, telegram
from app.text import partir_mensaje


def test_partir_mensaje_corta_en_saltos_de_linea_y_respeta_el_tope():
    texto = "\n".join(f"Orden {i}: paciente, médico y análisis" for i in range(300))
    partes = partir_mensaje(texto, 4000)
    assert len(partes) > 1 and all(len(p) <= 4000 for p in partes)
    assert "".join(p.replace("\n", "") for p in partes).replace(" ", "") == texto.replace("\n", "").replace(" ", "")
    assert partir_mensaje("corto") == ["corto"] and partir_mensaje("") == [""]


def test_telegram_manda_un_resumen_largo_en_varias_partes_y_con_timeout():
    llamadas = []

    def falso_urlopen(req, timeout=None):
        llamadas.append((len(req.data), timeout))
        return MagicMock(__enter__=lambda s: MagicMock(read=lambda: b"{}"), __exit__=lambda *a: False)

    with patch("app.services.telegram.urllib.request.urlopen", side_effect=falso_urlopen):
        telegram.send_message("1", "x" * 9000)
    assert len(llamadas) == 3
    assert all(tam < 4200 and timeout == 20 for tam, timeout in llamadas)


def test_alegra_fuera_de_produccion_manda_la_factura_como_borrador_explicito(monkeypatch):
    cuerpos = []
    monkeypatch.setattr(alegra, "_request", lambda m, p, body=None: cuerpos.append(body) or {"id": 1})
    monkeypatch.setattr(alegra, "ALEGRA_PRODUCTION", False)
    alegra.create_invoice(7, [{"id": 1, "quantity": 1, "price": 1000}], "2026-10-25")
    assert cuerpos[0]["status"] == "draft"
    alegra.create_invoice(7, [], "2026-10-25", status="open")
    assert cuerpos[1]["status"] == "open"  # un status explícito manda
    monkeypatch.setattr(alegra, "ALEGRA_PRODUCTION", True)
    alegra.create_invoice(7, [], "2026-10-25")
    assert "status" not in cuerpos[2]  # en producción decide Alegra, como antes


def test_el_tope_duro_del_debounce_no_bloquea_el_hilo_del_webhook():
    listo = threading.Event()

    def flush_lento(_texto):
        time.sleep(0.3)
        listo.set()

    d = debounce.MessageDebouncer(window_seconds=5, max_wait_seconds=0)  # tope ya vencido
    inicio = time.monotonic()
    d.submit("c1", "hola", flush_lento)
    assert time.monotonic() - inicio < 0.2  # volvió sin esperar el turno
    assert listo.wait(2)  # y el turno igual se procesó


def test_un_pdf_borrado_del_bucket_no_tira_la_pantalla():
    roto = MagicMock()
    roto.storage.from_.return_value.create_signed_url.side_effect = RuntimeError("Object not found")
    with patch.object(storage, "_client", roto):
        assert storage.result_signed_url("cliente/x.pdf") == ""


def test_token_de_plataforma_con_acento_da_401_y_no_500():
    from app.main import app

    app.config["TESTING"] = True
    r = app.test_client().get("/api/platform/overview", headers={"X-Platform-Token": "contraseña"})
    assert r.status_code == 401
    assert r.status_code != 500
