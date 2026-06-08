"""Importa el mapeo etiqueta diagnóstica -> prueba a la tabla diagnostic_label_tests.

Requiere haber aplicado antes la migración db/migrations/012_diagnostic_labels.sql
en Supabase. Es idempotente: vacía la tabla y vuelve a cargarla desde el JSON.

Uso:  python tools/scripts/import_diagnostic_labels.py
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.services import db

DATA_FILE = pathlib.Path(__file__).resolve().parents[1] / "data" / "diagnostic_labels.json"


def load_pairs() -> list[dict]:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    pairs = []
    for label, codes in data["labels"].items():
        for code in codes:
            pairs.append({"label": label, "test_code": str(code)})
    return pairs


def main() -> int:
    pairs = load_pairs()
    # Limpiar tabla (delete requiere un filtro; este matchea todas las filas).
    db._client.table("diagnostic_label_tests").delete().neq("test_code", "__none__").execute()

    batch = 500
    for i in range(0, len(pairs), batch):
        db._client.table("diagnostic_label_tests").insert(pairs[i:i + batch]).execute()

    labels = {p["label"] for p in pairs}
    print(f"Importados {len(pairs)} pares etiqueta-prueba ({len(labels)} etiquetas).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
