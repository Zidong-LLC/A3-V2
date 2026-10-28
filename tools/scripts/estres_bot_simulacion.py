"""Piezas simuladas del estrés del bot: base en memoria POR CHAT, modelo y cliente.

- Base: todo lo que ESCRIBE (sesión, mensajes, órdenes, pedidos) vive acá, separado por
  chat y con lock, para poder afirmar después que ningún chat pisó a otro. Lo que solo
  LEE (clientes, catálogo, motorizados) sigue yendo a Supabase real.
- Modelo: reemplaza `ai._completar`, el punto por el que pasan TODAS las llamadas a
  OpenAI. Devuelve JSON válido con los datos del escenario del chat que aparezcan en el
  mensaje, tras una latencia como la real (o lenta, o con caídas).
- Cliente: lee la última respuesta del bot y contesta lo que le preguntan.
"""
import copy
import json
import random
import re
import threading
import time
from collections import defaultdict

_lock = threading.RLock()
sesiones: dict[str, dict] = {}
mensajes: dict[str, list] = defaultdict(list)
ordenes: list[dict] = []
pedidos: dict[str, dict] = {}
contadores: dict[str, int] = defaultdict(int)
escenarios: dict[str, dict] = {}
actual = threading.local()  # chat del turno en curso, lo fija el envoltorio de process_turn
IA = {"modo": "normal"}

CAMPOS = ("clinic_name", "tax_id", "pickup_address", "exam_type", "patient_name", "species",
          "requesting_doctor", "patient_age", "owner_name", "breed", "sex", "sample_taken_date",
          "observations", "payment_method", "selected_tests", "removed_tests")


PREGUNTAS = (("requesting_doctor", "¿Qué médico veterinario lo solicita?"),
             ("patient_name", "¿Cómo se llama el paciente?"), ("species", "¿Qué especie es?"),
             ("breed", "¿De qué raza es?"), ("sex", "¿Es macho o hembra?"),
             ("patient_age", "¿Qué edad tiene?"), ("owner_name", "¿Cómo se llama el propietario?"),
             ("sample_taken_date", "¿En qué fecha se tomó la muestra?"),
             ("observations", "¿Alguna observación?"), ("exam_type", "¿Qué análisis o perfil desean?"),
             ("payment_method", "¿Cuál es la forma de pago: contraentrega o pago en línea?"))


def contar(clave: str, n: int = 1) -> None:
    with _lock:
        contadores[clave] += n


# ── Base en memoria ───────────────────────────────────────────────────────────
def get_or_create_session(chat_id, channel="telegram"):
    with _lock:
        if chat_id not in sesiones:
            sesiones[chat_id] = {"channel": channel, "external_chat_id": chat_id, "client_id": None,
                                 "phase_current": "fase_0_bienvenida", "intent_current": "unknown",
                                 "captured_fields": {}, "status": "in_progress"}
        return copy.deepcopy(sesiones[chat_id])


def update_session(chat_id, ai):
    with _lock:
        s = sesiones[chat_id]
        s.update(phase_current=ai["phase"], intent_current=ai["intent"],
                 captured_fields=copy.deepcopy(ai["captured_fields"]),
                 requires_handoff=ai["requires_handoff"], last_bot_message=ai["reply"])
        if ai.get("handoff_area"):
            s["handoff_area"] = ai["handoff_area"]


def _campos_sesion(chat_id, quitar):
    with _lock:
        campos = sesiones.get(chat_id, {}).get("captured_fields") or {}
        tenia = any(k in campos for k in quitar)
        for k in quitar:
            campos.pop(k, None)
        return tenia


def save_message(chat_id, content, role):
    with _lock:
        mensajes[chat_id].append({"role": role, "content": content})


def get_recent_messages(chat_id, limit=8):
    with _lock:
        return copy.deepcopy(mensajes[chat_id][-limit:])


def link_client_to_session(chat_id, client_id):
    with _lock:
        sesiones[chat_id]["client_id"] = client_id


