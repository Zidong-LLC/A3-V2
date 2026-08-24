"""
ERR-142 — Los fraseos de cierre del test en vivo (2026-08-21) no cerraban la oferta.

Chat real (EVI Emergencias, 15:21–15:24): ante "¿Agregamos otro análisis a esta orden,
o la dejamos así?" el cliente respondió CUATRO veces con fraseos naturales y el bot
repitió la misma pregunta en bucle:

    CLIENTE: Déjalo así está bien eso es todo   → detectada, pero 7 tokens > tope de 6
    CLIENTE: Avanzamos                          → "avanzamos" no estaba en los tokens
    CLIENTE: La dejamos así                     → la conjugación DEL PROPIO BOT no estaba
    CLIENTE: Dejamos estar orden así            → par dejar+así con palabras en el medio

Lo más grave: "la dejamos así" es la frase que el bot usa en su pregunta.
"""
import pytest

from app.detectors.analisis import (
    _proceed_phrase_in_text,
    _wants_to_proceed_to_payment,
)


FRASES_REALES_DEL_CHAT = [
    "Déjalo así está bien eso es todo",
    "Avanzamos",
    "La dejamos así",
    "Dejamos estar orden así",   # typo real del cliente ("estar" por "esta")
    "Dejamos esta orden así",
]


@pytest.mark.parametrize("frase", FRASES_REALES_DEL_CHAT)
def test_fraseos_reales_cierran_la_oferta(frase):
    assert _wants_to_proceed_to_payment(frase) is True, (
        f"{frase!r} respondía a la propia oferta del bot y debe cerrar el agregado")


def test_frase_explicita_exime_del_tope_de_longitud():
    """'Déjalo así está bien eso es todo' son 7 palabras: el tope de 6 del carril la
    descartaba. Una FRASE explícita es inequívoca sin importar el largo."""
    assert _proceed_phrase_in_text("Déjalo así está bien eso es todo") is True


def test_frase_sin_cierre_no_dispara_la_exencion():
    """La exención es solo para frases de cierre: una orden de agregar no la activa."""
    assert _proceed_phrase_in_text("agregale una glucosa y un sodio a la orden") is False


@pytest.mark.parametrize("frase", [
    "agregale otro análisis",
    "quiero sumar una glucosa",
])
def test_pedidos_de_agregar_no_cierran(frase):
    """No-regresión: pedir MÁS análisis nunca puede leerse como cerrar la oferta."""
    assert _wants_to_proceed_to_payment(frase) is False
