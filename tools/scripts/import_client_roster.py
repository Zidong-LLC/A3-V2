"""Carga las clínicas nuevas de la cartera actualizada (script one-off).

Uso:
    python tools/scripts/import_client_roster.py            # dry-run: solo reporta
    python tools/scripts/import_client_roster.py --apply    # escribe

Usa la misma clasificación que `analyze_client_roster.py` (nombre exacto → NIT → parecido con
`db._name_match_score`) y carga SOLO lo que no existe de ninguna forma:

  - Con NIT  -> `clients` (is_active=False) + cola de aprobación, vía create_pending_client_review.
  - Sin NIT  -> solo ficha en `clients_a3_knowledge` (habilita cargarle sus doctores, que tienen
               FK contra clinic_key). No van a la cola: con solo un nombre recepción no puede
               aprobar ni contactar, y ensuciarían la bandeja.

NUNCA da de baja a nadie ni toca `is_active` de un cliente existente: la ausencia en una
planilla no prueba que dejó de ser cliente.
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from app.services import db  # noqa: E402
from analyze_client_roster import (  # noqa: E402  — mismo directorio, sin convertir tools/ en paquete
    MIN_SCORE, fetch_clients, read_alegra_nits, read_roster,
)

SOURCE = "Clientes y Doctores A3 2026-07"


def _fetch_knowledge_keys() -> list[dict]:
    out, offset = [], 0
    while True:
        page = db._client.table("clients_a3_knowledge").select("clinic_key").range(offset, offset + 999).execute().data
        out += page
        if len(page) < 1000:
            break
        offset += 1000
    return out


def classify() -> tuple[list, list, list]:
    """Devuelve (nuevas_con_nit, nuevas_solo_nombre, existentes_sin_ficha).

    El tercer grupo son clínicas que YA son clientes pero no tienen fila en
    `clients_a3_knowledge`. Sin esa ficha no se les pueden cargar los médicos, porque
    `clients_a3_professionals.clinic_key` tiene FK contra knowledge.
    """
    roster, alegra, clients = read_roster(), read_alegra_nits(), fetch_clients()
    known = {row["clinic_key"] for row in _fetch_knowledge_keys()}
    by_nit: dict[str, list] = {}
    for client in clients:
        for candidate in db._nit_candidates(client.get("tax_id") or ""):
            key = db._normalize_nit(candidate)
            if key:
                by_nit.setdefault(key, []).append(client)
    by_key = {db._normalize_lookup_key(c["clinic_name"]): c for c in clients}

    with_nit, name_only, no_profile = [], [], []
    for name in roster:
        key = db._normalize_lookup_key(name)
        info = alegra.get(key) or {}
        if key in by_key or any(by_nit.get(db._normalize_nit(c)) for c in db._nit_candidates(info.get("tax_id") or "")):
            if key not in known:
                no_profile.append((name, key, info))
            continue
        tokens = [t for t in key.split("_") if t and t not in db._CLIENT_QUERY_STOPWORDS]
        compact = "".join(tokens)
        best = max((db._name_match_score(tokens, compact, c["clinic_name"]) for c in clients), default=0.0)
        if best >= MIN_SCORE:
            if key not in known:
                no_profile.append((name, key, info))
            continue
        if key in known:  # ya tiene ficha de una corrida anterior
            continue
        (with_nit if info.get("tax_id") else name_only).append((name, key, info))
    return with_nit, name_only, no_profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga las clínicas nuevas de la cartera.")
    parser.add_argument("--apply", action="store_true", help="Escribe en la base (sin esto, solo reporta)")
    args = parser.parse_args()

    with_nit, name_only, no_profile = classify()
    active_before = db._client.table("clients").select("id", count="exact").eq("is_active", True).limit(1).execute().count

    print(f"Nuevas con NIT (alta + cola de aprobación): {len(with_nit)}")
    for name, _key, info in with_nit:
        print(f"   {name[:40]:40} NIT={info['tax_id']}")
    print(f"Nuevas solo con nombre (ficha en knowledge): {len(name_only)}")
    print(f"Ya son clientes pero sin ficha (se crea)  : {len(no_profile)}")
    print(f"Clientes activos ahora: {active_before}  (no debe cambiar)")

    if not args.apply:
        print("\nDRY-RUN. Nada se escribió. Volvé a correr con --apply para aplicar.")
        return 0

    for name, key, info in with_nit:
        db.create_pending_client_review(
            {"clinic_name": name, "tax_id": str(info["tax_id"]).strip(),
             "phone": str(info.get("phone") or "").strip() or None,
             "address": info.get("address"), "is_active": False,
             # NOT NULL en la tabla; mismo default que usa el alta del dashboard (:1008).
             "billing_type": "cash"},
            {"source": SOURCE, "note": "Alta desde la cartera actualizada del cliente"},
            # requests_entry_channel_check solo admite telegram | liveconnect | manual.
            channel="manual",
        )
        db.upsert_client_profile({"clinic_key": key, "clinic_name": name, "source_excel": SOURCE,
                                  "email": info.get("email"), "phone": info.get("phone"),
                                  "address": info.get("address")})
    for name, key, _info in name_only:
        db.upsert_client_profile({"clinic_key": key, "clinic_name": name, "source_excel": SOURCE})
    for name, key, info in no_profile:
        # Ya es cliente: solo se crea la ficha que faltaba (habilita cargarle los médicos).
        db.upsert_client_profile({"clinic_key": key, "clinic_name": name, "source_excel": SOURCE,
                                  "is_registered": True, "email": info.get("email"),
                                  "phone": info.get("phone"), "address": info.get("address")})

    active_after = db._client.table("clients").select("id", count="exact").eq("is_active", True).limit(1).execute().count
    print(f"\nAltas pendientes: {len(with_nit)} | fichas nuevas: {len(name_only)}")
    print(f"Clientes activos: {active_before} -> {active_after}  {'OK' if active_before == active_after else 'ALERTA'}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
