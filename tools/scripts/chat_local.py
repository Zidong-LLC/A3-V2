"""
REPL de consola para testear el agente A3 con HISTORIAL 0 (conversación nueva).

Usa el modelo OpenAI REAL (gpt configurado en .env) pero la BD está MOCKEADA en
memoria — reutiliza los mocks de `validate_flows.py`. Así cada ejecución arranca
desde cero, no depende de Supabase y no deja rastro.

Cliente registrado de prueba: "Veterinaria San Roque" (NIT 900123456).

Uso:  python tools/scripts/chat_local.py
Comandos dentro del chat:
  /reset   reinicia la conversación (historial 0 otra vez)
  /estado  muestra fase, intent y campos capturados
  /salir   termina (también Ctrl+C)
"""
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Reutilizamos toda la infraestructura de mocks de DB del validador de flujos.
from validate_flows import _PATCHES, _reset, _state  # noqa: E402

CHAT_ID = "chat-local"


def _print_estado():
    s = _state["session"]
    print("  · fase   :", s.get("phase_current"))
    print("  · intent :", s.get("intent_current"))
    print("  · cliente:", s.get("client_id"))
    print("  · campos :", s.get("captured_fields"))


def main():
    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in _PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        from app.agent import process_turn

        _reset(CHAT_ID)
        print("=" * 64)
        print("CHAT LOCAL A3 — historial 0 (BD mockeada, modelo real)")
        print("Cliente de prueba registrado: Veterinaria San Roque / NIT 900123456")
        print("Comandos: /reset  /estado  /salir")
        print("=" * 64)

        while True:
            try:
                msg = input("\nTÚ  > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nChau 👋")
                break

            if not msg:
                continue
            if msg in ("/salir", "/exit", "/quit"):
                print("Chau 👋")
                break
            if msg == "/reset":
                _reset(CHAT_ID)
                print("(conversación reiniciada — historial 0)")
                continue
            if msg == "/estado":
                _print_estado()
                continue

            try:
                reply = process_turn(CHAT_ID, msg)
            except Exception as exc:  # noqa: BLE001
                print(f"BOT > [EXCEPCIÓN] {type(exc).__name__}: {exc}")
                continue

            if reply is None:
                print("BOT > (sesión bloqueada/sin respuesta — el agente dejó de atender)")
            else:
                print(f"BOT > {reply}")
    finally:
        for p in patchers:
            p.stop()


if __name__ == "__main__":
    main()
