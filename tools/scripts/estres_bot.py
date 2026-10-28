"""Estrés del bot SIN tokens: N veterinarias pidiendo recogidas a la vez por el webhook real.

Recorre la pila de producción entera: POST al webhook de Chatwoot de un servidor local →
debounce (5 s / 20 s, como en render.yaml) → `process_turn` real → respuesta. El modelo y
las escrituras van simulados (`estres_bot_simulacion.py`); las lecturas (clientes reales,
catálogo, motorizados) van a Supabase en SOLO LECTURA y la red de seguridad corta todo lo
demás. Cada veterinaria es un cliente real distinto, así que al final se verifica que
ninguna orden quedó con el cliente o el paciente de otro chat.

Uso:
  python tools/scripts/estres_bot.py --chats 10 25 40          # escalones
  python tools/scripts/estres_bot.py --chats 25 --ia lenta      # OpenAI tarda 15-40 s
  python tools/scripts/estres_bot.py --chats 25 --ia falla      # 30% de llamadas caídas
"""
import argparse
import logging
import os
import queue
import random
import statistics
import sys
import threading
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ), str(Path(__file__).parent)]
# Los valores de PRODUCCIÓN (render.yaml), no los del .env local. Antes de importar la app.
os.environ.update(MESSAGE_DEBOUNCE_SECONDS="5", MESSAGE_DEBOUNCE_MAX_WAIT="20", FSM_ENFORCE="false",
                  ANARVET_ENABLED="false", PDF_ENABLED="false")

import red_segura  # noqa: E402

red_segura.activar(permitir_openai=False)
import estres_bot_simulacion as sim  # noqa: E402
from estres_informe import Muestreador, pct, resumen_ms  # noqa: E402
import httpx  # noqa: E402
from app import main as appmain  # noqa: E402
from app.config import CHATWOOT_WEBHOOK_SECRET  # noqa: E402
from app.services import db  # noqa: E402

for _ruidoso in ("werkzeug", "httpx", "app.main"):
    logging.getLogger(_ruidoso).setLevel(logging.WARNING)
NOMBRES = ("Luna Max Rocky Kira Toby Nala Simba Coco Lola Bruno Maya Thor Mia Zeus Lucas Kiara Rex "
           "Canela Bobby Frida Tango Pelusa Milo Duque Sasha Oreo Chispa Bimba Ramón Lupe Tofu Gala "
           "Nerón Pipa Baloo Tita Romeo Olivia Pancho Greta Brisa Cleo Dante Fiona Kobu").split()
MEDICOS = [f"Dra. {n} {a}" for n in ("Laura", "Ana", "Paula", "Diana", "Sofía", "Marta", "Clara")
           for a in ("Méndez", "Ruiz", "Castro", "Rojas", "Pardo", "Vargas", "Torres")]
PROPIETARIOS = [f"{n} {a}" for n in ("Pedro", "Juan", "Luis", "Carlos", "Jorge", "Andrés", "Felipe")
                for a in ("Gómez", "Díaz", "Mora", "Silva", "Ortiz", "Peña", "Ríos")]
medidas = {"turnos": [], "db_ms": [], "alertas": [], "enviados": defaultdict(int)}
_m = threading.Lock()
colas: dict[str, queue.Queue] = defaultdict(queue.Queue)


def _clientes_reales(n: int) -> list[dict]:
    """Clientes activos con NIT y dirección, sin NIT ni nombre repetido (sedes), y con
    motorizado asignado — como todo cliente registrado de A3."""
    filas = db._paginado(lambda: db._client.table("clients").select("id, clinic_name, tax_id, address")
                         .eq("is_active", True).order("id"), 3000)
    asignados = {a["client_id"] for a in db._paginado(
        lambda: db._client.table("client_courier_assignment").select("client_id").order("id"), 5000)}
    nits = defaultdict(int)
    nombres = defaultdict(int)
    for c in filas:
        nits[str(c.get("tax_id") or "")] += 1
        nombres[(c.get("clinic_name") or "").strip().lower()] += 1
    aptos = [c for c in filas if c.get("tax_id") and c.get("address") and c["id"] in asignados
             and nits[str(c["tax_id"])] == 1 and nombres[c["clinic_name"].strip().lower()] == 1
             and len(str(c["tax_id"])) >= 6]
    random.Random(7).shuffle(aptos)
    return aptos[:n]


