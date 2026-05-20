import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


ZONE_COURIERS = {
    1: "Javier",
    2: "Jeeferson",
    3: "Diego",
    4: "Luis",
    5: "Gerardo",
    6: "Alexander",
    7: "Marlon",
    8: "Cesar",
}

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "barrios_zonas_a3.csv"


def normalize_key(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


ZONE_TOTALS = {
    1: {"barrios": 335, "cantidad_barrios": 477, "upz": 23, "localidades": 8},
    2: {"barrios": 82, "cantidad_barrios": 95, "upz": 15, "localidades": 5},
    3: {"barrios": 176, "cantidad_barrios": 242, "upz": 14, "localidades": 3},
    4: {"barrios": 202, "cantidad_barrios": 305, "upz": 28, "localidades": 7},
    5: {"barrios": 446, "cantidad_barrios": 573, "upz": 32, "localidades": 5},
    6: {"barrios": 40, "cantidad_barrios": 52, "upz": 11, "localidades": 7},
    7: {"barrios": 207, "cantidad_barrios": 303, "upz": 16, "localidades": 5},
    8: {"barrios": 161, "cantidad_barrios": 216, "upz": 8, "localidades": 1},
}


ZONE_LOCALITIES = {
    1: [
        ("san_cristobal", "San Cristobal", 140),
        ("usme", "Usme", 96),
        ("rafael_uribe_uribe", "Rafael Uribe Uribe", 65),
        ("sumapaz", "Sumapaz", 15),
        ("antonio_narino", "Antonio Narino", 14),
        ("tunjuelito", "Tunjuelito", 3),
        ("puente_aranda", "Puente Aranda", 1),
        ("ciudad_bolivar", "Ciudad Bolivar", 1),
    ],
    2: [
        ("puente_aranda", "Puente Aranda", 46),
        ("tunjuelito", "Tunjuelito", 20),
        ("kennedy", "Kennedy", 10),
        ("ciudad_bolivar", "Ciudad Bolivar", 5),
        ("bosa", "Bosa", 1),
    ],
    3: [("kennedy", "Kennedy", 171), ("puente_aranda", "Puente Aranda", 4), ("los_martires", "Los Martires", 1)],
    4: [
        ("fontibon", "Fontibon", 76),
        ("chapinero", "Chapinero", 49),
        ("barrios_unidos", "Barrios Unidos", 41),
        ("teusaquillo", "Teusaquillo", 31),
        ("engativa", "Engativa", 3),
        ("los_martires", "Los Martires", 1),
        ("puente_aranda", "Puente Aranda", 1),
    ],
    5: [
        ("suba", "Suba", 214),
        ("usaquen", "Usaquen", 134),
        ("engativa", "Engativa", 96),
        ("fontibon", "Fontibon", 1),
        ("antonio_narino", "Antonio Narino", 1),
    ],
    6: [
        ("los_martires", "Los Martires", 19),
        ("la_candelaria", "La Candelaria", 8),
        ("rafael_uribe_uribe", "Rafael Uribe Uribe", 6),
        ("antonio_narino", "Antonio Narino", 3),
        ("tunjuelito", "Tunjuelito", 2),
        ("kennedy", "Kennedy", 1),
        ("puente_aranda", "Puente Aranda", 1),
    ],
    7: [
        ("bosa", "Bosa", 160),
        ("santa_fe", "Santa Fe", 38),
        ("kennedy", "Kennedy", 7),
        ("tunjuelito", "Tunjuelito", 1),
        ("puente_aranda", "Puente Aranda", 1),
    ],
    8: [("ciudad_bolivar", "Ciudad Bolivar", 161)],
}


def build_zone_rows() -> list[dict]:
    rows = []
    for zone_number, courier_name in ZONE_COURIERS.items():
        totals = ZONE_TOTALS[zone_number]
        localities = ZONE_LOCALITIES[zone_number]
        rows.append({
            "zone_number": zone_number,
            "courier_name": courier_name,
            "courier_phone": "",
            "total_barrios": totals["barrios"],
            "total_cantidad_barrios": totals["cantidad_barrios"],
            "total_upz": totals["upz"],
            "total_localidades": totals["localidades"],
            "localities_text": ", ".join(name for _code, name, _count in localities),
        })
    return rows


def build_locality_zone_rows() -> list[dict]:
    rows = []
    for zone_number, localities in ZONE_LOCALITIES.items():
        for code, name, barrios_count in localities:
            rows.append({
                "zone_number": zone_number,
                "courier_name": ZONE_COURIERS[zone_number],
                "locality_code": code,
                "locality_name": name,
                "barrios_count": barrios_count,
            })
    return sorted(rows, key=lambda row: (row["zone_number"], row["locality_name"]))


@lru_cache(maxsize=1)
def load_neighborhood_rows() -> tuple[dict, ...]:
    if not DATA_PATH.exists():
        return ()
    with DATA_PATH.open(newline="", encoding="utf-8") as fh:
        rows = []
        for row in csv.DictReader(fh):
            rows.append({
                "locality_code": row["locality_code"],
                "locality_name": row["locality_name"],
                "upz_name": row["upz_name"],
                "neighborhood_name": row["neighborhood_name"],
                "zone_number": int(row["zone_number"]),
                "cantidad_barrios": int(row["cantidad_barrios"] or 0),
            })
        return tuple(rows)


def suggest_zone_for_location(
    *,
    neighborhood: str | None = None,
    locality: str | None = None,
    zone: str | None = None,
    address: str | None = None,
) -> dict:
    rows = load_neighborhood_rows()
    neighborhood_key = normalize_key(neighborhood)
    locality_key = normalize_key(locality or zone)
    address_key = normalize_key(address)

    if neighborhood_key:
        matches = [row for row in rows if normalize_key(row["neighborhood_name"]) == neighborhood_key]
        if locality_key:
            scoped = [row for row in matches if normalize_key(row["locality_name"]) == locality_key]
            if scoped:
                matches = scoped
        if matches:
            row = matches[0]
            return {**row, "courier_name": ZONE_COURIERS[row["zone_number"]], "match_type": "neighborhood", "confidence": "high"}

    if address_key:
        matches = [row for row in rows if normalize_key(row["neighborhood_name"]) and normalize_key(row["neighborhood_name"]) in address_key]
        if locality_key:
            scoped = [row for row in matches if normalize_key(row["locality_name"]) == locality_key]
            if scoped:
                matches = scoped
        if matches:
            row = max(matches, key=lambda item: len(normalize_key(item["neighborhood_name"])))
            return {**row, "courier_name": ZONE_COURIERS[row["zone_number"]], "match_type": "address", "confidence": "medium"}

    if locality_key:
        locality_rows = [row for row in build_locality_zone_rows() if normalize_key(row["locality_name"]) == locality_key]
        if locality_rows:
            row = max(locality_rows, key=lambda item: item["barrios_count"])
            return {**row, "courier_name": ZONE_COURIERS[row["zone_number"]], "match_type": "locality", "confidence": "medium"}

    zone_key = normalize_key(zone)
    if zone_key.isdigit() and int(zone_key) in ZONE_COURIERS:
        zone_number = int(zone_key)
        return {"zone_number": zone_number, "courier_name": ZONE_COURIERS[zone_number], "match_type": "zone", "confidence": "medium"}

    return {"zone_number": None, "courier_name": None, "match_type": "none", "confidence": "low"}


def search_neighborhoods(query: str, limit: int = 12) -> list[dict]:
    query_key = normalize_key(query)
    if len(query_key) < 2:
        return []

    scored = []
    for row in load_neighborhood_rows():
        neighborhood_key = normalize_key(row["neighborhood_name"])
        locality_key = normalize_key(row["locality_name"])
        upz_key = normalize_key(row["upz_name"])
        if query_key == neighborhood_key:
            score = 0
        elif neighborhood_key.startswith(query_key):
            score = 1
        elif query_key in neighborhood_key:
            score = 2
        elif locality_key.startswith(query_key):
            score = 3
        elif query_key in upz_key:
            score = 4
        else:
            continue
        scored.append((score, row["neighborhood_name"], row))

    results = []
    seen = set()
    for _score, _name, row in sorted(scored, key=lambda item: (item[0], normalize_key(item[1])))[:limit * 2]:
        key = (row["neighborhood_name"], row["locality_name"], row["zone_number"])
        if key in seen:
            continue
        seen.add(key)
        results.append({**row, "courier_name": ZONE_COURIERS[row["zone_number"]]})
        if len(results) >= limit:
            break
    return results
