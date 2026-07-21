"""Resolución unívoca de texto libre → análisis del catálogo.

Función PURA (sin I/O): recibe las filas del catálogo ya cargadas y decide, sin
adivinar, qué análisis pidió el cliente. Es la pieza que reemplaza el string-matching
disperso (`get_tests_by_codes_or_names`, `find_tests_by_area`, `_named_analysis_terms`)
que provocó ~20 parches de dinero (agregar tests no pedidos, precios inventados).

Principio: se AGREGA a la orden solo con match inequívoco. Un término genérico o de área
("sanguíneos", "orina") NUNCA resuelve por su cuenta a un test suelto: se ofrecen opciones
para que el cliente elija. Ante la duda, ofrecer — nunca adivinar (regla de dinero).
"""
import re
import math
from dataclasses import dataclass, field

EXACT = "exact"          # match inequívoco → agregar directo
AMBIGUOUS = "ambiguous"  # varios candidatos o término de área → ofrecer para elegir
NONE = "none"            # sin señal → preguntar cuál

# Palabras estructurales que no aportan distintividad al nombre de un análisis.
_FILLER = frozenset({"de", "del", "la", "el", "los", "las", "con", "en", "y", "e", "o",
                     "para", "por", "un", "una"})
# Palabras de ÁREA/muestra demasiado vagas: solas NO nombran un test concreto ('análisis de
# sangre' no es 'Sangre Oculta'). Se dejan para los menús de área / ayuda dedicada.
_AREA_WORDS = frozenset({"sangre", "sanguineo", "sanguinea", "sanguineos", "sanguineas",
                         "orina", "urinario", "urinaria", "heces", "fecal", "fecales",
                         "suero", "plasma"})
_ANALYSIS_NOUNS = frozenset({"analisis", "examen", "examenes", "prueba", "pruebas",
                             "perfil", "estudio", "estudios", "test", "tests"})
# Verbos/muletillas de pedido: no nombran un análisis ('NECESITO una prueba de orina').
_REQUEST_WORDS = frozenset({"necesito", "quiero", "quisiera", "dame", "deme", "hazme",
                            "hacer", "hacerle", "pon", "ponme", "ponle", "ponele",
                            "agregame", "agrega", "agregar", "agregarle", "sumale", "suma",
                            "favor", "porfa", "quiere", "queremos", "necesitamos",
                            "solicito", "vamos"})

# Palabras ESTRUCTURALES: jamás identifican un área/muestra del catálogo. Sin este filtro,
# el "con" de 'vamos CON el 152...' matcheaba la muestra 'Tubo Tapa Azul CON 3/4 de sangre'
# y ofrecía el menú de Coagulación (prueba real 2026-07-16). Lo usan este módulo y
# db.find_tests_by_area (fuente única del vocabulario estructural).
STRUCTURAL_TOKENS = frozenset(_FILLER | _ANALYSIS_NOUNS | _REQUEST_WORDS)

# Descriptores GENÉRICOS del español: aparecen en nombres de tests ('Estudio de CÁLCULO',
# 'Espermograma BÁSICO', 'PANEL Test', 'CUADRO Hemático', 'LECTURA Sedimento', 'Calcio
# TOTAL') pero también en el habla corriente ('hazme el cálculo', 'algo básico', 'te paso
# el cuadro'). SOLOS nunca nombran un test — la auditoría de trampas léxicas (ERR-064)
# mostró que 'cálculo' suelto auto-agregaba un test de $83.000. Solo cuentan como APOYO
# junto a una palabra distintiva del dominio ('cuadro HEMÁTICO' sí nombra).
GENERIC_DESCRIPTORS = frozenset({
    "basico", "basica", "basicos", "basicas", "completo", "completa", "general",
    "generales", "total", "totales", "parcial", "parciales", "panel", "paneles",
    "cuadro", "cuadros", "lectura", "lecturas", "calculo", "calculos", "control",
    "controles", "simple", "doble", "triple", "tiempo", "tiempos", "medio", "media",
    "directo", "directa", "indirecto", "indirecta", "rapido", "rapida", "fresco",
    "fresca", "especial", "comun",
})

_SPLIT = re.compile(r"\s*(?:,|;|/|\+|\by\b|\be\b|\bmas\b|\bmás\b)\s*")


def split_items(text: str) -> list[str]:
    """Ítems de un pedido múltiple, en el orden en que el cliente los dijo."""
    return [i.strip() for i in _SPLIT.split(text or "") if i and i.strip()]


@dataclass
class ResolveResult:
    status: str
    tests: list = field(default_factory=list)   # EXACT: a agregar; AMBIGUOUS: opciones a ofrecer
    area: str | None = None                      # nombre del área cuando el match es por categoría
    # Ítems del pedido que NO quedaron representados en `tests` (ERR-076). Un PERFIL vive en
    # `catalog_profiles`, no acá, así que "un pre quirúrgico" no resuelve y desaparecía en
    # silencio: el que pide debe poder ofrecerlo en vez de perderlo. Campo informativo — no
    # cambia `status` ni `tests`, así que ningún consumidor existente se entera.
    unresolved: list = field(default_factory=list)


