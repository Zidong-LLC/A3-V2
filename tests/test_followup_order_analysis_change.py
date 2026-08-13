"""
El perfil de la orden anterior no puede contaminar la orden siguiente.

Prueba real por Telegram (chat 4, 2026-08-12). El cliente cerró una orden con el perfil 653,
pidió otra y quiso cambiar el análisis:

    CLIENTE: Todo igual menos el tipo de análisis
    BOT:     Tenemos varias áreas de análisis. Algunas opciones del catálogo son: 1. 1101…
    CLIENTE: Un pre quirúrgico
    BOT:     Perfecto, anoto PREQUIRURGICO como análisis. ¿Cuál es el nombre del paciente?

Debía ofrecer los 11 perfiles prequirúrgicos. Y lo que no se veía en el chat era peor: la
orden quedaba con `exam_type = "Perfil Senior Canino III"` — el perfil de $58.000 del
paciente ANTERIOR. Error de dinero, familia ERR-077/103/105.

Dos causas encadenadas, una por archivo:

1. `"Todo igual menos el TIPO de ANÁLISIS"` se clasificaba como ajuste PARCIAL (tiene "igual"
   y "menos"), así que el bloque que limpia el análisis reofrecido nunca corría. Y antes
   incluso, `_is_catalog_overview_question` lo leía como "¿qué tipos de análisis hacen?".
2. Con el perfil heredado vivo, los cuatro enforcers que debían ofrecer el menú de
   prequirúrgicos ceden por sus guards de entrada.

Este archivo fija la distinción de la causa 1, que es la que destraba todo lo demás.
"""
import pytest

from app.detectors.analisis import (
    _wants_partial_analysis_change as quiere_ajuste_parcial,
    _wants_to_change_analysis as quiere_otro_analisis,
)


# Lo que EXCLUYE es el campo entero → cambio total, hay que limpiar el análisis heredado.
CAMBIO_TOTAL = [
    "Todo igual menos el tipo de análisis",
    "todo igual menos el análisis",
    "lo mismo pero cambiá el perfil",
    "otro análisis",
]

# Lo que excluye es UNA prueba concreta → ajuste parcial, el perfil base se conserva.
AJUSTE_PARCIAL = [
    "el mismo pero sin coproscópico",
    "igual pero sin el 1101",
    "el mismo menos la glucosa",
    "igual más glucosa",
]


@pytest.mark.parametrize("frase", CAMBIO_TOTAL)
def test_excluir_el_campo_entero_es_cambio_total(frase):
    assert quiere_otro_analisis(frase) is True, f"{frase!r} debería limpiar el análisis"
    assert quiere_ajuste_parcial(frase) is False


@pytest.mark.parametrize("frase", AJUSTE_PARCIAL)
def test_excluir_una_prueba_sigue_siendo_ajuste_parcial(frase):
    """No-regresión: el perfil base se conserva y se personaliza, no se tira."""
    assert quiere_ajuste_parcial(frase) is True, f"{frase!r} debería conservar el perfil"
    assert quiere_otro_analisis(frase) is False


def test_todo_igual_a_secas_no_toca_el_analisis():
    """Aceptar el reofrecimiento completo no es ni cambio ni ajuste."""
    assert quiere_otro_analisis("todo igual") is False
    assert quiere_ajuste_parcial("todo igual") is False


def test_el_reofrecimiento_gana_sobre_la_pregunta_de_catalogo():
    """`"el TIPO de ANÁLISIS"` tiene las palabras de una consulta de catálogo, pero cuando
    hay un reofrecimiento pendiente es una respuesta a ESE reofrecimiento."""
    from app.agent import _is_catalog_overview_question

    # El detector sigue viendo la pregunta de catálogo (no se tocó)...
    assert _is_catalog_overview_question("Todo igual menos el tipo de análisis") is True
    # ...y por eso el guard vive en process_turn, condicionado a _stable_confirm_pending.
    # Este test documenta esa división: si alguien "arregla" el detector, que sepa por qué
    # quedó así.
