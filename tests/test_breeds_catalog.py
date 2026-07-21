"""Catálogo de RAZAS: normalizar la grafía e inferir la especie sin depender del LLM.

La regla que más importa acá es la negativa: una raza ambigua entre especies (Criollo,
Mestizo) o desconocida NUNCA debe inferir especie ni vaciar el campo. Un match de más
sería peor que no tener catálogo, porque saltaría una pregunta con el dato equivocado.
"""
import pytest

from app import breeds

# Espejo del catálogo real (Supabase), con los casos límite que importan: las 8 razas
# ambiguas, las que colisionan con palabras de especie y el par boer/boxer.
CATALOG_ROWS = [
    {"breed_key": "pastor_aleman", "name": "Pastor Alemán", "species": "Canino"},
    {"breed_key": "labrador_retriever", "name": "Labrador Retriever", "species": "Canino"},
    {"breed_key": "golden_retriever", "name": "Golden Retriever", "species": "Canino"},
    {"breed_key": "schnauzer", "name": "Schnauzer", "species": "Canino"},
    {"breed_key": "doberman", "name": "Doberman", "species": "Canino"},
    {"breed_key": "yorkshire_terrier", "name": "Yorkshire Terrier", "species": "Canino"},
    {"breed_key": "chihuahua", "name": "Chihuahua", "species": "Canino"},
    {"breed_key": "boxer", "name": "Boxer", "species": "Canino"},
    {"breed_key": "mcnab", "name": "McNab", "species": "Canino"},
    {"breed_key": "siames", "name": "Siamés", "species": "Felino"},
    {"breed_key": "boer", "name": "Boer", "species": "Caprino"},
    {"breed_key": "brahman", "name": "Brahman", "species": "Bovino"},
    {"breed_key": "holstein", "name": "Holstein", "species": "Bovino"},
    {"breed_key": "duroc", "name": "Duroc", "species": "Porcino"},
    {"breed_key": "dorper", "name": "Dorper", "species": "Ovino"},
    {"breed_key": "andaluz", "name": "Andaluz", "species": "Equino"},
    {"breed_key": "holland_lop", "name": "Holland Lop", "species": "Conejo"},
    {"breed_key": "sirio", "name": "Sirio", "species": "Roedor"},
    {"breed_key": "peruano", "name": "Peruano", "species": "Roedor"},
    {"breed_key": "isa_brown", "name": "Isa Brown", "species": "Ave"},
    {"breed_key": "gecko_leopardo", "name": "Gecko Leopardo", "species": "Reptil"},
    {"breed_key": "huron_domestico", "name": "Hurón Doméstico", "species": "Hurón"},
    {"breed_key": "erizo_africano", "name": "Erizo Africano", "species": "Erizo"},
    {"breed_key": "sugar_glider", "name": "Sugar Glider", "species": "Sugar Glider"},
    # Ambiguas: la misma raza en más de una especie
    {"breed_key": "mestizo", "name": "Mestizo", "species": "Canino"},
    {"breed_key": "mestizo", "name": "Mestizo", "species": "Felino"},
    {"breed_key": "criollo", "name": "Criollo", "species": "Bovino"},
    {"breed_key": "criollo", "name": "Criollo", "species": "Equino"},
    {"breed_key": "criollo", "name": "Criollo", "species": "Felino"},
    {"breed_key": "angora", "name": "Angora", "species": "Felino"},
    {"breed_key": "angora", "name": "Angora", "species": "Conejo"},
    {"breed_key": "hampshire", "name": "Hampshire", "species": "Ovino"},
    {"breed_key": "hampshire", "name": "Hampshire", "species": "Porcino"},
    # Colisiones con palabras de especie de species.py
    {"breed_key": "conejo", "name": "Conejo", "species": "Conejo"},
    {"breed_key": "gallina", "name": "Gallina", "species": "Ave"},
    {"breed_key": "cebu", "name": "Cebú", "species": "Bovino"},
]


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    monkeypatch.setattr(breeds, "_fetch_rows", lambda: list(CATALOG_ROWS))
    breeds._load.cache_clear()
    yield
    breeds._load.cache_clear()


@pytest.mark.parametrize("text,name,species", [
    ("Pastor Alemán", "Pastor Alemán", "Canino"),
    ("pastor aleman", "Pastor Alemán", "Canino"),   # sin tildes
    ("PASTOR ALEMAN", "Pastor Alemán", "Canino"),   # mayúsculas
    ("  pastor  aleman ", "Pastor Alemán", "Canino"),
    ("mcnab", "McNab", "Canino"),                   # capitalize() lo rompería a "Mcnab"
    ("siames", "Siamés", "Felino"),
    ("brahman", "Brahman", "Bovino"),
    ("duroc", "Duroc", "Porcino"),
    ("dorper", "Dorper", "Ovino"),
    ("boer", "Boer", "Caprino"),
    ("andaluz", "Andaluz", "Equino"),
    ("holland lop", "Holland Lop", "Conejo"),
    ("sirio", "Sirio", "Roedor"),
    ("isa brown", "Isa Brown", "Ave"),
    ("gecko leopardo", "Gecko Leopardo", "Reptil"),
    ("huron domestico", "Hurón Doméstico", "Hurón"),
    ("erizo africano", "Erizo Africano", "Erizo"),
])
def test_exact_breed_normalizes_and_infers_species(text, name, species):
    match = breeds.resolve_breed(text)
    assert match.status == breeds.EXACT
    assert match.breed == name
    assert match.species == species


