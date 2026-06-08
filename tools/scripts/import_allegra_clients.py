import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from tools.scripts.validate_allegra_clients import load_excel_rows, normalize_key


SOURCE_SHEET = "Alegra - Terceros"
SOURCE_EXCEL = "Alegra - Clientes A3 Laboratorio Clinico Veterinario.xlsx"


def chunked(rows: list[dict], size: int = 100) -> list[list[dict]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


def none_if_blank(value: str | None) -> str | None:
    value = str(value or "").strip()
    return value or None


def client_type_for(row: dict) -> str:
    if row.get("professional_name"):
        return "clinica"
    name = (row.get("clinic_name") or "").lower()
    if any(token in name for token in ("vet", "clinica", "clínica", "mascota", "pet", "animal")):
        return "clinica"
    return "medico_veterinario_independiente"


def build_branch_groups(rows: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for row in rows:
        if row.get("tax_id") and not row["is_deleted"]:
            groups[row["tax_id"]].append(row)
    return {nit: branches for nit, branches in groups.items() if len(branches) > 1}


def make_client_payload(row: dict, row_index: int) -> dict:
    phone_val = none_if_blank(row["phone"])
    if not phone_val:
        phone_val = f"s/tel-{row_index}"
    return {
        "external_code": none_if_blank(row["external_code"]),
        "clinic_name": row["clinic_name"],
        "tax_id": none_if_blank(row["tax_id"]),
        "phone": phone_val,
        "address": none_if_blank(row["address"]) or "Sin dirección",
        "city": none_if_blank(row["city"]) or "Bogotá",
        "zone": None,
        "billing_type": "cash",
        "is_active": not row["is_deleted"],
    }


def make_knowledge_payload(row: dict, synced_at: str, branch_info: dict | None = None) -> dict:
    source_payload = {
        "source": SOURCE_EXCEL,
        "sheet": SOURCE_SHEET,
        "row_number": row["row_number"],
        "raw_name": row["raw_name"],
        "invoice_status": row["invoice_status"],
        "professional_name": row.get("professional_name"),
    }
    observations_parts = []
    if row.get("professional_name"):
        observations_parts.append(f"Profesional responsable: {row['professional_name']}")
    if row["is_deleted"]:
        observations_parts.append("Registro eliminado en Alegra")
    if branch_info:
        observations_parts.append(branch_info["label"])
    observations = "; ".join(observations_parts) if observations_parts else None

    payload = {
        "clinic_key": row["clinic_key"],
        "clinic_name": row["clinic_name"],
        "is_registered": True,
        "is_new_client": False,
        "address": none_if_blank(row["address"]),
        "locality": none_if_blank(row["city"]),
        "phone": none_if_blank(row["phone"]),
        "email": none_if_blank(row["email"]),
        "sources_json": [source_payload],
        "source_excel": SOURCE_EXCEL,
        "source_updated_at": synced_at,
    }
    extra_sources = {}
    if none_if_blank(row["external_code"]):
        extra_sources["client_code"] = none_if_blank(row["external_code"])
    extra_sources["client_type"] = client_type_for(row)
    if none_if_blank(row["email"]):
        extra_sources["billing_email"] = none_if_blank(row["email"])
    extra_sources["electronic_invoicing"] = row["electronic_invoicing"]
    extra_sources["commercial_name"] = row["clinic_name"]
    if observations:
        extra_sources["observations"] = observations
    extra_sources["entered_flag"] = not row["is_deleted"]
    if row.get("tax_id"):
        extra_sources["tax_id"] = row["tax_id"]
    if branch_info:
        extra_sources["branch_group_nit"] = branch_info["nit"]
        extra_sources["branch_siblings"] = branch_info["siblings"]
        extra_sources["is_branch"] = True
    source_payload.update(extra_sources)
    payload["sources_json"] = [source_payload]
    return payload


def make_professional_payload(row: dict) -> dict | None:
    if not row.get("professional_name"):
        return None
    return {
        "clinic_key": row["clinic_key"],
        "professional_key": row["professional_key"],
        "professional_name": row["professional_name"],
        "source_sheet": SOURCE_SHEET,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga clientes de Alegra a la plataforma A3.")
    parser.add_argument("--apply", action="store_true", help="Aplica inserciones/upserts en Supabase.")
    args = parser.parse_args()

    load_dotenv()
    db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    all_rows = load_excel_rows()
    branch_groups = build_branch_groups(all_rows)

    existing_clients = db.table("clients").select("id, clinic_name, tax_id").limit(5000).execute().data or []
    existing_by_name = {normalize_key(row.get("clinic_name") or ""): row for row in existing_clients}

    new_rows = []
    update_rows = []
    for row in all_rows:
        key = row["clinic_key"]
        if key in existing_by_name:
            update_rows.append(row)
        else:
            new_rows.append(row)

    synced_at = datetime.now(timezone.utc).isoformat()

    client_inserts = [make_client_payload(row, idx) for idx, row in enumerate(new_rows)]
    client_updates = [make_client_payload(row, idx + len(new_rows)) for idx, row in enumerate(update_rows)]

    deleted_count = sum(1 for r in all_rows if r["is_deleted"])
    new_count = len(new_rows)
    update_count = len(update_rows)
    branch_count = sum(1 for r in all_rows if r.get("tax_id") and r["tax_id"] in branch_groups and not r["is_deleted"])
    no_nit_count = sum(1 for r in all_rows if not row.get("tax_id") or not row["tax_id"].strip()) if False else sum(1 for r in all_rows if not none_if_blank(r["tax_id"]))

    knowledge_payloads = []
    for row in all_rows:
        branch_info = None
        if row.get("tax_id") and row["tax_id"] in branch_groups and not row["is_deleted"]:
            branches = branch_groups[row["tax_id"]]
            siblings = [b["clinic_name"] for b in branches if b["clinic_key"] != row["clinic_key"]]
            branch_info = {
                "nit": row["tax_id"],
                "label": f"Sucursal de NIT {row['tax_id']} ({len(branches)} sedes)",
                "siblings": siblings,
            }
        knowledge_payloads.append(make_knowledge_payload(row, synced_at, branch_info))

    professional_payloads = [payload for row in all_rows if (payload := make_professional_payload(row))]

    print("IMPORT ALEGRA CLIENTES")
    print(f"modo={'apply' if args.apply else 'dry-run'}")
    print(f"total_excel={len(all_rows)}")
    print(f"activos={len(all_rows) - deleted_count}")
    print(f"eliminados_incluidos={deleted_count}")
    print(f"sin_nit_incluidos={no_nit_count}")
    print(f"sucursales_identificadas={len(branch_groups)} grupos, {branch_count} filas")
    print(f"clientes_existentes_actualizar={update_count}")
    print(f"clientes_nuevos_insertar={new_count}")
    print(f"knowledge_upserts={len(knowledge_payloads)}")
    print(f"profesionales_upserts={len(professional_payloads)}")

    if branch_groups:
        print("\nSucursales detectadas:")
        for nit, branches in branch_groups.items():
            names = [b["clinic_name"] for b in branches]
            print(f"  NIT {nit}: {', '.join(names)}")

    if not args.apply:
        print("\nNo se aplicaron cambios. Ejecuta con --apply para cargar.")
        return

    existing_phones = {
        row["phone"] for row in db.table("clients").select("phone").limit(10000).execute().data or [] if row.get("phone")
    }
    existing_external_codes = {
        row["external_code"] for row in db.table("clients").select("external_code").limit(10000).execute().data or [] if row.get("external_code")
    }

    inserted = 0
    for payload in client_inserts:
        phone = payload["phone"]
        while phone in existing_phones:
            phone = f"{payload['phone']}-{len(existing_phones)}"
            payload["phone"] = phone
        ext = payload.get("external_code")
        if ext and ext in existing_external_codes:
            payload["external_code"] = f"{ext}-dup"
        try:
            db.table("clients").insert(payload).execute()
            existing_phones.add(payload["phone"])
            if payload.get("external_code"):
                existing_external_codes.add(payload["external_code"])
            inserted += 1
        except Exception as e:
            print(f"  ERROR insertando {payload['clinic_name']}: {e}")
    print(f"Clientes insertados: {inserted}/{len(client_inserts)}")

    updated = 0
    for row, payload in zip(update_rows, client_updates):
        existing = existing_by_name[row["clinic_key"]]
        phone = payload["phone"]
        while phone in existing_phones and phone != existing.get("phone"):
            phone = f"{payload['phone']}-{len(existing_phones)}"
            payload["phone"] = phone
        try:
            db.table("clients").update(payload).eq("id", existing["id"]).execute()
            existing_phones.add(payload["phone"])
            updated += 1
        except Exception as e:
            print(f"  ERROR actualizando {payload['clinic_name']}: {e}")
    print(f"Clientes actualizados: {updated}/{len(client_updates)}")

    for batch in chunked(knowledge_payloads):
        db.table("clients_a3_knowledge").upsert(batch, on_conflict="clinic_key").execute()
    for batch in chunked(professional_payloads):
        db.table("clients_a3_professionals").upsert(
            batch,
            on_conflict="clinic_key,professional_key,source_sheet",
        ).execute()

    print("Carga aplicada correctamente.")


if __name__ == "__main__":
    main()