import argparse
import json
import os
import re
from pathlib import Path
from urllib import error, request

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIGRATION = ROOT / "db" / "migrations" / "006_territorial_zones.sql"


def _load_env(path: str | None) -> None:
    load_dotenv(path or ROOT / ".env")


def _project_ref() -> str:
    explicit = os.environ.get("SUPABASE_PROJECT_REF", "").strip()
    if explicit:
        return explicit
    url = os.environ.get("SUPABASE_URL", "")
    match = re.search(r"https://([^.]+)\.supabase\.co", url)
    if not match:
        raise SystemExit("Missing SUPABASE_PROJECT_REF or valid SUPABASE_URL")
    return match.group(1)


def _execute_sql_with_access_token(sql: str) -> None:
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing SUPABASE_ACCESS_TOKEN. Service role keys cannot create tables.")

    endpoint = f"https://api.supabase.com/v1/projects/{_project_ref()}/database/query"
    payload = json.dumps({"query": sql}).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            print(f"migration_status={resp.status}")
            if body.strip():
                print("migration_response=ok")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"migration_failed status={exc.code} body={body[:500]}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Aplica una migracion SQL en Supabase usando SUPABASE_ACCESS_TOKEN.")
    parser.add_argument("--env-file", help="Ruta a .env con SUPABASE_URL y SUPABASE_ACCESS_TOKEN")
    parser.add_argument("--migration", default=str(DEFAULT_MIGRATION), help="Ruta del archivo SQL a aplicar")
    args = parser.parse_args()

    _load_env(args.env_file)
    sql = Path(args.migration).read_text(encoding="utf-8")
    _execute_sql_with_access_token(sql)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
