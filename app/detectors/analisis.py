"""Detectores y utilidades puras del ANÁLISIS/perfil (texto → señal).

Capa de detección que desbloquea la migración de enforcers (Paso 3.4): solo depende de
app.text/app.flow/otros detectores — sin I/O ni helpers de agent."""
import re

from app.text import tokenize as _tokenize, ACCENT_TRANSLATION as _ACCENT_TRANSLATION
from app.detectors.orden import _detect_correction_field, _is_same_as_previous, _SAME_AS_PREVIOUS_TOKENS
from app.detectors.basico import _AFFIRMATIVE_TOKENS, _NEGATIVE_TOKENS



_PARTIAL_KEEP_MARKERS = frozenset({"pero", "salvo", "excepto", "menos", "sin", "aunque", "mas", "más"})


_ANALYSIS_ADD_REMOVE_TOKENS = frozenset({
    "agregar", "agrega", "agregale", "agrégale", "agregarle", "agregarlo", "añadir",
    "anadir", "añade", "añadile", "sumar", "suma", "sumale", "incluir", "incluye", "incluile",
    "quitar", "quita", "quitale", "quítale", "sacar", "saca", "sacale", "sácale",
    "retirar", "retira", "remover", "remueve",
})


_ANALYSIS_CHANGE_SIGNAL_TOKENS = frozenset({
    "otro", "otra", "otros", "otras", "nuevo", "nueva", "distinto", "distinta",
    "diferente", "cambiar", "cambia", "cambie", "cambiarlo", "cambiamos",
})


_ANALYSIS_NOUN_TOKENS = frozenset({
    "analisis", "análisis", "examen", "examenes", "exámenes",
    "perfil", "perfiles", "prueba", "pruebas",
})


_PROFILE_SPECIFIC_SUFFIXES = frozenset({
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
})


_PROFILE_DETAIL_TOKENS = frozenset({
    "incluye", "incluyen", "contiene", "contienen", "trae", "traen",
    "detalle", "detalles", "detallar", "componentes", "composicion", "composición",
})


_DOESNT_KNOW_PHRASES = (
    "no se", "no sé", "no estoy seguro", "no tengo claro", "ni idea",
    "no sabria", "no sabría", "no sé cuál", "no se cual",
)


_EXAM_ITEM_SEPARATOR = re.compile(r",|;|\n|\b y \b|\b e \b|\+", re.IGNORECASE)


_RECOMMENDATION_TOKENS = frozenset({
    "recomienda", "recomiendas", "recomiende", "recomienden", "recomiendan",
    "recomiendame", "recomiéndame", "recomendacion", "recomendación",
    "sugieres", "sugiere", "sugieran", "sugieren", "sugerencia", "sugerencias",
    "aconsejas", "aconseja", "conviene", "convienen", "convendria", "convendría",
})


_PRICE_QUESTION_TOKENS = frozenset({"cuanto", "cuánto", "cuesta", "costaria", "costaría", "valor", "precio", "cotizar", "cotizacion", "cotización"})

_TOTAL_QUESTION_TOKENS = frozenset({
    "todos", "todas", "total", "todo", "junto", "juntos", "completo", "suma", "sumando",
    "conjunto", "sumados",
})

_PRICE_STOPWORDS = _PRICE_QUESTION_TOKENS | _TOTAL_QUESTION_TOKENS | {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "ese", "esos",
    "esa", "esas", "esto", "este", "estos", "y", "e", "o", "u", "me", "que", "es", "son",
    "seria", "serían", "serian", "sería", "sale", "saldria", "saldría", "para", "por",
    "con", "sin", "mas", "más", "todos", "analisis", "análisis", "examen", "examenes",
    "exámenes", "prueba", "pruebas", "perfil", "perfiles", "cada", "uno",
}


_ACTION_STOPWORDS = frozenset({
    "quiero", "quiere", "queria", "quería", "necesito", "agregar", "agrega", "agregame",
    "agregue", "agregarle", "agregarme", "sumar", "suma", "añadir", "anadir", "poner",
    "ponme", "incluir", "incluye", "otro", "otra", "otros", "otras", "tambien", "también",
    "quitar", "quita", "sacar", "saca", "eliminar", "elimina", "cambiar", "cambia",
})


_REMOVE_TOKENS = frozenset({"quitar", "quita", "quitale", "quítale", "sacar", "saca", "sacale",
                            "sácale", "sin", "menos", "retirar", "remover", "remueve"})


