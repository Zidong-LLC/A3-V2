"""Carga web en SOLO LECTURA: personal del laboratorio y veterinarias del portal navegando a la vez.

Levanta la app en un servidor local con el MISMO tope que producción (gunicorn 1 worker ×
8 hilos: el pedido 9 espera) y la red de seguridad encendida: las pantallas leen Supabase
real; cualquier escritura o llamada externa queda bloqueada y contada. Mide por pantalla
p50/p95/máx y errores, y sobre todo `/health` mientras dura la carga: Render corta el
health check a los 5 s (ERR-182) y reinicia el servicio — y un reinicio corta los chats.

Uso:
  python tools/scripts/estres_web.py --usuarios 10 20 40 --segundos 60
"""
import argparse
import os
import random
import re
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent)]
# Anarvet encendido como en producción: las pantallas del espejo leen Supabase; si alguna
# intentara conectarse a Anarvet en vivo, la red de seguridad lo bloquea y lo cuenta.
os.environ.update(ANARVET_ENABLED="true", PDF_ENABLED="false", MESSAGE_DEBOUNCE_SECONDS="5")

import red_segura  # noqa: E402

red_segura.activar(permitir_openai=False)
import logging  # noqa: E402

import requests  # noqa: E402
from estres_informe import Muestreador, pct, resumen_ms  # noqa: E402

from app.config import DASHBOARD_ADMIN_PASSWORD, DASHBOARD_ADMIN_USER  # noqa: E402
from app.main import app  # noqa: E402
from app.services import db  # noqa: E402

for _ruidoso in ("werkzeug", "httpx"):
    logging.getLogger(_ruidoso).setLevel(logging.WARNING)

PERSONAL = ["/dashboard", "/operacion", "/clientes", "/clientes/nuevo", "/solicitudes", "/solicitudes/nueva",
            "/muestras", "/motorizados", "/facturacion", "/pedidos", "/resultados", "/resultados/anarvet",
            "/resultados/anarvet/clientes", "/agenda", "/cargas", "/usuarios", "/api/dashboard/overview",
            "/api/dashboard/invoices", "/api/dashboard/custom-profiles", "/api/dashboard/historial",
            "/api/dashboard/anarvet/clients", "/api/dashboard/neighborhood-search?q=kennedy",
            "/clientes/buscar?q=animal", "/clientes?q=animal+pet", "/api/dashboard/invoices/export"]
PORTAL = ["/portal/mis/solicitudes", "/portal/mis/solicitudes/nueva", "/portal/mis/perfil",
          "/portal/mis/resultados", "/portal/mis/notificaciones", "/portal/mis/cuenta"]
TRAZAS = ("Traceback (most recent call last)", "UndefinedError", "jinja2.exceptions", "Internal Server Error")


class _TopeDeHilos:
    """8 pedidos a la vez, como `--threads 8`: el resto espera turno."""

    def __init__(self, wsgi, n: int):
        self.wsgi, self.sem = wsgi, threading.BoundedSemaphore(n)

    def __call__(self, environ, start_response):
        with self.sem:
            return list(self.wsgi(environ, start_response))


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""


def _sesion_personal(base: str) -> requests.Session:
    s = requests.Session()
    token = _csrf(s.get(f"{base}/login", timeout=60).text)
    r = s.post(f"{base}/login", data={"username": DASHBOARD_ADMIN_USER, "password": DASHBOARD_ADMIN_PASSWORD,
                                      "csrf_token": token}, timeout=60, allow_redirects=False)
    if r.status_code not in (302, 303):
        raise SystemExit(f"No se pudo entrar al dashboard ({r.status_code}): revisar DASHBOARD_ADMIN_* del .env")
    return s


def _copia(sesion: requests.Session) -> requests.Session:
    """Una sesión por usuario virtual (requests.Session no se comparte entre hilos)."""
    s = requests.Session()
    s.cookies.update(sesion.cookies)
    return s


def _veterinarias(n: int) -> list[dict]:
    filas = db._paginado(lambda: db._client.table("clients").select("clinic_name, tax_id")
                         .eq("is_active", True).order("id"), 3000)
    nits = defaultdict(int)
    for c in filas:
        nits[str(c.get("tax_id") or "")] += 1
    aptas = [c for c in filas if c.get("tax_id") and nits[str(c["tax_id"])] == 1 and len(str(c["tax_id"])) >= 6]
    random.Random(11).shuffle(aptas)
    return aptas[:n]


