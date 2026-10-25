"""Limpieza de los datos transaccionales de PRUEBA, para arrancar con datos reales.

Borra SOLO lo transaccional. Las tablas maestras no se tocan nunca: clients (992),
catalog_tests/catalog_profiles/catalog_breeds, couriers, client_courier_assignment,
client_custom_profiles, discount_tiers y anarvet_* (27.102 informes).

Exige respaldo previo con `backup_transaccional.py` y el flag --confirmar:

    python tools/scripts/backup_transaccional.py
    python tools/scripts/limpiar_transaccional.py --confirmar

El orden respeta las claves foráneas: los mensajes cuelgan de telegram_sessions, y
telegram_sessions.request_id apunta a requests — por eso las sesiones se borran antes
que las solicitudes.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.db import _client  # noqa: E402

UUID_IMPOSIBLE = "00000000-0000-0000-0000-000000000000"
TEXTO_IMPOSIBLE = "__nunca_existe__"

# (tabla, columna PK, valor imposible) en orden seguro de borrado.
# Cadena de dependencias: conversation_messages -> telegram_sessions -> requests -> pedidos
# (telegram_sessions.request_id apunta a requests, y requests.pedido_id apunta a pedidos).
ORDEN = [
    ("conversation_messages", "id", UUID_IMPOSIBLE),
    ("portal_notifications", "id", UUID_IMPOSIBLE),
    ("lab_results", "id", UUID_IMPOSIBLE),
    ("invoices_cache", "alegra_invoice_id", TEXTO_IMPOSIBLE),
    ("dashboard_column_prefs", "user_key", TEXTO_IMPOSIBLE),
    ("telegram_sessions", "id", UUID_IMPOSIBLE),
    ("requests", "id", UUID_IMPOSIBLE),
    ("pedidos", "id", UUID_IMPOSIBLE),
]

# Contadores de numeración: se reinician para que las órdenes reales arranquen en 1.
CONTADORES = [("order_number_counters", "year"), ("pedido_number_counters", "year")]

INTOCABLES = [
    "clients", "catalog_tests", "catalog_profiles", "catalog_breeds", "couriers",
    "client_courier_assignment", "client_custom_profiles", "discount_tiers",
    "anarvet_results", "anarvet_client_map",
]


def _contar(tabla: str) -> int:
    return _client.table(tabla).select("*", count="exact").limit(1).execute().count or 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirmar", action="store_true", help="ejecuta el borrado de verdad")
    args = ap.parse_args()

    respaldos = sorted((ROOT / "data" / "backups").glob("transaccional-*"))
    if not respaldos:
        print("ABORTADO: no hay respaldo. Corré primero backup_transaccional.py")
        return 1
    print(f"Respaldo mas reciente: {respaldos[-1].name}\n")

    print("A BORRAR:")
    for tabla, _, _ in ORDEN:
        print(f"  {tabla:<24} {_contar(tabla):>6}")
    print("\nSE CONSERVA:")
    for tabla in INTOCABLES:
        print(f"  {tabla:<26} {_contar(tabla):>6}")

    if not args.confirmar:
        print("\nSimulacion. Volvé a correrlo con --confirmar para borrar.")
        return 0

    print("\nBorrando...")
    for tabla, pk, imposible in ORDEN:
        antes = _contar(tabla)
        if antes:
            _client.table(tabla).delete().neq(pk, imposible).execute()
        print(f"  {tabla:<24} {antes:>6} -> {_contar(tabla)}")

    for tabla, pk in CONTADORES:
        antes = _contar(tabla)
        if antes:
            _client.table(tabla).delete().neq(pk, -1).execute()
        print(f"  {tabla:<24} {antes:>6} -> {_contar(tabla)} (numeracion reiniciada)")

    print("\nVerificando que los maestros sigan intactos:")
    for tabla in INTOCABLES:
        print(f"  {tabla:<26} {_contar(tabla):>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
