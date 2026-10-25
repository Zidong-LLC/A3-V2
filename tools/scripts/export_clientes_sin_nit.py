"""Exporta los clientes activos SIN NIT, para que A3 complete el dato.

Sirve dos veces: sin NIT una veterinaria **no puede entrar al portal** (se accede con el
nombre de la clínica y el NIT) y **no se le puede emitir factura electrónica**.

    python tools/scripts/export_clientes_sin_nit.py

Escribe data/clientes-sin-nit-<fecha>.csv. Solo lectura sobre la base.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.db import _client  # noqa: E402

CAMPOS = (
    "id, clinic_name, tax_id, phone, address, city, zone, email, "
    "client_courier_assignment(couriers(name))"
)
PAGE = 1000


def _clientes_activos() -> list[dict]:
    filas: list[dict] = []
    while True:
        lote = (
            _client.table("clients").select(CAMPOS).eq("is_active", True)
            .order("clinic_name").range(len(filas), len(filas) + PAGE - 1).execute().data
        ) or []
        filas.extend(lote)
        if len(lote) < PAGE:
            return filas


def _motorizado(fila: dict) -> str:
    """Supabase devuelve la relación como lista o como dict según el caso — mismo
    criterio que `_assignment_from_client` en app/dashboard.py."""
    asignacion = fila.get("client_courier_assignment")
    if isinstance(asignacion, list):
        asignacion = asignacion[0] if asignacion else None
    if not isinstance(asignacion, dict):
        return ""
    return (asignacion.get("couriers") or {}).get("name") or ""


def main() -> int:
    activos = _clientes_activos()
    sin_nit = [f for f in activos if not str(f.get("tax_id") or "").strip()]

    salida = ROOT / "data" / f"clientes-sin-nit-{datetime.now().strftime('%Y%m%d')}.csv"
    salida.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig y ';': para que Excel en español abra las tildes y las columnas bien.
    with open(salida, "w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh, delimiter=";")
        escritor.writerow(["Veterinaria", "NIT (completar)", "Telefono", "Direccion",
                           "Ciudad", "Zona", "Correo", "Motorizado asignado"])
        for fila in sin_nit:
            escritor.writerow([
                fila.get("clinic_name") or "", "", fila.get("phone") or "",
                fila.get("address") or "", fila.get("city") or "", fila.get("zone") or "",
                fila.get("email") or "", _motorizado(fila),
            ])

    print(f"clientes activos : {len(activos)}")
    print(f"sin NIT          : {len(sin_nit)}  (no entran al portal ni se les puede facturar)")
    print(f"\nArchivo: {salida.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
