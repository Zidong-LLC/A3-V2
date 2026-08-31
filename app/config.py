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

# Ráfagas de mensajes (ERR-065): segundos que se espera a que el cliente termine de
# escribir antes de procesar TODOS sus mensajes juntos como uno solo. 0 = apagado
# (respuesta inmediata mensaje a mensaje, modo de los tests). MAX_WAIT es el tope duro.
MESSAGE_DEBOUNCE_SECONDS = float(os.environ.get("MESSAGE_DEBOUNCE_SECONDS", "5"))
MESSAGE_DEBOUNCE_MAX_WAIT = float(os.environ.get("MESSAGE_DEBOUNCE_MAX_WAIT", "20"))

# FSM en modo BLOQUEO (3.2): repara estados incoherentes además de loggearlos. Apagado
# por defecto: se enciende cuando los logs del observador acumulen evidencia limpia.
FSM_ENFORCE = os.environ.get("FSM_ENFORCE", "false").lower() in ("1", "true", "yes")

CHATWOOT_URL = os.environ.get("CHATWOOT_URL", "").rstrip("/")
CHATWOOT_ACCOUNT_ID = os.environ.get("CHATWOOT_ACCOUNT_ID", "")
CHATWOOT_API_TOKEN = os.environ.get("CHATWOOT_API_TOKEN", "")
CHATWOOT_AGENT_BOT_TOKEN = os.environ.get("CHATWOOT_AGENT_BOT_TOKEN", "")
# Secreto del webhook de Chatwoot (tapón #3 de WhatsApp): Chatwoot no firma los webhooks
# de agent bot, así que el secreto viaja en la URL (?token=...). Con la variable seteada
# el endpoint rechaza todo lo que no lo traiga; vacía = modo abierto SOLO para desarrollo.
CHATWOOT_WEBHOOK_SECRET = os.environ.get("CHATWOOT_WEBHOOK_SECRET", "")
CHATWOOT_INBOX_ID = os.environ.get("CHATWOOT_INBOX_ID", "")
CHATWOOT_TEAM_CONTABILIDAD = os.environ.get("CHATWOOT_TEAM_CONTABILIDAD", "")
CHATWOOT_TEAM_OPERACIONES = os.environ.get("CHATWOOT_TEAM_OPERACIONES", "")

PLATFORM_API_TOKEN = os.environ.get("PLATFORM_API_TOKEN", "")
DASHBOARD_ADMIN_USER = os.environ.get("DASHBOARD_ADMIN_USER", "admin")
DASHBOARD_ADMIN_PASSWORD = os.environ["DASHBOARD_ADMIN_PASSWORD"]

# Alegra — facturación electrónica DIAN (integración por fases, ver decisión 009).
# Con ALEGRA_ENABLED desactivado el agente se comporta igual que hoy: el flag protege
# producción mientras se prueba contra una cuenta nueva. Para migrar a la cuenta del
# cliente solo se cambian ALEGRA_EMAIL/ALEGRA_API_TOKEN en el .env, sin tocar código.
ALEGRA_ENABLED = os.environ.get("ALEGRA_ENABLED", "false").lower() in ("1", "true", "yes")
ALEGRA_EMAIL = os.environ.get("ALEGRA_EMAIL", "")
ALEGRA_API_TOKEN = os.environ.get("ALEGRA_API_TOKEN", "")
ALEGRA_BASE_URL = os.environ.get("ALEGRA_BASE_URL", "https://api.alegra.com/api/v1").rstrip("/")
# Mientras sea false (default) estamos en cuenta de PRUEBAS: el módulo de Facturación
# del dashboard deshabilita acciones que emiten/envían (reenviar correo, descargar XML).
# Solo se pone true al migrar a la cuenta real del cliente y autorizar emisión. Ver
# docs/guardrails-entorno-y-datos.md.
ALEGRA_PRODUCTION = os.environ.get("ALEGRA_PRODUCTION", "false").lower() in ("1", "true", "yes")
# Jerarquía PEDIDO → ÓRDENES → ANÁLISIS (decisión 011): la forma de pago no es un dato de
# cada orden sino del PEDIDO — se pregunta UNA vez al cerrar y se emite UNA factura con todas
# las órdenes. ENCENDIDO por defecto (2026-08-14): es lo acordado con A3, no un experimento,
# y con el default en false el flujo viejo volvía solo en cualquier entorno donde nadie
# configurara la variable. `PEDIDOS_ENABLED=false` queda como interruptor de emergencia.
PEDIDOS_ENABLED = os.environ.get("PEDIDOS_ENABLED", "true").lower() in ("1", "true", "yes")

