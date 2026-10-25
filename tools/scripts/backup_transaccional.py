"""Respaldo de las tablas transaccionales antes de limpiar los datos de prueba.

Se ejecuta ANTES de `limpiar_transaccional.py`. Vuelca a JSON, con fecha en el nombre,
cada tabla que la limpieza va a vaciar. No toca las tablas maestras (clients, catalog_*,
couriers, anarvet_*): esas nunca se borran.

    python tools/scripts/backup_transaccional.py

Salida: data/backups/transaccional-<YYYYMMDD-HHMMSS>/<tabla>.json + manifiesto.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.db import _client  # noqa: E402

# Las tablas que la limpieza vacía. El orden no importa para el respaldo.
TABLAS = [
    "requests",
    "pedidos",
    "conversation_messages",
    "portal_notifications",
    "invoices_cache",
    "telegram_sessions",
    "dashboard_column_prefs",
    "lab_results",
    "order_number_counters",
    "pedido_number_counters",
]

PAGINA = 1000


def _dump_table(name: str) -> list[dict]:
    """Trae la tabla completa paginando: Supabase corta en 1000 filas por request."""
    filas: list[dict] = []
    desde = 0
    while True:
        lote = _client.table(name).select("*").range(desde, desde + PAGINA - 1).execute().data
        filas.extend(lote)
        if len(lote) < PAGINA:
            return filas
        desde += PAGINA


def main() -> int:
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = ROOT / "data" / "backups" / f"transaccional-{sello}"
    destino.mkdir(parents=True, exist_ok=True)

    manifiesto: dict[str, int] = {}
    for tabla in TABLAS:
        try:
            filas = _dump_table(tabla)
        except Exception as exc:  # tabla inexistente o sin permisos: se registra, no se corta
            print(f"  {tabla:<24} ERROR {exc}"[:120])
            manifiesto[tabla] = -1
            continue
        (destino / f"{tabla}.json").write_text(
            json.dumps(filas, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        manifiesto[tabla] = len(filas)
        print(f"  {tabla:<24} {len(filas):>6} filas")

    (destino / "manifiesto.json").write_text(
        json.dumps({"fecha": sello, "tablas": manifiesto}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    total = sum(v for v in manifiesto.values() if v > 0)
    print(f"\nRespaldo completo: {total} filas en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
