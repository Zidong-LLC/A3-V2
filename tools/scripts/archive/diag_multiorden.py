"""
Reproduce el flujo MULTI-ORDEN (caso Luciano) contra BD real + modelo real, sin
escribir. Imprime el estado de la orden en cada turno para ver por qué la orden de
seguimiento hereda paciente/análisis y cierra sola.  Uso: python tools/scripts/diag_multiorden.py
"""
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import diag_identificacion as di  # reutiliza _MEM_PATCHES (sesión en memoria, clientes reales)

SEQ = [
    "Holaaa", "1", "53115419-1", "Si",                       # Animal Pets por NIT
    "Dr Diego Grillo", "Lolo", "Es una perra Pitbull de 8 años", "Hembra", "José", "No",
    "hemograma", "contraentrega", "Si",                       # orden 1 registrada
    "A qué hora pasan aproximadamente?",                      # turno INTERMEDIO (saca de fase terminal)
    "Necesito hacer otra orden",                              # Fix 1: reset robusto pese al intermedio
    "Es para otro perro, el mismo médico y el mismo propietario",  # Fix 4: el mismo X por campo
    "Es una hembra se llama Leija",                           # R25: capturar sexo + nombre nuevo
]


def _st():
    f = di._state["session"]["captured_fields"]
    return (f"patient={f.get('patient_name')!r} exam={f.get('exam_type')!r} "
            f"tests={f.get('selected_tests')} doctor={f.get('requesting_doctor')!r} "
            f"phase={di._state['session'].get('phase_current')}")


def main():
    patchers = [patch(f"app.services.db.{n}", side_effect=fn) for n, fn in di._MEM_PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        from app.agent import process_turn
        di._reset("luciano-diag")
        for i, msg in enumerate(SEQ):
            reply = process_turn("luciano-diag", msg)
            print(f"USR: {msg}")
            print(f"BOT: {(reply or '').splitlines()[0][:150] if reply else reply}")
            print(f"   [{_st()}]")
            print("-")
    finally:
        for p in patchers:
            p.stop()


if __name__ == "__main__":
    main()
