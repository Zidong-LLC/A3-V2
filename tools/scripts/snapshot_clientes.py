"""Guarda una foto del padrón de clientes, para comparar contra listas futuras de A3.

Cada vez que A3 pase una lista actualizada, `conciliar_clientes.py` la compara contra la
base viva; este snapshot sirve además para ver cómo evolucionó el padrón entre fechas.

    python tools/scripts/snapshot_clientes.py

Escribe data/snapshots/clientes-<fecha>.csv. Solo lectura.
"""

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.db import _client  # noqa: E402

CAMPOS = "id, clinic_name, tax_id, phone, address, city, zone, email, is_active, electronic_invoice, created_at"
PAGE = 1000


def main() -> int:
    filas: list[dict] = []
    while True:
        lote = (
            _client.table("clients").select(CAMPOS).order("clinic_name")
            .range(len(filas), len(filas) + PAGE - 1).execute().data
        ) or []
        filas.extend(lote)
        if len(lote) < PAGE:
            break

    salida = ROOT / "data" / "snapshots" / f"clientes-{date.today().strftime('%Y%m%d')}.csv"
    salida.parent.mkdir(parents=True, exist_ok=True)
    columnas = [c.strip() for c in CAMPOS.split(",")]
    with open(salida, "w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.DictWriter(fh, fieldnames=columnas, delimiter=";", extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)

    activos = sum(1 for f in filas if f.get("is_active"))
    con_nit = sum(1 for f in filas if str(f.get("tax_id") or "").strip())
    print(f"clientes    : {len(filas)}  (activos {activos})")
    print(f"con NIT     : {con_nit}  |  sin NIT: {len(filas) - con_nit}")
    print(f"\nSnapshot: {salida.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
