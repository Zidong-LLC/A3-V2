"""
Reproducción de los HALLAZGOS de conversaciones reales de Chatwoot contra el
agente + modelo REALES (mockea solo Supabase, igual que validate_flows.py).

Cada flujo replica el guion de una conversación real problemática
(ver tasks/analisis-chatwoot/hallazgos.md) y verifica si el agente actual cae
en la misma trampa o ya la resolvió.

Uso:  python tools/scripts/diag_chatwoot.py            # todos
      python tools/scripts/diag_chatwoot.py H1 H3      # solo algunos
"""
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Reutilizamos TODA la infraestructura de validate_flows (BD en memoria + harness).
from tools.scripts.validate_flows import (  # noqa: E402
    _PATCHES, _reset, _state, _norm, _run_conversation, CLIENT,
)


def _count_confirmation_prompts(replies):
    """Cuántas veces el bot re-pidió confirmar el resumen (sin contar el cierre
    'Quedó registrado', que es el éxito, no un bucle)."""
    return sum(1 for r in replies if r and ("confirmas estos datos" in r.lower()
                                            or "¿confirmas o quieres cambiar" in r.lower()))


def main():
    only = [a.upper() for a in sys.argv[1:]]
    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in _PATCHES.items()]
    for p in patchers:
        p.start()
    results = []
    try:
        # ── H1 — Confirmación trabada (Conv 10, Gusmery) ────────────────────
        # Completa la orden, mete turnos intermedios y confirma varias veces.
        # FALLA si: la orden no se registra, o el resumen se repite >2 veces (bucle).
        def checks_h1(replies):
            out = []
            if len(_state["requests"]) < 1:
                out.append("H1 VIVO: el cliente confirmó pero la orden NUNCA se registró")
            if _count_confirmation_prompts(replies) > 3:
                out.append(f"H1 VIVO: pidió confirmar {_count_confirmation_prompts(replies)} veces sin cerrar (bucle)")
            return out

        if not only or "H1" in only:
            results.append(_run_conversation(
                "H1. Confirmación trabada (Gusmery)", "cw-h1",
                # Clave del caso real: el cliente NUNCA confirma la dirección explícitamente
                # (no dice "sí, esa está bien"); solo avanza dando el médico. La dirección
                # queda en _address_confirmation_pending y eso bloqueaba el cierre.
                ["Hola", "1", "Somos la Veterinaria San Roque",
                 "el médico es Dr. Juan Perez", "Fifi", "felino", "siamés", "hembra",
                 "2 meses", "Oscar Diaz", "sin observaciones", "perfil hepático felino",
                 "contraentrega",
                 # turnos de confirmación reales, con ruido intercalado:
                 "Confirmo los datos", "sí", "cierra la orden",
                 "esto no avanza", "ninguno", "sí"],
                checks_h1,
            ))

        # ── H3 — 2ª orden no pide paciente/análisis nuevos (Conv 1, Luciano) ─
        # Cierra orden 1, pide otra "para otro paciente". El bot DEBE volver a
        # pedir el paciente nuevo, no cerrar de una.
        def checks_h3(replies):
            out = []
            # Tras pedir "otra orden para otro paciente", el bot debe preguntar
            # por el paciente (no saltar al cierre).
            after = " ".join((r or "") for r in replies[15:]).lower()
            asked_patient = "paciente" in after or "cómo se llama" in after or "nombre del" in after
            if not asked_patient:
                out.append("H3 VIVO: la 2ª orden no volvió a pedir el paciente nuevo")
            if len(_state["requests"]) >= 2 and not asked_patient:
                out.append("H3 VIVO: registró la 2ª orden sin pedir paciente/análisis nuevos (arrastre)")
            return out

        if not only or "H3" in only:
            results.append(_run_conversation(
                "H3. Multi-orden: 2ª orden arrastra datos (Luciano)", "cw-h3",
                ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
                 "Dra. Laura Méndez", "Firulais", "canino", "labrador", "macho",
                 "3 años", "Pedro Gómez", "sin observaciones", "hemograma",
                 "contraentrega", "sí, confirmo",
                 # multi-orden real:
                 "podría ser otro análisis para otro paciente",
                 "sí, dale", "otro paciente nuevo"],
                checks_h3,
            ))

        # ── H4 — Estado arrastrado post-cierre (Conv 4, Chuuck) ──────────────
        # Tras cerrar, el cliente hace una pregunta general ("¿analizan reptiles?").
        # El bot NO debe responder con una pregunta de campo de orden ("¿médico?").
        def checks_h4(replies):
            out = []
            post = (replies[-1] or "").lower()
            if "médico solicitante" in post or "nombre del paciente" in post:
                out.append(f"H4 VIVO: tras el cierre, ante pregunta general respondió con un campo de orden: '{(replies[-1] or '')[:80]}'")
            return out

        if not only or "H4" in only:
            results.append(_run_conversation(
                "H4. Estado arrastrado post-cierre (Chuuck)", "cw-h4",
                ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
                 "Dra. Laura Méndez", "Firulais", "canino", "labrador", "macho",
                 "3 años", "Pedro Gómez", "sin observaciones", "hemograma",
                 "contraentrega", "sí, confirmo",
                 "¿hacen análisis a reptiles?"],
                checks_h4,
            ))

        # ── H2 — Bucle de identificación "soy veterinario" (Conv 11, Jorge) ──
        # Muchas coincidencias para "veterinario". El bot NO debe responder lo
        # mismo turno tras turno; debe mostrar opciones distintas o derivar.
        if not only or "H2" in only:
            MANY = [dict(CLIENT, id=f"c{i}", clinic_name=f"Veterinaria Norte {i}") for i in range(8)]

            def _h2_matches(q, limit=6):
                k = _norm(q)
                if "vet" in k or "veterinari" in k:
                    return MANY[:limit]
                return []

            with patch("app.services.db.find_client_matches", side_effect=_h2_matches):
                def checks_h2(replies):
                    out = []
                    # bucle: misma respuesta consecutiva ya lo detecta el harness;
                    # acá: ¿se quedó pidiendo afinar sin ofrecer derivar nunca?
                    bot = [r for r in replies if r]
                    last3 = bot[-3:]
                    derived = any(("comunic" in (r or "").lower() or "deriv" in (r or "").lower()
                                   or "operacion" in (r or "").lower() or "persona" in (r or "").lower())
                                  for r in last3)
                    stuck = len(set(last3)) == 1 and len(last3) == 3
                    if stuck and not derived:
                        out.append("H2 VIVO: 3 respuestas idénticas seguidas sin derivar (bucle de identificación)")
                    return out

                results.append(_run_conversation(
                    "H2. Bucle identificación 'soy veterinario' (Jorge)", "cw-h2",
                    ["Hola", "1", "soy veterinario", "Ver", "Vet",
                     "soy la veterinaria Josefa", "tienda mis mascotas"],
                    checks_h2,
                ))

        # ── H6 — Cliente nuevo: respuestas vacías + no recuerda "soy nuevo" (Conv 5) ──
        # El cliente dice de entrada que es nuevo y da un cliente inexistente. El bot
        # NO debe dar respuestas vacías ("Perfecto.") ni dar vueltas: debe escalar.
        def checks_h6(replies):
            out = []
            empty = [r for r in replies if r and len(r.strip()) < 15]
            if empty:
                out.append(f"H6 VIVO: respuestas vacías sin contenido útil: {empty}")
            if _state["session"]["phase_current"] != "fase_7_escalado":
                out.append(f"H6 VIVO: no escaló al cliente nuevo (phase={_state['session']['phase_current']})")
            return out

        if not only or "H6" in only:
            results.append(_run_conversation(
                "H6. Cliente nuevo: respuestas vacías (Sérgio)", "cw-h6",
                ["Hola", "Soy cliente nuevo y quiero tomar servicios",
                 "quiero programar ruta", "Pok Store Mascotas",
                 "1085253918", "sí, soy nuevo"],
                checks_h6,
            ))

        # ── H7 — Orden de campos: raza preguntada tarde (Conv 7, Adriana) ────
        # Tras dar especie, el bot debe pedir la RAZA antes que observaciones.
        # Observacional + check: que no pregunte observaciones teniendo la raza vacía.
        def checks_h7(replies):
            out = []
            joined = [(r or "").lower() for r in replies]
            obs_idx = next((i for i, r in enumerate(joined) if "observación" in r or "observacion" in r), None)
            raza_idx = next((i for i, r in enumerate(joined) if "raza" in r), None)
            if obs_idx is not None and raza_idx is not None and raza_idx > obs_idx:
                out.append("H7 VIVO: preguntó observaciones ANTES que la raza (orden de campos roto)")
            return out

        if not only or "H7" in only:
            results.append(_run_conversation(
                "H7. Orden de campos: raza tardía (Adriana)", "cw-h7",
                ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
                 "Dra. Adriana Rodríguez", "cuadro hemático", "Cenizo",
                 "equino", "macho", "3 años", "Josue Moreno"],
                checks_h7,
            ))
    finally:
        for p in patchers:
            p.stop()

    print("=" * 72)
    print("RESUMEN — Reproducción de hallazgos Chatwoot")
    for title, status, issues in results:
        if status == "SKIP":
            continue
        print(f"  [{status}] {title}")
    ran = [r for r in results if r[1] != "SKIP"]
    bad = [r for r in ran if r[1] != "OK"]
    print(f"\n{len(ran) - len(bad)}/{len(ran)} hallazgos SIN reproducir (OK = ya resuelto)")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