def _sesion_portal(base: str, cliente: dict) -> requests.Session | None:
    s = requests.Session()
    token = _csrf(s.get(f"{base}/portal/login", timeout=60).text)
    r = s.post(f"{base}/portal/login", data={"clinic_name": cliente["clinic_name"], "nit": cliente["tax_id"],
                                             "csrf_token": token}, timeout=60, allow_redirects=False)
    return s if r.status_code in (302, 303) and "login" not in r.headers.get("Location", "") else None


def _usuario(base, sesion, rutas, fin, medidas, lock):
    rnd = random.Random(id(sesion))
    while time.monotonic() < fin:
        ruta = rnd.choice(rutas)
        inicio, status, traza = time.monotonic(), 0, False
        try:
            r = sesion.get(base + ruta, timeout=60, allow_redirects=False)
            status = r.status_code
            traza = any(t in r.text for t in TRAZAS)
        except requests.RequestException:
            status = -1  # timeout del lado del cliente: el navegador ya se rindió
        with lock:
            medidas[ruta.split("?")[0] + ("?" if "?" in ruta else "")].append(
                ((time.monotonic() - inicio) * 1000, status, traza))
        time.sleep(rnd.uniform(1.0, 3.0))  # lo que tarda una persona en leer y hacer clic


def escalon(base: str, n: int, segundos: int, personal, portal) -> bool:
    medidas, lock = defaultdict(list), threading.Lock()
    n_portal = min(len(portal), max(1, n * 3 // 10))
    plan = [(portal[i], PORTAL) for i in range(n_portal)] + [(_copia(personal), PERSONAL) for _ in range(n - n_portal)]
    fin = time.monotonic() + segundos
    with Muestreador(f"{base}/health") as muestras:
        hilos = [threading.Thread(target=_usuario, args=(base, s, rutas, fin, medidas, lock)) for s, rutas in plan]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
    total = sum(len(v) for v in medidas.values())
    malos = sum(1 for v in medidas.values() for _, s, t in v if s >= 500 or s < 0 or t)
    print(f"\n=== {n} usuarios ({n - n_portal} del laboratorio, {n_portal} del portal) · {segundos}s ===")
    print(f"pedidos: {total} · con error (5xx, traza o timeout 60s): {malos}")
    print(f"{'pantalla':45s} {'n':>4} {'p50':>7} {'p95':>7} {'máx':>7}  errores")
    for ruta, v in sorted(medidas.items(), key=lambda kv: -pct([m for m, _, _ in kv[1]], 95)):
        ms = [m for m, _, _ in v]
        err = [s for _, s, t in v if s >= 500 or s < 0 or t]
        otros = sorted({s for _, s, _ in v if s not in (200, 302)} - set(err))
        print(f"{ruta[:45]:45s} {len(v):>4} {pct(ms, 50) / 1000:>6.2f}s {pct(ms, 95) / 1000:>6.2f}s "
              f"{max(ms) / 1000:>6.2f}s  {len(err) or ''}{' status ' + str(otros) if otros else ''}")
    for linea in muestras.informe():
        print(linea)
    lentos = sum(1 for m, s in muestras.salud if m > 5000 or s != 200)
    return malos == 0 and lentos == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usuarios", type=int, nargs="+", default=[10])
    ap.add_argument("--segundos", type=int, default=60)
    ap.add_argument("--hilos", type=int, default=8, help="los --threads de gunicorn (Dockerfile)")
    args = ap.parse_args()
    if max(args.usuarios) > 40:
        raise SystemExit("Tope acordado con el usuario: 40 usuarios simultáneos sobre la base real.")
    from werkzeug.serving import make_server

    servidor = make_server("127.0.0.1", 0, _TopeDeHilos(app, args.hilos), threaded=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{servidor.server_port}"
    personal = _sesion_personal(base)
    portal = [s for s in (_sesion_portal(base, c) for c in _veterinarias(12)) if s]
    print(f"sesiones: laboratorio OK · portal {len(portal)} veterinarias reales · {args.hilos} hilos")
    ok = all([escalon(base, n, args.segundos, personal, portal) for n in args.usuarios])
    servidor.shutdown()
    ok = ok and not red_segura.bloqueos
    print("\nRESULTADO:", "OK" if ok else "CON FALLAS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