# País de la cuenta Alegra: cambia los campos obligatorios al crear contactos e ítems
# (Colombia pide NIT/régimen/tipo de persona; Argentina pide CUIT/condición de IVA/unidad).
# Vacío = se detecta solo contra /company la primera vez que hay que crear algo.
ALEGRA_COUNTRY = os.environ.get("ALEGRA_COUNTRY", "").strip().lower()

# Portal Web (staff + clientes). La anon key solo se usa para el login GoTrue;
# si falta, el login del portal falla con mensaje claro sin afectar el resto.
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
PORTAL_RESULTS_BUCKET = os.environ.get("PORTAL_RESULTS_BUCKET", "lab-results")

# Modo demo del portal: SOLO para mostrar el portal en una llamada/presentación.
# Con PORTAL_DEMO_MODE=true, abrir el portal inicia sesión automáticamente como el
# cliente PORTAL_DEMO_CLIENT_ID, sin contraseña ni Supabase Auth. Mantener en false
# (o sin definir) en producción: el login normal queda intacto.
PORTAL_DEMO_MODE = os.environ.get("PORTAL_DEMO_MODE", "false").lower() in ("1", "true", "yes")
PORTAL_DEMO_CLIENT_ID = os.environ.get("PORTAL_DEMO_CLIENT_ID", "")

# Anarvet — espejo de resultados de exámenes (Fase 1, ver decisión 013). Acceso de SOLO
# lectura a su PostgreSQL: el usuario únicamente puede ejecutar fn_reporte_examenes().
# Todo con .get(): si falta una variable, la app arranca igual y el flag queda apagado —
# una var obligatoria faltante tumbaría el arranque entero en Render.
ANARVET_ENABLED = os.environ.get("ANARVET_ENABLED", "false").lower() in ("1", "true", "yes")
ANARVET_DB_HOST = os.environ.get("ANARVET_DB_HOST", "")
ANARVET_DB_PORT = int(os.environ.get("ANARVET_DB_PORT") or "5432")
ANARVET_DB_NAME = os.environ.get("ANARVET_DB_NAME", "VETERINARIA")
ANARVET_DB_USER = os.environ.get("ANARVET_DB_USER", "consulta")
ANARVET_DB_PASSWORD = os.environ.get("ANARVET_DB_PASSWORD", "")
# Servidor expuesto por IP cruda: probablemente sin TLS. "prefer" negocia cifrado si
# existe y no rompe si no; se puede forzar "require" desde el entorno sin tocar código.
ANARVET_SSLMODE = os.environ.get("ANARVET_SSLMODE", "prefer")

# Generación de PDF en el servidor (Anarvet Fase 2). Solo hace falta para PUBLICAR un
# informe al portal: verlo e imprimirlo desde el navegador nunca depende de esto. Se
# despliega apagado, igual que ANARVET_ENABLED, y se enciende tras verificar /health.
PDF_ENABLED = os.environ.get("PDF_ENABLED", "false").lower() in ("1", "true", "yes")
PDF_TIMEOUT_MS = int(os.environ.get("PDF_TIMEOUT_MS") or "20000")
# En Windows apunta al Chrome ya instalado (cero descarga); en Linux se deja vacío para
# usar el Chromium del entorno.
PDF_CHROME_CHANNEL = os.environ.get("PDF_CHROME_CHANNEL", "")
PDF_EXECUTABLE_PATH = os.environ.get("PDF_EXECUTABLE_PATH", "")
