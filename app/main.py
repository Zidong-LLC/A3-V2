import time
from flask import Flask, request, jsonify, abort
from app.config import TELEGRAM_WEBHOOK_SECRET, FLASK_SECRET_KEY
from app.agent import process_turn
from app.services import telegram, chatwoot
from app.services.db import get_or_create_session
from app.platform_api import platform_api
from app.dashboard import dashboard

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.register_blueprint(platform_api)
app.register_blueprint(dashboard)

# Pausa tras el mensaje de progreso para que se sienta humano (segundos)
PROGRESS_PAUSE_SECONDS = 1.5


def _make_progress_callback(channel, chat_id: str):
    """Devuelve un callback que envía un mensaje de progreso ('déjame revisar…'),
    activa el indicador de 'escribiendo…' y espera una pausa corta. Cualquier
    error de red se ignora para no interrumpir el turno."""
    def on_progress(message: str) -> None:
        try:
            channel.send_message(chat_id, message)
            channel.send_typing(chat_id)
            time.sleep(PROGRESS_PAUSE_SECONDS)
        except Exception as e:
            app.logger.warning("Fallo enviando mensaje de progreso a %s: %s", chat_id, e)
    return on_progress


@app.route("/webhooks/telegram", methods=["POST"])
def telegram_webhook():
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if token != TELEGRAM_WEBHOOK_SECRET:
        abort(403)

    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message") or data.get("edited_message")

    if not message or "text" not in message:
        return jsonify({"ok": True})

    chat_id = str(message["chat"]["id"])
    user_text = message["text"]

    try:
        reply = process_turn(chat_id, user_text, on_progress=_make_progress_callback(telegram, chat_id))
    except Exception as e:
        app.logger.error("Error processing turn for %s: %s", chat_id, e, exc_info=True)
        return jsonify({"ok": True})

    # reply None: sesión bloqueada (cliente final). No se responde.
    if not reply:
        return jsonify({"ok": True})

    try:
        telegram.send_message(chat_id, reply)
    except Exception as e:
        app.logger.error("Error sending message to %s: %s", chat_id, e)

    return jsonify({"ok": True})


@app.route("/chatwoot/webhook", methods=["POST"])
def chatwoot_webhook():
    data = request.get_json(force=True, silent=True) or {}

    if data.get("event") != "message_created":
        return jsonify({"ok": True})
    if data.get("message_type") != "incoming":
        return jsonify({"ok": True})
    if data.get("private") is True:
        return jsonify({"ok": True})

    content = str(data.get("content") or "").strip()
    conversation_raw_id = (data.get("conversation") or {}).get("id")
    conversation_id = str(conversation_raw_id or "")
    if not content or not conversation_id:
        return jsonify({"ok": True})

    try:
        reply = process_turn(conversation_id, content, on_progress=_make_progress_callback(chatwoot, conversation_id))
    except Exception as e:
        app.logger.error("Error en process_turn chatwoot %s: %s", conversation_id, e, exc_info=True)
        return jsonify({"ok": True})

    # reply None: sesión bloqueada (cliente final). No se responde.
    if not reply:
        return jsonify({"ok": True})

    try:
        chatwoot.send_message(conversation_id, reply)
        session = get_or_create_session(conversation_id)
        if session.get("requires_handoff") and session.get("handoff_area"):
            chatwoot.assign_team(conversation_id, session["handoff_area"])
    except Exception as e:
        app.logger.error("Error enviando a chatwoot %s: %s", conversation_id, e, exc_info=True)

    return jsonify({"ok": True})


@app.route("/setup-webhook", methods=["POST"])
def setup_webhook():
    from app.config import TELEGRAM_WEBHOOK_URL, TELEGRAM_WEBHOOK_SECRET
    result = telegram.set_webhook(TELEGRAM_WEBHOOK_URL, TELEGRAM_WEBHOOK_SECRET)
    return jsonify(result)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
