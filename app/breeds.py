"""Catálogo de RAZAS (323 razas / 14 especies) — fuente única raza → especie.

Hace dos cosas y ninguna más: normaliza la grafía de la raza que dijo el cliente
("pastor aleman" → "Pastor Alemán") e infiere la especie cuando la raza es inequívoca
("Holstein" → Bovino), para que el agente no tenga que preguntarla. Es el espejo de
`app/species.py`, que hace lo mismo con especie/sexo: normalización determinística, sin
depender del criterio del LLM.

NUNCA bloquea el flujo. Una raza desconocida ("mestizo de la calle", "no sé") o ambigua
entre especies ("Criollo") devuelve NONE/AMBIGUOUS y todo sigue exactamente como antes.
Si la tabla no existe o la red falla, el catálogo queda vacío y el comportamiento es
idéntico al que había sin este módulo.

Las razas NO se inyectan al prompt: son ~4k tokens por turno y el modelo ya captura la
raza bien. Si algún día el QA real muestra que no reconoce razas raras, la salida es una
función `breeds_context_for_species(species, limit=10)` gateada a cuando el bot está
preguntando la raza — 10 razas de una especie, no 323.
"""
import difflib
import logging
from dataclasses import dataclass
from functools import lru_cache

from app.species import RECOVERABLE_SPECIES
from app.text import catalog_item_key, tokenize

logger = logging.getLogger(__name__)

EXACT = "exact"          # raza reconocida y de especie inequívoca
AMBIGUOUS = "ambiguous"  # raza reconocida, especie NO inferible
NONE = "none"            # sin señal: el flujo sigue igual que hoy

# Más estricto que el fuzzy de clientes (db.py: 0.85 desde 4 letras) porque acá un match
# errado además se saltaría la pregunta de especie. El mínimo de 6 letras es el que separa
# 'boer' (Caprino) de 'boxer' (Canino), que tienen ratio 0.889 y cruzarían especies.
_MIN_RATIO = 0.87
_MIN_LENGTH = 6
_MARGIN = 0.05
_MAX_TOKENS = 4


@dataclass(frozen=True)
class BreedMatch:
    status: str
    breed: str | None = None    # grafía canónica del catálogo
    species: str | None = None  # solo cuando status == EXACT


_NO_MATCH = BreedMatch(NONE)


def _fetch_rows() -> list[dict]:
    from app.services import db
    return db.list_catalog_breeds()


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, str], dict[str, frozenset[str]], frozenset[str]]:
    """Lee el catálogo UNA vez por proceso. Devuelve (canónicos, especies, palabras-especie).

    La ambigüedad se DERIVA: una raza con más de una especie no infiere. Igual que
    `species.py` deriva `RECOVERABLE_SPECIES` de `ANIMAL_DOMAIN`, acá nada se marca a mano.
    """
    try:
        rows = _fetch_rows()
    except Exception:  # la raza es un dato descriptivo: no vale tumbar el turno por él
        logger.exception("No se pudo cargar catalog_breeds; el agente sigue sin catálogo de razas")
        return {}, {}, frozenset()

    canonical: dict[str, str] = {}
    species: dict[str, set[str]] = {}
    for row in rows:
        key = row.get("breed_key") or catalog_item_key(row.get("name"))
        if not key or not row.get("name"):
            continue
        canonical.setdefault(key, row["name"])
        if row.get("species"):
            species.setdefault(key, set()).add(row["species"])
    # Razas que son en realidad palabras de especie (Conejo, Ave, Gallina...): la palabra le
    # pertenece a species.py, que ya la resuelve aguas arriba. Acá solo se corrige la grafía.
    species_words = frozenset(canonical) & frozenset(RECOVERABLE_SPECIES)
    return canonical, {k: frozenset(v) for k, v in species.items()}, species_words


def _fuzzy_key(key: str, canonical: dict[str, str]) -> str | None:
    """Mejor candidato por similitud, o None si hay empate o no alcanza el umbral."""
    if len(key) < _MIN_LENGTH:
        return None
    scored = sorted(
        ((difflib.SequenceMatcher(None, key, candidate).ratio(), candidate)
         for candidate in canonical if len(candidate) >= _MIN_LENGTH),
        reverse=True,
    )
    if not scored or scored[0][0] < _MIN_RATIO:
        return None
    best_ratio, best_key = scored[0]
    if len(scored) > 1 and best_ratio - scored[1][0] < _MARGIN:
        return None
    return best_key


def resolve_breed(text: str | None) -> BreedMatch:
    """Resuelve la raza que dijo el cliente. Nunca lanza; ante la duda devuelve NONE."""
    key = catalog_item_key(text)
    if not key:
        return _NO_MATCH
    canonical, species_by_key, species_words = _load()
    if not canonical:
        return _NO_MATCH

    if key not in canonical:
        if len(tokenize(str(text))) > _MAX_TOKENS:  # la raza es una frase corta, no una oración
            return _NO_MATCH
        fuzzy = _fuzzy_key(key, canonical)
        if not fuzzy:
            return _NO_MATCH
        key = fuzzy

    name = canonical[key]
    if key in species_words:
        return BreedMatch(AMBIGUOUS, name)
    candidates = species_by_key.get(key) or frozenset()
    if len(candidates) != 1:
        return BreedMatch(AMBIGUOUS, name)
    return BreedMatch(EXACT, name, next(iter(candidates)))