def _escenario(i: int, cliente: dict) -> dict:
    especie, raza = (("canino", "criollo"), ("felino", "siamés"), ("canino", "labrador"))[i % 3]
    datos = {"patient_name": NOMBRES[i % len(NOMBRES)], "species": especie, "breed": raza,
             "sex": ("macho", "hembra")[i % 2], "patient_age": f"{2 + i % 9} años",
             "owner_name": PROPIETARIOS[i % len(PROPIETARIOS)], "requesting_doctor": MEDICOS[i % len(MEDICOS)],
             "exam_type": "hemograma", "sample_taken_date": "hoy", "observations": "sin observaciones",
             "clinic_name": cliente["clinic_name"], "tax_id": str(cliente["tax_id"])}
    ident = f"NIT {cliente['tax_id']}" if i % 10 < 7 else f"Somos {cliente['clinic_name']}"
    return {"client_id": cliente["id"], "clinic_name": cliente["clinic_name"], "tax_id": str(cliente["tax_id"]),
            "identificacion": ident, "datos": datos}


def _turno_medido(real):
    def turno(chat_id, text, on_progress=None, channel="telegram"):
        sim.actual.chat, sim.actual.ia_ms, sim.actual.db_n, sim.actual.db_ms = chat_id, 0, 0, 0
        inicio, ok, respuesta, error = time.monotonic(), True, None, None
        try:
            respuesta = real(chat_id, text, on_progress=on_progress, channel=channel)
            return respuesta
        except Exception as exc:
            ok, error = False, f"{type(exc).__name__}: {exc}"[:160]
            raise
        finally:
            with _m:
                medidas["turnos"].append({"chat": chat_id, "ms": (time.monotonic() - inicio) * 1000,
                                          "ia_ms": sim.actual.ia_ms, "db_n": sim.actual.db_n,
                                          "db_ms": sim.actual.db_ms, "ok": ok, "error": error,
                                          "fragmentos": text.count("\n") + 1})
            sim.actual.chat = None
            colas[chat_id].put(respuesta)
    return turno


def _medir_supabase():
    original = httpx.Client.send

    def send(self, request, *args, **kwargs):
        inicio = time.monotonic()
        try:
            return original(self, request, *args, **kwargs)
        finally:
            ms = (time.monotonic() - inicio) * 1000
            if getattr(sim.actual, "chat", None):
                sim.actual.db_n += 1
                sim.actual.db_ms += ms
            with _m:
                medidas["db_ms"].append(ms)
    httpx.Client.send = send


def _parches(real_turn) -> list:
    escritoras = [n for n in ("approve_pending_client", "reject_pending_client", "update_request", "insert_rows",
                              "update_rows", "create_request_event", "update_request_order_fields",
                              "record_custom_profile_use", "create_pending_client_review", "update_request_status",
                              "create_client", "upsert_client_assignment") if n not in sim.SIMULADAS]
    p = [patch(f"app.services.db.{n}", new=f) for n, f in sim.SIMULADAS.items()]
    p += [patch(f"app.services.db.{n}", new=(lambda n: lambda *a, **k: sim.contar(f"escritura:{n}"))(n))
          for n in escritoras]

    def alerta(contexto, exc, detalle=""):
        with _m:
            medidas["alertas"].append(f"{contexto}: {type(exc).__name__}")
        return False

    def enviado(canal):
        def send(chat_id, text, *a, **k):
            with _m:
                medidas["enviados"][canal] += 1
        return send
    p += [patch("app.main.get_or_create_session", new=sim.get_or_create_session),
          patch("app.services.ai._completar", new=sim.completar),
          patch("app.main.process_turn", new=_turno_medido(real_turn)),
          patch("app.services.chatwoot.send_message", new=enviado("chatwoot")),
          patch("app.services.chatwoot.send_typing", new=lambda *a, **k: None),
          patch("app.services.chatwoot.assign_team", new=lambda *a, **k: sim.contar("handoff")),
          patch("app.services.telegram.send_message", new=enviado("telegram")),
          patch("app.services.telegram.send_typing", new=lambda *a, **k: None),
          patch("app.main.deliver_pending", new=lambda *a, **k: 0),
          patch("app.billing.invoice_order", new=lambda *a, **k: sim.contar("factura")),
          patch("app.services.system_db.registrar", new=lambda kind, comp, level="info", *a, **k:
                sim.contar(f"evento:{kind}:{level}"))]
    p += [patch(f"{m}.notify_error", new=alerta) for m in ("app.main", "app.alerts", "app.results_delivery")]
    return p


