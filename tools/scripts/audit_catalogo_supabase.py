# -*- coding: utf-8 -*-
"""Contraste READ-ONLY: catálogo vivo en Supabase vs tabla canónica del PDF.
Solo SELECTs — no escribe nada (regla de guardrails)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from audit_catalogo_pdf import PDF_TESTS, PDF_PROFILES  # noqa: E402

from app.services import db  # noqa: E402

tests = db.list_catalog_tests()
profiles = db._client.table("catalog_profiles").select("code,name,price,is_active").execute().data

pdf_all = {**PDF_TESTS, **PDF_PROFILES}
live = {}
for r in tests:
    live[str(r["code"])] = (r.get("price"), r.get("name"), "tests")
for r in profiles:
    if r.get("is_active", True):
        live[str(r["code"])] = (r.get("price"), r.get("name"), "profiles")

faltan = sorted(set(pdf_all) - set(live), key=int)
extra = sorted(set(live) - set(pdf_all), key=int)
mismatch = []
for c in set(pdf_all) & set(live):
    p_pdf, p_live = pdf_all[c][0], live[c][0]
    if p_pdf is not None and p_live is not None and int(p_pdf) != int(p_live):
        mismatch.append((c, p_pdf, p_live, live[c][1]))

print(f"Supabase vivo: {len(tests)} tests + {len([r for r in profiles if r.get('is_active', True)])} perfiles activos")
if faltan:
    print(f"\nFALTAN en Supabase ({len(faltan)}):")
    for c in faltan:
        print(f"  {c}  {pdf_all[c][1]}")
if extra:
    print(f"\nEn Supabase pero no en el PDF ({len(extra)}):")
    for c in extra:
        print(f"  {c}  {live[c][1]}  [{live[c][2]}]")
if mismatch:
    print(f"\nPRECIOS distintos ({len(mismatch)}):")
    for c, a, b, n in sorted(mismatch, key=lambda x: int(x[0])):
        print(f"  {c}  {n}: PDF ${a:,} vs BD ${b:,}")
if not faltan and not mismatch:
    print("\nOK: la base viva cubre el PDF completo con los precios correctos")
sys.exit(1 if (faltan or mismatch) else 0)
