RESPONSE_SCHEMA = {
    "name": "agent_response",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reply": {"type": "string"},
            "intent": {
                "type": "string",
                "enum": ["route_scheduling", "results", "accounting", "new_client", "unknown"],
            },
            "phase": {
                "type": "string",
                "enum": [
                    "fase_0_bienvenida",
                    "fase_1_clasificacion",
                    "fase_2_recogida_datos",
                    "fase_3_validacion",
                    "fase_4_confirmacion",
                    "fase_5_ejecucion",
                    "fase_6_cierre",
                    "fase_7_escalado",
                ],
            },
            "service_area": {
                "type": "string",
                "enum": ["route_scheduling", "accounting", "results", "new_client", "unknown"],
            },
            "captured_fields": {
                "type": "object",
                "properties": {
                    "clinic_name":    {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "tax_id":         {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "pickup_address": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "exam_type":      {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "patient_name":   {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "species":        {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "requesting_doctor": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "patient_age":    {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "owner_name":     {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "breed":          {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "sex":            {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "observations":   {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "payment_method": {
                        "anyOf": [
                            {"type": "string", "enum": ["contraentrega", "pago_linea"]},
                            {"type": "null"},
                        ]
                    },
                    "selected_tests": {
                        "anyOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ]
                    },
                    "removed_tests": {
                        "anyOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ]
                    },
                },
                "required": [
                    "clinic_name", "tax_id", "pickup_address", "exam_type",
                    "patient_name", "species", "requesting_doctor",
                    "patient_age", "owner_name", "breed", "sex", "observations",
                    "payment_method",
                    "selected_tests",
                    "removed_tests",
                ],
                "additionalProperties": False,
            },
            "message_mode": {
                "type": "string",
                "enum": ["flow_progress", "side_question", "intent_switch", "small_talk", "cancellation"],
            },
            # Lectura semántica de QUÉ hace el usuario en este turno, interpretando la
            # intención (no las palabras exactas). El código la usa como fuente primaria
            # y cae a los detectores de tokens como red de seguridad. "unclear" = sin señal.
            "user_intent_signal": {
                "type": "string",
                "enum": [
                    "provides_requested_data",
                    "affirm",
                    "negate",
                    "correction",
                    "new_or_unregistered_client",
                    "provides_client_identifier",
                    "same_as_previous",
                    "change_client",
                    "new_branch",
                    "another_order",
                    "farewell",
                    "cancel",
                    "off_topic",
                    "unclear",
                ],
            },
            "requires_handoff": {"type": "boolean"},
            "handoff_area": {
                "anyOf": [
                    {"type": "string", "enum": ["contabilidad", "operaciones", "tecnico"]},
                    {"type": "null"},
                ]
            },
            "resume_prompt":   {"type": "string"},
            "confidence":      {"type": "number"},
            "pending_intents": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "reply", "intent", "phase", "service_area", "captured_fields",
            "message_mode", "user_intent_signal", "requires_handoff", "handoff_area",
            "resume_prompt", "confidence", "pending_intents",
        ],
        "additionalProperties": False,
    },
}
