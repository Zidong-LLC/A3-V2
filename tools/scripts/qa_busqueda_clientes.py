"""¿Cada cliente se encuentra en TODOS los buscadores? Exhaustivo y de SOLO LECTURA.

Nació de un reporte del usuario (2026-10-29): «busqué un cliente que sé que estaba y no me
aparecía bien». Para cada cliente de la base prueba las formas reales de buscarlo —nombre
exacto, sin tildes ni mayúsculas, palabras en otro orden, una palabra propia y el NIT— en:

  1. la tabla de Clientes del dashboard (`client_filters.filtrar` sobre la lista completa)
  2. las sugerencias mientras se escribe (`/clientes/buscar`, también el buscador de Resultados)
  3. la identificación del bot (nombre exacto y NIT)
  4. el login del portal (nombre + NIT)

Uso:  python tools/scripts/qa_busqueda_clientes.py
"""
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent)]
os.environ.setdefault("ANARVET_ENABLED", "false")

import red_segura  # noqa: E402

red_segura.activar(permitir_openai=False, silenciosa=True)
import logging  # noqa: E402

logging.disable(logging.WARNING)
from app import client_filters  # noqa: E402
from app.dashboard import build_dashboard_context  # noqa: E402
from app.portal.auth import _find_sedes  # noqa: E402
from app.services import db  # noqa: E402
from app.verificacion_cliente import GENERICAS, _tokens  # noqa: E402


def consultas(cliente: dict) -> dict[str, str]:
    nombre = (cliente.get("clinic_name") or "").strip()
    palabras = nombre.split()
    propias = [t for t in _tokens(nombre) if t not in GENERICAS and len(t) >= 4]
    nit = re.sub(r"\D", "", str(cliente.get("tax_id") or "").split("-")[0].removesuffix(".0"))
    q = {"nombre exacto": nombre, "sin tildes ni mayúsculas": client_filters.normalizar(nombre)}
    if len(palabras) >= 2:
        q["palabras en otro orden"] = " ".join(reversed(palabras))
    if propias:
        q["una palabra propia"] = max(propias, key=len)
    if len(nit) >= 6:
        q["NIT"] = nit
    return q


def _reintentando(fn, *args, **kwargs):
    """Un 502 de Cloudflare suelto no es una falla del buscador: se reintenta dos veces."""
    for intento in range(3):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            if intento == 2:
                raise
            time.sleep(1 + intento)


def revisar(cliente: dict, filas_tabla: list[dict], cuantos_con: dict) -> list[str]:
    fallas = []
    cid = cliente["id"]
    for forma, q in consultas(cliente).items():
        tabla = client_filters.filtrar(filas_tabla, q)
        if not any(str(f.get("client_id")) == cid for f in tabla):
            fallas.append(f"tabla de Clientes · {forma} «{q}»")
        sugeridos = _reintentando(db.search_clients_for_dashboard, q, limit=12)
        # Una palabra que comparten más de 12 clientes no entra entera en 12 sugerencias:
        # eso es esperable en un autocompletar; con menos de 12, el cliente TIENE que estar.
        amplia = forma == "una palabra propia" and cuantos_con.get(q, 0) > 12
        if not amplia and not any(f.get("id") == cid for f in sugeridos):
            fallas.append(f"sugerencias · {forma} «{q}»")
    if cliente.get("is_active"):
        nombre = cliente.get("clinic_name") or ""
        exacto = _reintentando(db.find_client_exact, nombre)
        if not exacto or (exacto.get("id") != cid and exacto.get("tax_id") != cliente.get("tax_id")):
            fallas.append(f"bot · nombre exacto «{nombre}» → {(exacto or {}).get('clinic_name')}")
        nit = consultas(cliente).get("NIT")
        if nit:
            if not any(f.get("id") == cid for f in _reintentando(db.find_clients_by_tax_id, nit)):
                fallas.append(f"bot · NIT «{nit}»")
            if not any(f.get("id") == cid for f in _reintentando(_find_sedes, nit, nombre)):
                fallas.append(f"portal · nombre + NIT «{nombre}» / {nit}")
    return fallas


def main() -> int:
    clientes = db._paginado(lambda: db._client.table("clients")
                            .select("id, clinic_name, tax_id, is_active").order("id"), 5000)
    filas_tabla = build_dashboard_context().get("clients_rows") or []
    print(f"clientes en la base: {len(clientes)} · filas en la tabla de Clientes: {len(filas_tabla)}")
    faltan = {c["id"] for c in clientes} - {str(f.get("client_id")) for f in filas_tabla}
    if faltan:
        print(f"FALLA: {len(faltan)} cliente(s) de la base NO aparecen en la tabla de Clientes")
    cuantos_con: dict[str, int] = {}
    for c in clientes:
        for t in set(_tokens(c.get("clinic_name"))):
            cuantos_con[t] = cuantos_con.get(t, 0) + 1
    with ThreadPoolExecutor(max_workers=4) as hilos:
        resultados = list(hilos.map(lambda c: (c, revisar(c, filas_tabla, cuantos_con)), clientes))
    con_falla = [(c, f) for c, f in resultados if f]
    por_buscador: dict[str, int] = {}
    for _, fallas in con_falla:
        for f in fallas:
            buscador = f.split(" · ")[0]
            por_buscador[buscador] = por_buscador.get(buscador, 0) + 1
    print(f"clientes que se encuentran por TODAS las vías: {len(clientes) - len(con_falla)}/{len(clientes)}")
    print("fallas por buscador:", por_buscador or "ninguna")
    # Primero las fallas que NO son de sugerencias (bot, portal, tabla): son las más raras.
    con_falla.sort(key=lambda cf: all(f.startswith("sugerencias") for f in cf[1]))
    for c, fallas in con_falla[:40]:
        print(f"  · {c.get('clinic_name')} ({c.get('tax_id') or 'sin NIT'})")
        for f in fallas:
            print(f"      - {f}")
    return 1 if con_falla or faltan or red_segura.bloqueos else 0


if __name__ == "__main__":
    raise SystemExit(main())
