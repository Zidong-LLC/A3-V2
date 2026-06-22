"""
Script de diagnóstico: prueba conexión Supabase y lookup de clientes.
Uso: py test_db.py
"""
from dotenv import load_dotenv
from supabase import create_client
import os


def main() -> None:
    load_dotenv()

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    db = create_client(url, key)

    print("=== Conexión Supabase: OK ===")

    print("\n=== Columnas disponibles en 'clients' ===")
    result = db.table("clients").select("*").limit(1).execute()
    if result.data:
        cols = list(result.data[0].keys())
        print("  Columnas:", cols)
        print("  Ejemplo de fila:")
        for k, v in result.data[0].items():
            print(f"    {k}: {v}")
    else:
        print("  Tabla vacía.")

    print("\n=== Primeros 5 clientes activos ===")
    result2 = db.table("clients").select("*").eq("is_active", True).limit(5).execute()
    if result2.data:
        for c in result2.data:
            print(f"  NIT: {c.get('tax_id')} | Nombre: {c.get('clinic_name')}")
    else:
        print("  Sin clientes activos.")


if __name__ == "__main__":
    main()