def _norm(s) -> str:
    s = str(s or "").strip().lower()
    s = s.translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _tokens(s) -> list[str]:
    return [t for t in _norm(s).split() if t]


def _significant(tokens) -> list[str]:
    return [t for t in tokens if t not in _FILLER]


def _content_only(tokens) -> list[str]:
    """Tokens que de verdad NOMBRAN un análisis: sin fillers, sin sustantivos genéricos
    ('prueba', 'análisis'), sin palabras de área sueltas ('orina', 'sangre'). Sin este
    filtro, 'necesito una PRUEBA de ORINA' matcheaba 'PRUEBA Cruzada de Coombs' y
    'Cortisol en ORINA' por las palabras genéricas (QA del flujo real del usuario)."""
    return [t for t in tokens if t not in _FILLER and t not in _ANALYSIS_NOUNS
            and t not in _AREA_WORDS]


def _name_is_named_by(user_tokens: set[str], name_tokens: list[str]) -> bool:
    """¿El texto del usuario nombra ESTE análisis de forma inequívoca? Se compara solo el
    CONTENIDO distintivo de ambos lados: cubre el token inicial (el más distintivo) o al
    menos la mitad de los tokens. Además, el match debe incluir al menos UNA palabra
    distintiva del dominio: los descriptores genéricos del español solos ('cálculo',
    'básico', 'panel', 'cuadro') NO nombran un test — solo apoyan (ERR-064)."""
    sig = _content_only(name_tokens)
    if not sig:
        return False
    matched = [t for t in sig if t in user_tokens]
    if not matched or all(t in GENERIC_DESCRIPTORS for t in matched):
        return False
    if sig[0] in user_tokens:
        return True
    return len(matched) >= math.ceil(0.5 * len(sig))


def _overlaps(user_tokens: set[str], name_tokens: list[str]) -> bool:
    """Overlap DÉBIL (último recurso para ofrecer): exige palabras de contenido de ≥4
    letras en ambos lados — la 'a' de '...va A nombre de...' matcheaba 'Amiloide Sérico A
    Felino' y generaba un menú fantasma (verificado en vivo, 3.3)."""
    sig = {t for t in _content_only(name_tokens) if len(t) >= 4 and t not in GENERIC_DESCRIPTORS}
    return bool({t for t in user_tokens if len(t) >= 4} & sig)


def _dedupe(rows) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        code = r.get("code")
        if code and code not in seen:
            out.append(r)
            seen.add(code)
    return out


def _resolve_one(text: str, rows: list[dict], species: str | None) -> ResolveResult:
    user_tokens = set(_tokens(text))
    if not user_tokens:
        return ResolveResult(NONE)

    # Solo el CONTENIDO distintivo nombra un análisis: sin verbos de pedido ('necesito'),
    # sustantivos genéricos ('prueba') ni palabras de área sueltas ('orina', 'sangre').
    # 'necesito una prueba de orina' NO nombra ningún test (match_tokens vacío) → NONE,
    # y el caller ofrece las opciones del área. Evita 'prueba'→'Prueba de Coombs'.
    match_tokens = user_tokens - _FILLER - _AREA_WORDS - _ANALYSIS_NOUNS - _REQUEST_WORDS

    by_code = {str(r.get("code")): r for r in rows if r.get("code")}

    # 1) Código exacto mencionado en el texto.
    codes = [by_code[t] for t in user_tokens if t in by_code]
    if codes:
        return ResolveResult(EXACT, _dedupe(codes))

    if not match_tokens:
        return ResolveResult(NONE)

    # 2) Nombre canónico: el usuario nombra el análisis de forma inequívoca. Varios
    #    candidatos que cubren tokens DISTINTOS son varios pedidos en una frase
    #    ('cuadro hematico sodio' → ambos); solo hay ambigüedad real cuando compiten
    #    por las MISMAS palabras ('una glucosa' → las tres glucosas).
    named = [r for r in rows if _name_is_named_by(match_tokens, _tokens(r.get("name")))]
    if named:
        def _cov(r):
            return user_tokens & set(_significant(_tokens(r.get("name"))))
        named = _dedupe(sorted(named, key=lambda r: len(_cov(r)), reverse=True))
        picked, consumed = [], set()
        for cand in named:
            new = _cov(cand) - consumed
            if not new:
                continue  # no aporta tokens nuevos: variante ya cubierta por otro candidato
            if any(c is not cand and c not in picked and (_cov(c) - consumed) == new
                   for c in named):
                return ResolveResult(AMBIGUOUS, named)  # empate real sobre los mismos tokens
            picked.append(cand)
            consumed |= new
        if picked:
            return ResolveResult(EXACT, picked)
        return ResolveResult(AMBIGUOUS, named)

    # 3) Término de área: coincide con una categoría/tipo de muestra → ofrecer esas opciones.
    area, area_tests = _resolve_area(user_tokens, rows, species)
    if area_tests:
        return ResolveResult(AMBIGUOUS, area_tests, area=area)

    # 4) Overlap débil (un token secundario compartido): ofrecer, no agregar.
    weak = _dedupe([r for r in rows if _overlaps(match_tokens, _tokens(r.get("name")))])
    if weak:
        return ResolveResult(AMBIGUOUS, weak)

    return ResolveResult(NONE)


