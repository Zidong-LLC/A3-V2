"""Apunta el Agent Bot de Chatwoot al servicio de producción (Render).

Es el ÚNICO recableado que necesita el deploy: Chatwoot administra el webhook de
Telegram (URL fija) y nosotros solo cambiamos a dónde nos manda las conversaciones.

Desde ERR-177 la URL saliente DEBE llevar el secreto:
    https://<servicio>.onrender.com/chatwoot/webhook?token=<CHATWOOT_WEBHOOK_SECRET>
Sin el token el webhook responde 403 y el bot queda mudo.

Por defecto solo MUESTRA lo que haría (no toca nada). Con --aplicar, lo hace.

    python tools/scripts/cablear_produccion.py https://a3-plataforma.onrender.com
    python tools/scripts/cablear_produccion.py https://a3-plataforma.onrender.com --aplicar
"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402


def _pedir(metodo: str, url: str, cuerpo: dict | None = None,
           headers: dict | None = None) -> tuple[int, str]:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    cabeceras = {"Content-Type": "application/json", **(headers or {})}
    req = request.Request(url, data=datos, headers=cabeceras, method=metodo)
    try:
        with request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def _json(metodo: str, url: str, cuerpo=None, headers=None):
    estado, texto = _pedir(metodo, url, cuerpo, headers)
    if estado >= 400:
        raise RuntimeError(f"{metodo} {url} -> {estado}: {texto[:300]}")
    return json.loads(texto or "{}")


def _requerido(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise SystemExit(f"Falta {nombre} en el entorno (.env)")
    return valor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="URL pública del servicio, ej. https://a3.onrender.com")
    parser.add_argument("--aplicar", action="store_true",
                        help="Aplica el cambio. Sin esto, solo muestra qué haría.")
    args = parser.parse_args()

    load_dotenv()
    publica = args.url.rstrip("/")
    chatwoot = _requerido("CHATWOOT_URL").rstrip("/")
    cuenta = _requerido("CHATWOOT_ACCOUNT_ID")
    token_api = _requerido("CHATWOOT_API_TOKEN")
    inbox = os.environ.get("CHATWOOT_INBOX_ID", "1")
    secreto = os.environ.get("CHATWOOT_WEBHOOK_SECRET", "").strip()
    headers = {"api_access_token": token_api}

    # 1. El servicio tiene que estar sano ANTES de mandarle las conversaciones.
    estado, cuerpo = _pedir("GET", f"{publica}/health")
    if estado != 200:
        print(f"FALLO: {publica}/health respondió {estado}. El servicio no está listo.")
        print(cuerpo[:400])
        return 1
    salud = json.loads(cuerpo)
    print(f"1. Salud del servicio: {salud.get('status')}")
    for nombre, check in (salud.get("checks") or {}).items():
        print(f"     {nombre}: {check.get('status')}")

    # 2. La URL destino, con el token (tapón #3 de WhatsApp, ERR-177).
    destino = f"{publica}/chatwoot/webhook"
    if secreto:
        destino += f"?token={secreto}"
    else:
        print("   AVISO: sin CHATWOOT_WEBHOOK_SECRET el webhook queda abierto a cualquiera.")

    # 3. El bot y su URL actual.
    bots = _json("GET", f"{chatwoot}/api/v1/accounts/{cuenta}/agent_bots", headers=headers)
    lista = bots if isinstance(bots, list) else bots.get("payload", [])
    if not lista:
        print("FALLO: la cuenta de Chatwoot no tiene ningún Agent Bot creado.")
        return 1
    bot = lista[0]
    print(f"\n2. Agent Bot: '{bot.get('name')}' (id {bot.get('id')})")
    print(f"     ahora apunta a: {bot.get('outgoing_url')}")
    print(f"     va a apuntar a: {destino.split('?')[0]}{'?token=…' if secreto else ''}")

    if not args.aplicar:
        print("\n(SIMULACIÓN — no se tocó nada. Repetir con --aplicar para hacerlo.)")
        return 0

    # 4. Aplicar: URL saliente + asociación al inbox.
    _json("PATCH", f"{chatwoot}/api/v1/accounts/{cuenta}/agent_bots/{bot['id']}",
          {"name": bot.get("name"), "outgoing_url": destino}, headers)
    _json("POST", f"{chatwoot}/api/v1/accounts/{cuenta}/inboxes/{inbox}/set_agent_bot",
          {"agent_bot": bot["id"]}, headers)

    # 5. Verificar que quedó.
    verif = _json("GET", f"{chatwoot}/api/v1/accounts/{cuenta}/agent_bots", headers=headers)
    lista2 = verif if isinstance(verif, list) else verif.get("payload", [])
    quedo = next((b.get("outgoing_url") for b in lista2 if b.get("id") == bot["id"]), "")
    ok_url = quedo == destino
    adjunto = _json("GET", f"{chatwoot}/api/v1/accounts/{cuenta}/inboxes/{inbox}/agent_bot",
                    headers=headers)
    ok_inbox = (adjunto.get("agent_bot") or {}).get("id") == bot["id"]

    print(f"\n3. URL saliente actualizada: {'OK' if ok_url else 'NO QUEDÓ'}")
    print(f"4. Bot asociado al inbox {inbox}: {'OK' if ok_inbox else 'NO QUEDÓ'}")

    # 6. El webhook de Telegram DEBE seguir apuntando a Chatwoot, no a nosotros.
    tg = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if tg:
        info = _json("GET", f"https://api.telegram.org/bot{tg}/getWebhookInfo")
        url_tg = (info.get("result") or {}).get("url", "")
        apunta_bien = chatwoot.split("//")[-1].split("/")[0] in url_tg
        print(f"5. Webhook de Telegram apunta a Chatwoot: {'OK' if apunta_bien else 'REVISAR'}")
        if not apunta_bien:
            print(f"     apunta a: {url_tg}")

    return 0 if (ok_url and ok_inbox) else 1


if __name__ == "__main__":
    raise SystemExit(main())
