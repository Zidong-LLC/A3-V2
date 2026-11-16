"""La opción 1 del menú escrita con un error de tipeo (prueba del 29/10).

El cliente contestó «Programar rita» (por «ruta») al menú de bienvenida. Para las opciones
1 y 3 no hay regla: las clasifica el modelo, y esa vez devolvió `unknown` y derivó a un
asesor a alguien que solo quería programar una recogida.

Esto NO reemplaza al modelo: es la red para el turno en que el modelo no entendió. Mira
si el mensaje, corto, trae una palabra de la opción 1 bien escrita o casi. Lógica pura.
"""
from difflib import SequenceMatcher

from app.text import tokenize

# Las palabras con las que se pide la opción 1 («Programar análisis y recogida de muestra»)
# y «ruta», que es como la llaman las veterinarias.
_PALABRAS = ("programar", "agendar", "recogida", "recoger", "recoleccion", "ruta", "muestra", "muestras")
_MAX_PALABRAS = 4      # una opción del menú, no una frase con otra intención adentro
_MIN_LETRAS = 5        # «rita» o «rota» solas no alcanzan para decidir nada
_PARECIDO = 0.84       # «progrmar» 0,94 · «recojida» 0,88 · «agendr» 0,92


def parece_programar(texto: str) -> bool:
    tokens = tokenize(texto)
    if not tokens or len(tokens) > _MAX_PALABRAS:
        return False
    for token in tokens:
        if token in _PALABRAS:
            return True
        if len(token) >= _MIN_LETRAS and any(
                SequenceMatcher(None, token, palabra).ratio() >= _PARECIDO for palabra in _PALABRAS):
            return True
    return False
