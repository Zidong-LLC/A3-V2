"""
conftest.py — Configuración global de pytest para A3-V2.

Inyecta variables de entorno dummy ANTES de que se importe cualquier módulo
de la app. Necesario porque config.py usa os.environ[] (falla sin .env).

Todos los tests mockean 100% las llamadas externas (Supabase, OpenAI, Telegram),
por lo que no se necesitan credenciales reales.
"""
import os
import pytest


def pytest_configure(config):
    """Inyectar env vars dummy antes de cualquier import de la app."""
    os.environ.setdefault("TELEGRAM_BOT_TOKEN",        "test-bot-token")
    os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET",   "test-webhook-secret")
    os.environ.setdefault("TELEGRAM_WEBHOOK_URL",      "https://test.example.com/webhook")
    os.environ.setdefault("SUPABASE_URL",              "https://test.supabase.co")
    # Clave con formato JWT válido para que el cliente Supabase no falle al importar.
    os.environ.setdefault(
        "SUPABASE_SERVICE_ROLE_KEY",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ0ZXN0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSJ9.signature",
    )
    os.environ.setdefault("OPENAI_API_KEY",            "test-openai-key")
    os.environ.setdefault("FLASK_SECRET_KEY",          "test-flask-secret")
    os.environ.setdefault("APP_ENV",                   "test")
    os.environ.setdefault("APP_TIMEZONE",              "America/Bogota")
    os.environ.setdefault("CUTOFF_TIME",               "17:30")
    os.environ.setdefault("DASHBOARD_ADMIN_PASSWORD",  "test-secret")
    os.environ.setdefault("SUPABASE_ANON_KEY",         "test-anon-key")
    # La API interna es fail-closed: sin token queda cerrada (503). Los tests la
    # ejercitan con token para probar el camino real, no un bypass.
    os.environ.setdefault("PLATFORM_API_TOKEN",        "test-platform-token")
    # Debounce de ráfagas APAGADO en tests: los webhooks responden síncrono e inmediato.
    os.environ.setdefault("MESSAGE_DEBOUNCE_SECONDS",  "0")
