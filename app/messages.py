"""Mensajes de texto fijos del agente (respuestas, prompts y preguntas).

Extraídos de `agent.py` (Paso 3.4 del refactor: partir el monolito). Son cadenas puras,
sin lógica ni dependencias — la fuente única de los textos que el agente devuelve tal cual.
El tono (humano, colombiano, cercano) se mantiene idéntico al original.
"""

# ── Bienvenida / identificación de cliente ──────────────────────────────────────
CLIENT_LOOKUP_PROGRESS_MESSAGE = "Permíteme un momentico mientras reviso nuestros registros 🔍"

WELCOME_MESSAGE = (
    "Hola! Buen día, me alegra que nos visites.\n"
    "Bienvenido a A3 laboratorio clínico veterinario 🧪 🧫\n"
    "Atendemos clínicas y profesionales veterinarios registrados.\n\n"
    "¿Con qué te ayudamos hoy? Respóndeme con el número:\n"
    "1. Programar análisis y recogida de muestra\n"
    "2. Consultar resultados\n"
    "3. Pagos\n"
    "4. Otro"
)

FINAL_USER_MESSAGE = (
    "A3 trabaja directamente con clínicas y profesionales veterinarios registrados. "
    "Para procesar muestras o programar recogidas, por favor gestiona la solicitud a través de tu veterinaria."
)

CLIENT_IDENTIFICATION_REQUIRED_MESSAGE = (
    "Para gestionar pedidos, A3 atiende clínicas y profesionales veterinarios registrados. "
    "Para continuar necesito una de estas dos opciones: 1) el NIT, o 2) el nombre exacto de la veterinaria o médico veterinario."
)

# A3 pidió (llamada 3) que al escalar se diga explícitamente que se asigna un asesor. Antes
# cada camino tenía su propia frase ("te comunico con ellos", "con una persona del equipo",
# "con el equipo correspondiente"), así que el cliente no sabía si quedaba alguien a cargo.
ADVISOR_ASSIGNMENT_LINE = "Te asignaremos un asesor que se comunicará contigo para ayudarte."

CLIENT_NOT_FOUND_MESSAGE = (
    "En este momento no encuentro el cliente registrado en nuestra base de datos.\n"
    "Para poder coordinar el retiro de muestras, primero necesitamos realizar el registro del cliente.\n"
    f"{ADVISOR_ASSIGNMENT_LINE}"
)

CLIENT_NEW_REGISTRATION_MESSAGE = (
    "Como aún no estás registrado, el alta la debe hacer atención al cliente. "
    f"{ADVISOR_ASSIGNMENT_LINE}"
)

CLIENT_SEARCH_FAILED_MESSAGE = (
    "No encuentro ningún cliente registrado con ese dato.\n"
    "¿Eres cliente nuevo?"
)

CLIENT_RETRY_NOT_FOUND_MESSAGE = (
    "Tampoco encuentro un cliente registrado con ese dato. "
    "¿Me confirmas si es cliente nuevo para ponerte en contacto con atención al cliente?"
)

CLIENT_IDENTIFIER_RETRY_MESSAGE = (
    "Para ubicar el cliente registrado, compárteme el NIT o el nombre exacto de la veterinaria o médico veterinario."
)

POST_TERMINAL_GREETING_REPLY = "Hola. ¿En qué podemos ayudarte hoy?"

# ── Opciones del menú (resultados / reconsiderar) ───────────────────────────────
# Opción 2 del menú (consultar resultados). Todavía no se resuelve por este medio:
# la consulta de estados se habilitará cuando se integre la plataforma.
RESULTS_PENDING_MESSAGE = (
    "Por ahora la consulta de resultados y estados de muestra todavía no está disponible por este medio. "
    "La estamos integrando con nuestra plataforma y muy pronto vas a poder consultarlos por aquí 🙌.\n"
    "Si necesitas un resultado puntual, escríbenos y con gusto te comunicamos con el equipo. "
    "¿Te ayudo con algo más, como programar una recogida?"
)

# El usuario se confundió de opción o quiere volver a elegir: se reofrece el menú.
OPTION_RECONSIDER_MESSAGE = (
    "Tranquilo, sin problema 🙂. ¿Con qué te ayudo? Respóndeme con el número:\n"
    "1. Programar análisis y recogida de muestra\n"
    "2. Consultar resultados\n"
    "3. Pagos\n"
    "4. Otro"
)

