"""
Regresión ERR-078 (prueba en vivo del usuario, 2026-07-21, chat 10): el cliente confirmó
"Equino" y más tarde dio el propietario "Jorge Toro". El apellido Toro está mapeado en
species.py como ("Bovino", "Macho"), y la orden pasó a species='Bovino': el menú de
perfiles llegó a decir "Para bovino te puedo recomendar" para un Cuarto de Milla.

Causa: `apply_implied_animal_fields` pisaba la especie SIEMPRE que la actual estuviera en
RECOVERABLE_SPECIES. La intención era NORMALIZAR ("perro" → "Canino"), pero la condición
también permitía REEMPLAZAR una especie por otra distinta.

Es primo de ERR-075 ("Toro" como nombre de paciente): el mismo apellido, otra ruta.
"""
from app.species import apply_implied_animal_fields


def test_apellido_toro_no_convierte_un_equino_en_bovino():
    """El caso exacto del chat 10: especie confirmada + propietario 'Jorge Toro'."""
    fields = {"species": "Equino", "breed": "Cuarto de Milla"}
    apply_implied_animal_fields(fields, "Jorge Toro")
    assert fields["species"] == "Equino"


def test_apellido_toro_tampoco_pisa_el_sexo_ya_dado():
    fields = {"species": "Equino", "sex": "Hembra"}
    apply_implied_animal_fields(fields, "Jorge Toro")
    assert fields["sex"] == "Hembra"


def test_sigue_normalizando_la_misma_especie():
    """No se rompe lo que la función existe para hacer: 'perro' → 'Canino'."""
    fields = {"species": "perro"}
    apply_implied_animal_fields(fields, "es un canino")
    assert fields["species"] == "Canino"


def test_sigue_llenando_la_especie_vacia():
    fields = {}
    apply_implied_animal_fields(fields, "es un toro de 3 años")
    assert fields["species"] == "Bovino"
    assert fields["sex"] == "Macho"


def test_correccion_explicita_sigue_funcionando():
    """Tras limpiar el campo (lo que hace el detector de corrección), sí se aplica."""
    fields = {"species": None}
    apply_implied_animal_fields(fields, "en realidad es un toro")
    assert fields["species"] == "Bovino"
