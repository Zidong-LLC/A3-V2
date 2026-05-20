import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_WEBHOOK_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]
TELEGRAM_WEBHOOK_URL = os.environ["TELEGRAM_WEBHOOK_URL"]

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-nano")

APP_TIMEZONE = ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Bogota"))
CUTOFF_HOUR, CUTOFF_MINUTE = map(int, os.environ.get("CUTOFF_TIME", "17:30").split(":"))

FLASK_SECRET_KEY = os.environ["FLASK_SECRET_KEY"]
APP_ENV = os.environ.get("APP_ENV", "production")

CHATWOOT_URL = os.environ.get("CHATWOOT_URL", "").rstrip("/")
CHATWOOT_ACCOUNT_ID = os.environ.get("CHATWOOT_ACCOUNT_ID", "")
CHATWOOT_API_TOKEN = os.environ.get("CHATWOOT_API_TOKEN", "")
CHATWOOT_AGENT_BOT_TOKEN = os.environ.get("CHATWOOT_AGENT_BOT_TOKEN", "")
CHATWOOT_INBOX_ID = os.environ.get("CHATWOOT_INBOX_ID", "")
CHATWOOT_TEAM_CONTABILIDAD = os.environ.get("CHATWOOT_TEAM_CONTABILIDAD", "")
CHATWOOT_TEAM_OPERACIONES = os.environ.get("CHATWOOT_TEAM_OPERACIONES", "")

PLATFORM_API_TOKEN = os.environ.get("PLATFORM_API_TOKEN", "")
DASHBOARD_ADMIN_USER = os.environ.get("DASHBOARD_ADMIN_USER", "admin")
DASHBOARD_ADMIN_PASSWORD = os.environ.get("DASHBOARD_ADMIN_PASSWORD", "admin123")
