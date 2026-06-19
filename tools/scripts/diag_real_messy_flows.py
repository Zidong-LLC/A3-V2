"""
Batería de conversaciones reales imperfectas contra modelo real + lecturas reales.
Mockea solo sesión/escritura: no inserta solicitudes ni mensajes en Supabase.

Uso: python tools/scripts/diag_real_messy_flows.py
"""
import re
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import diag_identificacion as di  # noqa: E402


ROBOTIC_MARKERS = (
    "dato que tengas a mano",
    "escribe 'hablar con alguien'",
    "Para avanzar, dime ese dato",
    "Para seguir con la orden necesito ese dato",
)


def _norm(text):
    text = (text or "").lower().translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]", "", text)


def _run(title, chat_id, turns, check):
    from app.agent import process_turn

    patchers = [patch(f"app.services.db.{name}", side_effect=fn) for name, fn in di._MEM_PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        di._reset(chat_id)
        replies = []
        print("=" * 72)
        print(f"FLUJO: {title}")
        for msg in turns:
            reply = process_turn(chat_id, msg, channel="chatwoot")
            replies.append(reply)
            print(f"  USR: {msg}")
            print(f"  BOT: {reply}")
            print("  -")

        issues = []
        bot_replies = [r for r in replies if r]
        for prev, cur in zip(bot_replies, bot_replies[1:]):
            if prev == cur:
                issues.append(f"BUCLE: respuesta repetida: {cur[:90]}")
        for reply in bot_replies:
            for marker in ROBOTIC_MARKERS:
                if marker in reply:
                    issues.append(f"ROBÓTICO: {marker!r} en {reply[:90]!r}")
        issues.extend(check(replies, di._state["session"].get("captured_fields") or {}))
        status = "OK" if not issues else "PROBLEMAS"
        print(f"  >>> {status}")
        for issue in issues:
            print(f"      ! {issue}")
        return title, status, issues
    finally:
        for p in patchers:
            p.stop()


def main():
    results = []

    def check_animal_planet(replies, fields):
        out = []
        if "Animal Planet" not in (replies[2] or "") or "Cuál es el correcto" not in (replies[2] or ""):
            out.append("no mostró opciones para Animal Planet dentro de frase larga")
        if fields.get("_client_not_found"):
            out.append("marcó como no encontrado un cliente que tenía opciones")
        if "sangre" not in _norm(fields.get("exam_type")):
            out.append(f"no absorbió análisis fuera de orden: {fields.get('exam_type')!r}")
        if "canino" not in _norm(fields.get("species")):
            out.append(f"no absorbió especie fuera de orden: {fields.get('species')!r}")
        if "5" not in _norm(fields.get("patient_age")):
            out.append(f"no absorbió edad fuera de orden: {fields.get('patient_age')!r}")
        return out

    results.append(_run(
        "A. Cliente en frase larga + datos adelantados",
        "messy-a",
        [
            "Hola",
            "Hola Siqui, quise hacer un análisis para un paciente que tengo",
            "La veterinaria con la que trabajo es Animal Planet, y pues básicamente quiero hacer un análisis de sangre para un perro que tiene alrededor de cinco años",
        ],
        check_animal_planet,
    ))

    def check_side_question(replies, fields):
        out = []
        answer = replies[1] or ""
        if "recog" not in _norm(answer) and "motorizado" not in _norm(answer):
            out.append("no respondió la pregunta lateral sobre recogida/motorizado")
        if not di._state["session"].get("client_id"):
            out.append("no identificó el cliente mencionado junto con la pregunta lateral")
        if "hembra" not in _norm(fields.get("sex")) or "canino" not in _norm(fields.get("species")):
            out.append("no absorbió 'perrita' como canino/hembra")
        return out

    results.append(_run(
        "B. Pregunta lateral + cliente exacto + datos mezclados",
        "messy-b",
        [
            "Hola",
            "quiero programar una ruta, ustedes sí recogen con motorizado? soy de Animal Planet HVP y necesito hemograma para una perrita de 5 años",
        ],
        check_side_question,
    ))

    def check_out_of_order(replies, fields):
        out = []
        expected = {
            "requesting_doctor": "laura",
            "patient_name": "luna",
            "species": "felino",
            "breed": "siames",
            "sex": "hembra",
            "patient_age": "2",
            "owner_name": "camila",
        }
        for field, value in expected.items():
            if value not in _norm(fields.get(field)):
                out.append(f"{field}: esperaba ~{value!r}, quedó {fields.get(field)!r}")
        if "observ" not in _norm(replies[-1] or "") and "analisis" not in _norm(replies[-1] or ""):
            out.append("no retomó el siguiente dato faltante después de absorber el bloque")
        return out

    results.append(_run(
        "C. Bloque de datos fuera de orden tras identificar",
        "messy-c",
        [
            "Hola",
            "1",
            "51731849-8",
            "sí, esa dirección está bien",
            "La doctora es Laura Méndez, la paciente Luna es una gatica siamesa hembra de 2 años y la propietaria es Camila Torres",
        ],
        check_out_of_order,
    ))

    def check_not_loop(replies, fields):
        out = []
        if "Cuál es el correcto" not in (replies[2] or ""):
            out.append("no hizo lookup inmediato de Animal Planet en la frase larga")
        if "Cuál es el correcto" not in (replies[3] or "") or "Animal Planet" not in (replies[3] or ""):
            out.append("ante 'ya te dije' no reofreció las opciones pendientes")
        if fields.get("clinic_name") and "ya te dije" in _norm(fields.get("clinic_name")):
            out.append("capturó la queja 'ya te dije' como nombre de clínica")
        if fields.get("_client_not_found"):
            out.append("terminó en no encontrado por una queja, no por un identificador real")
        if "Animal Planet" not in "\n".join(r or "" for r in replies):
            out.append("no mantuvo/reofreció las opciones reales de Animal Planet")
        return out

    results.append(_run(
        "D. Queja 'ya te dije' no debe convertirse en clínica",
        "messy-d",
        [
            "Hola",
            "1",
            "La veterinaria con la que trabajo es Animal Planet, necesito análisis de sangre para un perro de cinco años",
            "Ya te dije el nombre de la veterinaria",
        ],
        check_not_loop,
    ))

    def check_species_side_question(replies, fields):
        out = []
        reply = replies[-1] or ""
        if "canino" not in _norm(reply) and "felino" not in _norm(reply):
            out.append("no respondió la duda lateral sobre especies/animales")
        if "paciente" not in _norm(reply):
            out.append("no retomó el nombre del paciente después de responder la duda lateral")
        if fields.get("exam_type"):
            out.append(f"capturó una pregunta lateral como análisis: {fields.get('exam_type')!r}")
        return out

    results.append(_run(
        "E. Pregunta lateral de especies mientras pide paciente",
        "messy-e",
        [
            "Hola", "1", "51731849-8", "sí, esa dirección está bien", "Luciano Cutipa",
            "una pregunta, para qué cantidad de animales hacen análisis?",
        ],
        check_species_side_question,
    ))

    def check_blood_options(replies, fields):
        out = []
        reply = replies[-1] or ""
        if "1101" not in reply or "Cuadro Hem" not in reply:
            out.append("'análisis de sangre' no mostró opciones concretas de hematología")
        if fields.get("exam_type"):
            out.append(f"dejó 'análisis de sangre' como exam_type cerrado: {fields.get('exam_type')!r}")
        if not fields.get("_test_menu_options"):
            out.append("no guardó opciones de análisis para elegir por número")
        return out

    results.append(_run(
        "F. Análisis de sangre genérico muestra catálogo",
        "messy-f",
        [
            "Hola", "1", "51731849-8", "sí, esa dirección está bien", "Luciano Cutipa",
            "Mare", "básicamente es un perro de sin raza",
            "es una hembrita de cinco años más o menos, y quiero hacer un análisis de sangre",
        ],
        check_blood_options,
    ))

    def check_catalog_question(replies, fields):
        out = []
        reply = replies[-1] or ""
        if "opciones del catálogo" not in reply and "opciones del catalogo" not in _norm(reply):
            out.append("no mostró catálogo cuando el usuario pidió qué análisis hacen")
        if "1101" not in reply:
            out.append("el catálogo no incluyó códigos/precios de pruebas")
        if not fields.get("_test_menu_options"):
            out.append("no dejó opciones seleccionables después de mostrar catálogo")
        return out

    results.append(_run(
        "G. Pregunta 'qué análisis hacen' muestra opciones",
        "messy-g",
        [
            "Hola", "1", "51731849-8", "sí, esa dirección está bien", "Luciano Cutipa",
            "Mare", "perro sin raza hembra de 5 años", "Luciano", "sin observaciones",
            "no quisiera hacer otro tipo de análisis, yo no sé qué le puedo dar, me puedes decir qué tipo de análisis hacen",
        ],
        check_catalog_question,
    ))

    print("\n" + "=" * 72)
    print("RESUMEN")
    total = len(results)
    ok = sum(1 for _, status, _ in results if status == "OK")
    for title, status, _ in results:
        print(f"  [{status}] {title}")
    print(f"\n{ok}/{total} flujos imperfectos OK")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
