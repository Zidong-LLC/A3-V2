"""Abre cada pantalla en Chromium de verdad y junta los errores de JavaScript.

El smoke HTTP (`qa_web_smoke.py`) ve el HTML, no lo que pasa en el navegador: un error de
sintaxis en un <script> deja botones muertos con la pantalla en 200 (así pasó con el editor
de descuentos, ERR-166). Este recorrido carga cada pantalla del laboratorio y del portal
con su sesión real y falla si aparece un error de consola, una excepción de la página o un
pedido propio que responde 5xx. SOLO LECTURA: con la red de seguridad encendida.

Uso:  python tools/scripts/qa_consola_navegador.py
"""
import os
import sys
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent)]
os.environ.update(ANARVET_ENABLED="true", PDF_ENABLED="false", MESSAGE_DEBOUNCE_SECONDS="5")

import red_segura  # noqa: E402

red_segura.activar(permitir_openai=False)
import estres_web as web  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

# Ruido conocido que no es nuestro: recursos de terceros que el navegador no pudo cargar.
AJENOS = ("tile.openstreetmap.org", "unpkg.com", "fonts.g", "favicon")


def recorrer(contexto, base: str, rutas: list[str]) -> list[str]:
    problemas = []
    for ruta in rutas:
        errores = []
        pagina = contexto.new_page()  # una pestaña por pantalla: los listeners no se mezclan
        pagina.on("console", lambda m: errores.append(f"consola: {m.text}") if m.type == "error" else None)
        pagina.on("pageerror", lambda e: errores.append(f"excepción JS: {e}"))
        pagina.on("response", lambda r: errores.append(f"{r.status} {r.url}")
                  if r.status >= 500 and r.url.startswith(base) else None)
        try:
            pagina.goto(base + ruta, wait_until="networkidle", timeout=60000)
        except Exception as exc:  # noqa: BLE001
            errores.append(f"no cargó: {exc}")
        propios = [e for e in errores if not any(a in e for a in AJENOS)]
        print(("OK   " if not propios else "FALLA") + f" {ruta}" + (f" — {propios[:3]}" if propios else ""))
        problemas += [f"{ruta}: {e}" for e in propios]
        pagina.close()
    return problemas


def main() -> int:
    from werkzeug.serving import make_server

    servidor = make_server("127.0.0.1", 0, web._TopeDeHilos(web.app, 8), threaded=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{servidor.server_port}"
    personal = web._sesion_personal(base)
    portal = next(s for s in (web._sesion_portal(base, c) for c in web._veterinarias(5)) if s)
    problemas = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        for sesion, rutas in ((personal, [r for r in web.PERSONAL if not r.startswith("/api/")]),
                              (portal, web.PORTAL)):
            contexto = navegador.new_context()
            contexto.add_cookies([{"name": c.name, "value": c.value, "url": base} for c in sesion.cookies])
            problemas += recorrer(contexto, base, rutas)
            contexto.close()
        navegador.close()
    servidor.shutdown()
    print(f"\n{len(problemas)} problema(s)" if problemas else "\nTODO OK: ninguna pantalla con errores de JavaScript")
    return 1 if problemas or red_segura.bloqueos else 0


if __name__ == "__main__":
    raise SystemExit(main())
