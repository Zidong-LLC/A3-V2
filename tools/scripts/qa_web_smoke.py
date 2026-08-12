"""Smoke HTTP del portal del cliente y del dashboard del personal.

Recorre las pantallas reales contra un Flask ya levantado (no usa test_client:
la idea es ver lo mismo que verá el navegador en la demo). Por cada ruta valida
status esperado, que el HTML no traiga una traza de error y que rinda contenido.

Además prueba el aislamiento: sin sesión no se entra, y la sesión del portal no
abre el dashboard.

SOLO LECTURA: ningún GET de este script crea, modifica ni borra datos.

Uso:
    python tools/scripts/qa_web_smoke.py                  # portal + dashboard
    python tools/scripts/qa_web_smoke.py --base http://localhost:5000
    python tools/scripts/qa_web_smoke.py --request-id <uuid>   # incluye la orden de servicio
"""
import argparse
import re
import sys
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import DASHBOARD_ADMIN_USER, DASHBOARD_ADMIN_PASSWORD  # noqa: E402

# Marcadores de que el servidor devolvió una traza en vez de una pantalla.
ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "UndefinedError",
    "werkzeug.exceptions",
    "jinja2.exceptions",
    "Internal Server Error",
)

# Pantallas del portal del cliente. (ruta, status esperado, texto que debe aparecer)
PORTAL_PAGES = [
    ("/portal/mis/solicitudes", 200, "solicitud"),
    ("/portal/mis/solicitudes/nueva", 200, "Paciente"),
    ("/portal/mis/perfil", 200, None),
    ("/portal/mis/resultados", 200, None),
    ("/portal/mis/notificaciones", 200, None),
]

# Pantallas del personal.
DASHBOARD_PAGES = [
    ("/dashboard", 200, None),
    ("/operacion", 200, None),
    ("/clientes", 200, None),
    ("/clientes/nuevo", 200, None),
    ("/solicitudes", 200, None),
    ("/muestras", 200, None),
    ("/motorizados", 200, None),
    ("/facturacion", 200, None),
    ("/resultados", 200, None),
]

# GET de la API interna del dashboard (solo lectura).
DASHBOARD_API = [
    "/api/dashboard/overview",
    "/api/dashboard/invoices",
    "/api/dashboard/custom-profiles",
    "/api/dashboard/column-prefs",
    "/api/dashboard/neighborhood-search?q=kennedy",
]

_fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK  " if ok else "FALLA"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        _fails.append(f"{label} — {detail}")


def check_page(sess, base, path, expected_status, must_contain) -> None:
    try:
        r = sess.get(base + path, timeout=60, allow_redirects=False)
    except Exception as e:
        check(path, False, f"{type(e).__name__}: {e}")
        return
    if r.status_code != expected_status:
        check(path, False, f"status {r.status_code} (esperado {expected_status})")
        return
    body = r.text
    for marker in ERROR_MARKERS:
        if marker in body:
            check(path, False, f"traza en el HTML: {marker}")
            return
    if must_contain and must_contain.lower() not in body.lower():
        check(path, False, f"no aparece {must_contain!r}")
        return
    check(path, True, f"{len(body)} bytes")


def portal_suite(base: str) -> None:
    print("\n== PORTAL DEL CLIENTE ==")
    anon = requests.Session()
    r = anon.get(base + "/portal/mis/solicitudes", timeout=30, allow_redirects=False)
    check("sin sesión → redirect a login", r.status_code in (301, 302),
          f"status {r.status_code}")

    sess = requests.Session()
    r = sess.get(base + "/portal/login", timeout=60, allow_redirects=False)
    check("/portal/login inicia sesión demo", r.status_code in (200, 302),
          f"status {r.status_code}")
    if not sess.cookies:
        check("cookie de sesión del portal", False, "el login no dejó cookie")
        return

    for path, status, needle in PORTAL_PAGES:
        check_page(sess, base, path, status, needle)

    r = sess.get(base + "/dashboard", timeout=30, allow_redirects=False)
    check("sesión de portal NO abre /dashboard", r.status_code in (301, 302),
          f"status {r.status_code}")
    r = sess.get(base + "/clientes", timeout=30, allow_redirects=False)
    check("sesión de portal NO abre /clientes", r.status_code in (301, 302),
          f"status {r.status_code}")

    fake = "11111111-1111-1111-1111-111111111111"
    r = sess.get(base + f"/portal/mis/resultados/{fake}", timeout=30, allow_redirects=False)
    check("resultado ajeno → 404", r.status_code == 404, f"status {r.status_code}")