# ── Número de orden ─────────────────────────────────────────────────────────────
ORDER_NUMBER_NEEDS_CLIENT_MESSAGE = (
    "Para darte el número de tu orden necesito identificarte primero. "
    "¿Me compartes el NIT o el nombre de la veterinaria o médico veterinario?"
)
ORDER_NUMBER_NOT_FOUND_MESSAGE = (
    "Todavía no encuentro una orden registrada a tu nombre. ¿Quieres que programemos una recogida?"
)

# ── Cierre / despedida ──────────────────────────────────────────────────────────
FAREWELL_REPLY = (
    "Con mucho gusto, para eso estamos! "
    "Si en algún momento necesitas algo más, acá seguimos. ¡Hasta luego, cuídate!"
)

# Cierre cordial al final de una orden registrada: ofrecer otra orden o terminar.
CLOSING_PROMPT = (
    "Si necesitas crear otra orden para otro paciente, escríbeme: otra orden. "
    "Si eso es todo, quedamos atentos. 🙂"
)

# Cierre cuando la orden va dentro de un PEDIDO abierto (decisión 011): el pedido admite más
# órdenes y la forma de pago se pregunta una sola vez, al cerrarlo, para toda la factura.
PEDIDO_CLOSING_PROMPT = (
    "¿Necesitas cargar otra orden para otro paciente? Escríbeme: otra orden. "
    "Si eso es todo, seguimos con la forma de pago y cerramos el pedido."
)

# Último turno antes de cerrar: observación del PEDIDO (opcional) + forma de pago. Van
# juntas a propósito — A3 pidió poder dejar una observación general (reunión 28/07), y
# preguntarla en un turno aparte le agregaba un paso a quien no tiene nada que observar.
PEDIDO_CLOSING_QUESTION = (
    "Listo. ¿Alguna observación para el pedido? Y decime cómo prefieres el pago: "
    "contraentrega con el motorizado o pago en línea."
)

# ── Pago ────────────────────────────────────────────────────────────────────────
PAYMENT_METHOD_QUESTION = "Antes de cerrar, ¿cómo prefieres el pago: contraentrega con el motorizado o pago en línea?"
PAYMENT_ONLINE_HANDOFF_MESSAGE = (
    "Tu orden quedó registrada. Como elegiste pago en línea, nuestro equipo de contabilidad "
    "te contactará en breve para enviarte el link y procesar el pago. "
    "La recogida de la muestra sigue programada con normalidad."
)

# ── Armado de orden (análisis, motorizado, edad, corrección) ────────────────────
# Oferta de agregar más análisis antes del pago. Se repite tras cada agregado hasta que el
# cliente decida seguir (decline o dé el método de pago). El "si ya está, seguimos con el
# pago" deja la salida clara para no caer en bucle.
EXTRA_ANALYSIS_OFFER = (
    "¿Quieres agregar otro análisis o perfil, o personalizar este? "
    "Si ya está, seguimos con el pago."
)

# Con la jerarquía de pedidos (decisión 011) después de la orden NO viene el pago, sino el
# resumen de ESTA orden y la oferta de cargar otra: prometer el pago acá le miente al cliente
# sobre el paso siguiente. La salida sigue siendo igual de explícita, que es lo que evita el
# bucle. Cuál de las dos se usa lo decide `flow.extra_analysis_offer()`.
EXTRA_ANALYSIS_OFFER_PEDIDO = (
    "¿Quieres agregar otro análisis o perfil, o personalizar este? "
    "Si ya está, cerramos esta orden."
)

# ERR-093: el cliente nombró el pago en una frase ambigua ("No seguimos con el pago, te
# estoy diciendo" — ¿"no, sigamos" o "no sigamos"?). Ante la duda se pregunta en vez de
# adivinar; adivinar mal re-mostraba el menú de perfiles y tiraba el avance de la orden.
EXTRA_ANALYSIS_AMBIGUOUS_QUESTION = (
    "Perdona, no te entendí bien: ¿avanzamos con el pago o quieres agregar otro análisis?"
)

NO_COURIER_HANDOFF_MESSAGE = (
    "Recibimos la orden. En este momento no veo un motorizado asignado al cliente, "
    "así que operaciones la va a coordinar manualmente."
)

AGE_QUESTION = "¿Qué edad tiene el paciente? Indícame número y unidad, por ejemplo: 5 años, 3 meses o 45 días."

# Confirmación editable previa al registro (Sección 7.1 del spec).
CORRECTION_PROMPT = (
    "Claro. ¿Qué dato quieres corregir? "
    "(dirección, médico, paciente, especie, raza, sexo, edad, propietario, observaciones, análisis o forma de pago)"
)
