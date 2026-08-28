"""Utilidades de texto puras (Fase 3.4 — descomponer el monolito `agent.py`).

Tokenización, normalización para matching y formateo de dinero. Sin I/O ni estado: funciones
puras y testeables, reutilizables por `agent.py`, `catalog.py`, `state.py`. Es la capa base de
la que dependen los detectores de intención y la resolución de catálogo.
"""
import re

# Traducción de acentos para comparaciones insensibles a tildes.
ACCENT_TRANSLATION = str.maketrans("áéíóúüñ", "aeiouun")


def tokenize(text: str) -> list[str]:
    """Tokens en minúsculas y SIN tildes (Etapa N del refactor de comprensión, 2026-08-21).

    Antes conservaba los acentos y cada lista de vocabulario tenía que duplicar
    "sácalo/sacalo, análisis/analisis…" — y una variante no listada rompía el detector
    (la gente escribe sin tildes). Ahora la normalización vive acá, una sola vez, igual
    que en `catalog.py::_norm`: los sets comparan contra tokens ya normalizados y la
    tilde deja de importar. La ñ→n es deliberada y consistente en ambos lados
    ("años" en un set se normaliza igual que el token "anos" del mensaje)."""
    return re.findall(r"[a-z0-9]+", text.lower().translate(ACCENT_TRANSLATION))


def money(value: int | None) -> str:
    """Formato colombiano: separador de miles con PUNTO y sin sufijo de moneda ($18.000).
    Antes salía "$18,000 COP" —coma inglesa—, que A3 pidió corregir (llamada 7)."""
    return f"${int(value or 0):,}".replace(",", ".")


def short_datetime(value) -> str:
    """Fecha legible para las tablas: '2026-08-28T16:22:03+00:00' -> '28/08 16:22'.
    Antes se recortaba a mano en la plantilla y salía el ISO crudo, partido en dos
    líneas dentro de la celda."""
    texto = str(value or "")
    if len(texto) < 16:
        return texto or "-"
    return f"{texto[8:10]}/{texto[5:7]} {texto[11:16]}"


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


def strip_question_sentences(text: str) -> str:
    """Deja solo las frases que NO son pregunta: para anteponer el acuse de un turno
    lateral a la re-pregunta del flujo sin duplicar interrogantes."""
    chunks = [c.strip() for c in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if c.strip()]
    kept = [chunk for chunk in chunks if "?" not in chunk and "¿" not in chunk]
    return " ".join(kept).strip()


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
