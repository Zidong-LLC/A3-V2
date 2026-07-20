"""Detectores de identificación de cliente (cambio de cliente, sede nueva,
no-registrado, identificadores) y su vocabulario."""
from app.text import tokenize as _tokenize


_BRANCH_NOUN_TOKENS = frozenset({"sucursal", "sucursales", "sede", "sedes", "local", "locales"})


_CLIENT_CHANGE_SIGNAL_TOKENS = frozenset({
    "otra", "otras", "otro", "otros", "cambiar", "cambia", "cambio", "cambió", "distinta", "distinto",
    "diferente", "no", "equivoque", "equivoqué", "equivoco", "equivocado", "equivocada",
    "nueva", "nuevo",
    # Formas verbales flexivas de cambiar/poner/facturar/mandar aplicadas al cliente (QA de
    # estrés 2026-07-20: 'cambiala/cambiemos/ponela a nombre de otra clínica' no matcheaban
    # y el turno no llegaba al modelo que sí clasifica change_client). La ventana de
    # adyacencia (ver _wants_to_change_client) exige un sustantivo de cliente/sede CERCA,
    # así 'pasa el hemograma' no dispara — solo 'pasala a la otra clínica'.
    "cambiala", "cámbiala", "cambiale", "cámbiale", "cambiemos", "cambien", "cambienla", "cambiénla",
    "ponela", "ponla", "pónla", "póngala", "pongala", "pasala", "pásala", "pasala",
    "mandala", "mándala", "factura", "facturala", "factúrala", "facturá",
})


_CLIENT_NOUN_TOKENS = frozenset({
    "veterinaria", "veterinarias", "clinica", "clínica", "clinicas", "clínicas",
    "consultorio", "hospital", "cliente", "clientes",
})


_BRANCH_NEW_SIGNAL_TOKENS = frozenset({
    "nueva", "nuevo", "nuevas", "nuevos", "registrar", "registro",
    "agregar", "añadir", "anadir", "abrir", "abrimos", "abrieron", "abrio", "abrió",
    "inaugurar", "inauguramos", "ninguna", "ninguno",
})


_NON_IDENTIFIER_TOKENS = frozenset({
    "paciente", "mascota", "perro", "gato", "examen", "analisis", "análisis",
    "muestra", "hemograma", "perfil", "llama", "resultado", "resultados",
    "motivo", "motivos", "muerte", "muerto", "muerta", "fallecio", "falleció",
    "registrado", "registrados", "registrada", "registradas", "registrarme",
    "dije", "dicho",
    # Correcciones / confusión de opción: nunca son el NIT ni el nombre del cliente.
    "confundi", "confundí", "confundido", "confundida", "equivoque", "equivoqué",
    "equivoco", "equivocado", "equivocada", "opcion", "opción", "opciones", "menu", "menú",
})


_REJECT_ALL_MATCH_TOKENS = frozenset({
    "ninguno", "ninguna", "ningun", "ningún", "ningunos", "ningunas", "tampoco",
})



def _wants_to_change_client(text: str) -> bool:
    """¿El usuario indica que la orden es para OTRA veterinaria/cliente/sede?
    Exige un sustantivo de cliente o SEDE + una señal de cambio para no confundir un
    'confirmo los datos del cliente' con un cambio real. Incluye sede/sucursal porque
    'esta orden es para la otra sede' es un cambio de cliente (QA extremo: se interpretaba
    como una selección de perfil espuria).
    Señal y sustantivo deben estar CERCA (ventana de 3 palabras): 'sangre de OTRO peludo
    de la CLÍNICA' menciona la clínica de pasada y NO es un cambio — el falso positivo
    robaba el turno de another_order (QA real 2026-07-18; clase ERR-066: el dato es una
    secuencia, no palabras sueltas). Los fraseos lejanos los cubre la señal del modelo."""
    toks = _tokenize(text)
    nouns = _CLIENT_NOUN_TOKENS | _BRANCH_NOUN_TOKENS
    for i, tok in enumerate(toks):
        if tok in _CLIENT_CHANGE_SIGNAL_TOKENS:
            window = toks[max(0, i - 3):i + 4]
            if any(t in nouns for t in window):
                return True
    return False



def _wants_new_branch(text: str) -> bool:
    """¿El usuario quiere usar/registrar una SUCURSAL o SEDE nueva no registrada?"""
    tokens = set(_tokenize(text))
    return bool(tokens & _BRANCH_NOUN_TOKENS) and bool(tokens & _BRANCH_NEW_SIGNAL_TOKENS)



def _claims_unregistered_client(text: str) -> bool:
    normalized = " ".join(_tokenize(text))
    phrases = (
        "no estoy registrado", "no estamos registrados", "no esta registrado",
        "no está registrado", "no estoy en la base", "no estamos en la base",
        # Formas naturales de decir que no está registrado / es independiente / es nuevo
        "de forma independiente", "soy independiente", "trabajo independiente",
        "trabajo de forma independiente", "de manera independiente", "por mi cuenta",
        "me tendria que registrar", "me tendría que registrar", "tendria que registrarme",
        "tendría que registrarme", "tengo que registrarme", "me tengo que registrar",
        "registrarme de nuevo", "no me he registrado", "todavia no estoy registrado",
        "todavía no estoy registrado", "aun no estoy registrado", "aún no estoy registrado",
    )
    return any(phrase in normalized for phrase in phrases)



def _asks_if_new_client(reply: str) -> bool:
    return "cliente nuevo" in " ".join(_tokenize(reply))



def _is_no_identifier_text(text: str) -> bool:
    words = set(_tokenize(text))
    return "no" in words and bool(words & {"se", "sé", "tengo", "dato", "ninguno"})



def _looks_like_bare_client_name(text: str) -> bool:
    if _claims_unregistered_client(text):
        return False
    tokens = _tokenize(text)
    if not tokens or len(tokens) > 4:
        return False
    if tokens[0] in {"para", "por", "porque", "como", "cómo", "que", "qué", "cual", "cuál", "tengo"}:
        return False
    return not (set(tokens) & _NON_IDENTIFIER_TOKENS)



def _asks_for_client_identity(reply: str) -> bool:
    tokens = set(_tokenize(reply))
    return "nit" in tokens and ("veterinaria" in tokens or "nombre" in tokens)



def _rejects_match_options(text: str) -> bool:
    """El cliente indica que NINGUNA de las coincidencias listadas es la suya
    ('ninguno de esos', 'no es ninguna', 'tampoco')."""
    return bool(set(_tokenize(text)) & _REJECT_ALL_MATCH_TOKENS)
