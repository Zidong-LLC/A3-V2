"""Marca qué clientes NO llevan factura electrónica, desde el Excel de terceros de Alegra.

Fuente: «Documentos de actualizacion/Alegra - Terceros v2 Actualizado.xlsx», columna
«Factura electrónica». Regla acordada con A3 (2026-08-27):

  - columna con «NO»  -> el cliente NO lleva factura electrónica: la factura sale a
    Consumidor Final y su nombre va en las notas (`electronic_invoice = false`).
  - columna vacía     -> sí lleva: se factura a su NIT y razón social (default `true`).

El cruce es por identificación contra `clients.tax_id`, normalizando el dígito de
verificación (el Excel trae «80871972» y la base «80871972-1»).

    python tools/scripts/import_factura_electronica.py            # simulación
    python tools/scripts/import_factura_electronica.py --aplicar  # escribe en la base
"""

import argparse
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.db import _client  # noqa: E402

EXCEL = ROOT / "Documentos de actualizacion" / "Alegra - Terceros v2 Actualizado.xlsx"
COL_NOMBRE, COL_IDENT, COL_FE = 0, 1, 9


def _base_nit(valor) -> str:
    """Solo dígitos y sin dígito de verificación: '80871972-1' y '80.871.972' -> '80871972'."""
    texto = str(valor or "").strip().split("-", 1)[0]
    return re.sub(r"[^0-9]", "", texto)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="escribe los cambios en la base")
    args = ap.parse_args()

    filas = list(openpyxl.load_workbook(EXCEL, data_only=True).active.iter_rows(values_only=True))[1:]
    sin_fe = [r for r in filas if str(r[COL_FE] or "").strip().upper() == "NO"]
    print(f"Excel: {len(filas)} terceros, {len(sin_fe)} marcados «NO»\n")

    clientes = _client.table("clients").select("id,clinic_name,tax_id").limit(2000).execute().data
    por_nit: dict[str, list[dict]] = {}
    for c in clientes:
        base = _base_nit(c.get("tax_id"))
        if base:
            por_nit.setdefault(base, []).append(c)

    # Un mismo NIT puede tener varias sedes (ERR-157: sucursal, no duplicado). Cuando pasa,
    # la nota de cada sede es su propio nombre — usar el del Excel le pondría a todas la
    # nota de una sola sede. Con un único cliente sí se usa el del Excel, que trae el
    # formato «(Veterinaria) Médico» que A3 ya escribe a mano en las facturas.
    encontrados, huerfanos, vistos = [], [], set()
    for fila in sin_fe:
        base = _base_nit(fila[COL_IDENT])
        candidatos = por_nit.get(base, [])
        if not candidatos:
            huerfanos.append((str(fila[COL_NOMBRE] or "")[:40], fila[COL_IDENT]))
            continue
        del_excel = str(fila[COL_NOMBRE] or "").strip()
        for c in candidatos:
            if c["id"] in vistos:
                continue
            vistos.add(c["id"])
            nota = del_excel if len(candidatos) == 1 else (c.get("clinic_name") or del_excel)
            encontrados.append((c, nota))

    print(f"Casan con un cliente de la base: {len(encontrados)}")
    for c, nota in encontrados:
        print(f"   {str(c['clinic_name'])[:34]:<34} NIT {str(c['tax_id']):<14} nota: {nota[:32]}")
    if huerfanos:
        print(f"\nSin cliente en la base ({len(huerfanos)}) — revisar a mano:")
        for nombre, ident in huerfanos:
            print(f"   {nombre:<42} ident {ident}")

    if not args.aplicar:
        print("\nSimulación. Volvé a correrlo con --aplicar para escribir.")
        return 0

    for c, nota in encontrados:
        _client.table("clients").update(
            {"electronic_invoice": False, "invoice_note": nota or c["clinic_name"]}
        ).eq("id", c["id"]).execute()
    marcados = _client.table("clients").select("id", count="exact").eq(
        "electronic_invoice", False
    ).limit(1).execute().count
    print(f"\nListo: {marcados} clientes quedaron como «sin factura electrónica».")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