_PROCEED_TO_PAYMENT_TOKENS = frozenset({
    "no", "nada", "ninguno", "ninguna", "listo", "lista", "seguimos", "sigamos", "sigue",
    "continuemos", "continua", "continúa", "ya", "pago", "paga", "pagar", "cerramos",
    "cierra", "finalizar", "terminar", "eso", "suficiente", "completo", "completa",
})


_PROCEED_TO_PAYMENT_PHRASES = (
    "asi esta", "asi está", "esta bien", "está bien", "asi nomas", "nada mas", "nada más",
    "es todo", "con eso", "sigamos con el pago", "seguimos con el pago", "vamos al pago",
    "asi quedamos", "ya esta", "ya está", "dejalo asi", "déjalo así",
)



# Palabras que nombran el CAMPO análisis, no una prueba concreta del catálogo.
_ANALYSIS_FIELD_WORDS = frozenset({
    "analisis", "análisis", "perfil", "perfiles", "examen", "examenes", "exámenes",
    "tipo", "tipos", "estudio", "estudios", "prueba", "pruebas",
})
# Muletillas del "todo igual menos …": no aportan a distinguir parcial de total.
_PARTIAL_CHANGE_STOPWORDS = frozenset({
    "todo", "toda", "todos", "todas", "igual", "iguales", "mismo", "misma", "mismos",
    "lo", "el", "la", "los", "las", "un", "una", "de", "del", "menos", "salvo",
    "excepto", "pero", "sin", "y", "que", "es", "son", "solo", "sólo", "cambia",
    "cambiá", "cambiar", "cambiame", "cambiemos",
})


def _wants_partial_analysis_change(text: str) -> bool:
    """¿El cliente quiere MANTENER el análisis/perfil anterior y solo ajustarlo
    (agregar o quitar pruebas), no empezar de cero? Ej.: 'el mismo pero sin coproscópico',
    'igual más glucosa', 'sacale estas dos'. En ese caso NO se limpia: se personaliza el
    perfil base por el camino existente (`_profile_customizing`)."""
    tokens = set(_tokenize(text))
    if tokens & _ANALYSIS_ADD_REMOVE_TOKENS:
        return True
    if (tokens & {"extra", "extras", "adicional", "adicionales"}
            and tokens & {"analisis", "análisis", "examen", "examenes", "exámenes", "prueba", "pruebas"}):
        return True
    if tokens & {"personalizar", "personalizarlo", "ajustar", "ajustarlo", "modificar"}:
        return True
    if (_is_same_as_previous(text) or tokens & _SAME_AS_PREVIOUS_TOKENS) and tokens & _PARTIAL_KEEP_MARKERS:
        # "el mismo MENOS el coproscópico" es un ajuste parcial: excluye UNA prueba.
        # "todo igual MENOS el tipo de análisis" es un cambio TOTAL: lo que excluye es el
        # campo entero, no un ítem. Se distinguen por lo que queda al sacar las muletillas:
        # si no nombró ninguna prueba concreta, está hablando del análisis como campo.
        # (Prueba real, chat 4: se leía como parcial y el perfil de la orden anterior
        # sobrevivía, apagando la validación del análisis nuevo.)
        if not (tokens - _PARTIAL_CHANGE_STOPWORDS - _ANALYSIS_FIELD_WORDS):
            return False
        return True
    return False



def _wants_to_change_analysis(text: str) -> bool:
    """¿El cliente quiere reemplazar el análisis/perfil por otro TOTALMENTE distinto
    (empezar el análisis de cero)? Ej.: 'con otro análisis', 'quisiste hacer otro análisis',
    'cambiemos el perfil'. NO aplica a un ajuste parcial ('el mismo pero sin X'): eso se
    mantiene y se personaliza, no se limpia."""
    if _wants_partial_analysis_change(text):
        return False
    tokens = set(_tokenize(text))
    if not (tokens & _ANALYSIS_NOUN_TOKENS):
        return False
    if tokens & _ANALYSIS_CHANGE_SIGNAL_TOKENS:
        return True
    # "todo igual MENOS el análisis": excluir el campo entero del "todo igual" ES pedir otro
    # análisis, aunque no aparezca ningún verbo de cambio. Misma condición que usa
    # `_wants_partial_analysis_change` para descartarlo, del otro lado.
    return bool(tokens & _PARTIAL_KEEP_MARKERS) and not (
        tokens - _PARTIAL_CHANGE_STOPWORDS - _ANALYSIS_FIELD_WORDS)



