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
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

APP_TIMEZONE = ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Bogota"))
CUTOFF_HOUR, CUTOFF_MINUTE = map(int, os.environ.get("CUTOFF_TIME", "17:30").split(":"))

# Descuentos por volumen para perfiles personalizados (Sección 5 del spec).
# Lista de tramos (mínimo de pruebas, fracción de descuento). Ajustables desde aquí
# por variación de costos. 15+ pruebas mantienen el tope de 27%.
# NO aplica a pruebas de convenio (ver CONVENIO_LABELS): esas no reciben descuento
# ni cuentan para el número de pruebas que define el tramo.
DISCOUNT_TIERS: list[tuple[int, float]] = [
    (2, 0.12), (3, 0.13), (4, 0.14), (5, 0.16), (6, 0.18),
    (7, 0.19), (8, 0.20), (9, 0.21), (10, 0.22), (11, 0.23),
    (12, 0.24), (13, 0.25), (14, 0.26), (15, 0.27),
]

# Pruebas de convenio: excluidas de descuentos por volumen (parte final del portafolio).
CONVENIO_LABELS: tuple[str, ...] = (
    "Convenio Servipat", "Convenio serología de rabia", "Convenio LMV", "Convenio Mascolab",
)

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
