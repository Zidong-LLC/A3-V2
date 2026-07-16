"""Detectores de intención por texto (texto → bool), por tema (Paso 3.4).

Superficie de import idéntica al detectors.py original: todo se re-exporta acá.
"""
from app.detectors.basico import (  # noqa: F401
    _AFFIRMATIVE_TOKENS,
    _CONTINUE_TOKENS,
    _FAREWELL_TOKENS,
    _GREETING_TOKENS,
    _NEGATIVE_TOKENS,
    _OTHER_CHOICE_TOKENS,
    _RESULTS_CHOICE_TOKENS,
    _confirms_new_client,
    _explicitly_says_new_client,
    _is_affirmative_text,
    _is_farewell,
    _is_greeting_only,
    _is_negative_text,
    _is_other_choice,
    _is_results_choice,
)
from app.detectors.perfil import (  # noqa: F401
    _AMBIGUOUS_PROFILE_TOKENS,
    _ARMED_PROFILE_TOKENS,
    _CLOSE_PROFILE_PHRASES,
    _CLOSE_PROFILE_TOKENS,
    _PROFILE_CONFIRM_TOKENS,
    _PROFILE_CUSTOMIZE_TOKENS,
    _asks_for_armed_profiles,
    _is_ambiguous_profile_change,
    _is_profile_confirmation,
    _is_profile_customization_request,
    _wants_to_close_custom_profile,
)
from app.detectors.direccion import (  # noqa: F401
    _ADDRESS_CONFIRM_TOKENS,
    _NO_OWNER_PHRASES,
    _NO_OWNER_TOKENS,
    _confirms_address,
    _rejects_address,
    _says_no_owner,
)
from app.detectors.orden import (  # noqa: F401
    _CONFIRM_ORDER_TOKENS,
    _CORRECTION_TOKENS,
    _HANDOFF_ACCEPT_TOKENS,
    _OPTION_CORRECTION_TOKENS,
    _OPTION_WORDS,
    _ORDER_REQUEST_TOKENS,
    _RECONSIDER_HINT_TOKENS,
    _accepts_handoff_offer,
    _confirms_order_now,
    _expresses_order_request,
    _is_correction_request,
    _is_order_confirmation,
    _wants_to_reconsider_option,
)
from app.detectors.cliente import (  # noqa: F401
    _BRANCH_NEW_SIGNAL_TOKENS,
    _BRANCH_NOUN_TOKENS,
    _CLIENT_CHANGE_SIGNAL_TOKENS,
    _CLIENT_NOUN_TOKENS,
    _NON_IDENTIFIER_TOKENS,
    _REJECT_ALL_MATCH_TOKENS,
    _asks_for_client_identity,
    _asks_if_new_client,
    _claims_unregistered_client,
    _is_no_identifier_text,
    _looks_like_bare_client_name,
    _rejects_match_options,
    _wants_new_branch,
    _wants_to_change_client,
)
