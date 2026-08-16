"""Enforcer del paso de CONFIRMACIÓN de la orden (Paso 3.4a — movido TAL CUAL de agent.py).

Muestra el resumen editable, maneja los ajustes de análisis durante la confirmación y
ejecuta el cierre determinístico cuando el cliente confirma con la orden completa."""
from app import state
from app.text import as_text_items as _as_text_items, tokenize as _tokenize
from app.flow import (
    base_route_response as _base_route_response,
    missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
)
from app.detectors import (
    _confirms_order_now,
    _detect_correction_field,
    _is_bare_confirmation,
    _is_order_confirmation,
    _named_analysis_terms,
    _payment_method_from_text,
    _profile_codes_from_text,
    _wants_partial_analysis_change,
)
from app.menus import _store_selected_profile_fields
from app.laterales import _operational_side_question_answer
from app.orders import (
    _add_tests_to_order,
    _area_options_for_profile_addition,
    _price_answer_for_order,
    _route_closure_summary,
    _route_confirmation_summary,
)
from app.messages import CONFIRMATION_AMBIGUOUS_QUESTION, PAYMENT_ONLINE_HANDOFF_MESSAGE
from app.services import db

CONFIRMATION_PHASE = state.Phase.CONFIRMACION.value


def _add_profile_in_confirmation(fields: dict, user_message: str) -> dict | None:
    """ERR-080 (segunda capa): un código de PERFIL ("1331") no resuelve como análisis
    (`get_tests_by_codes_or_names` no ve perfiles), así que agregar un perfil durante la
    confirmación repreguntaba para siempre (chat 10). Resuelve el perfil por código primero
    (determinístico) y por nombre como fallback; si hay perfil base lo suma como perfil
    adicional (mecanismo de ERR-077, el resumen ya lo muestra y suma), si no, lo fija de base."""
    species = fields.get("species")
    profile = None
    codes = _profile_codes_from_text(user_message)
    if codes:
        try:
            matches = db.get_catalog_profiles_by_codes(codes[:1], species)
        except Exception:
            matches = []
        profile = matches[0] if matches else None
    if not profile:
        try:
            profile = db.find_catalog_profile(user_message, species)
        except Exception:
            profile = None
    if not profile:
        return None

    code = str(profile.get("code"))
    if fields.get("_selected_profile_code"):
        extras = list(fields.get("_extra_profiles") or [])
        already = code == str(fields.get("_selected_profile_code")) or any(
            str(p.get("code")) == code for p in extras
        )
        if not already:
            extras.append({"code": profile.get("code"), "name": profile.get("name"),
                           "price": int(profile.get("price") or 0)})
            fields["_extra_profiles"] = extras
    else:
        _store_selected_profile_fields(fields, profile)

    fields.pop("_awaiting_additional_test", None)
    fields.pop("_correction_pending", None)
    # Si se muestra el resumen, la oferta de agregar YA no está en pantalla: su marca no puede
    # quedar viva o el "Sí" siguiente cae en ese carril en vez de registrar la orden.
    fields.pop("_offering_extra_analysis", None)
    summary = _route_confirmation_summary(fields)
    response = _base_route_response(
        summary or f"Listo, agrego {profile.get('code')} {profile.get('name')}.", fields
    )
    response["phase"] = CONFIRMATION_PHASE
    return response