def _looks_like_catalog_profile(value: str | None) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    tokens = set(_tokenize(text))
    return text.isdigit() or bool(tokens & {"perfil", "panel"})



def _looks_like_specific_profile_query(value: str | None) -> bool:
    tokens = _tokenize(value or "")
    return bool(tokens and (tokens[-1] in _PROFILE_SPECIFIC_SUFFIXES or any(token.isdigit() for token in tokens)))



def _is_profile_detail_question(text: str) -> bool:
    return bool(set(_tokenize(text)) & _PROFILE_DETAIL_TOKENS)



def _is_generic_blood_analysis(text: str | None) -> bool:
    tokens = set(_tokenize(text or ""))
    if not tokens or {"oculta", "oculto"} & tokens:
        return False
    return "sangre" in tokens and bool(tokens & {"analisis", "análisis", "examen", "prueba"})



def _doesnt_know_what_to_ask(text: str) -> bool:
    """¿El cliente responde que no sabe qué análisis pedir o pide ayuda/opciones?"""
    lower = (text or "").lower()
    if any(p in lower for p in _DOESNT_KNOW_PHRASES):
        return True
    return bool(set(_tokenize(text)) & {
        "opciones", "ayuda", "ayudame", "ayúdame", "orienta", "orientame",
        "oriéntame", "muestrame", "muéstrame", "orientas",
    })



def _split_multiple_exam_items(text: str | None) -> list[str]:
    """Parte un texto de análisis en ítems individuales ('hemograma, química y
    urianálisis' -> 3 ítems). Devuelve >=2 solo si claramente hay varios."""
    if not text:
        return []
    items = []
    for part in _EXAM_ITEM_SEPARATOR.split(text):
        item = part.strip(" .,:;-")
        if len(item) >= 2:
            items.append(item)
    return items



def _profile_codes_from_text(text: str) -> list[str]:
    codes = []
    for code in re.findall(r"\b\d{3,4}\b", text or ""):
        if code not in codes:
            codes.append(code)
    return codes



def _last_bot_message(history: list[dict]) -> str:
    for msg in reversed(history):
        if msg["role"] == "bot":
            return msg["content"]
    return ""



def _detect_which_field_is_being_asked(history: list[dict]) -> str | None:
    bot_msg = _last_bot_message(history).lower()
    field_patterns = [
        ("medico solicitante", "requesting_doctor"),
        ("médico solicitante", "requesting_doctor"),
        ("nombre del paciente", "patient_name"),
        ("nombre del propietario", "owner_name"),
        ("propietario", "owner_name"),
        ("especie", "species"),
        ("canino", "species"),
        ("felino", "species"),
        ("raza", "breed"),
        ("macho o hembra", "sex"),
        ("sexo", "sex"),
        ("edad", "patient_age"),
        ("dirección de retiro", "pickup_address"),
        ("domicilio", "pickup_address"),
        ("retiro", "pickup_address"),
        ("análisis", "exam_type"),
        ("perfil", "exam_type"),
        ("examen", "exam_type"),
        ("observaci", "observations"),
        ("pago", "payment_method"),
        ("contraentrega", "payment_method"),
    ]
    for pattern, field in field_patterns:
        if pattern in bot_msg:
            return field
    return None



def _wants_profile_recommendation(text: str) -> bool:
    """¿El cliente pide que le recomendemos o sugiramos un análisis o perfil?"""
    return bool(set(_tokenize(text)) & _RECOMMENDATION_TOKENS)



def _named_analysis_terms(text: str) -> list[str]:
    """Palabras de la pregunta que podrían nombrar un análisis (descarta las de precio,
    artículos, muletillas y verbos de acción). Sirve para resolver '¿cuánto sale el hemograma?'.
    Los dígitos sueltos de 1-2 cifras NO son códigos de análisis (los códigos tienen ≥3):
    admitirlos hacía que 'parasitológico 3' resolviera a 'T3 Total' por parecido de nombre."""
    stop = _PRICE_STOPWORDS | _ACTION_STOPWORDS
    return [
        t for t in _tokenize(text)
        if ((len(t) >= 4) or (t.isdigit() and len(t) >= 3)) and t not in stop
    ]



