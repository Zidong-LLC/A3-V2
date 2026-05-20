import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.territory import ZONE_COURIERS  # noqa: E402

DATA_PATH = ROOT / "data" / "barrios_zonas_a3.csv"


def _load_env(path: str | None) -> None:
    if path:
        load_dotenv(path)
    else:
        load_dotenv(ROOT / ".env")


def _table_exists(client, table: str) -> bool:
    try:
        client.table(table).select("*").limit(1).execute()
        return True
    except Exception:
        return False


def _find_courier(client, name: str) -> dict | None:
    result = client.table("couriers").select("id, name, phone, availability, is_active").ilike("name", name).limit(1).execute()
    return (result.data or [None])[0]


def _ensure_couriers(client) -> dict[int, dict]:
    couriers_by_zone = {}
    for zone_number, name in ZONE_COURIERS.items():
        row = _find_courier(client, name)
        if row:
            client.table("couriers").update({"is_active": True, "availability": row.get("availability") or "available"}).eq("id", row["id"]).execute()
            couriers_by_zone[zone_number] = row
            continue
        payload = {
            "name": name,
            "phone": f"pendiente-zona-{zone_number}",
            "availability": "available",
            "is_active": True,
        }
        created = client.table("couriers").insert(payload).execute().data[0]
        couriers_by_zone[zone_number] = created
    return couriers_by_zone


def _read_neighborhoods() -> list[dict]:
    with DATA_PATH.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _build_zone_payloads(rows: list[dict], couriers_by_zone: dict[int, dict]) -> list[dict]:
    by_zone = defaultdict(list)
    for row in rows:
        by_zone[int(row["zone_number"])].append(row)

    payloads = []
    for zone_number, courier_name in ZONE_COURIERS.items():
        zone_rows = by_zone[zone_number]
        localities = sorted({row["locality_name"] for row in zone_rows})
        upz = {row["upz_name"] for row in zone_rows}
        courier = couriers_by_zone[zone_number]
        payloads.append({
            "zone_number": zone_number,
            "courier_id": courier["id"],
            "courier_name": courier_name,
            "courier_phone": courier.get("phone") or "",
            "total_barrios": len(zone_rows),
            "total_cantidad_barrios": sum(int(row["cantidad_barrios"] or 0) for row in zone_rows),
            "total_upz": len(upz),
            "total_localidades": len(localities),
            "localities_text": ", ".join(localities),
            "source": "barrios_zonas_a3",
        })
    return payloads


def _build_neighborhood_payloads(rows: list[dict]) -> list[dict]:
    return [
        {
            "locality_code": row["locality_code"],
            "locality_name": row["locality_name"],
            "upz_name": row["upz_name"],
            "neighborhood_name": row["neighborhood_name"],
            "zone_number": int(row["zone_number"]),
            "courier_name": ZONE_COURIERS[int(row["zone_number"])],
            "cantidad_barrios": int(row["cantidad_barrios"] or 0),
            "source": "barrios_zonas_a3",
        }
        for row in rows
    ]


def _chunks(rows: list[dict], size: int = 400):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga zonas territoriales A3 en Supabase.")
    parser.add_argument("--env-file", help="Ruta a .env con SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY")
    args = parser.parse_args()

    _load_env(args.env_file)
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    rows = _read_neighborhoods()
    couriers_by_zone = _ensure_couriers(client)

    print(f"couriers_ok={len(couriers_by_zone)}")
    if not _table_exists(client, "territorial_zones") or not _table_exists(client, "territorial_neighborhoods"):
        print("territory_tables_missing=1")
        print("apply_migration=db/migrations/006_territorial_zones.sql")
        return 2

    client.table("territorial_zones").upsert(_build_zone_payloads(rows, couriers_by_zone), on_conflict="zone_number").execute()
    neighborhood_payloads = _build_neighborhood_payloads(rows)
    for chunk in _chunks(neighborhood_payloads):
        client.table("territorial_neighborhoods").upsert(
            chunk,
            on_conflict="locality_code,upz_name,neighborhood_name,zone_number",
        ).execute()

    print("territorial_zones_ok=8")
    print(f"territorial_neighborhoods_ok={len(neighborhood_payloads)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