def dashboard_suite(base: str, request_id: str | None) -> None:
    print("\n== DASHBOARD DEL PERSONAL ==")
    anon = requests.Session()
    r = anon.get(base + "/dashboard", timeout=30, allow_redirects=False)
    check("sin sesión → redirect a /login", r.status_code in (301, 302),
          f"status {r.status_code}")

    sess = requests.Session()
    # El login del personal exige csrf_token (app/main.py:_csrf_protect): hay que
    # leerlo del formulario antes de postear, igual que hace el navegador.
    form = sess.get(base + "/login", timeout=60).text
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', form)
    check("csrf_token presente en /login", bool(m))
    r = sess.post(base + "/login", timeout=60, allow_redirects=False,
                  data={"username": DASHBOARD_ADMIN_USER,
                        "password": DASHBOARD_ADMIN_PASSWORD,
                        "csrf_token": m.group(1) if m else ""})
    check("login del personal", r.status_code in (200, 302), f"status {r.status_code}")

    bad = requests.Session()
    bad.get(base + "/login", timeout=30)
    r = bad.post(base + "/login", timeout=30, allow_redirects=False,
                 data={"username": DASHBOARD_ADMIN_USER,
                       "password": DASHBOARD_ADMIN_PASSWORD})
    check("POST /login sin csrf_token → 400", r.status_code == 400, f"status {r.status_code}")

    for path, status, needle in DASHBOARD_PAGES:
        check_page(sess, base, path, status, needle)

    if request_id:
        check_page(sess, base, f"/ordenes-servicio/{request_id}/imprimir", 200, None)

    print("\n-- API interna (GET, solo lectura) --")
    for path in DASHBOARD_API:
        try:
            r = sess.get(base + path, timeout=60)
            if r.status_code != 200:
                check(path, False, f"status {r.status_code}")
                continue
            r.json()
            check(path, True, "JSON válido")
        except Exception as e:
            check(path, False, f"{type(e).__name__}: {str(e)[:80]}")

    print("\n-- API externa de plataforma --")
    # _auth_required solo exige token si PLATFORM_API_TOKEN está definido
    # (app/platform_api.py:26). Sin él la API queda abierta: eso es lo que se mide.
    from app.config import PLATFORM_API_TOKEN
    r = requests.get(base + "/api/platform/overview", timeout=30)
    if PLATFORM_API_TOKEN:
        check("/api/platform/overview sin token → 401", r.status_code == 401,
              f"status {r.status_code}")
    else:
        check("/api/platform/* SIN AUTENTICACIÓN (PLATFORM_API_TOKEN vacío)",
              False, f"status {r.status_code} — la API responde datos a cualquiera")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5000")
    ap.add_argument("--request-id", default=None)
    ap.add_argument("--only", choices=["portal", "dashboard"], default=None)
    args = ap.parse_args()

    base = args.base.rstrip("/")
    try:
        requests.get(base + "/health", timeout=10).raise_for_status()
    except Exception as e:
        print(f"El servidor no responde en {base}/health: {e}")
        return 2

    if args.only != "dashboard":
        portal_suite(base)
    if args.only != "portal":
        dashboard_suite(base, args.request_id)

    print("\n" + "=" * 60)
    if _fails:
        print(f"RESUMEN: {len(_fails)} problema(s)")
        for f in _fails:
            print(f"  - {f}")
        return 1
    print("RESUMEN: todo OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