def _wants_to_proceed_to_payment(text: str) -> bool:
    """Ante la oferta de agregar más, ¿el cliente decide SEGUIR al pago (o ya dio el método)?
    Una orden de agregar/quitar ('agregale X') nunca cuenta como seguir."""
    if _payment_method_from_text(text):
        return True
    ordered = _tokenize(text)
    tokens = set(ordered)
    if tokens & (_ANALYSIS_ADD_REMOVE_TOKENS | _REMOVE_TOKENS):
        return False
    normalized = " ".join(ordered)  # ORDENADO: las frases necesitan el orden original
    if any(p in normalized for p in _PROCEED_TO_PAYMENT_PHRASES):
        return True
    return bool(tokens & _PROCEED_TO_PAYMENT_TOKENS)



def _payment_method_from_text(text: str) -> str | None:
    """Red de respaldo del método de pago. La fuente primaria es lo que captura el MODELO
    (que interpreta la intención); esto solo cubre el turno en que no lo marcó.

    Los fraseos indirectos están acá porque el cliente describe CUÁNDO paga, no cómo se
    llama el método: "les pagamos cuando pasen a recoger", "mandanos el link"."""
    tokens = set(_tokenize(text))
    # "contra entrega" separado es la MISMA palabra que "contraentrega": el cliente la escribe
    # de las dos formas y la red no reconocía la segunda ("pagamos contra entrega" → None).
    if "contraentrega" in tokens or "efectivo" in tokens or (
            "contra" in tokens and {"entrega", "entregar", "entregarla"} & tokens):
        return "contraentrega"
    if "pse" in tokens or "transferencia" in tokens or "tarjeta" in tokens:
        return "pago_linea"
    if ({"pago", "pagar"} & tokens) and ({"linea", "línea", "online"} & tokens):
        return "pago_linea"
    # Pedir un link o los datos de la cuenta es pedir pago a distancia.
    if ("link" in tokens or "consignacion" in tokens or "consignación" in tokens) and (
            {"pago", "pagar", "pagamos", "paga"} & tokens or "link" in tokens):
        return "pago_linea"
    # "pagamos cuando pasen/lleguen/recojan/entreguen" = al momento de la recogida.
    paga = {"pagamos", "pagar", "pago", "paga", "pagarles", "cancelamos"} & tokens
    al_recibir = {"pasen", "pasan", "lleguen", "llegan", "recojan", "recogen",
                  "entreguen", "recibir", "recibirlo", "vengan", "venga"} & tokens
    if paga and al_recibir:
        return "contraentrega"
    return None


_SOCIAL_PHRASES = (
    "como vas", "como estas", "como andas", "como te va", "como va",
    "que mas", "que tal", "todo bien", "que cuentas", "que hubo",
    "como amaneciste", "como sigues", "como va todo",
)


_OFF_TOPIC_SMALL_TALK_TOKENS = frozenset({
    "hola", "holi", "ola", "buenas", "buenos", "buen", "dia", "dias",
    "tarde", "tardes", "noche", "noches", "hey", "hi", "saludos",
    "como", "estas", "va", "vas", "andas", "anda", "todo", "bien",
    "que", "tal", "mas", "gracias", "jaja", "jeje", "jajaja", "uy",
    # conectores y muletillas que acompañan al small talk
    "y", "ah", "ahh", "ay", "oye", "pero", "pues", "eh", "este",
    "ok", "okay", "che", "ja", "bueno",
})


_ORDER_QUERY_TOKENS = frozenset({"orden", "ordenes", "órdenes", "pedido", "pedidos", "solicitud", "radicado"})


_ORDER_CREATE_TOKENS = frozenset({
    "crear", "crea", "nueva", "nuevo", "otra", "otro", "hacer", "haz", "programar",
    "generar", "agendar", "necesito", "quiero", "registrar",
})


_ORDER_NUMBER_TOKENS = frozenset({
    "numero", "número", "num", "codigo", "código", "rastreo", "rastrear",
    "seguimiento", "radicado", "referencia",
})


_FINAL_USER_PHRASES = (
    "cliente final", "persona particular", "soy particular", "soy dueño",
    "soy dueno", "soy el dueño", "soy el dueno", "soy propietario",
    "soy el propietario", "dueño de mascota", "dueno de mascota",
    "tutor de mascota", "mi mascota", "mi perro", "mi gato",
    "no soy veterinario", "no soy veterinaria", "no soy de una veterinaria",
    "no tengo veterinaria",
)


