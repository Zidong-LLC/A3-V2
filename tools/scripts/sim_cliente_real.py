"""
Simulador adversarial contra DATOS REALES.

Diferencia con `sim_cliente.py`: aquel usa un cliente de juguete ("Veterinaria San Roque")
y todo el catálogo mockeado. Acá las LECTURAS van contra Supabase real — los 992 clientes,
el catálogo de análisis y el de perfiles — y solo se mockea lo que ESCRIBE. Una IA hace de
cliente humano (typos, datos en desorden, se corrige a mitad), así que el agente se prueba
con lenguaje real sobre datos reales, no con respuestas perfectas a un guion.

Nace de una prueba que dio "todo bien" con guion perfecto mientras el carril real perdía un
perfil pedido por código.

NO ESCRIBE NADA: `create_request` y `create_request_event` están mockeados.

Uso:
  python tools/scripts/sim_cliente_real.py                    # todas las personas
  python tools/scripts/sim_cliente_real.py perfil_por_codigo  # solo esa
  python tools/scripts/sim_cliente_real.py --turns 20
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools" / "scripts"))

from replay_chatwoot_qa import _WRITE_PATCHES, _state, _reset  # noqa: E402
from sim_cliente import _cliente_simulado, _juez  # noqa: E402

# Cliente REAL de la base (verificado en solo lectura): NIT, dirección y motorizado propios.
CLIENTE_REAL = (
    "Trabajás en 'Animal Pets', una veterinaria REAL registrada con A3 "
    "(NIT 53115419-1, dirección DG 51A SUR 61B-03). "
    "Médico solicitante: Dra. Laura Méndez. Paciente: Firulais, canino, labrador, "
    "macho, 3 años. Dueño: Pedro Gómez. Pago contraentrega."
)

PERSONAS = {
    # El carril que perdió el perfil: pedir un PERFIL por su código cuando el bot
    # ofrece "¿querés agregar otro análisis o perfil?".
    "perfil_por_codigo": (
        "Sos un veterinario práctico que se sabe los códigos del portafolio de memoria. "
        "Identificate, dá los datos del paciente cuando te los pidan (podés darlos de a "
        "dos o con algún typo). Cuando llegue el momento del análisis pedí primero un "
        "cuadro hemático. Cuando el bot te pregunte si querés agregar algo más, pedí un "
        "perfil por su CÓDIGO, tal cual: 'perfil 903'. Si el bot NO te lo toma, insistí "
        "una vez con '903'. Si SÍ te lo tomó, seguí adelante: pedí pasar al pago "
        "(contraentrega). Cuando veas el resumen final, leelo de verdad: si el 903 está, "
        "confirmá la orden; si no está, decílo y pedí que lo agreguen."
    ),
    "codigos_mezclados": (
        "Escribís rápido, con typos y sin tildes. Pedís varias cosas juntas mezclando "
        "códigos de análisis y de perfiles: 'necesito el 1101 y el perfil 701'. Si el bot "
        "te ofrece un menú, respondés con la categoría en vez del número ('el "
        "prequirurgico'). Al final querés ver todo lo que pediste en el resumen."
    ),
    "caotico_real": (
        "Escribís con typos, sin tildes, mezclás mayúsculas y das los datos en el orden "
        "que se te ocurre, no en el que te preguntan. A veces contestás otra cosa. Te "
        "desviás una vez preguntando cuánto sale, y después seguís. Querés un hemograma."
    ),
    # ERR-088: el escalado por "no estamos registrados" tiene que poder deshacerse.
    "se_creia_no_registrado": (
        "Primero elegís la opción 1 para programar. Cuando el bot te pida identificarte, "
        "decís con dudas que creés que NO están registrados ('uy, creo que no estamos "
        "registrados con ustedes'). Al turno siguiente te acordás y te corregís: 'ah no, "
        "sí estamos, somos Animal Pets'. A partir de ahí seguís normal con la orden: "
        "Dra. Laura Méndez, Firulais, canino labrador macho de 3 años, dueño Pedro Gómez, "
        "un cuadro hemático, pago contraentrega. Si el bot deja de responderte, insistí "
        "un par de veces y después escribí '[FIN]'."
    ),
    "corrige_sobre_la_marcha": (
        "Das datos y te corregís a mitad de camino: decís que el paciente es macho y al "
        "rato 'perdón, es hembra'; cambiás la edad; y cuando ya estás en el resumen final "
        "pedís cambiar un dato. Esperás que el bot tome la última versión sin repreguntar "
        "todo de nuevo."
    ),
}


def _run(name: str, desc: str, max_turns: int) -> dict:
    from app.agent import process_turn

    chat_id = f"simreal-{name}"
    _reset(chat_id)
    transcript = []
    print("=" * 72)
    print(f"PERSONA: {name}")
    print("=" * 72)

    for _ in range(max_turns):
        user_msg = _cliente_simulado(desc, transcript, CLIENTE_REAL)
        if user_msg.strip().upper().startswith("[FIN]"):
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
            print("  AGENTE: (dejó de responder — sesión bloqueada)")
            transcript.append(("bot", "[SIN RESPUESTA]"))
            break
        print(f"  AGENTE: {reply}")
        transcript.append(("bot", reply))

    veredicto = _juez(transcript)
    icono = {"BIEN": "[OK]", "REGULAR": "[!!]", "MAL": "[XX]"}.get(veredicto.get("veredicto"), "[??]")
    print("-" * 72)
    print(f"  {icono} {veredicto.get('veredicto')}: {veredicto.get('resumen')}")
    for p in veredicto.get("problemas", []):
        print(f"      ! {p}")
    if _state["requests"]:
        campos = _state["requests"][-1].get("captured_fields") or {}
        print(f"  ORDEN: exam_type={campos.get('exam_type')!r}")
        perfil = campos.get("profile") or {}
        if perfil:
            print(f"         total_estimated=${perfil.get('total_estimated')}")
            for t in (perfil.get("added_tests") or []):
                print(f"         + {t.get('code')} {t.get('name')} ${t.get('price')}")
    else:
        print("  ORDEN: ninguna creada")
    print()
    return veredicto


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    max_turns = 18
    if "--turns" in sys.argv:
        max_turns = int(sys.argv[sys.argv.index("--turns") + 1])
    elegidas = {k: v for k, v in PERSONAS.items() if not args or k in args}

    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in _WRITE_PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        resultados = {n: _run(n, d, max_turns) for n, d in elegidas.items()}
    finally:
        for p in patchers:
            p.stop()

    print("=" * 72)
    for nombre, v in resultados.items():
        print(f"  {v.get('veredicto', '?'):<8} {nombre}")
    return 0 if all(v.get("veredicto") == "BIEN" for v in resultados.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
