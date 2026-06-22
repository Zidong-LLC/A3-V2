"""
Valida la COMPRENSIÓN del agente contra BD + modelo real (sin escribir): sinónimos,
datos implícitos, datos adelantados/múltiples y "el mismo X, cambia Y".
Uso:  python tools/scripts/diag_comprension.py
"""
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import diag_identificacion as di  # reutiliza _MEM_PATCHES (sesión en memoria, clientes reales)

NIT = "53115419-1"  # Animal Pets


def _norm(s):
    import re
    s = (s or "").lower().translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]", "", s)


def _run(turns):
    patchers = [patch(f"app.services.db.{n}", side_effect=fn) for n, fn in di._MEM_PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        from app.agent import process_turn
        di._reset("diag-comp")
        last = None
        for m in turns:
            last = process_turn("diag-comp", m)
        return last, di._state["session"]["captured_fields"]
    finally:
        for p in patchers:
            p.stop()


def check(titulo, turns, expect):
    reply, f = _run(turns)
    issues = []
    for field, val in expect.items():
        got = f.get(field)
        if _norm(val) not in _norm(got):
            issues.append(f"{field}: esperaba ~{val!r}, quedó {got!r}")
    estado = "OK" if not issues else "FALLA"
    print(f"[{estado}] {titulo}")
    print(f"   último BOT: {(reply or '').splitlines()[0][:110] if reply else reply}")
    for i in issues:
        print(f"   ! {i}")
    return not issues


if __name__ == "__main__":
    print("=" * 64)
    print("COMPRENSIÓN — sinónimos, datos implícitos y adelantados (modelo real)")
    print("=" * 64)
    # 1) "es una perra" al pedir especie → Canino + Hembra (dato implícito)
    check("1. 'es una perra' -> Canino + Hembra",
          ["Hola", "1", NIT, "si", "Dr Test", "Firulais", "es una perra"],
          {"species": "canino", "sex": "hembra"})
    # 2) Varios datos juntos al pedir el paciente
    check("2. 'Greta, una perra bulldog de 6 años' (varios datos)",
          ["Hola", "1", NIT, "si", "Dr Test", "Greta, una perra bulldog de 6 años"],
          {"patient_name": "greta", "species": "canino", "breed": "bulldog", "sex": "hembra"})
    # 3) Médico dentro de una frase larga
    check("3. médico en frase larga -> requesting_doctor",
          ["Hola", "1", NIT, "si", "voy a pedir varias órdenes, todas para el mismo doctor, soy el Dr. Gastón Alcojor"],
          {"requesting_doctor": "gaston"})
    # 4) "el mismo X, cambia Y" en orden de seguimiento: al pedir el PROPIETARIO, "el mismo
    #    que el anterior, solo cambia el paciente" debe resolver el PROPIETARIO (no el paciente).
    check("4. 'el mismo, solo cambia el paciente' (al pedir propietario) -> propietario",
          ["Hola", "1", NIT, "si", "Dra. Ana Ruiz", "Rocky",
           "es un perro macho labrador de 3 años", "José Pérez", "sin observaciones",
           "hemograma", "contraentrega", "si",
           "necesito otra orden", "perfecto",
           "el paciente se llama Mia", "es una gata siamesa de 2 años",
           "el mismo que el anterior, solo cambia el paciente"],
          {"owner_name": "jose"})