_AREA_OPTION_QUESTION_TOKENS = frozenset({
    "que", "qué", "cuales", "cuáles", "cual", "cuál", "tienen", "tienes", "tiene",
    "hay", "ofrecen", "ofreces", "manejan", "maneja", "disponibles", "disponible",
    "opciones", "tipos", "tipo", "muestrame", "muéstrame", "muestra", "lista",
})


_ANALYSIS_TOKENS = frozenset({"analisis", "análisis", "examen", "examenes", "exámenes", "perfil", "prueba", "muestra", "muestras"})


_FOLLOWUP_NEW_TOKENS = frozenset({"otra", "otras", "otro", "otros", "nueva", "nuevo", "nuevas", "nuevos"})


_FOLLOWUP_CREATE_TOKENS = frozenset({
    "crear", "crea", "hacer", "haz", "programar", "agendar", "generar", "necesito", "quiero",
})


_FOLLOWUP_OBJECT_TOKENS = frozenset({
    "orden", "ordenes", "órdenes", "servicio", "pedido", "pedidos", "muestra",
    "muestras", "ruta", "recogida", "retiro", "paciente", "animal", "analisis", "análisis",
})



def _looks_off_topic_smalltalk(text: str) -> bool:
    # El tokenizador conserva acentos; se normalizan para comparar.
    norm = " ".join(t.translate(_ACCENT_TRANSLATION) for t in _tokenize(text))
    if not norm:
        return False
    if any(phrase in norm for phrase in _SOCIAL_PHRASES):
        return True
    return set(norm.split()) <= _OFF_TOPIC_SMALL_TALK_TOKENS



def _is_order_number_query(text: str) -> bool:
    tokens = set(_tokenize(text))
    if tokens & _ORDER_CREATE_TOKENS:
        return False
    # "sigo con la SIGUIENTE orden" es avanzar, no preguntar un número (Ronda 3: el atajo
    # respondía el nº de la orden anterior en medio de un multi-orden).
    if tokens & {"siguiente", "sigo", "seguimos", "continuo", "continúo"}:
        return False
    # "código 1101" nombra un ANÁLISIS del catálogo (los códigos tienen 3-4 cifras), no
    # pregunta el número de una orden ya creada.
    if re.search(r"\b(?:codigo|código|cod)s?\.?\s*:?\s*\d{3,4}\b", (text or "").lower()):
        return False
    return bool(tokens & _ORDER_QUERY_TOKENS) and bool(tokens & _ORDER_NUMBER_TOKENS)



def _is_final_user_text(text: str) -> bool:
    normalized = " ".join(_tokenize(text))
    return any(phrase in normalized for phrase in _FINAL_USER_PHRASES)



def _asks_for_area_options(text: str) -> bool:
    """¿El mensaje es una pregunta abierta por opciones de un área ('qué análisis de
    orina tienen', 'qué tipos de sangre manejan'), en vez de nombrar un test exacto?"""
    tokens = set(_tokenize(text))
    return bool(tokens & _AREA_OPTION_QUESTION_TOKENS) or "?" in (text or "")



def _followup_wants_new_analysis(text: str) -> bool:
    """En el mismo mensaje de 'otra orden', ¿el cliente pidió CAMBIAR el análisis?
    Ej.: 'otra orden con los mismos datos pero cambiale el análisis a glucosa'. Exige
    nombrar el análisis/examen/perfil junto a una señal de cambio para no confundir con
    'otra orden para otro paciente' (que mantiene el análisis anterior)."""
    tokens = set(_tokenize(text))
    if not (tokens & _ANALYSIS_TOKENS):
        return False
    if re.search(r"(?i)\bcambi", text or ""):
        return True
    return bool(tokens & {"otro", "otra", "nuevo", "nueva", "distinto", "distinta", "diferente"})



def _replaces_offered_analysis(text: str, inherited_code: str | None) -> bool:
    """En la reoferta de datos estables ('Mantengo estos datos… ¿Confirmas o quieres cambiar
    alguno?'), ¿el mensaje REEMPLAZA el análisis heredado de la orden anterior?

    Nació de 'analisis quiero el 653' (prueba en vivo 2026-08-14): ningún detector de verbos
    disparó (`_wants_to_change_analysis` exige 'cambi-' u 'otro/nuevo'), el pipeline fijó el
    653 como perfil base y los AGREGADOS heredados de la orden anterior sobrevivieron — la
    orden salió $24.000 más cara con análisis que el cliente nunca pidió en ella.

    Decide con lo que el sistema YA sabe, no con verbos: el campo al que apunta el mensaje
    (`_detect_correction_field`) o un CÓDIGO de catálogo distinto del heredado. Un ajuste
    parcial ('el mismo pero sin la glucosa') queda afuera: eso personaliza el perfil ofrecido,
    no lo reemplaza."""
    if _wants_partial_analysis_change(text):
        return False
    if _detect_correction_field(text) == "exam_type":
        return True
    heredado = str(inherited_code or "")
    return any(c != heredado for c in _profile_codes_from_text(text))


