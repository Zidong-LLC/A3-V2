"""Crea usuarios del Portal Web de clientes en Supabase Auth (entorno de PRUEBAS).

El portal es SOLO para clientes veterinarias: cada cuenta queda ligada a un
client_id en app_metadata (solo editable con service role). El personal del
laboratorio usa el dashboard, no el portal. Este script es la única vía de alta.

Uso:
  python tools/scripts/create_portal_user.py --email vet@x.test --password '...' \
      --client-id <uuid de clients>
"""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Alta de clientes del Portal Web A3.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--client-id", required=True, help="UUID en clients")
    parser.add_argument("--env-file", help="Ruta a .env (default: raíz del repo)")
    args = parser.parse_args()

    load_dotenv(args.env_file or ROOT / ".env")
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    result = sb.table("clients").select("id, clinic_name").eq("id", args.client_id).execute()
    if not result.data:
        raise SystemExit(f"client_id {args.client_id} no existe en clients")
    print(f"cliente={result.data[0]['clinic_name']}")

    created = sb.auth.admin.create_user({
        "email": args.email,
        "password": args.password,
        "email_confirm": True,
        "app_metadata": {"portal_role": "client", "client_id": args.client_id},
    })
    print(f"usuario_creado id={created.user.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
