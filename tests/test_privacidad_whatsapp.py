"""Autorización de datos antes de conversar por WhatsApp (propuesta del 28/09).

Lo que importa: antes del menú sale la política con botones, un «sí» solo vale si ya se
preguntó, lo que no se entiende se repregunta, y con «sí» sigue todo como siempre."""
from unittest.mock import patch

import pytest

from app import main, privacidad
from app.services import chatwoot

TELEFONO = "+573001112233"


@pytest.fixture
def mundo(monkeypatch):
    """Base en memoria y Chatwoot simulado; la autorización encendida."""
    estado = {"eventos": [], "opciones": [], "mensajes": [], "historia": []}
    monkeypatch.setattr(privacidad, "WHATSAPP_PRIVACY_ENABLED", True)
    monkeypatch.setattr(privacidad.privacy_db, "ultimo_evento",
                        lambda c: next((e["evento"] for e in reversed(estado["eventos"]) if e["contacto"] == c), None))

    def registrar(contacto, canal, chat_id, evento, version, url, respuesta=None):
        estado["eventos"].append({"contacto": contacto, "canal": canal, "chat": chat_id, "evento": evento,
                                  "version": version, "url": url, "respuesta": respuesta})

    monkeypatch.setattr(privacidad.privacy_db, "registrar", registrar)
    monkeypatch.setattr(privacidad.chatwoot, "send_options", lambda c, t, o: estado["opciones"].append((c, t, o)))
    monkeypatch.setattr(privacidad.chatwoot, "send_message", lambda c, t: estado["mensajes"].append((c, t)))
    monkeypatch.setattr(privacidad.db, "get_recent_messages", lambda c, limit=8: estado["historia"])
    return estado


def _eventos(mundo):
    return [e["evento"] for e in mundo["eventos"]]


def test_el_primer_mensaje_recibe_la_politica_con_dos_botones(mundo):
    assert privacidad.atender("7", "Hola", "whatsapp", TELEFONO) is True
    chat, texto, botones = mundo["opciones"][0]
    assert chat == "7" and privacidad.PRIVACY_POLICY_URL in texto and texto.endswith("¿Estás de acuerdo?")
    assert [b["title"] for b in botones] == ["Sí 👍", "No 👎"]
    assert all(len(b["title"]) <= 20 for b in botones), "WhatsApp rechaza títulos de más de 20 caracteres"
    assert _eventos(mundo) == ["asked"]


def test_tocar_si_deja_evidencia_y_pasa_al_agente_que_saluda_con_el_menu(mundo):
    privacidad.atender("7", "Hola", "whatsapp", TELEFONO)
    assert privacidad.atender("7", "Sí 👍", "whatsapp", TELEFONO) is False
    aceptado = mundo["eventos"][-1]
    assert aceptado["evento"] == "accepted" and aceptado["respuesta"] == "Sí 👍"
    assert aceptado["contacto"] == TELEFONO and aceptado["version"] == privacidad.VERSION_POLITICA
    assert aceptado["url"] == privacidad.PRIVACY_POLICY_URL


def test_quien_ya_acepto_no_vuelve_a_ver_la_pregunta_ni_en_otra_conversacion(mundo):
    privacidad.atender("7", "Hola", "whatsapp", TELEFONO)
    privacidad.atender("7", "si", "whatsapp", TELEFONO)
    mundo["opciones"].clear()
    assert privacidad.atender("99", "Buenas", "whatsapp", TELEFONO) is False
    assert mundo["opciones"] == []


def test_un_si_sin_pregunta_previa_no_autoriza(mundo):
    assert privacidad.atender("7", "Si buenas", "whatsapp", TELEFONO) is True
    assert privacidad.atender("8", "si", "whatsapp", "+573009998877") is True
    assert _eventos(mundo) == ["asked", "asked"], "nadie aceptó todavía"


def test_tocar_no_avisa_deja_evidencia_y_no_atiende(mundo):
    privacidad.atender("7", "Hola", "whatsapp", TELEFONO)
    assert privacidad.atender("7", "No 👎", "whatsapp", TELEFONO) is True
    assert mundo["mensajes"] == [("7", privacidad.RECHAZO)] and _eventos(mundo) == ["asked", "rejected"]


def test_quien_rechazo_puede_cambiar_de_opinion(mundo):
    privacidad.atender("7", "Hola", "whatsapp", TELEFONO)
    privacidad.atender("7", "no", "whatsapp", TELEFONO)
    mundo["opciones"].clear()
    assert privacidad.atender("7", "hola otra vez", "whatsapp", TELEFONO) is True
    assert len(mundo["opciones"]) == 1, "se vuelve a preguntar"
    assert privacidad.atender("7", "acepto", "whatsapp", TELEFONO) is False
    assert _eventos(mundo)[-1] == "accepted"


@pytest.mark.parametrize("texto", ["no sé", "qué política?", "1", "quiero una recogida", "no entiendo", "sí pero qué dice"])
def test_lo_que_no_se_entiende_se_vuelve_a_preguntar(mundo, texto):
    privacidad.atender("7", "Hola", "whatsapp", TELEFONO)
    mundo["opciones"].clear()
    assert privacidad.atender("7", texto, "whatsapp", TELEFONO) is True
    assert len(mundo["opciones"]) == 1 and _eventos(mundo) == ["asked"], "ni acepta ni rechaza"


