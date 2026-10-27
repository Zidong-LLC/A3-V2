"""Métricas del panel de sistema: estado en vivo de cada servicio, resúmenes puros de
los eventos y de las conversaciones, y el gasto del mes.

Las funciones `resumen_*` son puras (listas de filas → dict) y se prueban sin base.
"""
import json
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.config import (APP_TIMEZONE, CHATWOOT_API_TOKEN, CHATWOOT_URL, OPENAI_ADMIN_KEY,
                        RENDER_API_KEY, RENDER_SERVICE_ID, SUPABASE_ACCESS_TOKEN, SUPABASE_URL,
                        TELEGRAM_BOT_TOKEN)
from app.health import _timed

# Precio de lista por plan (USD/mes), para estimar el gasto cuando la API dice el plan pero
# no la factura. Si Render o Supabase cambian precios, se ajusta acá.
PRECIO_PLAN_RENDER = {"free": 0, "starter": 7, "standard": 25, "pro": 85, "pro plus": 175, "pro max": 225, "pro ultra": 450}
PRECIO_PLAN_SUPABASE = {"free": 0, "pro": 25, "team": 599}

COMPONENTES = ("supabase", "openai", "telegram", "chatwoot", "whatsapp", "alegra", "anarvet", "pdf", "bot", "web")


def componente_de(contexto: str, exc: BaseException | None = None) -> str:
    """A qué servicio pertenece un error, por el contexto del aviso y el tipo de excepción."""
    servicios = (("openai", "openai"), ("whatsapp", "whatsapp"), ("chatwoot", "chatwoot"),
                 ("telegram", "telegram"), ("alegra", "alegra"), ("anarvet", "anarvet"),
                 ("pdf", "pdf"), ("supabase", "supabase"), ("postgrest", "supabase"))
    # Primero la excepción (su módulo y su texto dicen QUÉ se cayó), después el contexto
    # (dice DÓNDE pasó): un turno de Telegram que falla por Supabase es un error de Supabase.
    excepcion = f"{type(exc).__module__} {type(exc).__name__} {exc}".lower() if exc else ""
    for texto in (excepcion, (contexto or "").lower()):
        for clave, componente in servicios:
            if clave in texto:
                return componente
    return "bot" if "turno" in (contexto or "").lower() else "web"


def _chatwoot_ping() -> None:
    req = urllib.request.Request(f"{CHATWOOT_URL}/api", headers={"api_access_token": CHATWOOT_API_TOKEN})
    with urllib.request.urlopen(req, timeout=8) as r:
        if json.loads(r.read()).get("data_services") != "ok":
            raise RuntimeError("Chatwoot reporta su base de datos como «failing»")


def _telegram_ping() -> None:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=8) as r:
        if not json.loads(r.read()).get("ok"):
            raise RuntimeError("getMe no respondió ok")


def estado_servicios() -> dict:
    """Los chequeos de /health/detalle más Chatwoot y Telegram, que el health no mira.
    Los tres a la vez: en serie sumaban 5-9 s por carga del panel."""
    from app.health import check_all

    with ThreadPoolExecutor(max_workers=3) as hilos:
        base = hilos.submit(check_all)
        chatwoot = hilos.submit(_timed, _chatwoot_ping) if CHATWOOT_URL else None
        telegram = hilos.submit(_timed, _telegram_ping) if TELEGRAM_BOT_TOKEN else None
    estado = dict(base.result()[0].get("checks", {}))
    estado["chatwoot"] = chatwoot.result() if chatwoot else {"status": "not_configured"}
    estado["telegram"] = telegram.result() if telegram else {"status": "not_configured"}
    return estado