def _postear(base: str, conv: str, texto: str) -> int:
    import json

    cuerpo = json.dumps({"event": "message_created", "message_type": "incoming", "content": texto,
                         "conversation": {"id": conv, "channel": "Channel::Telegram"}}).encode()
    req = urllib.request.Request(f"{base}/chatwoot/webhook?token={CHATWOOT_WEBHOOK_SECRET}", data=cuerpo,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def _veterinaria(base: str, conv: str, esc: dict, rafagas: float, max_turnos: int, res: dict) -> None:
    """Una veterinaria: saluda, pide la recogida y contesta lo que el bot pregunta hasta
    que el pedido se cierra. Algunas respuestas salen partidas en ráfaga (2 mensajes en
    menos de 1,5 s), como escribe la gente real: el debounce debe juntarlas en UN turno."""
    rnd = random.Random(conv)
    texto, enviados = "Hola", 0
    time.sleep(rnd.uniform(0, 3))  # que no arranquen todas en el mismo milisegundo
    for _ in range(max_turnos):
        palabras = texto.split()
        if len(palabras) >= 3 and rnd.random() < rafagas:
            corte = rnd.randint(1, len(palabras) - 1)
            partes = [" ".join(palabras[:corte]), " ".join(palabras[corte:])]
        else:
            partes = [texto]
        for i, parte in enumerate(partes):
            if i:
                time.sleep(rnd.uniform(0.3, 1.5))
            if _postear(base, conv, parte) != 200:
                res["errores_http"] += 1
        enviados += 1
        try:
            respuesta = colas[conv].get(timeout=180)
        except queue.Empty:
            res["sin_respuesta"].append(conv)
            return
        if any(p["external_chat_id"] == conv and p["status"] == "cerrado" for p in sim.pedidos.values()):
            res["completos"].append(conv)
            break
        if respuesta is None:
            break
        texto = sim.responder(respuesta, esc)
    res["rafagas_enviadas"][conv] = enviados


def _verificar_aislamiento() -> list[str]:
    """Cada orden con el cliente y el paciente de SU chat — ninguno de otro."""
    problemas = []
    pacientes = {c: e["datos"]["patient_name"] for c, e in sim.escenarios.items()}
    for o in sim.ordenes:
        esc = sim.escenarios[o["chat_id"]]
        paciente = o["fields"].get("patient_name") or ""
        if o["client_id"] != esc["client_id"]:
            problemas.append(f"{o['chat_id']}: orden con client_id de otro ({o['client_id']})")
        if esc["datos"]["patient_name"].lower() not in paciente.lower():
            ajenos = [c for c, p in pacientes.items() if p.lower() in paciente.lower() and c != o["chat_id"]]
            problemas.append(f"{o['chat_id']}: paciente {paciente!r}" + (f" (es de {ajenos})" if ajenos else ""))
    return problemas


def escalon(base: str, n: int, clientes: list[dict], rafagas: float, max_turnos: int) -> dict:
    for coleccion in (sim.sesiones, sim.mensajes, sim.pedidos, sim.contadores, sim.escenarios):
        coleccion.clear()
    sim.ordenes.clear()
    for clave in ("turnos", "db_ms", "alertas"):
        medidas[clave].clear()
    medidas["enviados"].clear()
    res = {"errores_http": 0, "sin_respuesta": [], "completos": [], "rafagas_enviadas": {}}
    convs = []
    for i in range(n):
        conv = f"9{n:02d}{i:04d}"
        sim.escenarios[conv] = _escenario(i, clientes[i])
        convs.append(conv)
    inicio = time.monotonic()
    with Muestreador(f"{base}/health") as muestras:
        hilos = [threading.Thread(target=_veterinaria, args=(base, c, sim.escenarios[c], rafagas, max_turnos, res))
                 for c in convs]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
    res["duracion_s"] = time.monotonic() - inicio
    res["muestras"] = muestras
    return res


def informe(n: int, res: dict) -> bool:
    t = medidas["turnos"]
    propio = [x["ms"] - x["ia_ms"] for x in t if x["ok"]]
    fallidos = [x for x in t if not x["ok"]]
    turnos_por_chat = defaultdict(int)
    for x in t:
        turnos_por_chat[x["chat"]] += 1
    partidos = sum(1 for c, k in res["rafagas_enviadas"].items() if turnos_por_chat[c] != k)
    aislamiento = _verificar_aislamiento()
    escapes = {k: v for k, v in sim.contadores.items() if k.startswith("escritura:")}
    eventos = ", ".join(f"{k.split(':', 1)[1]}={v}" for k, v in sorted(sim.contadores.items())
                        if k.startswith("evento:"))
    print(f"\n=== {n} veterinarias a la vez · IA {sim.IA['modo']} · {res['duracion_s']:.0f}s ===")
    print(f"pedidos completos: {len(res['completos'])}/{n} · órdenes: {len(sim.ordenes)} · "
          f"facturas (simuladas): {sim.contadores.get('factura', 0)}")
    print(f"turnos: {len(t)} · fallidos: {len(fallidos)} · sin respuesta: {len(res['sin_respuesta'])} · "
          f"HTTP != 200: {res['errores_http']}")
    print(f"turno completo: {resumen_ms([x['ms'] for x in t])}")
    print(f"código propio (turno - IA): {resumen_ms(propio)}")
    print(f"consultas a Supabase por turno: p50 {pct([x['db_n'] for x in t], 50):.0f} · "
          f"máx {max([x['db_n'] for x in t], default=0)} · latencia {resumen_ms(medidas['db_ms'])}")
    print(f"debounce: chats con ráfagas mal agrupadas: {partidos}")
    print(f"aislamiento entre chats: {'OK' if not aislamiento else f'{len(aislamiento)} PROBLEMA(S)'}")
    for linea in aislamiento[:8]:
        print("   ", linea)
    print(f"alertas al responsable técnico: {len(medidas['alertas'])} · eventos: {eventos}")
    for linea in res["muestras"].informe():
        print(linea)
    if escapes:
        print(f"escrituras sin simular (no salieron, se contaron): {escapes}")
    for x in fallidos[:5]:
        print("   turno fallido:", x["chat"], x["error"])
    for c in res["sin_respuesta"][:5]:
        print("   sin respuesta:", c, sim.mensajes[c][-1:] if sim.mensajes[c] else "")
    if n == 1:  # calibración: la conversación entera
        for m in next(iter(sim.mensajes.values()), []):
            print(f"   {m['role'][:3].upper()}: {m['content'][:160]!r}")
    incompletos = [c for c in sim.escenarios if c not in res["completos"]]
    for c in incompletos[:3]:
        print(f"   incompleto {c}: último bot -> {(sim.sesiones.get(c, {}).get('last_bot_message') or '')[:140]!r}")
    normal = sim.IA["modo"] == "normal"
    return not (normal and (fallidos or incompletos)) and not aislamiento and not res["sin_respuesta"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chats", type=int, nargs="+", default=[10])
    ap.add_argument("--ia", choices=("normal", "lenta", "falla"), default="normal")
    ap.add_argument("--rafagas", type=float, default=0.3)
    ap.add_argument("--max-turnos", type=int, default=35)
    args = ap.parse_args()
    if max(args.chats) > 40:
        raise SystemExit("Tope acordado con el usuario: 40 usuarios simultáneos sobre la base real.")
    sim.IA["modo"] = args.ia
    clientes = _clientes_reales(max(args.chats))
    print(f"{len(clientes)} veterinarias reales elegidas (NIT y nombre únicos, con motorizado)")
    _medir_supabase()
    parches = _parches(appmain.process_turn)
    for p in parches:
        p.start()
    from werkzeug.serving import make_server

    servidor = make_server("127.0.0.1", 0, appmain.app, threaded=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{servidor.server_port}"
    ok = True
    try:
        for n in args.chats:
            ok = informe(n, escalon(base, n, clientes, args.rafagas, args.max_turnos)) and ok
    finally:
        servidor.shutdown()
        for p in parches:
            p.stop()
    ok = ok and not red_segura.bloqueos
    print("\nRESULTADO:", "OK" if ok else "CON FALLAS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