@pytest.mark.parametrize("texto,esperado", [
    ("Sí 👍", "si"), ("No 👎", "no"), ("si", "si"), ("SI", "si"), ("acepto", "si"), ("de acuerdo", "si"),
    ("estoy de acuerdo", "si"), ("👍", "si"), ("si señor", "si"), ("Sí 👍\nquiero una recogida", "si"),
    ("no", "no"), ("no acepto", "no"), ("no estoy de acuerdo", "no"), ("no gracias", "no"), ("👎", "no"),
    ("no sé", None), ("", None), ("hola", None), ("si claro pero cuánto vale", None),
])
def test_lectura_de_la_respuesta(texto, esperado):
    assert privacidad._lectura(texto) == esperado


def test_una_conversacion_en_curso_retoma_su_ultima_pregunta(mundo):
    mundo["historia"] = [{"role": "user", "content": "Coco"}, {"role": "bot", "content": "¿Cuál es la raza?"}]
    privacidad.atender("7", "Hola", "whatsapp", TELEFONO)
    assert privacidad.atender("7", "Sí 👍", "whatsapp", TELEFONO) is True, "un «sí» suelto no entra al flujo"
    assert mundo["mensajes"][-1][1].endswith("¿Cuál es la raza?")


def test_telegram_no_pasa_por_la_autorizacion(mundo):
    assert privacidad.atender("7", "Hola", "chatwoot", "") is False
    assert mundo["eventos"] == [] and mundo["opciones"] == []


def test_apagada_no_hace_nada(mundo, monkeypatch):
    monkeypatch.setattr(privacidad, "WHATSAPP_PRIVACY_ENABLED", False)
    assert privacidad.atender("7", "Hola", "whatsapp", TELEFONO) is False


def test_sin_numero_la_autorizacion_queda_por_conversacion(mundo):
    privacidad.atender("7", "Hola", "whatsapp", "")
    assert mundo["eventos"][0]["contacto"] == "chat:7"


def test_si_falla_la_tabla_el_bot_sigue_atendiendo_y_avisa(mundo, monkeypatch):
    def rota(_):
        raise RuntimeError("tabla no existe")

    monkeypatch.setattr(privacidad.privacy_db, "ultimo_evento", rota)
    with patch.object(privacidad, "notify_error") as aviso:
        assert privacidad.atender("7", "Hola", "whatsapp", TELEFONO) is False
    assert aviso.call_count == 1


def test_send_options_manda_botones_a_chatwoot():
    with patch.object(chatwoot, "_post") as post:
        chatwoot.send_options("7", "¿Estás de acuerdo?", privacidad.BOTONES)
    ruta, cuerpo = post.call_args.args
    assert ruta == "/conversations/7/messages" and cuerpo["content_type"] == "input_select"
    assert cuerpo["content_attributes"]["items"] == privacidad.BOTONES and cuerpo["message_type"] == "outgoing"


# ── De punta a punta por el webhook ─────────────────────────────────────────────────


def _webhook(content, monkeypatch, **extra):
    monkeypatch.setattr("app.main.CHATWOOT_WEBHOOK_SECRET", "s")
    cliente = main.app.test_client()
    payload = {"event": "message_created", "message_type": "incoming", "content": content,
               "conversation": {"id": 7, "channel": "Channel::Whatsapp"}, **extra}
    with patch("app.main._debouncer.submit") as sub:
        cliente.post("/chatwoot/webhook?token=s", json=payload)
    return sub.call_args.args[2]


def test_el_webhook_identifica_al_remitente_y_el_agente_no_corre_hasta_autorizar(mundo, monkeypatch):
    flush = _webhook("Hola", monkeypatch, sender={"phone_number": TELEFONO})
    with patch("app.main.process_turn", return_value=None) as turno:
        flush("Hola")
        assert turno.call_count == 0, "el agente no corre antes de autorizar"
    assert mundo["eventos"][0]["contacto"] == TELEFONO
    flush2 = _webhook("Sí 👍", monkeypatch, sender={"phone_number": TELEFONO})
    with patch("app.main.process_turn", return_value=None) as turno:
        flush2("Sí 👍")
        assert turno.call_count == 1, "con el sí sigue el flujo de siempre"


def test_el_numero_tambien_se_lee_de_la_conversacion(mundo, monkeypatch):
    # sin `sender` en el mensaje: viene en conversation.meta.sender
    flush = _webhook("Hola", monkeypatch, conversation={"id": 7, "channel": "Channel::Whatsapp",
                                                        "meta": {"sender": {"phone_number": TELEFONO}}})
    with patch("app.main.process_turn", return_value=None):
        flush("Hola")
    assert mundo["eventos"][0]["contacto"] == TELEFONO


def test_modo_prueba_solo_pregunta_a_los_numeros_configurados(mundo, monkeypatch):
    monkeypatch.setattr(privacidad, "WHATSAPP_PRIVACY_ONLY_NUMBERS", {"573001112233"})
    assert privacidad.atender("7", "Hola", "whatsapp", "+573009998877") is False
    assert mundo["eventos"] == []
    assert privacidad.atender("8", "Hola", "whatsapp", TELEFONO) is True
    assert len(mundo["opciones"]) == 1
