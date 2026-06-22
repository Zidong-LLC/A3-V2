"""
Script para limpiar datos de prueba de Supabase.
Borra: telegram_sessions, conversation_messages, requests, request_events.
NO toca: clients, client_courier_assignment (datos de referencia).
"""
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
import os

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
db = create_client(url, key)

tablas = ["request_events", "requests", "conversation_messages", "telegram_sessions"]

for tabla in tablas:
    result = db.table(tabla).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print(f"Limpiada: {tabla} ({len(result.data)} registros eliminados)")

print("\nListo. Podés empezar el test desde cero.")
