"""
Script para limpiar datos de prueba de Supabase.
Borra: lab_results, request_events, requests, pedidos, conversation_messages,
telegram_sessions (en ese orden por las FK).
NO toca: clients, client_courier_assignment, catálogo (datos de referencia).
"""
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
import os

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
db = create_client(url, key)

# lab_results y pedidos se sumaron al esquema después de la versión original: sin
# borrarlos primero, la FK de requests frena todo (medido 2026-08-17).
tablas = ["lab_results", "request_events", "requests", "pedidos",
          "conversation_messages", "telegram_sessions"]

for tabla in tablas:
    result = db.table(tabla).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print(f"Limpiada: {tabla} ({len(result.data)} registros eliminados)")

print("\nListo. Podés empezar el test desde cero.")
