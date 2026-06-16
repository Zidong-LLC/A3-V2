"""
Demo ANTES/DESPUÉS de ERR-018: corregir un dato en la confirmación.
Reutiliza los mocks de validate_flows (BD en memoria) y el MODELO REAL.
Corre un solo flujo (corrección del paciente) y reporta si la orden se registró.

Uso:  python tools/scripts/demo_correccion.py
"""
import sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))               # para importar validate_flows
sys.path.insert(0, str(HERE.parents[1]))    # raíz del proyecto (para app.*)

import validate_flows as vf  # reutiliza CLIENT, COURIER, _PATCHES, _reset, _state

TURNS = [
    "Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
    "Dra. Laura Méndez", "Firulais", "canino", "labrador", "macho",
    "3 años", "Pedro Gómez", "sin observaciones", "hemograma",
    "contraentrega",
    "espera, corrige el paciente: ahora se llama Rocky",   # <-- la corrección
    "sí, confirmo",                                         # <-- el cierre
]


def main():
    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in vf._PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        from app.agent import process_turn
        vf._reset("demo-err018")
        for msg in TURNS:
            reply = process_turn("demo-err018", msg)
            print(f"  USR: {msg}")
            print(f"  BOT: {reply}")
            print("  -")
        n = len(vf._state["requests"])
        paciente = None
        if n:
            paciente = (vf._state["requests"][-1].get("captured_fields") or {}).get("patient_name")
        print("=" * 60)
        print(f"  >>> ÓRDENES REGISTRADAS: {n}   (paciente: {paciente!r})")
        print("  >>> RESULTADO:", "OK — la orden se cerró" if n == 1 else "BUG — la orden NO se registró")
    finally:
        for p in patchers:
            p.stop()


if __name__ == "__main__":
    main()
