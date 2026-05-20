"""Verify and repair the local Telegram -> Chatwoot -> Agent Bot flow.

Preconditions:
- Flask is running on port 5000.
- ngrok is running against port 5000.

This script does not call Telegram setWebhook directly. Chatwoot owns the
Telegram webhook in the local development flow.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from dotenv import load_dotenv


def _request(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            text = resp.read().decode("utf-8", "replace")
            return resp.status, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        return exc.code, text
    except Exception as exc:
        return 0, str(exc)


def _json_request(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    status, text = _request(method, url, body, headers)
    if status < 200 or status >= 300:
        raise RuntimeError(f"{method} {url} failed: {status} {text[:300]}")
    if not text:
        return {}
    return json.loads(text)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def _domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc or url


def main() -> int:
    load_dotenv()

    chatwoot_url = _required_env("CHATWOOT_URL").rstrip("/")
    account_id = _required_env("CHATWOOT_ACCOUNT_ID")
    api_token = _required_env("CHATWOOT_API_TOKEN")
    inbox_id = os.environ.get("CHATWOOT_INBOX_ID", "1")
    telegram_token = _required_env("TELEGRAM_BOT_TOKEN")

    chatwoot_headers = {"api_access_token": api_token}

    tunnels = _json_request("GET", "http://127.0.0.1:4040/api/tunnels")
    tunnel = next((t for t in tunnels.get("tunnels", []) if t.get("proto") == "https"), None)
    if not tunnel:
        raise RuntimeError("No active https ngrok tunnel found at http://127.0.0.1:4040")

    public_url = tunnel["public_url"].rstrip("/")
    desired_outgoing_url = f"{public_url}/chatwoot/webhook"

    status, health = _request(
        "GET",
        f"{public_url}/health",
        headers={"ngrok-skip-browser-warning": "true"},
    )
    if status != 200 or '"ok"' not in health and '"status"' not in health:
        raise RuntimeError(f"Public health failed: {status} {health[:300]}")

    bots = _json_request(
        "GET",
        f"{chatwoot_url}/api/v1/accounts/{account_id}/agent_bots",
        headers=chatwoot_headers,
    )
    bot = next((item for item in bots if item.get("name") == "A3"), None) or (bots[0] if bots else None)
    if not bot:
        raise RuntimeError("No Chatwoot Agent Bot found")

    bot_id = bot["id"]
    if bot.get("outgoing_url") != desired_outgoing_url:
        bot = _json_request(
            "PATCH",
            f"{chatwoot_url}/api/v1/accounts/{account_id}/agent_bots/{bot_id}",
            {
                "name": bot.get("name", "A3"),
                "bot_type": bot.get("bot_type", "webhook"),
                "outgoing_url": desired_outgoing_url,
            },
            chatwoot_headers,
        )

    _request(
        "POST",
        f"{chatwoot_url}/api/v1/accounts/{account_id}/inboxes/{inbox_id}/set_agent_bot",
        {"agent_bot": bot_id},
        chatwoot_headers,
    )

    attached = _json_request(
        "GET",
        f"{chatwoot_url}/api/v1/accounts/{account_id}/inboxes/{inbox_id}/agent_bot",
        headers=chatwoot_headers,
    )
    attached_bot = attached.get("agent_bot") or {}
    if attached_bot.get("id") != bot_id:
        raise RuntimeError("Agent Bot is not attached to the Telegram inbox")

    tg_info = _json_request("GET", f"https://api.telegram.org/bot{telegram_token}/getWebhookInfo")
    tg_url = (tg_info.get("result") or {}).get("url", "")
    if _domain(chatwoot_url) not in tg_url:
        raise RuntimeError(f"Telegram webhook is not pointing to Chatwoot: {_domain(tg_url)}")

    status, ping = _request(
        "POST",
        desired_outgoing_url,
        {"event": "ping"},
        {"ngrok-skip-browser-warning": "true"},
    )
    if status != 200:
        raise RuntimeError(f"Agent webhook ping failed: {status} {ping[:300]}")

    print("OK local agent flow verified")
    print(f"Public URL: {public_url}")
    print(f"Agent outgoing_url: {desired_outgoing_url}")
    print(f"Telegram webhook host: {_domain(tg_url)}")
    print(f"Attached Agent Bot: {attached_bot.get('name')} (id={bot_id})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