def _resolve_area(user_tokens: set[str], rows: list[dict], species: str | None):
    """Análisis cuya categoría o tipo de muestra coincide con una palabra del usuario.
    Solo cuentan palabras de CONTENIDO en ambos lados: una preposición ('con') o un
    genérico ('medio') no identifican un área aunque aparezcan en el nombre de la muestra."""
    user_tokens = user_tokens - STRUCTURAL_TOKENS - GENERIC_DESCRIPTORS

    def keyset(value):
        return {t for t in _tokens(value) if len(t) >= 3 and t not in _FILLER}

    sp = (species or "").strip().lower()
    scoped = [r for r in rows
              if not r.get("species") or sp not in ("canino", "felino")
              or r.get("species") in (sp, "ambos")]

    by_cat: dict[str, list[dict]] = {}
    for r in scoped:
        if user_tokens & keyset(r.get("category")):
            by_cat.setdefault(r.get("category") or "", []).append(r)
    if by_cat:
        best = max(by_cat, key=lambda c: len(by_cat[c]))
        return best, _dedupe(by_cat[best])

    sample_hits = [r for r in scoped if user_tokens & keyset(r.get("sample"))]
    if sample_hits:
        # Etiqueta = la categoría MÁS COMÚN entre los hits ('orina' → Uroanálisis), no la
        # del primero (mostraba 'Para hormonas...' por el Cortisol en Orina; chat real).
        from collections import Counter
        area = Counter(r.get("category") for r in sample_hits).most_common(1)[0][0]
        return (area, _dedupe(sample_hits))
    return None, []


def names_test(text: str, row: dict) -> bool:
    """¿El texto nombra inequívocamente ESTE análisis (o menciona su código)? Mismo criterio
    de contenido distintivo que la resolución: palabras de área ('orina'), genéricas
    ('prueba') o de pedido ('necesito') NO nombran. Sirve para validar el anclaje (I3) de
    códigos que el modelo capturó por su cuenta: 'potasio sodio y orina' nombra Potasio y
    Sodio, pero NO nombra 'Parcial de Orina' — ese debe ofrecerse, no asumirse."""
    tokens = set(_tokens(text))
    if str(row.get("code") or "") in tokens:
        return True
    match_tokens = tokens - _FILLER - _AREA_WORDS - _ANALYSIS_NOUNS - _REQUEST_WORDS
    return bool(match_tokens) and _name_is_named_by(match_tokens, _tokens(row.get("name")))


def resolve_tests(text: str, rows: list[dict], species: str | None = None,
                  collect_partial: bool = False) -> ResolveResult:
    """Resuelve uno o varios análisis nombrados en `text` contra `rows` (catálogo cargado).
    Varios ítems separados por coma/"y" se resuelven por separado.
    - Por defecto (agregar a la orden): all-or-nothing — si algún ítem es ambiguo se pide
      aclarar, para no agregar a medias.
    - `collect_partial=True` (cotizar un precio): devuelve los ítems que SÍ resuelven de
      forma inequívoca e ignora el ruido (p. ej. '...glucosa en ayunas, ¿cuánto es el total?')."""
    if not rows:
        return ResolveResult(NONE)
    items = [i for i in _SPLIT.split(text.strip()) if i and i.strip()]
    if len(items) <= 1:
        return _resolve_one(text, rows, species)

    collected, all_exact, unresolved = [], True, []
    for item in items:
        r = _resolve_one(item, rows, species)
        if r.status == EXACT:
            collected.extend(r.tests)
        else:
            all_exact = False
            unresolved.append(item)
    if collected and (all_exact or collect_partial):
        return ResolveResult(EXACT, _dedupe(collected), unresolved=unresolved)
    # Mezcla ambigua: intentar el texto completo como un único término antes de rendirse.
    # Este fallback hace funcionar los nombres multi-palabra que el splitter parte mal, así que
    # su semántica no se toca; pero es donde un ítem que no resuelve (un perfil) se evaporaba sin
    # dejar rastro. Se reporta en `unresolved` para que el que llama pueda ofrecerlo (ERR-076).
    whole = _resolve_one(text, rows, species)
    return ResolveResult(whole.status, whole.tests, whole.area, unresolved)
