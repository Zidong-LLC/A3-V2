"""Modelo de dominio de ANIMALES: A3 atiende todas las especies, no solo perros/gatos.
La normalización especie/sexo es determinística (no depende del criterio del LLM), así
"toro"/"vaca"/"cerdo"/"conejo" se interpretan igual de bien que "perro"/"gato".
"""
import pytest

from app import agent


@pytest.mark.parametrize("word,species,sex", [
    ("toro", "Bovino", "Macho"),
    ("vaca", "Bovino", "Hembra"),
    ("novillo", "Bovino", "Macho"),
    ("ternera", "Bovino", "Hembra"),
    ("res", "Bovino", None),
    ("cerdo", "Porcino", None),
    ("marrana", "Porcino", "Hembra"),
    ("yegua", "Equino", "Hembra"),
    ("caballo", "Equino", None),
    ("oveja", "Ovino", "Hembra"),
    ("carnero", "Ovino", "Macho"),
    ("cabra", "Caprino", "Hembra"),
    ("conejo", "Conejo", None),
    ("gallina", "Ave", "Hembra"),
    ("gallo", "Ave", "Macho"),
    ("perra", "Canino", "Hembra"),
    ("michi", "Felino", None),
])
def test_species_and_implied_sex_are_normalized(word, species, sex):
    fields = {}
    agent._apply_implied_animal_fields(fields, f"es un {word} de 3 años")
    assert fields.get("species") == species
    assert fields.get("sex") == sex


def test_generic_words_do_not_assume_sex():
    """Palabras genéricas (perro, gato, cerdo, caballo) NO asumen sexo."""
    for word in ("perro", "gato", "cerdo", "caballo", "conejo", "cordero"):
        fields = {}
        agent._apply_implied_animal_fields(fields, f"un {word}")
        assert fields.get("sex") is None, f"{word} no debería asumir sexo"


def test_species_domain_is_single_source_of_truth():
    """_RECOVERABLE_SPECIES se deriva del modelo único (sin duplicar datos)."""
    assert agent._RECOVERABLE_SPECIES["toro"] == "Bovino"
    assert agent._RECOVERABLE_SPECIES["conejo"] == "Conejo"
    assert agent._IMPLIED_ANIMAL_FIELDS is agent._ANIMAL_DOMAIN
    # toda especie recuperable tiene su entrada en el dominio
    assert set(agent._RECOVERABLE_SPECIES) == set(agent._ANIMAL_DOMAIN)
