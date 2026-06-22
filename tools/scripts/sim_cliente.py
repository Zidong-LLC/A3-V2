"""
Simulador adversarial: una IA hace de CLIENTE humano (caótico, con typos, datos
en desorden, off-topic, evasivo) y conversa contra el AGENTE REAL (process_turn
con modelo OpenAI real). Sirve para encontrar dónde el agente AGUANTA datos
imperfectos y dónde se rompe — sin respuestas hardcodeadas.

BD mockeada en memoria (reutiliza validate_flows). Cliente registrado de prueba:
"Veterinaria San Roque" / NIT 900123456.

Uso:
  python tools/scripts/sim_cliente.py                # corre todas las personas
  python tools/scripts/sim_cliente.py apurado caotico  # solo esas personas
  python tools/scripts/sim_cliente.py --turns 16     # límite de turnos por charla
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from validate_flows import _PATCHES, _reset, _state  # noqa: E402
from app.config import OPENAI_API_KEY, OPENAI_MODEL  # noqa: E402
from openai import OpenAI  # noqa: E402

_oai = OpenAI(api_key=OPENAI_API_KEY)

# Datos REALES que el cliente simulado conoce (coinciden con los mocks de BD).
DATOS_CLIENTE = (
    "Trabajás en la 'Veterinaria San Roque' (registrada, NIT 900123456). "
    "Médico solicitante: Dra. Laura Méndez. Paciente: Firulais, canino, labrador, "
    "macho, 3 años. Dueño: Pedro Gómez. Querés un hemograma. Pago contraentrega."
)

# Cada persona estresa una dimensión distinta de la robustez del agente.
PERSONAS = {
    "apurado": (
        "Sos un veterinario apurado y cortante. Respondés con frases muy cortas, "
        "a veces das dos datos juntos, a veces uno incompleto. No saludás de más. "
        "Querés programar la recogida YA."
    ),
    "caotico": (
        "Escribís con typos, sin tildes, mezclás mayúsculas, y a veces metés el "
        "dato pedido junto con otra cosa que no se pidió. Das la edad sin unidad "
        "('3'), el NIT como 'nit 900123456'. Te desviás una vez preguntando algo "
        "del clima o cómo va el día, y después seguís."
    ),
    "evasivo": (
        "Dudás de los datos. A veces decís 'no me acuerdo ahora', 'déjame ver', "
        "'creo que...'. No das todo de una. Hay que insistirte con calidez. "
        "Eventualmente terminás dando los datos."
    ),
    "desordenado": (
        "Das los datos en el orden que se te ocurre, NO en el que te preguntan. "
        "Si te piden la especie podés contestar el sexo o el nombre del dueño. "
        "Adelantás datos y después te confundís de cuál falta."
    ),
    "preventa": (
        "Antes de identificarte, hacés preguntas de preventa: '¿atienden en "
        "Bogotá?', '¿cómo es la metodología?', '¿ustedes recogen la muestra?'. "
        "Recién después decís que estás registrado y querés programar."
    ),
    "no_registrado": (
        "Trabajás en la 'Clínica Patitas del Norte', que NO está registrada con "
        "A3. Insistís en que te programen una recogida. No tenés NIT en el sistema."
    ),
    "particular": (
        "NO sos veterinario: sos el dueño de una mascota y querés un examen para "
        "tu perrito. Insistís en que te atiendan directamente."
    ),
    "multi_orden": (
        "Querés programar DOS órdenes seguidas. Primero la de Firulais. Cuando esa "
        "quede registrada, pedís OTRA orden para un segundo paciente: 'Michi', felino "
        "siamés, hembra, 2 años, mismo dueño Pedro Gómez, también un hemograma. El "
        "médico y la dirección son los mismos de antes ('el de siempre')."
    ),
    "multi_intencion": (
        "Mezclás varias cosas en un mismo mensaje: una duda + el pedido + varios datos "
        "juntos. Ej: '¿ustedes recogen la muestra? necesito un hemograma para Firulais, "
        "un labrador macho de 3 años, soy de San Roque'. Esperás que te respondan TODO, "
        "no solo una parte."
    ),
    "contradictorio": (
        "Das datos y te corregís a mitad de camino. Ej: decís que el paciente es macho "
        "y al rato 'perdón, es hembra'; o cambiás la edad o el nombre del paciente. "
        "Esperás que el bot tome la última versión sin repreguntar lo que ya diste."
    ),
    "precios": (
        "Sos un veterinario registrado al que le importa el PRECIO. PRIMER mensaje: "
        "elegí la opción 1 (programar) e identificate de una ('soy de Veterinaria San "
        "Roque, NIT 900123456'). Cuando el bot te pida el análisis, ANTES de elegir "
        "preguntás '¿cuánto sale un hemograma?'. Cuando te den el valor, decís 'dale, "
        "un hemograma, y agregale una glucosa, ¿cuánto sería todo junto?'. Querés ver "
        "el valor de cada análisis al lado de su nombre. Después das el resto de datos "
        "(Firulais, canino labrador macho 3 años, Dra. Laura Méndez, dueño Pedro Gómez, "
        "pago contraentrega) y cerrás la orden."
    ),
}

JUEZ_SYSTEM = (
    "Sos un QA senior de un laboratorio veterinario. Te paso la transcripción de "
    "una conversación entre un CLIENTE (humano simulado) y el AGENTE (bot A3). "
    "El agente A3 hace 4 cosas: programar recogida de muestras, consultar "
    "resultados, pagos (escala a contabilidad) y cliente nuevo/no registrado "
    "(escala a recepción). Reglas clave: identificar al cliente antes de "
    "registrar; cliente nuevo y particulares NO se atienden, se escalan; debe "
    "sonar humano y colombiano, NO robótico ni repetitivo.\n\n"
    "DATOS DEL ENTORNO (no los marques como fallas):\n"
    "- 'Veterinaria San Roque' (NIT 900123456) SÍ está registrada: atenderla y "
    "cerrar la orden es lo correcto, NO hay que escalarla.\n"
    "- A3 NO confirma hora/fecha exacta de recogida: eso lo coordina operaciones "
    "después. No es falla que el bot no dé una hora ni 'valide agenda'.\n"
    "- El saludo de bienvenida fijo es parte del diseño; no lo marques como "
    "robótico salvo que se repita o ignore lo que pidió el cliente.\n\n"
    "Evaluá SOLO con base en la transcripción. Respondé JSON válido:\n"
    "{\"veredicto\": \"BIEN\"|\"REGULAR\"|\"MAL\", "
    "\"problemas\": [\"...\"], \"resumen\": \"1 frase\"}\n"
    "Marcá SOLO problemas reales y observables: bucles (frase repetida), preguntas "
    "repetidas, no escalar un cliente nuevo/no registrado o un particular, capturar "
    "mal un dato, inventar datos, o no cerrar/dejar colgada la conversación."
)


def _cliente_simulado(persona_desc, transcript, objetivo_con_datos):
    """Genera el próximo mensaje del cliente humano. Devuelve texto o '[FIN]'."""
    system = (
        f"{persona_desc}\n\nContexto: escribís por chat a un laboratorio "
        f"veterinario en Bogotá para resolver tu objetivo. {objetivo_con_datos}\n\n"
        "Escribí SOLO tu próximo mensaje como cliente (1-2 frases, natural, "
        "colombiano, informal). No expliques que sos una simulación. Si ya "
        "lograste tu objetivo o el bot te despachó/escaló y no hay más que "
        "hacer, respondé exactamente '[FIN]'."
    )
    # Invertimos roles: para el cliente, los mensajes del BOT son 'user'.
    messages = [{"role": "system", "content": system}]
    for who, text in transcript:
        messages.append({"role": "user" if who == "bot" else "assistant", "content": text})
    if not transcript:
        messages.append({"role": "user", "content": "(inicia tú la conversación)"})
    resp = _oai.chat.completions.create(
        model=OPENAI_MODEL, messages=messages, temperature=0.9, max_completion_tokens=120,
    )
    return resp.choices[0].message.content.strip()


def _juez(transcript):
    convo = "\n".join(f"{'CLIENTE' if w == 'user' else 'AGENTE'}: {t}" for w, t in transcript)
    resp = _oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": JUEZ_SYSTEM},
                  {"role": "user", "content": convo}],
        response_format={"type": "json_object"}, temperature=0.2,
    )
    return json.loads(resp.choices[0].message.content)


def _run_persona(name, desc, max_turns):
    from app.agent import process_turn

    chat_id = f"sim-{name}"
    _reset(chat_id)
    objetivo = DATOS_CLIENTE if name in (
        "apurado", "caotico", "evasivo", "desordenado",
        "multi_orden", "multi_intencion", "contradictorio", "precios",
    ) else (
        "Estás registrado y querés programar; usá los datos que tengas a mano."
        if name == "preventa" else "Usá tu situación tal cual; no inventes registro."
    )
    transcript = []  # lista de (who, text): who in {'user'(cliente), 'bot'}
    print("=" * 72)
    print(f"PERSONA: {name} — {desc[:60]}...")
    print("-" * 72)

    for _ in range(max_turns):
        user_msg = _cliente_simulado(desc, transcript, objetivo)
        if user_msg.strip().upper().startswith("[FIN]") or user_msg.strip() == "[FIN]":
            break
        print(f"  CLIENTE: {user_msg}")
        transcript.append(("user", user_msg))
        try:
            reply = process_turn(chat_id, user_msg)
        except Exception as exc:  # noqa: BLE001
            print(f"  AGENTE: [EXCEPCIÓN] {type(exc).__name__}: {exc}")
            transcript.append(("bot", f"[EXCEPCIÓN {type(exc).__name__}: {exc}]"))
            break
        if reply is None:
            print("  AGENTE: (bloqueó la sesión / dejó de atender)")
            break
        print(f"  AGENTE: {reply}")
        transcript.append(("bot", reply))

    verdict = _juez(transcript)
    icon = {"BIEN": "✅", "REGULAR": "⚠️", "MAL": "❌"}.get(verdict.get("veredicto"), "❓")
    print("-" * 72)
    print(f"  {icon} {verdict.get('veredicto')}: {verdict.get('resumen')}")
    for p in verdict.get("problemas", []):
        print(f"      ! {p}")
    return name, verdict


def main():
    max_turns = 14
    raw = sys.argv[1:]
    if "--turns" in raw:
        i = raw.index("--turns")
        max_turns = int(raw[i + 1])
        raw = raw[:i] + raw[i + 2:]
    args = [a for a in raw if not a.startswith("--")]
    selected = {k: v for k, v in PERSONAS.items() if not args or k in args}
    if not selected:
        print(f"Personas disponibles: {', '.join(PERSONAS)}")
        return 1

    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in _PATCHES.items()]
    for p in patchers:
        p.start()
    results = []
    try:
        for name, desc in selected.items():
            results.append(_run_persona(name, desc, max_turns))
    finally:
        for p in patchers:
            p.stop()

    print("=" * 72)
    print("RESUMEN")
    for name, v in results:
        icon = {"BIEN": "✅", "REGULAR": "⚠️", "MAL": "❌"}.get(v.get("veredicto"), "❓")
        print(f"  {icon} {name}: {v.get('veredicto')}")
    bad = [r for r in results if r[1].get("veredicto") == "MAL"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
