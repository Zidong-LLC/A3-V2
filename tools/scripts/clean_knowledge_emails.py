"""Normaliza el campo `email` de `clients_a3_knowledge` (script one-off).

Uso:
    python tools/scripts/clean_knowledge_emails.py            # dry-run: solo reporta
    python tools/scripts/clean_knowledge_emails.py --apply    # escribe

De 1.083 filas con el campo lleno, 241 no son correos: quedaron `"N/A"`, `"vet"` y hasta
nombres de persona de importaciones viejas. Un campo que dice `"N/A"` es peor que uno vacío:
aparenta tener el dato y nadie lo completa. Este script los pasa a NULL.

Conservador por diseño: solo toca lo que NO valida como correo. Los 842 válidos no se tocan.
"""
import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.services import db  # noqa: E402

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
# Algunos valores traen el correo válido dentro de ruido ("P 201 correo@ejemplo.com",
# "otro@ejemplo.com - lab"): se rescata en vez de perderlo.
EMBEDDED_RE = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.IGNORECASE)


def clean(value: str) -> str | None:
    """Devuelve el correo normalizado, o None si el valor no contiene ninguno."""
    text = str(value or "").strip()
    if EMAIL_RE.match(text):
        return text
    found = EMBEDDED_RE.search(text)
    return found.group(0).strip(" .,;-") if found else None


def fetch_rows() -> list[dict]:
    out, offset = [], 0
    while True:
        page = (
            db._client.table("clients_a3_knowledge")
            .select("clinic_key, clinic_name, email")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        out += page
        if len(page) < 1000:
            break
        offset += 1000
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Vacía los valores de email que no son correos.")
    parser.add_argument("--apply", action="store_true", help="Escribe en la base (sin esto, solo reporta)")
    args = parser.parse_args()

    rows = fetch_rows()
    filled = [r for r in rows if str(r.get("email") or "").strip()]
    valid = [r for r in filled if EMAIL_RE.match(str(r["email"]).strip())]
    rescued = [(r, clean(r["email"])) for r in filled if r not in valid and clean(r["email"])]
    to_null = [r for r in filled if r not in valid and not clean(r["email"])]

    print(f"Filas               : {len(rows)}")
    print(f"  campo email lleno : {len(filled)}")
    print(f"  correos válidos   : {len(valid)}  (no se tocan)")
    print(f"  rescatados        : {len(rescued)}  (traían el correo entre ruido)")
    print(f"  a vaciar          : {len(to_null)}")
    for row, value in rescued:
        print(f'     "{str(row["email"])[:38]}" -> {value}')
    from collections import Counter
    for value, count in Counter(str(r["email"]).strip() for r in to_null).most_common(6):
        print(f'     "{value[:40]}" x{count}')

    if not args.apply:
        print("\nDRY-RUN. Nada se escribió. Volvé a correr con --apply para aplicar.")
        return 0

    for row, value in rescued:
        db._client.table("clients_a3_knowledge").update({"email": value}).eq("clinic_key", row["clinic_key"]).execute()
    for row in to_null:
        db._client.table("clients_a3_knowledge").update({"email": None}).eq("clinic_key", row["clinic_key"]).execute()
    print(f"\nRescatados: {len(rescued)} | vaciados: {len(to_null)} | válidos conservados: {len(valid)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