def clear_client_from_session(chat_id):
    with _lock:
        sesiones[chat_id]["client_id"] = None


def create_request(chat_id, session, ai, pedido_id=None):
    from app.services import db as real

    with _lock:
        n = len(ordenes) + 1
        perfil = real._profile_event_payload(ai.get("captured_fields") or {})
        ordenes.append({"chat_id": chat_id, "client_id": session.get("client_id"), "pedido_id": pedido_id,
                        "order_number": f"EST-{n:04d}", "fields": copy.deepcopy(ai.get("captured_fields") or {}),
                        "profile": perfil})
        return {"request_id": f"est-req-{n}", "order_number": f"EST-{n:04d}",
                "event_payload": {"profile": perfil} if perfil else {}}


def create_pedido(client_id, chat_id, entry_channel="telegram"):
    with _lock:
        pid = f"est-ped-{len(pedidos) + 1}"
        pedidos[pid] = {"id": pid, "pedido_number": f"P-EST-{len(pedidos) + 1:04d}", "status": "abierto",
                        "external_chat_id": chat_id, "client_id": client_id, "payment_method": None,
                        "created_at": "2026-10-28T00:00:00+00:00"}
        return copy.deepcopy(pedidos[pid])


def get_open_pedido(chat_id):
    with _lock:
        return next((copy.deepcopy(p) for p in pedidos.values()
                     if p["external_chat_id"] == chat_id and p["status"] == "abierto"), None)


def get_pedido(pid):
    with _lock:
        return copy.deepcopy(pedidos.get(pid))


def close_pedido(pid, payment_method=None):
    with _lock:
        if pid in pedidos:
            pedidos[pid].update(status="cerrado", payment_method=payment_method)
        return copy.deepcopy(pedidos.get(pid))


def list_pedido_requests(pid):
    with _lock:
        return [{"order_number": o["order_number"], "patient_name": o["fields"].get("patient_name"),
                 "exam_type": o["fields"].get("exam_type")} for o in ordenes if o["pedido_id"] == pid]


def get_pedido_profiles(pid, con_request_id=False):
    with _lock:
        return [o["profile"] for o in ordenes if o["pedido_id"] == pid and o["profile"]]


SIMULADAS = {
    "get_or_create_session": get_or_create_session, "update_session": update_session,
    "save_message": save_message, "get_recent_messages": get_recent_messages,
    "link_client_to_session": link_client_to_session, "clear_client_from_session": clear_client_from_session,
    "clear_pending_result_delivery": lambda c: _campos_sesion(c, ("_deliver_results",)),
    "limpiar_pedido_de_sesion": lambda c: _campos_sesion(c, ("_pedido_id", "_pedido_profiles", "_pedido_ordenes")),
    "create_request": create_request, "create_pedido": create_pedido, "get_open_pedido": get_open_pedido,
    "get_pedido": get_pedido, "close_pedido": close_pedido, "list_pedido_requests": list_pedido_requests,
    "get_pedido_profiles": get_pedido_profiles, "list_stale_pedidos": lambda horas=1, limit=20: [],
    "touch_pedido": lambda pid: None, "mark_pedido_invoiced": lambda pid, invoice_id=None: None,
}


# ── Modelo simulado ───────────────────────────────────────────────────────────
def _latencia() -> None:
    lo, hi = {"normal": (2.0, 6.0), "lenta": (15.0, 40.0), "falla": (2.0, 6.0)}[IA["modo"]]
    espera = random.uniform(lo, hi)
    time.sleep(espera)
    actual.ia_ms = getattr(actual, "ia_ms", 0) + espera * 1000
    if IA["modo"] == "falla" and random.random() < 0.3:
        import httpx
        import openai

        contar("ia_caida")
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


