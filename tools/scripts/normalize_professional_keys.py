"""Normaliza `clients_a3_professionals.clinic_key` y fusiona los duplicados (script one-off).

Uso:
    python tools/scripts/normalize_professional_keys.py            # dry-run
    python tools/scripts/normalize_professional_keys.py --apply    # escribe

Las cargas históricas guardaron la clave con espacios ("animal pets") en vez de la forma
canónica de `_normalize_lookup_key` ("animal_pets"). Como la carga nueva sí usó la forma
canónica, la MISMA clínica quedó partida en dos grupos y sus médicos aparecen separados —
y la deduplicación anterior no los fusionó porque agrupa por clave exacta.

Invariantes verificadas antes de escribir y de nuevo después (aborta si alguna falla):
  - ningún médico desaparece: el conjunto (clínica_normalizada, médico) es idéntico
  - ninguna tarjeta profesional se pierde
"""
import argparse
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.services import db  # noqa: E402


def fetch_all() -> list[dict]:
    out, offset = [], 0
    while True:
        page = (
            db._client.table("clients_a3_professionals")
            .select("id, clinic_key, professional_key, professional_name, professional_card, source_sheet, synced_at")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        out += page
        if len(page) < 1000:
            break
        offset += 1000
    return out


def card_value(raw) -> str:
    text = re.sub(r"\.0+$", "", str(raw or "").strip())
    digits = re.sub(r"\D", "", text)
    return digits.lstrip("0") or digits


def accent_score(name: str) -> int:
    return sum(1 for ch in str(name or "") if unicodedata.category(ch) != "Mn" and ord(ch) > 127)


def pair(row: dict) -> tuple[str, str]:
    return (db._normalize_lookup_key(row["clinic_key"]), db._normalize_lookup_key(row.get("professional_name")))


def snapshot(rows: list[dict]) -> tuple[set, set]:
    pairs = {pair(r) for r in rows if pair(r)[1]}
    cards = {(pair(r), card_value(r.get("professional_card"))) for r in rows if card_value(r.get("professional_card"))}
    return pairs, cards


def main() -> int:
    parser = argparse.ArgumentParser(description="Normaliza clinic_key y fusiona duplicados.")
    parser.add_argument("--apply", action="store_true", help="Escribe en la base")
    args = parser.parse_args()

    rows = fetch_all()
    malformed = [r for r in rows if r["clinic_key"] != db._normalize_lookup_key(r["clinic_key"])]

    groups = defaultdict(list)
    for row in rows:
        if pair(row)[1]:
            groups[pair(row)].append(row)

    to_update, to_delete, conflicts = [], [], []
    for (clinic_key, _doc), group in groups.items():
        cards = {card_value(r.get("professional_card")) for r in group if card_value(r.get("professional_card"))}
        if len(cards) > 1:
            conflicts.append((clinic_key, group))
            continue
        keeper = sorted(group, key=lambda r: (
            0 if card_value(r.get("professional_card")) else 1,
            -accent_score(r.get("professional_name")),
            str(r.get("synced_at") or ""),
        ))[0]
        if keeper["clinic_key"] != clinic_key:
            to_update.append((keeper, clinic_key))
        to_delete += [r for r in group if r["id"] != keeper["id"]]

    print(f"Filas                          : {len(rows)}")
    print(f"  con clinic_key mal formada   : {len(malformed)}")
    print(f"  a reescribir la clave        : {len(to_update)}")
    print(f"  duplicados a fusionar (borrar): {len(to_delete)}")
    print(f"  grupos con tarjeta en conflicto (no se tocan): {len(conflicts)}")

    pairs_before, cards_before = snapshot(rows)
    remaining = [r for r in rows if r["id"] not in {d["id"] for d in to_delete}]
    pairs_after, cards_after = snapshot(remaining)
    ok_pairs, ok_cards = pairs_before == pairs_after, cards_before <= cards_after
    print("\nInvariantes (simulado):")
    print(f"  [{'OK ' if ok_pairs else '!! '}] ningún médico desaparece: {len(pairs_before)} -> {len(pairs_after)}")
    print(f"  [{'OK ' if ok_cards else '!! '}] ninguna tarjeta se pierde: {len(cards_before)} -> {len(cards_after)}")
    if not (ok_pairs and ok_cards):
        print("\nABORTA: se perdería información.")
        return 1

    if not args.apply:
        print("\nDRY-RUN. Nada se escribió. Volvé a correr con --apply para aplicar.")
        return 0

    # Borrar primero: evita chocar con el unique (clinic_key, professional_key, source_sheet)
    # al reescribir una clave que ya existe en su forma canónica.
    for row in to_delete:
        db._client.table("clients_a3_professionals").delete().eq("id", row["id"]).execute()
    for row, clinic_key in to_update:
        db._client.table("clients_a3_professionals").update(
            {"clinic_key": clinic_key,
             "professional_key": db._normalize_lookup_key(row.get("professional_name"))}
        ).eq("id", row["id"]).execute()

    after = fetch_all()
    pairs_real, cards_real = snapshot(after)
    left = [r for r in after if r["clinic_key"] != db._normalize_lookup_key(r["clinic_key"])]
    print(f"\nFusionadas: {len(to_delete)} | claves reescritas: {len(to_update)} | filas ahora: {len(after)}")
    print(f"  pares (clínica, médico): {len(pairs_before)} -> {len(pairs_real)} "
          f"{'OK' if pairs_before == pairs_real else 'ALERTA'}")
    print(f"  tarjetas               : {'OK' if cards_before <= cards_real else 'ALERTA'}")
    print(f"  claves mal formadas restantes: {len(left)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