@pytest.mark.parametrize("text,name", [
    ("mestizo", "Mestizo"),
    ("Criollo", "Criollo"),
    ("angora", "Angora"),
    ("hampshire", "Hampshire"),
])
def test_ambiguous_breed_never_infers_species(text, name):
    """Contrato duro: raza en varias especies corrige la grafía pero NO adivina la especie."""
    match = breeds.resolve_breed(text)
    assert match.status == breeds.AMBIGUOUS
    assert match.breed == name
    assert match.species is None


@pytest.mark.parametrize("text,name", [("conejo", "Conejo"), ("gallina", "Gallina"), ("cebu", "Cebú")])
def test_species_words_delegate_to_species_module(text, name):
    """Conejo/Gallina/Cebú son palabras de especie: las resuelve species.py, no este módulo."""
    match = breeds.resolve_breed(text)
    assert match.status == breeds.AMBIGUOUS
    assert match.breed == name
    assert match.species is None


@pytest.mark.parametrize("text", [
    None, "", "   ", "no sé", "no se", "criollo raro", "mestizo de la calle",
    "xyzqw", "aaa", "123", "🐶", "no tengo ni idea de la raza del paciente la verdad",
])
def test_unknown_breed_returns_none(text):
    """Raza desconocida no bloquea nada: el valor del modelo queda intacto."""
    match = breeds.resolve_breed(text)
    assert match.status == breeds.NONE
    assert match.breed is None
    assert match.species is None


@pytest.mark.parametrize("typo,name,species", [
    ("pastor alman", "Pastor Alemán", "Canino"),
    ("labradr retriever", "Labrador Retriever", "Canino"),
    ("golden retrver", "Golden Retriever", "Canino"),
    ("yorkshire terier", "Yorkshire Terrier", "Canino"),
    ("schnauser", "Schnauzer", "Canino"),
    ("doverman", "Doberman", "Canino"),
])
def test_fuzzy_recovers_real_typos(typo, name, species):
    match = breeds.resolve_breed(typo)
    assert match.status == breeds.EXACT
    assert match.breed == name
    assert match.species == species


@pytest.mark.parametrize("text,name,species", [("boer", "Boer", "Caprino"), ("boxer", "Boxer", "Canino")])
def test_boer_and_boxer_do_not_cross_species(text, name, species):
    """boer/boxer tienen ratio 0.889: con el umbral de db.py un typo cruzaría especies."""
    match = breeds.resolve_breed(text)
    assert match.status == breeds.EXACT
    assert match.breed == name
    assert match.species == species


@pytest.mark.parametrize("typo", ["bxer", "boxr", "bower", "boerr", "boxerr", "boex"])
def test_short_typos_near_boer_and_boxer_never_infer(typo):
    """Nada de 5 letras o menos entra al fuzzy: es donde boer/boxer se confunden.
    Preferimos preguntar la especie antes que inferir Caprino en vez de Canino."""
    assert breeds.resolve_breed(typo).status == breeds.NONE


def test_chiwawa_is_a_documented_miss():
    """'chiwawa' está a ratio 0.625 de 'chihuahua': queda fuera por diseño, no es un bug.
    Si el QA real lo pide, la salida es una tabla de alias, no bajar el umbral."""
    assert breeds.resolve_breed("chiwawa").status == breeds.NONE


def test_empty_catalog_degrades_to_current_behaviour(monkeypatch):
    """Sin tabla o sin red, el agente se comporta exactamente como antes de este módulo."""
    monkeypatch.setattr(breeds, "_fetch_rows", lambda: [])
    breeds._load.cache_clear()
    assert breeds.resolve_breed("pastor aleman") == breeds.BreedMatch(breeds.NONE)


def test_db_failure_never_breaks_the_turn(monkeypatch):
    def boom():
        raise RuntimeError("supabase caído")

    monkeypatch.setattr(breeds, "_fetch_rows", boom)
    breeds._load.cache_clear()
    assert breeds.resolve_breed("pastor aleman").status == breeds.NONE


def test_catalog_is_read_once_per_process(monkeypatch):
    calls = []

    def counting():
        calls.append(1)
        return list(CATALOG_ROWS)

    monkeypatch.setattr(breeds, "_fetch_rows", counting)
    breeds._load.cache_clear()
    for _ in range(5):
        breeds.resolve_breed("pastor aleman")
    assert len(calls) == 1


def test_ambiguity_is_derived_not_hardcoded():
    """Nada se marca a mano: la ambigüedad sale de contar especies por raza."""
    _canonical, species_by_key, species_words = breeds._load()
    assert species_by_key["criollo"] == frozenset({"Bovino", "Equino", "Felino"})
    assert species_by_key["pastor_aleman"] == frozenset({"Canino"})
    assert species_words == frozenset({"conejo", "gallina", "cebu"})


def test_never_raises_and_never_returns_empty_breed():
    for row in CATALOG_ROWS:
        match = breeds.resolve_breed(row["name"])
        assert match.breed, f"{row['name']} no debería perder la grafía"
    for junk in (None, "", "?!", "🐶🐱", "a" * 300, 42):
        assert breeds.resolve_breed(junk).status in (breeds.NONE, breeds.EXACT, breeds.AMBIGUOUS)
