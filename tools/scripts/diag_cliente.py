"""
Diagnóstico read-only: verifica a qué Supabase apunta el agente y por qué no
encuentra un cliente. Usa el MISMO cliente Supabase que el agente (mismas
credenciales del .env). Uso:  python tools/scripts/diag_cliente.py "Animal Planet"
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.config import SUPABASE_URL
from app.services import db

query = sys.argv[1] if len(sys.argv) > 1 else "Animal Planet"

print(f"Proyecto Supabase del agente: {SUPABASE_URL}")
print(f"Buscando: {query!r}")
print("-" * 64)

# 1) Filas en `clients` cuyo nombre contiene cada palabra (SIN filtrar is_active)
tokens = [t for t in query.split() if len(t) >= 3] or [query]
for term in tokens:
    res = (
        db._client.table("clients")
        .select("id, clinic_name, tax_id, is_active")
        .ilike("clinic_name", f"%{term}%")
        .execute()
    )
    rows = res.data or []
    print(f"clinic_name ILIKE %{term}%  →  {len(rows)} fila(s)")
    for r in rows:
        print(f"   - {r.get('clinic_name')!r:45} is_active={r.get('is_active')}  tax_id={r.get('tax_id')}")

print("-" * 64)
# 2) Lo que devuelve el agente (solo activos, con su scoring)
matches = db.find_client_matches(query)
print(f"find_client_matches({query!r})  →  {len(matches)} resultado(s) [solo is_active=True]")
for m in matches:
    print(f"   - {m.get('clinic_name')!r}")

print("-" * 64)
# 3) Totales para ubicar el contexto
total = db._client.table("clients").select("id", count="exact").execute()
activos = db._client.table("clients").select("id", count="exact").eq("is_active", True).execute()
print(f"clients totales: {total.count}   |   activos: {activos.count}")
