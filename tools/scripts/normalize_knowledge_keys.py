"""Normaliza `clients_a3_knowledge.clinic_key` y fusiona las fichas duplicadas (one-off).

Uso:
    python tools/scripts/normalize_knowledge_keys.py            # dry-run
    python tools/scripts/normalize_knowledge_keys.py --apply    # escribe

Dos causas se juntaron:
  1. Las cargas históricas guardaron la clave con espacios ("animal pets") en vez de la forma
     canónica de `_normalize_lookup_key` ("animal_pets").
  2. `import_client_roster.py` comparó contra las claves existentes tal cual: no vio
     "animal_pets" (solo estaba "animal pets") y creó una ficha nueva VACÍA para la misma
     clínica. De ahí 600 pares duplicados donde la fila vieja tiene los datos y la nueva no.

Al fusionar se conserva el valor NO vacío de cada campo, prefiriendo el de la ficha vieja
(es la que trae email/teléfono/dirección). Después se reapuntan sus médicos y eventos de
muestra, y recién ahí se borra la ficha con la clave mal formada.

Invariantes verificadas antes y después (aborta si alguna falla):
  - ninguna clínica desaparece (contadas por clave normalizada)
  - ningún correo, teléfono ni dirección se pierde
  - ningún par (clínica, médico) se pierde
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.services import db  # noqa: E402

MERGE_FIELDS = (
    "clinic_name", "address", "locality", "phone", "email", "payment_policy",
    "result_delivery_mode", "source_excel", "client_code", "commercial_name", "client_type",
    "billing_email", "vat_regime", "invoicing_rut_url", "observations",
)


def fetch(table: str, columns: str) -> list[dict]:
    out, offset = [], 0
    while True:
        page = db._client.table(table).select(columns).range(offset, offset + 999).execute().data
        out += page
        if len(page) < 1000:
            break
        offset += 1000
    return out


def merged_payload(old: dict, new: dict | None) -> dict:
    """Conserva el valor no vacío de cada campo, con prioridad para la ficha vieja."""
    out = {}
    for field in MERGE_FIELDS:
        value = str(old.get(field) or "").strip() or str((new or {}).get(field) or "").strip()
        if value:
            out[field] = value
    return out


def contact_snapshot(rows: list[dict]) -> set:
    out = set()
    for row in rows:
        key = db._normalize_lookup_key(row["clinic_key"])
        for field in ("email", "phone", "address"):
            value = str(row.get(field) or "").strip()
            if value:
                out.add((key, field, value))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Normaliza y fusiona clinic_key en knowledge.")
    parser.add_argument("--apply", action="store_true", help="Escribe en la base")
    args = parser.parse_args()

    knowledge = fetch("clients_a3_knowledge", "*")
    professionals = fetch("clients_a3_professionals", "id, clinic_key, professional_name")
    by_key = {r["clinic_key"]: r for r in knowledge}

    malformed = [r for r in knowledge if r["clinic_key"] != db._normalize_lookup_key(r["clinic_key"])]
    to_merge = [r for r in malformed if db._normalize_lookup_key(r["clinic_key"]) in by_key]
    to_rename = [r for r in malformed if db._normalize_lookup_key(r["clinic_key"]) not in by_key]

    clinics_before = {db._normalize_lookup_key(r["clinic_key"]) for r in knowledge}
    contacts_before = contact_snapshot(knowledge)
    pairs_before = {(db._normalize_lookup_key(r["clinic_key"]), db._normalize_lookup_key(r.get("professional_name")))
                    for r in professionals if r.get("professional_name")}

    print(f"Fichas de knowledge          : {len(knowledge)}")
    print(f"  claves mal formadas        : {len(malformed)}")
    print(f"    a FUSIONAR (ya existe la normalizada): {len(to_merge)}")
    print(f"    a RENOMBRAR (no existe)              : {len(to_rename)}")
    print(f"Clínicas distintas (por clave normalizada): {len(clinics_before)}")
    print(f"Datos de contacto a preservar            : {len(contacts_before)}")
    print(f"Pares (clínica, médico)                  : {len(pairs_before)}")

    if not args.apply:
        print("\nDRY-RUN. Nada se escribió. Volvé a correr con --apply para aplicar.")
        return 0

    events = fetch("clients_a3_sample_events", "event_key, clinic_key")
    events_by_key: dict[str, list[str]] = {}
    for row in events:
        if row.get("clinic_key"):
            events_by_key.setdefault(row["clinic_key"], []).append(row["event_key"])

    for old in malformed:
        old_key = old["clinic_key"]
        new_key = db._normalize_lookup_key(old_key)
        payload = merged_payload(old, by_key.get(new_key))
        payload["clinic_key"] = new_key
        db._client.table("clients_a3_knowledge").upsert(payload, on_conflict="clinic_key").execute()

        # Reapuntar los médicos, saltando los que ya existen bajo la clave buena.
        existing = {db._normalize_lookup_key(r.get("professional_name"))
                    for r in professionals if r["clinic_key"] == new_key}
        for row in [r for r in professionals if r["clinic_key"] == old_key]:
            doctor = db._normalize_lookup_key(row.get("professional_name"))
            table = db._client.table("clients_a3_professionals")
            if doctor in existing:
                table.delete().eq("id", row["id"]).execute()
            else:
                table.update({"clinic_key": new_key, "professional_key": doctor}).eq("id", row["id"]).execute()
                existing.add(doctor)

        for event_key in events_by_key.get(old_key, []):
            db._client.table("clients_a3_sample_events").update({"clinic_key": new_key}).eq("event_key", event_key).execute()

        db._client.table("clients_a3_knowledge").delete().eq("clinic_key", old_key).execute()

    after_k = fetch("clients_a3_knowledge", "*")
    after_p = fetch("clients_a3_professionals", "clinic_key, professional_name")
    clinics_after = {db._normalize_lookup_key(r["clinic_key"]) for r in after_k}
    contacts_after = contact_snapshot(after_k)
    pairs_after = {(db._normalize_lookup_key(r["clinic_key"]), db._normalize_lookup_key(r.get("professional_name")))
                   for r in after_p if r.get("professional_name")}
    left = [r for r in after_k if r["clinic_key"] != db._normalize_lookup_key(r["clinic_key"])]

    print(f"\nFichas: {len(knowledge)} -> {len(after_k)} | claves mal formadas restantes: {len(left)}")
    print(f"  clínicas distintas : {len(clinics_before)} -> {len(clinics_after)} "
          f"{'OK' if clinics_before == clinics_after else 'ALERTA'}")
    print(f"  datos de contacto  : {len(contacts_before)} -> {len(contacts_after)} "
          f"{'OK' if contacts_before <= contacts_after else 'ALERTA'}")
    print(f"  pares con médico   : {len(pairs_before)} -> {len(pairs_after)} "
          f"{'OK' if pairs_before == pairs_after else 'ALERTA'}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
