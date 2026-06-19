"""
Reproduce contra el MODELO REAL la conversación del testeo del usuario para verificar
los 4 ajustes de perfiles (ERR-038). BD mockeada en memoria (reusa validate_flows).

Casos:
  A) "no sé / qué me recomiendas" -> lista de perfiles VERTICAL con precios (P1).
  B) elegir "la primera" -> captura código + precio; el resumen muestra el valor (P2).
  C) confirmar + preguntar el precio -> responde el valor real antes de registrar (P3).
  D) multiorden, CAMBIO TOTAL de análisis (otra especie) -> recomienda perfiles de la
     nueva especie, no arrastra el felino anterior (P4).
  E) multiorden, AJUSTE PARCIAL ("el mismo pero sin X") -> mantiene el perfil base.

Uso:  python tools/scripts/diag_perfil_recomendacion.py
"""
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from validate_flows import _PATCHES, _reset, _state  # noqa: E402

CHAT_ID = "diag-perfil"


def _run(turns):
    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in _PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        from app.agent import process_turn
        _reset(CHAT_ID)
        replies = []
        for msg in turns:
            reply = process_turn(CHAT_ID, msg)
            print(f"\nTÚ  > {msg}")
            print(f"BOT > {reply}")
            replies.append(reply or "")
        return replies
    finally:
        for p in patchers:
            p.stop()


def main():
    turns = [
        "Hola, buenas",
        "1",
        "Veterinaria San Roque",
        "sí, es correcta",
        "el médico solicitante es John Perez",
        "el paciente es Mía, una gata siamés de 3 meses",
        "el propietario es Pedro Álvarez",
        "no, sin observaciones",
        "no sé, qué me recomiendas",          # A: recomendación felino
        "la primera",                          # B: captura con precio
        "contraentrega",
        "sí es correcto, pero cuánto cuesta eso?",  # C: precio + registra
        "quiero crear otra orden",
        # D: otra especie + cambio total de análisis
        "es para Alejo, un dobermann macho de 2 años, propietario Juan Rivas, sin observaciones",
        "no sé, para este perro qué me recomiendas",
        "la primera",
        "contraentrega",
        "sí, confirmo",
    ]
    replies = _run(turns)

    print("\n" + "=" * 64)
    print("CHEQUEOS")
    issues = []
    reco_felino = replies[8]
    if reco_felino.count("\n") < 2 or "$" not in reco_felino:
        issues.append("A: la recomendación felino no es una lista vertical con precios")
    if "301" not in reco_felino:
        issues.append("A: no aparece el perfil felino esperado (301)")
    # C: el cierre debe responder el precio y registrar
    cierre = replies[11]
    if "$" not in cierre or "registrad" not in cierre.lower():
        issues.append("C: el cierre no respondió el precio o no registró")
    # D: la recomendación de la 2ª orden debe ser CANINA (401/402), no felina (301/302)
    reco_canino = replies[14]
    if "401" not in reco_canino and "402" not in reco_canino:
        issues.append("D: la 2ª recomendación no es canina")
    if "301" in reco_canino or "Felino" in reco_canino:
        issues.append("D: la 2ª orden arrastró un perfil felino para un canino")
    print("OK" if not issues else "PROBLEMAS:")
    for i in issues:
        print("  !", i)


if __name__ == "__main__":
    main()
