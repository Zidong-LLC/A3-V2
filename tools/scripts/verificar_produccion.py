"""Chequeo de SOLO LECTURA del cableado de producción, para correr después de cada deploy.

    python tools/scripts/verificar_produccion.py https://a3-plataforma.onrender.com

Verifica: /health (el liviano), /health/detalle con el token de la plataforma, que el
Agent Bot de Chatwoot apunte a ESA URL con ?token=, que el bot esté asociado a los
inboxes de Telegram y WhatsApp, y que el webhook de Telegram siga apuntando a Chatwoot.
No cambia nada: si algo está mal lo dice y termina con código 1.
(El script hermano `verify_chatwoot_telegram_agent.py` es para la sesión LOCAL con ngrok
y SÍ reescribe la URL del bot.)
"""
import json
import os
import sys
import urllib.request

from dotenv import load_dotenv


def _get(url: str, headers: dict | None = None, timeout: int = 60) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main() -> int:
    load_dotenv()
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    fallas = []

    def check(nombre: str, ok: bool, detalle: str = "") -> None:
        print(("OK   " if ok else "FALLA") + f" {nombre}" + (f" — {detalle}" if detalle else ""))
        if not ok:
            fallas.append(nombre)

    status, cuerpo = _get(f"{base}/health")
    check("/health responde 200", status == 200, f"{status} {cuerpo[:120]}")

    token = os.environ.get("PLATFORM_API_TOKEN", "")
    status, cuerpo = _get(f"{base}/health/detalle", {"X-Platform-Token": token})
    try:
        checks = json.loads(cuerpo).get("checks", {})
        resumen = ", ".join(f"{k}={v.get('status')}" for k, v in checks.items())
    except (json.JSONDecodeError, AttributeError):
        checks, resumen = {}, cuerpo[:120]
    # 503 con JSON = una dependencia caída (se informa); 503 sin JSON = el servicio no está.
    check("/health/detalle con token", bool(checks) and status in (200, 503), f"{status} · {resumen}")
    status, _ = _get(f"{base}/health/detalle")
    check("/health/detalle SIN token devuelve 401", status == 401, str(status))

    chatwoot = os.environ.get("CHATWOOT_URL", "").rstrip("/")
    cuenta = os.environ.get("CHATWOOT_ACCOUNT_ID", "")
    cabeceras = {"api_access_token": os.environ.get("CHATWOOT_API_TOKEN", "")}
    secreto = os.environ.get("CHATWOOT_WEBHOOK_SECRET", "")
    esperada = f"{base}/chatwoot/webhook?token={secreto}"
    status, cuerpo = _get(f"{chatwoot}/api/v1/accounts/{cuenta}/agent_bots", cabeceras)
    bots = json.loads(cuerpo) if status == 200 else []
    bot = next((b for b in bots if b.get("name") == "A3"), bots[0] if bots else {})
    check("Agent Bot apunta a esta URL con ?token=", bot.get("outgoing_url") == esperada,
          (bot.get("outgoing_url") or "sin bot").split("?")[0])
    for inbox, nombre in ((os.environ.get("CHATWOOT_INBOX_ID", "1"), "Telegram"), ("3", "WhatsApp")):
        status, cuerpo = _get(f"{chatwoot}/api/v1/accounts/{cuenta}/inboxes/{inbox}/agent_bot", cabeceras)
        asociado = (json.loads(cuerpo).get("agent_bot") or {}) if status == 200 else {}
        check(f"Bot asociado al inbox {inbox} ({nombre})", asociado.get("id") == bot.get("id"), asociado.get("name") or "ninguno")

    tg = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    status, cuerpo = _get(f"https://api.telegram.org/bot{tg}/getWebhookInfo")
    info = json.loads(cuerpo).get("result", {}) if status == 200 else {}
    host_chatwoot = chatwoot.split("//")[-1]
    check("Webhook de Telegram apunta a Chatwoot", host_chatwoot in info.get("url", ""),
          f"pendientes={info.get('pending_update_count')} último_error={info.get('last_error_message')}")

    print("\nTODO OK" if not fallas else f"\n{len(fallas)} falla(s): {', '.join(fallas)}")
    return 0 if not fallas else 1


if __name__ == "__main__":
    raise SystemExit(main())
