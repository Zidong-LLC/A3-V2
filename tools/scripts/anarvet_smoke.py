"""Prueba de humo de la conexión a Anarvet (Fase 1 — espejo de lectura).

SOLO LECTURA: ejecuta fn_reporte_examenes() con un rango corto y muestra qué devuelve
de verdad (columnas, tipos Python, encoding), para fijar el DDL de la migración 023 con
datos reales y no con supuestos. También verifica que la sesión quede read-only y si la
conexión negoció TLS.

Uso (desde la raíz del repo, con las credenciales en .env):
    python tools/scripts/anarvet_smoke.py                          # ayer -> hoy
    python tools/scripts/anarvet_smoke.py --desde 2026-08-01 --hasta 2026-08-20
"""

import argparse
from datetime import datetime, timedelta

from app.config import ANARVET_DB_HOST, ANARVET_DB_PORT, ANARVET_DB_NAME, APP_TIMEZONE
from app.services import anarvet


def main() -> int:
    hoy = datetime.now(APP_TIMEZONE).date()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desde", default=str(hoy - timedelta(days=1)))
    parser.add_argument("--hasta", default=str(hoy))
    args = parser.parse_args()

    if not ANARVET_DB_HOST:
        print("[FALLO] Falta ANARVET_DB_HOST en .env.")
        return 1

    print(f"-> Conectando a Anarvet {ANARVET_DB_HOST}:{ANARVET_DB_PORT}/{ANARVET_DB_NAME}")
    try:
        with anarvet._connect() as conn:
            ro = conn.execute("SHOW default_transaction_read_only").fetchone()
            print(f"[OK] Conexión abierta. default_transaction_read_only = {ro}")
            try:
                ssl = conn.pgconn.ssl_in_use
                print(f"     TLS negociado: {'sí' if ssl else 'NO (tráfico en claro)'}")
            except Exception:
                print("     TLS: no se pudo determinar")
    except anarvet.AnarvetError as e:
        print(f"[FALLO] No se pudo conectar:\n  {e}")
        return 1

    print(f"-> fn_reporte_examenes('{args.desde}', '{args.hasta}')")
    try:
        rows = anarvet.fetch_report(args.desde, args.hasta)
    except anarvet.AnarvetError as e:
        print(f"[FALLO] La consulta falló:\n  {e}")
        return 1

    print(f"[OK] {len(rows)} filas (una por analito con resultado).")
    if rows:
        primera = rows[0]
        print("\nColumnas reales y tipo Python del primer valor:")
        for k, v in primera.items():
            print(f"  {k:<20} {type(v).__name__:<10} {v!r}")
        print("\nMuestra (repr, para revisar acentos/encoding):")
        for row in rows[:2]:
            print(f"  {row!r}")
    else:
        print("Sin filas en el rango: probá un rango más amplio con --desde/--hasta.")

    # ping() usa LIMIT sobre la función: confirmar acá que el servidor lo acepta.
    print("\n-> Verificando que LIMIT 1 funciona sobre la función (lo usa ping())")
    try:
        anarvet.ping()
        print("[OK] ping() responde.")
    except anarvet.AnarvetError as e:
        print(f"[FALLO] ping():\n  {e}")
        return 1

    print("\nListo. Con columnas y tipos confirmados se fija la migración 023.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
