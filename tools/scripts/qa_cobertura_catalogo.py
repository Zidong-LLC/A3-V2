"""
QA de COBERTURA DEL CATÁLOGO: el agente nunca puede negar algo que está en la base.

Regla de negocio (usuario, 2026-08-12): *"si te piden algo que está en esa base de datos, ya
sea por número, por nombre o lo que sea, que lo ofrezca — que no diga que no existe"*.

Nace de un caso real (EVI, 28/07): paciente felino, el cliente pidió el "Perfil 653" y el bot
respondió "No encuentro el Perfil 653 en el catálogo". El 653 existe: Perfil Senior Canino
III, $58.000. Lo escondía el filtro por especie.

Probar de a un caso no sirve — hay 159 análisis y 133 perfiles, y 125 de ellos están
etiquetados para una especie concreta. Este QA toma una MUESTRA REAL de la base, con sesgo
deliberado hacia los etiquetados (que son los que se escondían), y para cada ítem lo pide al
agente por CÓDIGO y por NOMBRE, verificando que la respuesta no niegue su existencia.

Corre contra el modelo real con lecturas reales; solo se mockean las escrituras. NO escribe
nada: ni órdenes, ni pedidos, ni facturas.

Uso:
  python tools/scripts/qa_cobertura_catalogo.py                # muestra por defecto
  python tools/scripts/qa_cobertura_catalogo.py --n 6          # 6 de cada tipo
  python tools/scripts/qa_cobertura_catalogo.py --especie Canino
"""
import random
import re
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools" / "scripts"))

from replay_chatwoot_qa import _WRITE_PATCHES, _state, _reset  # noqa: E402

# El bot niega de mil formas: "no encuentro", "no ubico", "no alcanzo a identificar", "no
# tengo el X en el catálogo". Una lista de frases exactas NO alcanza — la primera versión de
# este QA daba 16/16 mientras el bot decía "No ubico ese código", que la lista no cubría.
# Se busca el PATRÓN: un "no" seguido, cerca, de un verbo de tener/hallar/identificar.
_VERBOS_NEGADOS = (
    r"encuentr\w*|ubic\w*|teng\w*|tenemos|existe\w*|aparec\w*|figur\w*|"
    r"identific\w*|alcanzo|manejo|manejamos|dispong\w*|disponemos|hallo|veo|"
    r"reconozc\w*|localiz\w*"
)
_NEGACION_RE = re.compile(rf"\bno\b[^.!?]{{0,40}}?\b(?:{_VERBOS_NEGADOS})\b", re.IGNORECASE)

CAMPOS_BASE = {
    "_client_found": True, "clinic_name": "Animal Pets", "tax_id": "53115419-1",
    "pickup_address": "DG 51A SUR 61B-03", "requesting_doctor": "Dra. Laura Méndez",
    "patient_name": "Marla", "breed": "Mestizo", "sex": "Hembra",
    "patient_age": "6 años", "owner_name": "Marcela Hozorio",
    "observations": "sin observaciones",
}

PREGUNTA_ANALISIS = "Por último, ¿qué análisis o perfil desean?"


def _niega(reply: str) -> str | None:
    m = _NEGACION_RE.search(reply or "")
    return m.group(0).strip() if m else None


def _turno(frase: str, especie: str, i: int) -> str:
    from app.agent import process_turn

    chat = f"qacat-{i}"
    _reset(chat)
    _state["session"].update(
        client_id="qa-cli", phase_current="fase_2_recogida_datos",
        intent_current="route_scheduling",
        captured_fields=dict(CAMPOS_BASE, species=especie),
    )
    _state["history"] = [{"role": "bot", "content": PREGUNTA_ANALISIS}]
    try:
        return process_turn(chat, frase) or ""
    except Exception as exc:  # noqa: BLE001
        return f"[EXCEPCIÓN {type(exc).__name__}: {exc}]"


def _muestra(filas: list[dict], n: int, especie: str) -> list[dict]:
    """Sesga la muestra hacia los etiquetados para OTRA especie: son los que se escondían."""
    otra = [f for f in filas
            if str(f.get("species") or "").lower() not in ("ambos", "", "none")
            and str(f.get("species") or "").lower() != especie.lower()]
    generales = [f for f in filas if str(f.get("species") or "ambos").lower() in ("ambos", "")]
    random.shuffle(otra)
    random.shuffle(generales)
    return otra[:max(n - 1, 1)] + generales[:1]


def main() -> int:
    n = 4
    especie = "Felino"
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    if "--especie" in sys.argv:
        especie = sys.argv[sys.argv.index("--especie") + 1]

    patchers = [patch(f"app.services.db.{k}", **v) for k, v in _WRITE_PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        from app.services import db

        perfiles = db._client.table("catalog_profiles").select(
            "code,name,species").eq("is_active", True).limit(5000).execute().data or []
        analisis = db._client.table("catalog_tests").select(
            "code,name,species").eq("is_active", True).limit(5000).execute().data or []

        print("=" * 78)
        print(f"COBERTURA DEL CATÁLOGO — paciente {especie}")
        print(f"base: {len(perfiles)} perfiles, {len(analisis)} análisis")
        print("=" * 78)

        fallos, total, i = [], 0, 0
        for tipo, filas, plantillas in (
            ("PERFIL", _muestra(perfiles, n, especie),
             ("perfil {code}", "quiero el {name}")),
            ("ANÁLISIS", _muestra(analisis, n, especie),
             ("el {code}", "tenes {name}?")),
        ):
            print(f"\n--- {tipo} ---")
            for fila in filas:
                for plantilla in plantillas:
                    frase = plantilla.format(code=fila["code"], name=fila["name"])
                    i += 1
                    total += 1
                    reply = _turno(frase, especie, i)
                    negacion = _niega(reply)
                    marca = "XX" if negacion else "OK"
                    etiq = fila.get("species") or "ambos"
                    print(f"  [{marca}] ({etiq:<7}) {frase[:46]:<48} {reply[:60].strip()}")
                    if negacion:
                        fallos.append((frase, fila, negacion, reply))
    finally:
        for p in patchers:
            p.stop()

    print("\n" + "=" * 78)
    print(f"  {total - len(fallos)}/{total} sin negar")
    if fallos:
        print("\n  NEGÓ algo que SÍ está en la base:")
        for frase, fila, negacion, reply in fallos:
            print(f"   · {frase!r} → {fila['code']} {fila['name']} ({fila.get('species')})")
            print(f"     dijo {negacion!r}: {reply[:110].strip()}")
    return 0 if not fallos else 1


if __name__ == "__main__":
    raise SystemExit(main())
