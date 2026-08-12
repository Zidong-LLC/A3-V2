"""
La especie del catálogo es una ETIQUETA, no un veto (decisión 012).

Caso real, conversación del 28/07 con EVI Emergencias Veterinarias: paciente **felino**, el
cliente pidió el "Perfil 653" y el bot respondió *"No encuentro el Perfil 653 en el
catálogo"*. El 653 existe — Perfil Senior Canino III, $58.000, `species='canino'` — y lo
escondía el filtro por especie. Decirle a un cliente que no existe algo que sí existe es
peor que ofrecerle un perfil de otra especie: A3 confirmó que en su operación se piden
perfiles de una especie para otra sin problema.

La distinción que fija este archivo no es "filtrar o no filtrar", sino CÓMO llegó el pedido:

  - El cliente PIDE uno concreto (código, nombre, categoría) → se le da, sin filtrar.
  - El bot RECOMIENDA porque el cliente no sabe qué pedir → sí filtra, no tiene sentido
    sugerirle perfiles caninos a un gato.
"""
from unittest.mock import MagicMock

import pytest

from app.services import db


PERFILES = [
    {"code": "653", "name": "Perfil Senior Canino III", "category": "senior",
     "species": "canino", "price": 58000, "description": ""},
    {"code": "301", "name": "Perfil Felino I", "category": "felino",
     "species": "felino", "price": 30000, "description": ""},
    {"code": "152", "name": "Perfil Prequirúrgico I", "category": "prequirurgico",
     "species": "ambos", "price": 24000, "description": ""},
    {"code": "170", "name": "Perfil Prequirúrgico Canino", "category": "prequirurgico",
     "species": "canino", "price": 40000, "description": ""},
]


class _Query:
    """Mock de infraestructura: registra si alguien filtró por especie."""

    def __init__(self, registro, filas):
        self.registro, self.filas = registro, filas

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def in_(self, campo, valores):
        if campo == "species":
            self.registro.append(("filtro_especie", valores))
        if campo == "code":
            self.filas = [f for f in self.filas if f["code"] in valores]
        return self

    def execute(self):
        return MagicMock(data=list(self.filas))


@pytest.fixture
def catalogo(monkeypatch):
    registro = []
    monkeypatch.setattr(db._client, "table", lambda _n: _Query(registro, PERFILES))
    return registro


def _filtro_aplicado(registro):
    return any(evento == "filtro_especie" for evento, _ in registro)


def test_el_perfil_por_codigo_se_entrega_aunque_sea_de_otra_especie(catalogo):
    """EL caso de EVI: 653 (canino) pedido para un felino."""
    resultado = db.get_catalog_profiles_by_codes(["653"], "Felino")
    assert [p["code"] for p in resultado] == ["653"]
    assert not _filtro_aplicado(catalogo), "un código explícito no debe filtrarse por especie"


def test_el_perfil_por_nombre_tampoco_se_filtra(catalogo):
    perfil = db.find_catalog_profile("Perfil Senior Canino III", "Felino")
    assert perfil and perfil["code"] == "653"
    assert not _filtro_aplicado(catalogo)


def test_la_categoria_no_esconde_los_de_otra_especie(catalogo):
    """'prequirúrgico' para un felino trae los suyos Y el canino, sin ocultar nada."""
    resultado = db.list_catalog_profiles_matching_category("un prequirurgico", "Felino")
    assert {p["code"] for p in resultado} == {"152", "170"}


def test_la_categoria_pone_primero_los_del_paciente(catalogo):
    """No esconde, pero ordena: lo aplicable al paciente arriba."""
    resultado = db.list_catalog_profiles_matching_category("un prequirurgico", "Felino")
    assert resultado[0]["code"] == "152", "el 'ambos' debe ir antes que el canino"


def test_la_recomendacion_si_filtra(catalogo):
    """Cuando el bot SUGIERE, la especie sí manda: no se le ofrecen perfiles caninos a un gato."""
    db.list_catalog_profiles_for_species("Felino", limit=6)
    assert _filtro_aplicado(catalogo), "la recomendación por especie debe seguir filtrando"