def completar(messages, response_format, temperature, uso):
    contar(f"llm:{uso}")
    _latencia()
    texto = messages[-1]["content"]
    esc = escenarios.get(getattr(actual, "chat", ""), {})
    if uso == "dato de la orden":
        valor = re.search(r'respondió: "(.*)"\s*$', texto, re.S)
        return {"action": "save", "value": (valor.group(1) if valor else texto).strip(), "reply": None}
    if uso == "identificar cliente":
        bajo = texto.lower()
        return {"name": esc.get("clinic_name") if esc.get("clinic_name", "").lower() in bajo else None,
                "tax_id": esc.get("tax_id") if (esc.get("tax_id") or "") in texto else None}
    previos = {}
    for m in messages[1:3]:
        for linea in m["content"].splitlines() if m["role"] == "system" else []:
            if linea.startswith("Datos ya capturados:"):
                previos = json.loads(linea.split(":", 1)[1])
    campos = {k: None for k in CAMPOS}
    campos.update({k: v for k, v in previos.items() if k in campos})
    bajo = texto.lower()
    for k, v in esc.get("datos", {}).items():
        if v and v.lower() in bajo:
            campos[k] = v
    if "contraentrega" in bajo:
        campos["payment_method"] = "contraentrega"
    senal = ("another_order" if "otra orden" in bajo else "affirm" if re.match(r"\s*s[ií]\b", bajo)
             else "negate" if re.match(r"\s*no\b", bajo) else "provides_requested_data")
    # Como el modelo real: pregunta por el primer dato que falta (orden del guion A).
    pregunta = next((p for k, p in PREGUNTAS if not campos.get(k)), "¿Confirmas los datos de la orden?")
    return {"reply": f"Perfecto, anotado. {pregunta}", "intent": "route_scheduling", "phase": "fase_2_recogida_datos",
            "service_area": "route_scheduling", "captured_fields": campos, "message_mode": "flow_progress",
            "user_intent_signal": senal, "requires_handoff": False, "handoff_area": None,
            "resume_prompt": "", "confidence": 0.9, "pending_intents": []}


# ── Cliente simulado ──────────────────────────────────────────────────────────
def responder(respuesta: str, esc: dict) -> str:
    """Contesta lo que el bot preguntó. El orden importa: el resumen menciona todos los
    campos, así que 'otra orden' y 'confirmar' se miran antes que cada dato suelto."""
    r = (respuesta or "").lower()
    d = esc["datos"]
    if "cuál es el correcto" in r:  # varias sedes parecidas: elige la suya por el nombre
        for linea in (respuesta or "").splitlines():
            m = re.match(r"\s*(\d+)\)\s*(.+?)\s+-", linea)
            if m and m.group(2).strip().lower() == esc["clinic_name"].strip().lower():
                return m.group(1)
        return f"NIT {esc['tax_id']}"
    reglas = [
        (("otra orden",), "no, eso es todo. contraentrega"),
        (("respóndeme con el número",), "1"),
        (("el nit", "registrad"), esc["identificacion"]),
        (("confirmas", "confirmar", "¿está correcto", "¿todo bien"), "sí, confirmo"),
        (("forma de pago", "contraentrega", "pago en línea"), "contraentrega"),
        (("dirección", "domicilio", "¿es correcta"), "sí, esa está bien"),
        (("médico", "doctor", "doctora"), d["requesting_doctor"]),
        (("propietari", "dueñ", "tutor"), d["owner_name"]),
        (("especie",), d["species"]),
        (("raza",), d["breed"]),
        (("sexo", "macho o hembra"), d["sex"]),
        (("edad", "años tiene"), d["patient_age"]),
        (("agregamos otro análisis", "la dejamos así"), "no, así está bien"),
        (("fecha", "tomó la muestra", "toma de la muestra", "tomaron la muestra"), "hoy"),
        (("observaci",), "sin observaciones"),
        (("paciente", "mascota"), d["patient_name"]),
        (("análisis", "perfil", "examen"), "hemograma"),
        (("veterinaria", "clínica", "identific"), esc["identificacion"]),
    ]
    for claves, texto in reglas:
        if any(c in r for c in claves):
            return texto
    return "sí"