def _confirmation_analysis_adjustment(session: dict, fields: dict, user_message: str, signal: str | None) -> dict | None:
    pending_action = fields.get("_awaiting_additional_test")
    # SEÑAL-PRIMERO. Este carril entraba solo por lista de tokens, y la lista tiene agujeros:
    # medido, "agregale un coprológico" entra pero "agregame una glucosa" NO. Ahora que el
    # resumen ofrece explícitamente agregar otro análisis, la respuesta llega en cualquier
    # fraseo, así que la lectura del modelo manda y el detector queda como red.
    #
    # Pero la señal SOLA no alcanza: "quiero cambiar el médico" también es `correction`, y sin
    # acotar, este carril se la tragaba y respondía "¿Qué análisis quieres agregar?" — dejando
    # al cliente sin poder corregir ningún otro dato. Por eso, cuando se entra por señal, la
    # corrección no puede apuntar a OTRO campo de la orden.
    # Un "sí / dale / correcto" PELADO en la confirmación es CONFIRMAR, nunca "sí, quiero
    # agregar". Va primero porque el filtro de abajo lo dejaba pasar (medido:
    # `_detect_correction_field("Si")` es None) y la orden no se registraba nunca.
    #
    # "Pelado" se mide con `_is_bare_confirmation` —¿queda algo si le sacamos el sí?— y NO con
    # "¿pide además un ajuste?": esa segunda forma depende de reconocer el verbo, y un typo la
    # desarma. Caso real (2026-08-14): "si quiero agreagar sodio y potasio" pasaba por
    # confirmación pelada, el carril cedía, y como nadie resolvía nada contra el catálogo el
    # modelo contestó "Perfecto, agrego Sodio y Potasio" con `selected_tests` VACÍO. La orden
    # habría salido sin los análisis pedidos y facturada de menos.
    if not pending_action and _is_bare_confirmation(user_message):
        return None

    # Un método de pago como respuesta al resumen NO es un pedido de análisis (Ronda 3,
    # nit_con_formatos): "¿Confirmas estos datos?" → "Contraentrega." caía acá, el catálogo
    # no reconocía nada y el carril respondía "¿Qué análisis quieres agregar?" en bucle —
    # la orden no se registraba nunca. Cede al cierre determinístico, que lo lee como
    # confirmación con el pago adelantado.
    if (_payment_method_from_text(user_message)
            and not _profile_codes_from_text(user_message)
            and not _wants_partial_analysis_change(user_message)):
        return None

    if not pending_action:
        # Habla de OTRO dato de la orden ("cambiá el médico"): no es de este carril.
        campo = _detect_correction_field(user_message)
        if campo and campo != "exam_type":
            return None
        # Cualquier otra cosa PUEDE ser un pedido de análisis, y quien lo decide es el
        # CATÁLOGO —abajo, resolviendo el mensaje contra la base—, no un detector de verbos.
        #
        # Antes se exigía acá que un detector reconociera la intención ("agregale…") o que el
        # modelo marcara `correction`. Los dos fallan seguido: "añadime sodio y potasio" no
        # matchea la lista, y un mensaje que arranca con "dale" el modelo lo marca `affirm`.
        # Cuando fallaban los dos, este carril devolvía None y el cierre determinístico de
        # abajo REGISTRABA la orden sin los análisis pedidos (medido en vivo: 1 de 6 fraseos
        # se guardaba bien). Dejar que decida el catálogo saca del medio a los verbos.

    tokens = set(_tokenize(user_message))

    # NEGACIÓN antes que nada: "no, ninguno más", "no quiero agregar otro análisis". Se
    # evaluaba recién después de buscar análisis en el mensaje, así que una negación que
    # mencionaba la palabra "análisis" volvía a caer en el carril y repreguntaba en bucle
    # (prueba en vivo 2026-08-14). Al salir hay que APAGAR la espera: si queda encendida, el
    # turno siguiente vuelve a entrar por `pending_action` sin mirar nada más.
    # Se mira si nombró un CÓDIGO ("no, mejor el 1101" sí es un ajuste) y no los términos
    # sueltos: `_named_analysis_terms` devuelve palabras de la frase —"análisis" entre ellas—,
    # así que una negación que menciona la palabra volvía a caer en el carril.
    # `farewell` ("ya está, gracias") con la espera encendida es la MISMA salida que la
    # negación: el cliente da por terminado, no va a nombrar un análisis (Ronda 3: el carril
    # repreguntaba "¿Qué análisis quieres agregar?" sin salida posible).
    # Pero una CONFIRMACIÓN explícita ("Sí, confirmo esos datos") nunca es esta salida,
    # aunque el modelo la marque farewell (Ronda 5: caía en "no me quedó claro" y el
    # cliente terminó cancelando el pedido entero).
    if ((signal in ("negate", "farewell") or tokens & {"nada", "ninguno", "ninguna", "ningun", "ningún"})
            and not _is_order_confirmation(user_message)):
        if not _profile_codes_from_text(user_message):
            fields.pop("_awaiting_additional_test", None)
            fields.pop("_offering_extra_analysis", None)
            # Dijo que NO, pero no dijo a qué: "no agrego nada más" y "no confirmo" llevan a
            # lados opuestos. Se pregunta en vez de suponer.
            response = _base_route_response(CONFIRMATION_AMBIGUOUS_QUESTION, fields)
            response["phase"] = CONFIRMATION_PHASE
            return response
    action = pending_action or "add"
    if tokens & {"quitar", "quita", "quitale", "quítale", "sacar", "saca", "sin", "menos", "retirar", "remover"}:
        action = "remove"

    # Al AGREGAR, la mención de un ÁREA ('agregale un análisis de orina') va al menú de
    # esa área ANTES que cualquier match difuso por nombre ('orina' → Cortisol; chat 4).
    if action == "add":
        area_response = _area_options_for_profile_addition(fields, user_message, require_question=False)
        if area_response:
            area_response["phase"] = CONFIRMATION_PHASE
            return area_response

    rows = (db.get_tests_by_codes_or_names([user_message])
            or db.get_tests_by_codes_or_names(_named_analysis_terms(user_message)))
    if not rows:
        if signal == "negate" or tokens & {"nada", "ninguno", "ninguna"}:
            return None
        # El catálogo no reconoció nada Y el cliente estaba confirmando ("me sirve así,
        # avancemos con eso"): es una confirmación con más palabras, no un pedido de análisis.
        # Se cede para que el cierre determinístico registre la orden — sin esta salida,
        # ampliar la entrada del carril convertía cualquier "dale" largo en "¿qué análisis
        # quieres agregar?".
        # Pero si ADEMÁS pide un ajuste ("sí, pero agregale otro análisis"), no se cede: ahí
        # corresponde repreguntar cuál, no cerrar la orden. La señal del modelo cubre los
        # fraseos que no están en ninguna lista.
        confirma = _is_order_confirmation(user_message) or signal == "affirm"
        if (not pending_action and confirma
                and not _wants_partial_analysis_change(user_message)):
            return None
        # No nombró un test exacto: si pregunta por un ÁREA ('qué análisis de orina
        # tienen'), ofrecer las opciones de esa área para agregar, en vez de repreguntar
        # a ciegas y dejarlo trabado.
        area_response = _area_options_for_profile_addition(fields, user_message)
        if area_response:
            area_response["phase"] = CONFIRMATION_PHASE
            return area_response
        # ERR-080: si lo que nombró es un PERFIL del catálogo ("1331"), agregarlo acá;
        # sin esta rama el mensaje no resolvía nunca y la repregunta era un bucle sin salida.
        if action == "add":
            profile_response = _add_profile_in_confirmation(fields, user_message)
            if profile_response:
                return profile_response
        fields["_awaiting_additional_test"] = action
        ask = "¿Qué análisis quieres quitar?" if action == "remove" else "¿Qué análisis quieres agregar?"
        response = _base_route_response(f"Claro. {ask}", fields)
        response["phase"] = CONFIRMATION_PHASE
        return response

    _add_tests_to_order(fields, rows, action)
    # El acuse no puede adelantarse al ESTADO. Se verifica que los análisis quedaron de verdad
    # en la orden antes de decir que se agregaron: el 2026-08-14 el bot respondió "Perfecto,
    # agrego Sodio y Potasio" con `selected_tests` vacío, y la orden habría salido sin ellos y
    # facturada de menos — un error que el cliente no tiene forma de detectar.
    if action == "add":
        quedaron = set(_as_text_items(fields.get("selected_tests")))
        faltan = [r for r in rows if str(r.get("code") or r.get("name")) not in quedaron]
        if faltan:
            nombres = ", ".join(str(r.get("name") or r.get("code")) for r in faltan)
            fields["_awaiting_additional_test"] = "add"
            response = _base_route_response(
                f"Perdona, no pude agregar {nombres} a la orden. "
                f"¿Me confirmas el nombre o el código del análisis que necesitas?", fields)
            response["phase"] = CONFIRMATION_PHASE
            return response
    fields.pop("_awaiting_additional_test", None)
    fields.pop("_correction_pending", None)
    # Igual que en `_add_profile_in_confirmation`: con el resumen en pantalla, la marca de la
    # oferta no puede sobrevivir. Este era EL bug del 2026-08-14 — se agregaban Sodio y
    # Potasio, se mostraba el resumen, y el "Si" del turno siguiente lo agarraba
    # `_handle_extra_analysis_answer` como "sí, quiero agregar otro".
    fields.pop("_offering_extra_analysis", None)

    summary = _route_confirmation_summary(fields)
    response = _base_route_response(summary or _missing_route_field_question(_missing_route_field(session, fields)), fields)
    response["phase"] = CONFIRMATION_PHASE
    return response