def _removes_the_additions(text: str) -> bool:
    """¿El mensaje pide quitar 'los agregados' como conjunto?

    'Agregados' es el RÓTULO que el propio bot imprime en el resumen de la orden
    ('- Agregados: 1405-Sodio…'): el cliente lo cita tal cual lo leyó. No es una lista
    temática — es el vocabulario del bot, y el llamador además exige que la orden tenga
    agregados de verdad (estado), así que solo dispara cuando hay algo que quitar.

    Caso real (2026-08-14): 'en esta orden no quiero los agregados' caía en la repregunta
    genérica '¿Qué dato quieres corregir?'. Quitar UN análisis puntual ('quitale el sodio')
    no pasa por acá: eso ya lo maneja el ajuste de análisis en confirmación."""
    if not re.search(r"(?i)\bagregad", text or ""):
        return False
    tokens = set(_tokenize(text))
    return bool(tokens & {"no", "sin", "quita", "quitar", "quitale", "quítale", "saca",
                          "sacar", "sacame", "sácame", "elimina", "eliminar", "borra"})


_ORDEN_OBJECT_TOKENS = frozenset({
    "orden", "ordenes", "órdenes", "paciente", "pacientes", "pedido", "pedidos",
    "animal", "mascota", "perro", "perra", "gato", "gata",
})


def _wants_new_order_strict(text: str) -> bool:
    """Variante ACOTADA de `_explicitly_wants_another_order` para contextos donde el tema por
    defecto es el ANÁLISIS (el carril de agregado, la frontera de orden). La amplia cuenta
    "analisis" como objeto, y "quiero agregarle un analisis mas" disparaba como si fuera otra
    ORDEN (QA de estrés 2026-08-15). Acá el objeto tiene que ser la orden/el paciente."""
    if not _explicitly_wants_another_order(text):
        return False
    return bool(set(_tokenize(text)) & _ORDEN_OBJECT_TOKENS)


def _wants_another_service_order(text: str) -> bool:
    return _explicitly_wants_another_order(text)



def _explicitly_wants_another_order(text: str) -> bool:
    """Pide explícitamente OTRA orden. A diferencia de `_wants_another_service_order`,
    NO se conforma con un 'sí' suelto: se usa fuera de la fase terminal (cuando no venimos
    de la pregunta '¿necesitas otra orden?'), por eso exige señal fuerte de nueva orden."""
    words = set(_tokenize(text))
    if not words or "no" in words:
        return False
    if words & _FOLLOWUP_NEW_TOKENS and (words & _FOLLOWUP_OBJECT_TOKENS or len(words) <= 3):
        return True
    return bool(words & _FOLLOWUP_CREATE_TOKENS) and bool(words & _FOLLOWUP_OBJECT_TOKENS)



def _reply_asks_for_route_field(reply: str, field: str) -> bool:
    text = " ".join(_tokenize(reply))
    if field == "requesting_doctor":
        return "medico solicitante" in text or "médico solicitante" in text
    if field == "exam_type":
        return (
            "que tipo de analisis" in text or "qué tipo de análisis" in text
            or "analisis o perfil exacto" in text or "análisis o perfil exacto" in text
            or "cual van a enviar" in text or "cuál van a enviar" in text
            or "perfil desean" in text
        )
    if field == "patient_name":
        return "nombre del paciente" in text
    if field == "species":
        return "canino felino" in text or "otra especie" in text
    if field == "breed":
        return "raza del paciente" in text
    if field == "sex":
        return "macho o hembra" in text
    if field == "patient_age":
        return "edad tiene" in text
    if field == "owner_name":
        return "nombre del propietario" in text
    if field == "observations":
        return "observacion" in text or "observación" in text or "observaciones" in text
    if field == "payment_method":
        return "contraentrega" in text and ("linea" in text or "línea" in text)
    return False

