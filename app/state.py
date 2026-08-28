"""Estado explícito de la conversación (Fase 3.1 del refactor del "cómo").

Hoy el estado son ~41 flags `_*` sueltas mezcladas con los datos de negocio en un dict libre
que se arrastra a mano turno a turno, sin schema ni invariantes (una flag pegada = bucle). Este
módulo lo formaliza SIN cambiar el comportamiento: `ConversationState` ENVUELVE el mismo dict
(`captured_fields`), documenta el catálogo de flags válidas, centraliza el arrastre entre turnos
(`carry_over`) y expone invariantes verificables (`assert_valid`). Es el cimiento tipado sobre el
que se apoyan los pasos siguientes (FSM, invertir el orden de decisión).

Convención (igual que `app/services/ai.py`): las claves con prefijo `_` son estado de CONTROL
(no viajan al modelo como datos); el resto son datos de NEGOCIO (del schema de OpenAI).
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


# ── Fases de la conversación (FSM explícita, Fase 3.2) ──────────────────────────
# Antes eran strings mágicos que el modelo proponía y los enforcers reescribían. Aquí
# quedan tipadas y con su grafo de transiciones legales DOCUMENTADO (para detección en
# tests; todavía no se bloquea, igual que el estado no se impuso en 3.1). `Phase` hereda
# de str: `Phase.CIERRE == "fase_6_cierre"`, así es 100% compatible con el código actual.
class Phase(str, Enum):
    BIENVENIDA = "fase_0_bienvenida"
    CLASIFICACION = "fase_1_clasificacion"
    RECOGIDA = "fase_2_recogida_datos"
    VALIDACION = "fase_3_validacion"
    CONFIRMACION = "fase_4_confirmacion"
    EJECUCION = "fase_5_ejecucion"
    CIERRE = "fase_6_cierre"
    ESCALADO = "fase_7_escalado"


DONE_PHASES = frozenset({Phase.CIERRE})
ESCALATED_PHASES = frozenset({Phase.ESCALADO})
TERMINAL_PHASES = DONE_PHASES | ESCALATED_PHASES

# Grafo de transiciones observadas hoy (incluye la auto-transición: un turno puede quedarse
# en la misma fase). Documenta el flujo real; `is_legal_transition` lo usa para detección.
LEGAL_TRANSITIONS: dict[Phase, frozenset] = {
    Phase.BIENVENIDA:   frozenset({Phase.BIENVENIDA, Phase.CLASIFICACION, Phase.RECOGIDA, Phase.ESCALADO, Phase.CIERRE}),
    Phase.CLASIFICACION: frozenset({Phase.RECOGIDA, Phase.ESCALADO, Phase.CIERRE, Phase.BIENVENIDA}),
    Phase.RECOGIDA:     frozenset({Phase.RECOGIDA, Phase.CONFIRMACION, Phase.CIERRE, Phase.ESCALADO, Phase.BIENVENIDA}),
    Phase.CONFIRMACION: frozenset({Phase.CONFIRMACION, Phase.RECOGIDA, Phase.CIERRE, Phase.ESCALADO}),
    Phase.CIERRE:       frozenset({Phase.CIERRE, Phase.RECOGIDA, Phase.BIENVENIDA, Phase.ESCALADO}),   # otra orden
    Phase.ESCALADO:     frozenset({Phase.ESCALADO, Phase.RECOGIDA, Phase.BIENVENIDA, Phase.CIERRE}),   # otra orden / recuperación
}


def is_terminal(phase) -> bool:
    return phase in TERMINAL_PHASES


def is_legal_transition(prev, new) -> bool:
    """¿La transición prev→new está en el grafo documentado? Permisiva: sin prev/new, misma
    fase, o fase de origen aún no mapeada → se considera legal (no bloquea; sirve para
    detectar en tests transiciones nuevas no previstas)."""
    if not prev or not new or prev == new:
        return True
    try:
        allowed = LEGAL_TRANSITIONS.get(Phase(prev))
    except ValueError:
        return True
    if allowed is None:
        return True
    try:
        return Phase(new) in allowed
    except ValueError:
        return True

# ── Catálogo de flags de control, agrupadas por concepto (fuente única de verdad) ──
FLAGS_IDENTIFICACION = frozenset({
    "_client_found", "_client_not_found", "_client_display_name", "_client_address",
    "_client_phone", "_client_email", "_client_match_query", "_client_match_options",
    "_client_memory", "_client_memory_hint", "_asked_if_new_client", "_blocked",
    # ERR-088: escalado por "no encuentro tu registro". Distinto de `_blocked` (silencio
    # definitivo del cliente particular): este se deshace si el cliente da un identificador
    # que existe en la base.
    "_escalated_unfound_client",
    # Perfiles que la clínica más pide, precargados al identificarla (A3, 06/05).
    "_client_favorite_profiles",
})
FLAGS_ANALISIS = frozenset({
    "_selected_profile_code", "_selected_profile_name", "_selected_profile_price",
    "_selected_profile_description", "_profile_detail_offered", "_profile_detail_confirmed",
    "_profile_options_offered", "_profile_customizing", "_diagnostic_label",
    "_custom_profile_summary", "_test_menu_options", "_test_menu_adds_to_profile",
    "_profile_menu_options", "_offering_extra_analysis", "_awaiting_additional_test",
    "_awaiting_exact_name", "_pending_ambiguous_items",
    # Cuántas veces se re-ofreció el término pendiente: tope de reintentos para que un pedido
    # que el cliente nunca resuelve no trabe la orden para siempre (ERR-076).
    "_pending_offer_count",
    # Texto original de un pedido MIXTO ("un prequirúrgico, sodio y potasio"): al elegir el
    # cliente una opción llega solo "el 1", y sin esto los sueltos de la frase se perdían.
    "_mixed_request_text",
    # Perfiles ADICIONALES elegidos en la misma frase que el base ("1, 3 y 6"): van con su
    # precio de catálogo porque un código de perfil no resuelve como análisis (ERR-077).
    "_extra_profiles",
    # ERR-139: el análisis vigente viene HEREDADO de la orden anterior (reoferta de estables)
    # y el cliente todavía no lo confirmó ni eligió otro. Mientras esté encendida, una
    # DECLARACIÓN de análisis ("el análisis es 952") lo REEMPLAZA en vez de sumarse.
    "_analysis_inherited",
})
FLAGS_DIRECCION = frozenset({"_address_confirmation_pending", "_address_confirmed"})
FLAGS_CIERRE = frozenset({
    "_correction_pending", "_stable_confirm_pending", "_prev_order_snapshot",
    "_pending_intents", "_handoff_announced", "_handoff_offer_pending", "_order_registered",
    "_nc_capturing", "_offtrack_count", "_skip_resume", "_force_close_hint",
    # Jerarquía de pedidos (decisión 011): el pedido abierto al que se van colgando las
    # órdenes, y la marca de que ya se cerró y facturó.
    "_pedido_id", "_pedido_cerrado", "_pedido_awaiting_payment", "_pedido_offer_pending", "_pedido_offer_reasked", "_pedido_profiles", "_pedido_ordenes",
    # Corrección POST-CIERRE (2026-08-24, guiones M/M2): el id/número de la última orden
    # registrada y las dos marcas del flujo corregir→confirmar→actualizar.
    "_last_request_id", "_last_order_number", "_post_close_correction_field", "_post_close_correction",
    # Consulta de resultados por chat (paso 3.4a): ids de los PDF que main.py entrega
    # después de responder. Vive un solo turno: se limpia apenas se intenta el envío.
    "_deliver_results",
})
KNOWN_FLAGS = FLAGS_IDENTIFICACION | FLAGS_ANALISIS | FLAGS_DIRECCION | FLAGS_CIERRE

# Datos de negocio (deben coincidir con captured_fields del schema de OpenAI).
BUSINESS_FIELDS = frozenset({
    "clinic_name", "tax_id", "pickup_address", "exam_type", "patient_name", "species",
    "requesting_doctor", "patient_age", "owner_name", "breed", "sex",
    "sample_taken_date", "observations",
    "payment_method", "selected_tests", "removed_tests",
})

# Flags que NUNCA se arrastran al turno siguiente (se recomputan cada turno).
_NO_CARRY = frozenset({"_pending_intents", "_deliver_results"})

# Menús mutuamente excluyentes: mostrar uno limpia el otro (evita menús pegados).
_MENU_FLAGS = ("_test_menu_options", "_profile_menu_options")


@dataclass
class ConversationState:
    """Envoltorio tipado del dict `captured_fields`. No copia datos: opera sobre el mismo
    dict subyacente, por lo que es 100% compatible con el código que aún lee `fields[...]`."""
    data: dict

    # ── Construcción / serialización (compat total con Supabase y ai.py) ──
    @classmethod
    def from_dict(cls, d: dict | None) -> "ConversationState":
        return cls(d if isinstance(d, dict) else {})

    def to_dict(self) -> dict:
        return self.data

    def get(self, key, default=None):
        return self.data.get(key, default)

    # ── Arrastre entre turnos (reemplaza el merge inline de process_turn) ──
    def carry_over(self, prev: dict | None) -> None:
        """Arrastra las flags de control del turno anterior que este turno NO redefinió.
        Replica EXACTAMENTE el comportamiento histórico (agent.py: copiar toda clave `_*`
        salvo `_pending_intents` si no está ya en el dict actual)."""
        for key, value in (prev or {}).items():
            if key.startswith("_") and key not in _NO_CARRY and key not in self.data:
                self.data[key] = value

    # ── Introspección para validación / tests ──
    def flags(self) -> set[str]:
        return {k for k in self.data if k.startswith("_")}

    def unknown_flags(self) -> set[str]:
        """Flags de control presentes que NO están en el catálogo (posible typo o flag
        fantasma). El prefijo `_nc_*` es legado dinámico y se ignora."""
        return {k for k in self.flags()
                if k not in KNOWN_FLAGS and not k.startswith("_nc_")}

    def heal(self) -> list[str]:
        """Modo BLOQUEO de la FSM (3.2): repara los estados incoherentes conocidos con
        reglas documentadas, devolviendo qué reparó (para loggear). Solo corre con
        FSM_ENFORCE activo — se enciende cuando los logs en vivo del observador acumulen
        evidencia sin falsas alarmas.
        Reglas: (1) dirección confirmada Y pendiente → gana la confirmación (la pendiente
        quedó pegada); (2) cliente encontrado Y no-encontrado → gana encontrado (el
        no-encontrado es de un intento anterior); (3) bloqueado Y orden registrada →
        gana bloqueado (no debe operar)."""
        d, healed = self.data, []
        if d.get("_address_confirmed") and d.get("_address_confirmation_pending"):
            d["_address_confirmation_pending"] = False
            healed.append("_address_confirmation_pending")
        if d.get("_client_found") and d.get("_client_not_found"):
            d["_client_not_found"] = False
            healed.append("_client_not_found")
        if d.get("_blocked") and d.get("_order_registered"):
            d.pop("_order_registered", None)
            healed.append("_order_registered")
        return healed

    def assert_valid(self) -> None:
        """Invariantes de un estado coherente. Úsese en tests / modo defensivo."""
        d = self.data
        assert not (d.get("_address_confirmed") and d.get("_address_confirmation_pending")), \
            "dirección no puede estar confirmada y pendiente a la vez"
        assert not (d.get("_client_found") and d.get("_client_not_found")), \
            "cliente no puede estar encontrado y no-encontrado a la vez"
        assert not (d.get("_blocked") and d.get("_order_registered")), \
            "un cliente bloqueado no registra órdenes"

    # ── Helpers de dominio (un solo lugar para reglas hoy dispersas) ──
    def clear_menus(self) -> None:
        """Descarta los menús pegados (perfiles/análisis). Evita que un número incidental
        seleccione una opción vieja (raíz de varios bugs del QA extremo)."""
        for key in _MENU_FLAGS:
            self.data.pop(key, None)
        self.data.pop("_test_menu_adds_to_profile", None)

    @property
    def has_analysis(self) -> bool:
        """Hay análisis definido por cualquiera de las tres vías equivalentes."""
        return bool(self.data.get("exam_type")
                    or self.data.get("selected_tests")
                    or self.data.get("_selected_profile_code"))