def _enforce_confirmation_step(session: dict, ai_response: dict, fields: dict, previous_phase: str, user_message: str) -> dict:
    """Antes de registrar una orden completa, mostrar el resumen y pedir
    confirmación (Sí / Corregir). Solo deja cerrar cuando el usuario ya confirmó."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    if ai_response.get("message_mode") == "cancellation":
        return ai_response
    # La orden YA está registrada y tiene su número: no hay nada que confirmar. Sin este
    # guard, cualquier turno posterior con los campos completos volvía a mostrar el resumen
    # y el "Quedó registrado" — el cliente veía su orden cerrarse dos veces. Se limpia al
    # empezar otra orden (`_begin_followup_order`), así que el multi-orden no se ve afectado.
    if fields.get("_order_registered"):
        return ai_response

    if previous_phase == CONFIRMATION_PHASE:
        adjusted = _confirmation_analysis_adjustment(
            session, fields, user_message, ai_response.get("user_intent_signal")
        )
        if adjusted:
            return adjusted

    # Cierre DETERMINÍSTICO: si venimos del resumen (fase_4) y el usuario confirma
    # con la orden completa, cerrar SIEMPRE acá, sin depender de que el modelo emita
    # la fase terminal. Antes el cierre quedaba a criterio del AI y, si no devolvía
    # fase_6_cierre, la orden se quedaba trabada en la confirmación sin registrarse.
    # Pago como confirmación implícita (Ronda 3): al resumen "¿Confirmas estos datos?" el
    # cliente responde "Contraentrega." — está confirmando Y adelantando el pago del pedido.
    # Solo si el mensaje no trae NINGUNA otra intención (las señales de veto mandan).
    pago_adelantado = (
        previous_phase == CONFIRMATION_PHASE
        and _payment_method_from_text(user_message)
        and ai_response.get("user_intent_signal") not in {
            "negate", "correction", "change_client", "another_order", "cancel"}
        and not _detect_correction_field(user_message)
    )
    if (previous_phase == CONFIRMATION_PHASE
            and (_confirms_order_now(ai_response, user_message) or pago_adelantado)
            and not _missing_route_field(session, fields)):
        if pago_adelantado and not fields.get("payment_method"):
            fields["payment_method"] = _payment_method_from_text(user_message)
        operational_answer = _operational_side_question_answer(user_message)
        # Si confirmó y a la vez preguntó el precio, respondemos el valor REAL del análisis
        # ya elegido (no la respuesta genérica) antes del "Quedó registrado".
        price_answer = _price_answer_for_order(fields, user_message)
        if fields.get("payment_method") == "pago_linea":
            ai_response["phase"] = "fase_7_escalado"
            ai_response["requires_handoff"] = True
            ai_response["handoff_area"] = "contabilidad"
            ai_response["reply"] = PAYMENT_ONLINE_HANDOFF_MESSAGE
        else:
            ai_response["phase"] = "fase_6_cierre"
            ai_response["requires_handoff"] = False
            ai_response["handoff_area"] = None
            summary = _route_closure_summary(fields)
            if summary:
                ai_response["reply"] = summary
        prefix = price_answer or operational_answer
        if prefix:
            ai_response["reply"] = f"{prefix}\n\n{ai_response['reply']}"
        fields.pop("_correction_pending", None)
        ai_response["service_area"] = "route_scheduling"
        ai_response["message_mode"] = "flow_progress"
        return ai_response

    if _missing_route_field(session, fields):
        return ai_response
    # Ya estábamos en confirmación: el cierre lo maneja el bloque determinístico de
    # arriba y las correcciones su propio handler; cualquier otra respuesta la deja
    # pasar al modelo. No re-disparamos el resumen acá.
    if previous_phase == CONFIRMATION_PHASE:
        # Excepción: tras una corrección, cuando el dato nuevo llegó y la orden quedó
        # completa, re-mostrar el resumen para que el cliente vea el cambio antes del "sí".
        if fields.get("_correction_pending") and not _is_order_confirmation(user_message):
            fields.pop("_correction_pending", None)
            summary = _route_confirmation_summary(fields)
            if summary:
                ai_response["reply"] = summary
                ai_response["phase"] = CONFIRMATION_PHASE
                ai_response["requires_handoff"] = False
                ai_response["handoff_area"] = None
                ai_response["message_mode"] = "flow_progress"
                ai_response["captured_fields"] = fields
        return ai_response

    # Orden completa por primera vez: mostrar SIEMPRE el resumen determinístico, sin
    # depender de que el modelo haya devuelto una fase terminal. Antes, si el modelo
    # improvisaba la confirmación en fase_4 (no terminal), el sistema no tomaba control
    # y el bot daba vueltas con respuestas raras en vez de un resumen claro.
    summary = _route_confirmation_summary(fields)
    if not summary:
        return ai_response
    # ERR-080: el resumen supersede cualquier "¿quieres agregar?" que haya quedado abierto
    # en fases previas. Si el flag sobrevive, el "Sí" del cliente se intenta resolver como
    # análisis, falla, y el cierre determinístico nunca corre (chat 10: orden nunca registrada).
    fields.pop("_awaiting_additional_test", None)
    # El flag HERMANO, por la misma razón. Sin pedidos nunca coincidía con el resumen: la
    # orden no estaba completa (faltaba el pago), así que la confirmación no se disparaba en
    # ese momento. Con pedidos (decisión 011) los dos pasos caen en el MISMO turno, y al
    # sobrevivir la marca el "Sí" del cliente se leía como "sí, quiero agregar otro análisis":
    # el bot respondía "¿Qué análisis quieres agregar?" y la orden no se registraba nunca.
    fields.pop("_offering_extra_analysis", None)
    operational_answer = _operational_side_question_answer(user_message)
    if operational_answer:
        summary = f"{operational_answer}\n\n{summary}"
    ai_response["reply"] = summary
    ai_response["phase"] = CONFIRMATION_PHASE
    ai_response["requires_handoff"] = False
    ai_response["handoff_area"] = None
    ai_response["message_mode"] = "flow_progress"
    return ai_response