def _dia(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(APP_TIMEZONE).strftime("%d/%m")
    except (ValueError, AttributeError):
        return "?"


def resumen_errores(filas: list[dict]) -> dict:
    por_componente = Counter(f.get("component") or "web" for f in filas)
    por_dia = Counter(_dia(f.get("created_at", "")) for f in filas)
    return {"total": len(filas), "por_componente": dict(por_componente.most_common()),
            "por_dia": dict(sorted(por_dia.items())), "ultimos": filas[:60]}


def resumen_turnos(filas: list[dict]) -> dict:
    """Cuántos turnos atendió el bot, cuánto tardaron y cuántos fallaron."""
    tiempos = sorted(int((f.get("details") or {}).get("ms") or 0) for f in filas)
    fallidos = [f for f in filas if not (f.get("details") or {}).get("ok", True)]
    por_canal = Counter((f.get("details") or {}).get("channel") or "?" for f in filas)
    p50 = tiempos[len(tiempos) // 2] if tiempos else 0
    p95 = tiempos[int(len(tiempos) * 0.95)] if tiempos else 0
    return {"total": len(filas), "fallidos": len(fallidos), "p50_s": round(p50 / 1000, 1), "p95_s": round(p95 / 1000, 1),
            "por_canal": dict(por_canal), "chats": len({f.get("chat_id") for f in filas if f.get("chat_id")})}


def resumen_llm(filas: list[dict]) -> dict:
    entrada = sum(int((f.get("details") or {}).get("prompt_tokens") or 0) for f in filas)
    salida = sum(int((f.get("details") or {}).get("completion_tokens") or 0) for f in filas)
    por_dia = defaultdict(int)
    for f in filas:
        d = f.get("details") or {}
        por_dia[_dia(f.get("created_at", ""))] += int(d.get("prompt_tokens") or 0) + int(d.get("completion_tokens") or 0)
    return {"llamadas": len(filas), "tokens_entrada": entrada, "tokens_salida": salida,
            "tokens_por_dia": dict(sorted(por_dia.items()))}


def resumen_conversaciones(sesiones: list[dict], mensajes: list[dict], solicitudes: list[dict]) -> dict:
    ahora = datetime.now(timezone.utc)
    def horas(ts):
        try:
            return (ahora - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() / 3600
        except (ValueError, AttributeError):
            return 1e9
    activas_24h = [s for s in sesiones if horas(s.get("updated_at", "")) <= 24]
    bloqueadas = sum(1 for s in sesiones if (s.get("captured_fields") or {}).get("_blocked"))
    escaladas = Counter(s.get("handoff_area") or "sin área" for s in sesiones if s.get("requires_handoff"))
    return {
        "conversaciones_7d": len(sesiones), "activas_24h": len(activas_24h),
        "por_canal": dict(Counter(s.get("channel") or "telegram" for s in sesiones)),
        "por_fase": dict(Counter(s.get("phase_current") or "sin fase" for s in activas_24h)),
        "escaladas": dict(escaladas), "bloqueadas": bloqueadas,
        "mensajes_7d": len(mensajes), "mensajes_cliente_7d": sum(1 for m in mensajes if m.get("role") == "user"),
        "mensajes_por_dia": dict(sorted(Counter(_dia(m.get("created_at", "")) for m in mensajes).items())),
        "ordenes_7d": len(solicitudes),
        "ordenes_por_canal": dict(Counter(s.get("entry_channel") or "telegram" for s in solicitudes)),
    }


_cache_openai: dict = {"hasta": 0.0, "valor": None}


def gasto_openai_mes() -> dict:
    """Gasto real del mes en OpenAI (API de costos, requiere la Admin key). Cache de 10 min."""
    if not OPENAI_ADMIN_KEY:
        return {"disponible": False, "motivo": "Falta OPENAI_ADMIN_KEY (Admin key con permiso api.usage.read)"}
    if _cache_openai["valor"] and time.monotonic() < _cache_openai["hasta"]:
        return _cache_openai["valor"]
    inicio = int(datetime.now(APP_TIMEZONE).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
    req = urllib.request.Request(f"https://api.openai.com/v1/organization/costs?start_time={inicio}&limit=31",
                                 headers={"Authorization": f"Bearer {OPENAI_ADMIN_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            datos = json.loads(r.read())
    except Exception as exc:  # noqa: BLE001 — el panel muestra el motivo, no se cae
        return {"disponible": False, "motivo": f"No se pudo leer OpenAI: {str(exc)[:120]}"}
    total = sum((res.get("amount") or {}).get("value") or 0 for b in datos.get("data", []) for res in b.get("results", []))
    valor = {"disponible": True, "usd": round(total, 2)}
    _cache_openai.update(valor=valor, hasta=time.monotonic() + 600)
    return valor


def _get_json(url: str, headers: dict, timeout: int = 12) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "A3-sistema/1.0", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _cacheado(clave: str, fn, segundos: int = 600) -> dict:
    entrada = _cache_servicios.get(clave)
    if entrada and time.monotonic() < entrada["hasta"]:
        return entrada["valor"]
    valor = fn()
    _cache_servicios[clave] = {"valor": valor, "hasta": time.monotonic() + segundos}
    return valor


_cache_servicios: dict = {}


def estado_render() -> dict:
    """Plan, si está suspendido y el último deploy, por la API de Render."""
    if not (RENDER_API_KEY and RENDER_SERVICE_ID):
        return {"disponible": False, "motivo": "Faltan RENDER_API_KEY y RENDER_SERVICE_ID"}

    def leer():
        h = {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}
        servicio = _get_json(f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}", h)
        deploys = _get_json(f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys?limit=1", h)
        ultimo = ((deploys[0] if isinstance(deploys, list) and deploys else {}).get("deploy") or {})
        plan = str((servicio.get("serviceDetails") or {}).get("plan") or "").lower()
        suspendido = servicio.get("suspended") == "suspended"
        return {"disponible": True, "plan": plan or "?", "suspendido": suspendido,
                "estado": "suspendido" if suspendido else ("activo" if ultimo.get("status") == "live" else ultimo.get("status") or "?"),
                "ultimo_deploy": (ultimo.get("finishedAt") or ultimo.get("createdAt") or "")[:16].replace("T", " "),
                "region": (servicio.get("serviceDetails") or {}).get("region") or "",
                "usd": 0 if suspendido else PRECIO_PLAN_RENDER.get(plan, 0)}
    try:
        return _cacheado("render", leer)
    except Exception as exc:  # noqa: BLE001
        return {"disponible": False, "motivo": f"Render no respondió: {str(exc)[:100]}"}


def estado_supabase() -> dict:
    """Estado del proyecto, plan de la organización y add-ons, por la Management API."""
    ref = (SUPABASE_URL or "").split("//")[-1].split(".")[0]
    if not (SUPABASE_ACCESS_TOKEN and ref):
        return {"disponible": False, "motivo": "Falta SUPABASE_ACCESS_TOKEN"}

    def leer():
        h = {"Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}"}
        proyecto = _get_json(f"https://api.supabase.com/v1/projects/{ref}", h)
        # El plan y el nombre de la organización solo los ve un Owner/Admin: con un rol
        # menor el proyecto igual se reporta (estado y región), sin el gasto.
        try:
            org = _get_json(f"https://api.supabase.com/v1/organizations/{proyecto.get('organization_slug')}", h)
            addons = _get_json(f"https://api.supabase.com/v1/projects/{ref}/billing/addons", h)
            extras = sum(float(((a.get("variant") or {}).get("price") or {}).get("amount") or 0)
                         for a in (addons.get("selected_addons") or []))
            plan, nombre_org = str(org.get("plan") or "?").lower(), org.get("name") or ""
        except Exception:  # noqa: BLE001 — sin permiso para ver la organización
            plan, nombre_org, extras = "sin permiso (rol de la cuenta)", proyecto.get("organization_slug") or "", 0
        return {"disponible": True, "plan": plan, "organizacion": nombre_org,
                "estado": proyecto.get("status") or "?", "region": proyecto.get("region") or "",
                "usd": PRECIO_PLAN_SUPABASE.get(plan, 0) + extras}
    try:
        return _cacheado("supabase", leer)
    except Exception as exc:  # noqa: BLE001
        return {"disponible": False, "motivo": f"Supabase no respondió: {str(exc)[:100]}"}


def servicios_traspaso(costos: list[dict], openai: dict, salud: dict, llm: dict) -> list[dict]:
    """Los servicios que se traspasan al cliente: estado, plan y gasto del mes de cada uno.
    El gasto sale de la API cuando la hay; si no, del valor cargado a mano en `system_costs`."""
    manual = {c.get("service"): c for c in costos}

    def fila(clave, nombre, estado, detalle, auto: dict | None, fuente_auto: str):
        a_mano = manual.get(clave) or {}
        if auto and auto.get("disponible"):
            return {"clave": clave, "nombre": nombre, "estado": estado, "detalle": detalle,
                    "usd": round(float(auto.get("usd") or 0), 2), "fuente": fuente_auto, "manual": False}
        motivo = (auto or {}).get("motivo") or ""
        if clave not in manual:  # sin API y sin fila a mano (OpenAI sin Admin key): no se inventa
            return {"clave": clave, "nombre": nombre, "estado": estado, "detalle": f"{detalle} {motivo}".strip(),
                    "usd": 0.0, "fuente": "sin acceso a la API", "manual": False}
        return {"clave": clave, "nombre": nombre, "estado": estado, "detalle": f"{detalle} {motivo}".strip(),
                "usd": round(float(a_mano.get("monthly_usd") or 0), 2), "fuente": "cargado a mano",
                "manual": True, "nota": a_mano.get("note") or ""}

    render, supabase = estado_render(), estado_supabase()
    chat = salud.get("chatwoot") or {}
    filas = [
        fila("openai", "OpenAI (IA del bot)", "activo" if (salud.get("openai") or {}).get("status") == "ok" else "revisar",
             f"{llm.get('llamadas', 0)} llamadas · {llm.get('tokens_entrada', 0) + llm.get('tokens_salida', 0):,} tokens en {7} días".replace(",", "."),
             openai, "API de costos de OpenAI (mes en curso)"),
        fila("render", "Render (servidor)", render.get("estado", "sin acceso") if render.get("disponible") else "sin acceso",
             f"plan {render.get('plan')} · {render.get('region')} · último deploy {render.get('ultimo_deploy')}" if render.get("disponible") else "",
             render, "plan leído por la API de Render"),
        fila("supabase", "Supabase (base y PDFs)", supabase.get("estado", "sin acceso") if supabase.get("disponible") else "sin acceso",
             f"plan {supabase.get('plan')} · org {supabase.get('organizacion')} · {supabase.get('region')}" if supabase.get("disponible") else "",
             supabase, "plan leído por la API de Supabase"),
        fila("chatwoot", "Chatwoot (VPS / EasyPanel)", "activo" if chat.get("status") == "ok" else ("falla" if chat.get("status") == "error" else "?"),
             chat.get("error") or f"{chat.get('latency_ms', '?')} ms", None, ""),
    ]
    return filas
