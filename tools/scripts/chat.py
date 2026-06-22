"""
REPL de consola para testear el agente A3 directamente.
Uso: py chat.py [chat_id]
     py chat.py --reset   (limpia sesión antes de empezar)
"""
from dotenv import load_dotenv
load_dotenv()

import sys
import io
import textwrap

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")

TEST_CHAT_ID = "test-local-001"


def reset_session(chat_id: str):
    from supabase import create_client
    import os
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    for tabla in ["request_events", "requests", "conversation_messages", "telegram_sessions"]:
        db.table(tabla).delete().eq(
            "external_chat_id" if tabla in ("telegram_sessions", "conversation_messages") else "id",
            chat_id if tabla in ("telegram_sessions", "conversation_messages")
            else "00000000-0000-0000-0000-000000000001"  # no-op delete para requests
        ).execute()
    # Borrar requests vinculados a la sesión (por session_id)
    sessions = db.table("telegram_sessions").select("id").eq("external_chat_id", chat_id).execute()
    session_ids = [s["id"] for s in (sessions.data or [])]
    for sid in session_ids:
        db.table("request_events").delete().eq("request_id", sid).execute()
        db.table("requests").delete().eq("session_id", sid).execute()
    db.table("conversation_messages").delete().eq("external_chat_id", chat_id).execute()
    db.table("telegram_sessions").delete().eq("external_chat_id", chat_id).execute()
    print(f"[reset] Sesión {chat_id} limpiada.\n")


def main():
    args = sys.argv[1:]
    do_reset = "--reset" in args
    chat_id = next((a for a in args if not a.startswith("--")), TEST_CHAT_ID)

    if do_reset:
        reset_session(chat_id)

    from app.agent import process_turn

    print("=" * 60)
    print(f"  A3 Laboratorio Veterinario — Test REPL")
    print(f"  chat_id: {chat_id}")
    print(f"  Ctrl+C o escribe 'salir' para terminar")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[fin de sesión]")
            break

        if not user_input:
            continue
        if user_input.lower() in {"salir", "exit", "quit"}:
            print("[fin de sesión]")
            break

        try:
            reply = process_turn(chat_id, user_input)
            wrapped = textwrap.fill(reply, width=58, subsequent_indent="      ")
            print(f"A3:   {wrapped}\n")
        except Exception as e:
            print(f"[ERROR] {e}\n")


if __name__ == "__main__":
    main()
