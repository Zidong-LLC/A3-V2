"""Elimina filas REDUNDANTES de `clients_a3_professionals` sin perder ningún médico.

Uso:
    python tools/scripts/dedupe_professionals.py            # dry-run: solo reporta
    python tools/scripts/dedupe_professionals.py --apply    # borra

Origen del problema: importaciones históricas cargaron las mismas planillas más de una vez
(`Clientes` + `Copia de Clientes` explican 414 de los 488 casos). El unique de la tabla es
(clinic_key, professional_key, source_sheet), así que el mismo médico entrado desde dos hojas
convive como dos filas.

Qué fila se conserva, en orden de preferencia:
  1. la que TIENE número de tarjeta (nunca se pierde un dato por deduplicar)
  2. la que escribe el nombre con tildes (grafía más completa)
  3. la más antigua por `synced_at`

Grupos que NO se tocan: cuando dos copias traen tarjetas DISTINTAS (p. ej. 43562 vs 43652,
dígitos transpuestos) hay un conflicto real de datos y elegir una sería inventar. Se reportan
para revisión manual.

Invariantes verificadas antes y después (si alguna falla, aborta):
  - el conjunto de pares (clínica, médico) es idéntico
  - toda tarjeta que existía sigue existiendo
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
            .select("id, clinic_key, professional_name, professional_card, source_sheet, synced_at")
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
    """Normaliza la tarjeta: '8950.0' y '08950' son el mismo número."""
    text = str(raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"\.0+$", "", text)
    digits = re.sub(r"\D", "", text)
    return digits.lstrip("0") or digits


def accent_score(name: str) -> int:
    """Cuántos caracteres acentuados tiene: prefiere 'López' sobre 'Lopez'."""
    return sum(1 for ch in str(name or "") if unicodedata.category(ch) != "Mn" and ord(ch) > 127)


def pair_key(row: dict) -> tuple[str, str]:
    return (row["clinic_key"], db._normalize_lookup_key(row.get("professional_name")))


def snapshot(rows: list[dict]) -> tuple[set, set]:
    pairs = {pair_key(r) for r in rows if pair_key(r)[1]}
    cards = {(pair_key(r), card_value(r.get("professional_card"))) for r in rows if card_value(r.get("professional_card"))}
    return pairs, cards


def main() -> int:
    parser = argparse.ArgumentParser(description="Borra filas redundantes de médicos.")
    parser.add_argument("--apply", action="store_true", help="Borra (sin esto, solo reporta)")
    args = parser.parse_args()

    rows = fetch_all()
    groups = defaultdict(list)
    for row in rows:
        if pair_key(row)[1]:
            groups[pair_key(row)].append(row)

    to_delete, conflicts = [], []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        cards = {card_value(r.get("professional_card")) for r in group if card_value(r.get("professional_card"))}
        if len(cards) > 1:
            conflicts.append((key, group))
            continue
        keeper = sorted(group, key=lambda r: (
            0 if card_value(r.get("professional_card")) else 1,        # con tarjeta primero
            -accent_score(r.get("professional_name")),                  # grafía más completa
            str(r.get("synced_at") or ""),                              # la más antigua
        ))[0]
        to_delete += [r for r in group if r["id"] != keeper["id"]]

    print(f"Filas actuales              : {len(rows)}")
    print(f"Pares (clínica, médico)     : {len(groups)}")
    print(f"  con más de una fila       : {sum(1 for g in groups.values() if len(g) > 1)}")
    print(f"Filas redundantes a borrar  : {len(to_delete)}")
    print(f"Grupos con tarjeta EN CONFLICTO (no se tocan): {len(conflicts)}")
    for key, group in conflicts:
        cards = sorted({card_value(r.get("professional_card")) for r in group if card_value(r.get("professional_card"))})
        print(f"     {key[0][:26]:26} {str(group[0]['professional_name'])[:28]:28} tarjetas={cards}")

    pairs_before, cards_before = snapshot(rows)
    remaining = [r for r in rows if r["id"] not in {d["id"] for d in to_delete}]
    pairs_after, cards_after = snapshot(remaining)

    print("\nInvariantes (simulado sobre el resultado):")
    ok_pairs = pairs_before == pairs_after
    ok_cards = cards_before <= cards_after
    print(f"  [{'OK ' if ok_pairs else '!! '}] ningún médico desaparece: {len(pairs_before)} pares antes, {len(pairs_after)} después")
    print(f"  [{'OK ' if ok_cards else '!! '}] ninguna tarjeta se pierde: {len(cards_before)} antes, {len(cards_after)} después")
    if not (ok_pairs and ok_cards):
        print("\nABORTA: el borrado perdería información.")
        return 1

    if not args.apply:
        print("\nDRY-RUN. Nada se borró. Volvé a correr con --apply para aplicar.")
        return 0

    for row in to_delete:
        db._client.table("clients_a3_professionals").delete().eq("id", row["id"]).execute()

    after = fetch_all()
    pairs_real, cards_real = snapshot(after)
    print(f"\nBorradas: {len(to_delete)} | filas ahora: {len(after)}")
    print(f"  pares (clínica, médico): {len(pairs_before)} -> {len(pairs_real)} "
          f"{'OK' if pairs_before == pairs_real else 'ALERTA'}")
    print(f"  tarjetas conservadas   : {'OK' if cards_before <= cards_real else 'ALERTA'}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
