"""Utilidades de texto puras (Fase 3.4 — descomponer el monolito `agent.py`).

Tokenización, normalización para matching y formateo de dinero. Sin I/O ni estado: funciones
puras y testeables, reutilizables por `agent.py`, `catalog.py`, `state.py`. Es la capa base de
la que dependen los detectores de intención y la resolución de catálogo.
"""
import re

# Traducción de acentos para comparaciones insensibles a tildes.
ACCENT_TRANSLATION = str.maketrans("áéíóúüñ", "aeiouun")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9áéíóúñü]+", text.lower())


def money(value: int | None) -> str:
    return f"${int(value or 0):,} COP"


def catalog_item_key(value) -> str:
    """Clave normalizada (sin tildes ni símbolos, con `_`) para comparar nombres/códigos."""
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def strip_price_text(text: str) -> str:
    """Quita cifras de precio escritas dentro de un texto de análisis ('Coprológico $23k',
    'Cuadro Hemático $14.000'): el precio NUNCA viene del texto del modelo, sale del
    catálogo. No toca números que son parte del nombre ('Parcial de Orina (14 parámetros)')."""
    out = re.sub(r"\$\s*[\d.,]+\s*(?:k\b|cop\b)?", " ", text or "", flags=re.IGNORECASE)
    out = re.sub(r"\b\d+\s*k\b", " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\b\d{1,3}(?:[.,]\d{3})+(?:\s*cop)?\b", " ", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip(" -–—.,:;")


def as_text_items(value) -> list[str]:
    """Normaliza un valor libre (lista, string o nada) a lista de strings limpios.
    Fuente única para leer selected_tests/removed_tests con cualquier forma que el
    modelo los haya emitido."""
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [value]
    else:
        return []
    return [str(item).strip() for item in raw_items if str(item or "").strip()]
