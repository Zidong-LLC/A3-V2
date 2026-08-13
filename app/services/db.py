import re
import difflib
import unicodedata
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from app.rules import (
    INTENT_TO_SERVICE_AREA, calculate_custom_profile_total,
    calculate_profile_adjusted_total, get_scheduled_pickup_date,
)
# El catálogo que se inyecta al modelo debe traer el precio en el MISMO formato que usa el
# flujo determinístico: si acá dijera "$14,000 COP", el modelo imitaría ese formato al
# escribir texto libre y el precio saldría distinto según quién lo redacte.
from app.text import money

_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def ping() -> bool:
    """Consulta trivial para saber si Supabase responde (usada por /health)."""
    _client.table("clients").select("id").limit(1).execute()
    return True


# ── Session ───────────────────────────────────────────────────────────────────

def get_or_create_session(chat_id: str, channel: str = "telegram") -> dict:
    result = _client.table("telegram_sessions").select("*").eq("external_chat_id", chat_id).execute()
    if result.data:
        session = result.data[0]
        if channel and session.get("channel") != channel:
            _client.table("telegram_sessions").update({"channel": channel}).eq("external_chat_id", chat_id).execute()
            session["channel"] = channel
        return session
    new_session = {
        "channel":        channel,
        "external_chat_id": chat_id,
        "client_id":      None,
        "phase_current":  "fase_0_bienvenida",
        "intent_current": "unknown",
        "captured_fields": {},
        "status":         "in_progress",
    }
    _client.table("telegram_sessions").insert(new_session).execute()
    return new_session


_VALID_HANDOFF_AREAS = {"contabilidad", "operaciones", "tecnico"}


def update_session(chat_id: str, ai_response: dict) -> None:
    update_data = {
        "phase_current":    ai_response["phase"],
        "intent_current":   ai_response["intent"],
        "service_area":     ai_response["service_area"],
        "captured_fields":  ai_response["captured_fields"],
        "requires_handoff": ai_response["requires_handoff"],
        "last_bot_message": ai_response["reply"],
        "ai_confidence":    ai_response.get("confidence"),
    }
    handoff = ai_response["handoff_area"]
    if handoff is not None and handoff in _VALID_HANDOFF_AREAS:
        update_data["handoff_area"] = handoff
    _client.table("telegram_sessions").update(update_data).eq("external_chat_id", chat_id).execute()


def link_client_to_session(chat_id: str, client_id: str) -> None:
    _client.table("telegram_sessions").update({"client_id": client_id}).eq("external_chat_id", chat_id).execute()


def clear_client_from_session(chat_id: str) -> None:
    _client.table("telegram_sessions").update({"client_id": None}).eq("external_chat_id", chat_id).execute()


# ── Messages ──────────────────────────────────────────────────────────────────

def get_recent_messages(chat_id: str, limit: int = 8) -> list[dict]:
    result = (
        _client.table("conversation_messages")
        .select("role, content")
        .eq("external_chat_id", chat_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(result.data))


def save_message(chat_id: str, content: str, role: str) -> None:
    _client.table("conversation_messages").insert({
        "external_chat_id": chat_id,
        "role": role,
        "content": content,
    }).execute()


# ── Client identification ─────────────────────────────────────────────────────

def _normalize_nit(nit: str) -> str:
    return re.sub(r"[^0-9]", "", nit or "")


def _normalize_tax_id_compact(tax_id: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", tax_id or "").upper()


def _normalize_lookup_key(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = text.translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


_ROMAN_TO_ARABIC = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
}
_ARABIC_TO_ROMAN = {value: key for key, value in _ROMAN_TO_ARABIC.items()}


def _profile_lookup_variants(value: str | None) -> set[str]:
    key = _normalize_lookup_key(value)
    if not key:
        return set()

    parts = key.split("_")
    variants = {
        key,
        "_".join(_ROMAN_TO_ARABIC.get(part, part) for part in parts),
        "_".join(_ARABIC_TO_ROMAN.get(part, part) for part in parts),
    }
    for variant in list(variants):
        if variant.startswith("perfil_"):
            variants.add(variant.removeprefix("perfil_"))
        else:
            variants.add(f"perfil_{variant}")
    return {variant for variant in variants if variant}


def _catalog_profile_matches(value: str | None, row: dict) -> bool:
    lookups = _profile_lookup_variants(value)
    targets = _profile_lookup_variants(row.get("code")) | _profile_lookup_variants(row.get("name"))
    for lookup in lookups:
        for target in targets:
            if lookup == target or (len(lookup) >= 3 and lookup in target):
                return True
    return False


def _compact_lookup_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", _normalize_lookup_key(value))


def _name_matches(query: str | None, candidate: str | None) -> bool:
    query_key = _compact_lookup_key(query)
    candidate_key = _compact_lookup_key(candidate)
    if not query_key or not candidate_key:
        return False
    if query_key == candidate_key:
        return True
    return (
        len(query_key) >= 5 and query_key in candidate_key
    ) or (
        len(candidate_key) >= 5 and candidate_key in query_key
    )


def _nit_candidates(tax_id: str) -> list[str]:
    raw = (tax_id or "").strip()
    clean = _normalize_nit(raw)
    compact = _normalize_tax_id_compact(raw)

    candidates: list[str] = []

    def add(value: str) -> None:
        if value and value not in candidates:
            candidates.append(value)

    add(raw)
    add(raw.upper())
    add(clean)

    if raw.endswith(".0"):
        add(_normalize_nit(raw[:-2]))

    if len(compact) > 1 and compact[:-1].isdigit():
        base = compact[:-1]
        dv = compact[-1]
        add(base)
        add(f"{base}-{dv}")

    if len(clean) > 1:
        base = clean[:-1]
        dv = clean[-1]
        add(base)
        add(f"{base}-{dv}")

    return candidates


def _nit_base_candidates(tax_id: str) -> list[str]:
    bases: list[str] = []
    for candidate in _nit_candidates(tax_id):
        base = candidate.split("-", 1)[0]
        clean = _normalize_nit(base)
        if len(clean) >= 5 and clean not in bases:
            bases.append(clean)
    return bases


def _fetch_all_active_clients(select_fields: str = "*") -> list[dict]:
    PAGE = 1000
    all_rows: list[dict] = []
    offset = 0
    while True:
        result = (
            _client.table("clients")
            .select(select_fields)
            .eq("is_active", True)
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        batch = result.data or []
        all_rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return all_rows


def identify_client(name: str = None, tax_id: str = None) -> dict | None:
    if tax_id:
        for nit in _nit_candidates(tax_id):
            result = _client.table("clients").select("*").eq("tax_id", nit).eq("is_active", True).execute()
            if result.data:
                return result.data[0]
        for base in _nit_base_candidates(tax_id):
            result = _client.table("clients").select("*").ilike("tax_id", f"{base}-%").eq("is_active", True).execute()
            if result.data:
                return result.data[0]
    if name:
        result = (
            _client.table("clients")
            .select("*")
            .ilike("clinic_name", f"%{name}%")
            .eq("is_active", True)
            .execute()
        )
        if result.data:
            return result.data[0]
        for client in _fetch_all_active_clients():
            if _name_matches(name, client.get("clinic_name")):
                return client
    return None


def find_clients_by_tax_id(tax_id: str | None = None) -> list[dict]:
    """Todas las filas activas (sedes) que comparten un mismo NIT. Permite
    ofrecer el desglose de sucursales cuando un cliente tiene varias sedes."""
    if not tax_id:
        return []

    select_fields = "id, clinic_name, tax_id, phone, address, zone, email"
    matches: list[dict] = []
    seen: set[str] = set()

    def add_rows(rows: list[dict]) -> None:
        for row in rows or []:
            client_id = row.get("id")
            if client_id and client_id not in seen:
                matches.append(row)
                seen.add(client_id)

    for nit in _nit_candidates(tax_id):
        result = _client.table("clients").select(select_fields).eq("tax_id", nit).eq("is_active", True).execute()
        add_rows(result.data)
    for base in _nit_base_candidates(tax_id):
        result = _client.table("clients").select(select_fields).ilike("tax_id", f"{base}-%").eq("is_active", True).execute()
        add_rows(result.data)

    return matches


def _name_match_score(q_tokens: list[str], q_compact: str, candidate: str | None) -> float:
    """Puntúa cuán parecido es un nombre al texto buscado.
    Devuelve 0 si no es relevante; valores mayores = mejor coincidencia.
    Considera relevante un nombre que contiene TODAS las palabras del texto
    (en cualquier orden) o el texto pegado como subcadena."""
    c = _normalize_lookup_key(candidate)
    if not c or not q_tokens:
        return 0.0
    c_tokens = [t for t in c.split("_") if t]
    c_compact = c.replace("_", "")

    # Una palabra de la búsqueda se considera cubierta si coincide exacta, por prefijo,
    # o es MUY similar (tolerancia a errores de tipeo): difflib ratio alto en palabras de
    # 4+ letras (ej. "planett" ~ "planet", "bioanimall" ~ "bioanimal"). El umbral alto
    # (0.85) y el mínimo de 4 letras evitan falsos positivos.
    def _qt_covered(qt: str) -> bool:
        return any(
            qt == ct
            or (len(qt) >= 3 and ct.startswith(qt))
            or (len(qt) >= 4 and len(ct) >= 4 and difflib.SequenceMatcher(None, qt, ct).ratio() >= 0.85)
            for ct in c_tokens
        )

    covered = sum(1 for qt in q_tokens if _qt_covered(qt))
    coverage = covered / len(q_tokens)
    compact_hit = len(q_compact) >= 4 and q_compact in c_compact

    # Relevante solo si están todas las palabras, o el texto aparece pegado.
    if coverage < 1.0 and not compact_hit:
        return 0.0

    ratio = difflib.SequenceMatcher(None, q_compact, c_compact).ratio()
    return coverage + (0.5 if compact_hit else 0.0) + ratio * 0.5


_CLIENT_QUERY_STOPWORDS = frozenset({
    "soy", "somos", "de", "del", "la", "el", "los", "las", "mi", "es", "una", "un",
    "veterinaria", "clinica", "consultorio", "hospital", "centro", "vet",
})


def find_client_matches(name: str | None = None, limit: int = 5) -> list[dict]:
    """Coincidencias de clientes ordenadas por similitud al texto buscado.
    La más parecida queda primera (tolera errores de escritura y palabras sueltas
    como 'animal vet' -> 'Animal's Vet House Centenario')."""
    if not name:
        return []
    q = _normalize_lookup_key(name)
    q_tokens_all = [t for t in q.split("_") if t]
    # Filtrar muletillas para que "somos la veterinaria adryvete" matchee "Adryvete".
    # Si al filtrar queda vacío, conservar los originales (no perder la consulta).
    q_tokens = [t for t in q_tokens_all if t not in _CLIENT_QUERY_STOPWORDS] or q_tokens_all
    q_compact = "".join(q_tokens)
    if not q_tokens:
        return []

    scored: list[tuple[float, str, dict]] = []
    for c in _fetch_all_active_clients("id, clinic_name, tax_id, phone, address, zone, email"):
        score = _name_match_score(q_tokens, q_compact, c.get("clinic_name"))
        if score > 0:
            scored.append((score, c.get("clinic_name") or "", c))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [c for _, _, c in scored[:limit]]


def find_client_exact(name: str | None = None) -> dict | None:
    """Coincidencia EXACTA por nombre (normalizado, ignorando acentos/espacios/símbolos).
    Se usa en el segundo intento de identificación: si el cliente dice que ninguna de las
    coincidencias parciales es la suya, solo se identifica si el nombre que da coincide
    exactamente con un cliente registrado; si no, se trata como posible cliente nuevo."""
    if not name:
        return None
    key = _compact_lookup_key(name)
    if not key:
        return None
    for c in _fetch_all_active_clients("id, clinic_name, tax_id, phone, address, zone, email"):
        if _compact_lookup_key(c.get("clinic_name")) == key:
            return c
    return None


def get_client_by_id(client_id: str) -> dict | None:
    result = _client.table("clients").select("*").eq("id", client_id).eq("is_active", True).execute()
    if result.data:
        return result.data[0]
    return None


def find_client_for_dashboard(tax_id: str | None = None, phone: str | None = None, clinic_name: str | None = None) -> dict | None:
    if tax_id:
        for nit in _nit_candidates(tax_id):
            result = _client.table("clients").select("*").eq("tax_id", nit).execute()
            if result.data:
                return result.data[0]
    if phone:
        result = _client.table("clients").select("*").eq("phone", phone).execute()
        if result.data:
            return result.data[0]
    if clinic_name:
        result = _client.table("clients").select("*").ilike("clinic_name", f"%{clinic_name}%").execute()
        if result.data:
            return result.data[0]
    return None


def create_pending_client_review(client_payload: dict, review_payload: dict, channel: str = "manual") -> dict:
    phone = client_payload.get("phone")
    existing = _client.table("clients").select("id").eq("phone", phone).execute().data if phone else []
    if existing:
        client = existing[0]
    else:
        result = _client.table("clients").insert(client_payload).execute()
        client = result.data[0]
    now = datetime.now(timezone.utc).isoformat()
    request_data = {
        "client_id": client["id"],
        "entry_channel": channel,
        "service_area": "new_client",
        "intent": "new_client",
        "priority": "normal",
        "status": "received",
        "requested_at": now,
        "fallback_reason": "pending_client_review",
    }
    request_result = _client.table("requests").insert(request_data).execute()
    request_row = request_result.data[0]
    _client.table("request_events").insert({
        "request_id": request_row["id"],
        "event_type": "client_review_submitted",
        "event_payload": review_payload,
    }).execute()
    return {"client_id": client["id"], "request_id": request_row["id"]}


def list_pending_client_reviews(limit: int = 300) -> list[dict]:
    result = (
        _client.table("requests")
        .select("id, client_id, status, requested_at, fallback_reason, clients(id, clinic_name, tax_id, phone, address, zone, billing_type)")
        .eq("service_area", "new_client")
        .eq("fallback_reason", "pending_client_review")
        .order("requested_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = result.data or []
    for row in rows:
        event_result = (
            _client.table("request_events")
            .select("event_payload, created_at")
            .eq("request_id", row["id"])
            .eq("event_type", "client_review_submitted")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        row["review_payload"] = (event_result.data or [{}])[0].get("event_payload", {})
    return rows


def approve_pending_client(request_id: str) -> bool:
    request_result = _client.table("requests").select("id, client_id").eq("id", request_id).execute()
    if not request_result.data:
        return False
    client_id = request_result.data[0].get("client_id")
    if not client_id:
        return False
    event_result = (
        _client.table("request_events")
        .select("event_payload")
        .eq("request_id", request_id)
        .eq("event_type", "client_review_submitted")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    review_payload = (event_result.data or [{}])[0].get("event_payload") or {}
    courier_id = review_payload.get("courier_id")
    _client.table("clients").update({"is_active": True}).eq("id", client_id).execute()
    if courier_id:
        _client.table("client_courier_assignment").insert({
            "client_id": client_id,
            "courier_id": courier_id,
            "assigned_by": "dashboard_review",
        }).execute()
    _client.table("requests").update({"status": "processed", "fallback_reason": "client_review_approved"}).eq("id", request_id).execute()
    _client.table("request_events").insert({
        "request_id": request_id,
        "event_type": "client_review_approved",
        "event_payload": {"source": "dashboard"},
    }).execute()
    return True


def reject_pending_client(request_id: str, reason: str) -> bool:
    request_result = _client.table("requests").select("id").eq("id", request_id).execute()
    if not request_result.data:
        return False
    _client.table("requests").update({"status": "cancelled", "fallback_reason": "client_review_rejected"}).eq("id", request_id).execute()
    _client.table("request_events").insert({
        "request_id": request_id,
        "event_type": "client_review_rejected",
        "event_payload": {"source": "dashboard", "reason": reason},
    }).execute()
    return True


def delete_client_completely(client_id: str, clinic_key: str | None = None) -> bool:
    client_result = _client.table("clients").select("id, clinic_name").eq("id", client_id).execute()
    if not client_result.data:
        return False

    client = client_result.data[0]
    request_rows = _client.table("requests").select("id").eq("client_id", client_id).execute().data or []
    sample_rows = _client.table("lab_samples").select("id").eq("client_id", client_id).execute().data or []
    request_ids = [row["id"] for row in request_rows if row.get("id")]
    sample_ids = [row["id"] for row in sample_rows if row.get("id")]
    clinic_keys = []
    for raw_key in (clinic_key, client.get("clinic_name")):
        normalized = _normalize_lookup_key(raw_key)
        if normalized and normalized not in clinic_keys:
            clinic_keys.append(normalized)

    if request_ids:
        _client.table("request_events").delete().in_("request_id", request_ids).execute()
    if sample_ids:
        _client.table("lab_sample_events").delete().in_("sample_id", sample_ids).execute()
    _client.table("lab_samples").delete().eq("client_id", client_id).execute()
    _client.table("requests").delete().eq("client_id", client_id).execute()
    _client.table("client_courier_assignment").delete().eq("client_id", client_id).execute()
    _client.table("telegram_sessions").delete().eq("client_id", client_id).execute()
    for key in clinic_keys:
        _client.table("clients_a3_sample_events").delete().eq("clinic_key", key).execute()
        _client.table("clients_a3_knowledge").delete().eq("clinic_key", key).execute()
    delete_result = _client.table("clients").delete().eq("id", client_id).execute()
    return bool(delete_result.data)


def get_catalog_context(species: str | None = None) -> str:
    """Catálogo de PERFILES que se le inyecta al modelo. Va COMPLETO, sin filtrar por especie
    (decisión 012).

    El filtro dejaba al modelo sin ver 73 perfiles según la especie del paciente, y entonces
    respondía de buena fe que no existían: con un paciente felino, "tenés el 653?" recibía
    "no lo tengo identificado en el catálogo" aunque el 653 esté en la base. La regla del
    negocio es que **nada que esté en la base puede negarse**. El `species` de cada ítem es
    una etiqueta informativa; el modelo la usa para avisar, no para esconder.

    Costo medido: el contexto pasa de ~3.600 a ~4.900 tokens por turno. El parámetro se
    conserva por compatibilidad con los call sites.
    """
    query = _client.table("catalog_profiles").select("code, name, category, description, price").eq("is_active", True)
    rows = query.order("code").execute().data
    if not rows:
        return ""

    from collections import defaultdict
    by_cat: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        description = r.get("description") or "sin detalle"
        by_cat[r["category"]].append(f"{r['code']}-{r['name']}: {description} {money(r['price'])}")

    label = f" ({species})" if species else ""
    lines = [f"Catálogo A3{label}:"]
    for cat, items in by_cat.items():
        lines.append(f"[{cat}] " + ", ".join(items))
    return "\n".join(lines)


def list_catalog_breeds() -> list[dict]:
    """Catálogo completo de razas (breed_key, name, species). Lo cachea `app/breeds.py`."""
    result = (
        _client.table("catalog_breeds")
        .select("breed_key, name, species")
        .eq("is_active", True)
        .limit(5000)
        .execute()
    )
    return result.data or []


def find_catalog_profile(value: str | None, species: str | None = None) -> dict | None:
    """Perfil por NOMBRE. Igual que por código, no filtra por especie (decisión 012):
    nombrar un perfil es pedirlo, no pedir una sugerencia."""
    lookup = _normalize_lookup_key(value)
    if not lookup:
        return None

    query = (
        _client.table("catalog_profiles")
        .select("code, name, category, species, description, price")
        .eq("is_active", True)
        .limit(5000)
    )

    rows = query.execute().data or []
    for row in rows:
        if _catalog_profile_matches(value, row):
            return row
    return None


def find_catalog_profiles(value: str | None, species: str | None = None, limit: int = 20) -> list[dict]:
    """Búsqueda de perfiles por nombre/categoría. Sin filtro de especie (decisión 012)."""
    lookup = _normalize_lookup_key(value)
    if not lookup:
        return []

    query = (
        _client.table("catalog_profiles")
        .select("code, name, category, species, description, price")
        .eq("is_active", True)
        .limit(5000)
    )

    rows = query.execute().data or []
    matches = []
    for row in rows:
        category_key = _normalize_lookup_key(row.get("category"))
        if _catalog_profile_matches(value, row) or lookup == category_key or lookup in category_key:
            matches.append(row)
            if len(matches) >= limit:
                break
    return matches


def get_catalog_profiles_by_codes(codes: list[str], species: str | None = None) -> list[dict]:
    """Perfiles por CÓDIGO. NO filtra por especie a propósito (decisión 012).

    Un código es una petición explícita del cliente, no una sugerencia nuestra. El filtro
    hacía que el bot respondiera "no encuentro el Perfil 653 en el catálogo" a un cliente que
    pedía el 653 para un gato — el 653 existe (Perfil Senior Canino III) y A3 confirmó que en
    su operación un perfil de una especie se pide para otra sin problema. Quien decide es el
    veterinario; el `species` del catálogo queda como ETIQUETA informativa, no como veto.
    El parámetro se conserva para no romper los ~10 call sites.
    """
    clean_codes = [str(code).strip() for code in codes if str(code or "").strip()]
    if not clean_codes:
        return []

    query = (
        _client.table("catalog_profiles")
        .select("code, name, category, species, description, price")
        .in_("code", clean_codes)
        .eq("is_active", True)
    )

    rows = query.execute().data or []
    by_code = {str(row.get("code")): row for row in rows}
    return [by_code[code] for code in clean_codes if code in by_code]


def get_individual_tests_context(species: str | None = None) -> str:
    """Catálogo de ANÁLISIS sueltos para el contexto del modelo. Completo, sin filtrar por
    especie: mismo motivo que `get_catalog_context` (decisión 012).

    Verificado antes del cambio: con un paciente felino, "tenes el 1503?" respondía "No lo
    tengo identificado en el catálogo" — el 1503 es T4 Total Canino y está en la base. Eran
    52 análisis invisibles según la especie."""
    query = _client.table("catalog_tests").select("code, name, category, price").eq("is_active", True)
    rows = query.order("code").execute().data
    if not rows:
        return ""

    from collections import defaultdict
    by_cat: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(f"{r['code']}-{r['name']} {money(r['price'])}")

    label = f" ({species})" if species else ""
    lines = [f"Análisis individuales A3{label}:"]
    for cat, items in by_cat.items():
        lines.append(f"[{cat}] " + ", ".join(items))
    return "\n".join(lines)


def get_tests_by_codes(codes: list[str]) -> list[dict]:
    if not codes:
        return []
    result = (
        _client.table("catalog_tests")
        .select("code, name, price, category")
        .in_("code", codes)
        .eq("is_active", True)
        .execute()
    )
    return result.data or []


def get_tests_by_codes_or_names(items: list[str]) -> list[dict]:
    if not items:
        return []

    result = (
        _client.table("catalog_tests")
        .select("code, name, price, category")
        .eq("is_active", True)
        .limit(5000)
        .execute()
    )
    rows = result.data or []
    matched = []
    seen = set()
    for raw_item in items:
        lookup = _normalize_lookup_key(raw_item)
        if not lookup:
            continue
        for row in rows:
            code_key = _normalize_lookup_key(row.get("code"))
            name_key = _normalize_lookup_key(row.get("name"))
            if lookup == code_key or lookup == name_key or _tokens_contained(lookup, name_key):
                code = row.get("code")
                if code and code not in seen:
                    matched.append(row)
                    seen.add(code)
                break
    return matched


def _tokens_contained(needle_key: str, haystack_key: str) -> bool:
    """`needle_key` aparece como secuencia CONTIGUA de palabras completas dentro de
    `haystack_key` (ambos ya normalizados con '_' entre tokens). Reemplaza el viejo match
    por subcadena (`needle in haystack`), que producía falsos positivos absurdos al agregar
    análisis: '3' caía dentro de 't3_total', 'pt' dentro de nombres arbitrarios, etc. Con
    límite de palabra, un fragmento suelto ya no resuelve a un test que el cliente no pidió."""
    needle = [t for t in needle_key.split("_") if t]
    hay = [t for t in haystack_key.split("_") if t]
    if not needle or len(needle) > len(hay):
        return False
    for i in range(len(hay) - len(needle) + 1):
        if hay[i:i + len(needle)] == needle:
            return True
    return False


def find_tests_by_area(value: str | None, species: str | None = None, limit: int = 15) -> tuple[str | None, list[dict]]:
    """Análisis individuales que corresponden a un área o tipo de muestra descrito
    por el usuario (ej. "orina" → categoría Uroanálisis / sample "Orina Fresca").
    Devuelve (nombre del área, tests). Permite ofrecer opciones cuando el cliente
    pide por área y no por nombre/código exacto de un perfil."""
    key = _normalize_lookup_key(value)
    # Palabras estructurales y genéricos fuera: el "con" de 'vamos CON el 152...' no
    # identifica un área aunque aparezca en la muestra 'Tubo Tapa Azul CON 3/4 de sangre',
    # ni "medio" identifica Microbiología (vocabulario único en app.catalog; ERR-063/064).
    from app.catalog import STRUCTURAL_TOKENS, GENERIC_DESCRIPTORS
    stop = STRUCTURAL_TOKENS | GENERIC_DESCRIPTORS
    q_tokens = {t for t in key.split("_") if len(t) >= 3 and t not in stop}
    if not q_tokens:
        return None, []

    query = _client.table("catalog_tests").select("code, name, category, sample, price").eq("is_active", True).limit(5000)
    species_key = (species or "").strip().lower()
    if species_key in ("canino", "felino"):
        query = query.in_("species", [species_key, "ambos"])
    try:
        rows = query.execute().data or []
    except Exception:
        return None, []

    # 1) Coincidencia por categoría (más precisa): devuelve toda esa categoría.
    cat_hits: dict[str, list[dict]] = {}
    for row in rows:
        cat_tokens = set(_normalize_lookup_key(row.get("category")).split("_"))
        if q_tokens & cat_tokens:
            cat_hits.setdefault(row.get("category") or "", []).append(row)
    if cat_hits:
        best = max(cat_hits, key=lambda c: len(cat_hits[c]))
        return best, cat_hits[best][:limit]

    # 2) Coincidencia por tipo de muestra (ej. "orina" → "Orina Fresca"). Se excluyen las
    #    muestras ULTRA-genéricas ('sangre', 'suero', 'plasma'): casi todo análisis es de
    #    sangre, así que no identifican un área — 'análisis de sangre' no es "Coagulación".
    from collections import Counter
    _GENERIC_SAMPLE = {"sangre", "sanguineo", "sanguinea", "sanguineos", "suero", "plasma"}
    sample_q = q_tokens - _GENERIC_SAMPLE
    if sample_q:
        sample_hits = [
            row for row in rows
            if sample_q & set(_normalize_lookup_key(row.get("sample")).split("_"))
        ]
        if sample_hits:
            area = Counter(r.get("category") for r in sample_hits).most_common(1)[0][0]
            return area, sample_hits[:limit]

    return None, []


def list_diagnostic_labels(limit: int = 200) -> list[str]:
    """Etiquetas diagnósticas distintas disponibles (CARDIACO, SENIOR CANINO, ...).
    Defensivo: si la tabla aún no existe (migración 012 sin aplicar), devuelve []."""
    try:
        result = _client.table("diagnostic_label_tests").select("label").limit(5000).execute()
    except Exception:
        return []
    seen: list[str] = []
    for row in result.data or []:
        label = row.get("label")
        if label and label not in seen:
            seen.append(label)
    return sorted(seen)[:limit]


def _label_prefix_overlap(q_tokens: list[str], l_tokens: list[str], min_root: int = 5) -> bool:
    """Dos grupos de tokens comparten raíz morfológica si algún par tiene un prefijo
    común de al menos `min_root` caracteres (ej. 'dermatitis' y 'dermatologico' → 'dermat').
    Esto detecta variantes morfológicas sin necesitar listas de sinónimos."""
    for qt in q_tokens:
        for lt in l_tokens:
            if qt == lt:
                return True
            n = min(len(qt), len(lt))
            if n >= min_root:
                shared = sum(1 for a, b in zip(qt, lt) if a == b)
                # El prefijo compartido debe ser consecutivo desde el inicio
                prefix_len = 0
                for a, b in zip(qt, lt):
                    if a == b:
                        prefix_len += 1
                    else:
                        break
                if prefix_len >= min_root:
                    return True
    return False


def find_diagnostic_label(query: str | None, species: str | None = None) -> str | None:
    """Encuentra la etiqueta diagnóstica que mejor corresponde al texto del usuario.

    Tres niveles de coincidencia, del más al menos estricto:
    1. Exacta: el texto normalizado es idéntico a la clave de la etiqueta.
    2. Contenida: la etiqueta completa aparece como subcadena del texto.
    3. Raíz morfológica: algún token del texto y algún token de la etiqueta
       comparten un prefijo de ≥5 caracteres (ej. 'hepatico' ~ 'hepatico_canino',
       'dermatitis' ~ 'dermatologico', 'parasitos' ~ 'parasitologico').
       Cuando varios candidatos coinciden por raíz, se prefiere el que incluye
       la especie ya conocida; si hay empate, se devuelve el más corto/general.
    """
    key = _normalize_lookup_key(query)
    if not key:
        return None
    labels = list_diagnostic_labels()
    label_keys = {label: _normalize_lookup_key(label) for label in labels}

    # 1. Exacta
    for label, lk in label_keys.items():
        if lk == key:
            return label

    # 2. Etiqueta completa contenida en el texto
    for label, lk in label_keys.items():
        if lk and lk in key:
            return label

    # 3. Raíz morfológica compartida (tokens significativos ≥ 4 chars)
    q_tokens = [t for t in key.split("_") if len(t) >= 4]
    if not q_tokens:
        return None
    candidates: list[tuple[str, str]] = []
    for label, lk in label_keys.items():
        l_tokens = [t for t in lk.split("_") if len(t) >= 4]
        if _label_prefix_overlap(q_tokens, l_tokens):
            candidates.append((label, lk))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][0]
    # Desambiguar por especie cuando hay variantes canino/felino
    if species:
        species_key = _normalize_lookup_key(species)
        for label, lk in candidates:
            if species_key in lk:
                return label
    # Sin especie: devolver el más corto (más general)
    candidates.sort(key=lambda x: len(x[1]))
    return candidates[0][0]


def get_tests_for_label(label: str | None) -> list[dict]:
    """Pruebas (code, name, price, category) que conforman una etiqueta diagnóstica."""
    if not label:
        return []
    try:
        rows = (
            _client.table("diagnostic_label_tests")
            .select("test_code")
            .eq("label", label)
            .execute()
            .data
            or []
        )
    except Exception:
        return []
    codes = [r["test_code"] for r in rows if r.get("test_code")]
    return get_tests_by_codes(codes)


def list_catalog_tests(limit: int = 500) -> list[dict]:
    result = (
        _client.table("catalog_tests")
        .select("code, name, category, species, sample, price, is_active")
        .eq("is_active", True)
        .order("code")
        .limit(limit)
        .execute()
    )
    return result.data or []


def list_catalog_profiles(limit: int = 500) -> list[dict]:
    result = (
        _client.table("catalog_profiles")
        .select("code, name, category, species, description, price, is_active")
        .eq("is_active", True)
        .order("code")
        .limit(limit)
        .execute()
    )
    return result.data or []


def list_catalog_profiles_for_species(species: str | None = None, limit: int = 6) -> list[dict]:
    """Perfiles del catálogo aplicables a una especie, para recomendar cuando el
    cliente no sabe qué pedir. Prioriza los perfiles propios de la especie sobre los
    genéricos ('ambos'). Defensivo: si falla la consulta devuelve lista vacía."""
    try:
        query = (
            _client.table("catalog_profiles")
            .select("code, name, category, species, description, price")
            .eq("is_active", True)
            .order("code")
            .limit(5000)
        )
        species_key = (species or "").strip().lower()
        if species_key in ("canino", "felino"):
            query = query.in_("species", [species_key, "ambos"])
        rows = query.execute().data or []
    except Exception:
        return []
    rows.sort(key=lambda r: 0 if (r.get("species") or "").strip().lower() == (species or "").strip().lower() else 1)
    return rows[:limit]


def _normalize_for_category_match(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in decomposed if c.isalnum())


def filter_profiles_by_category_mention(rows: list[dict], text: str) -> list[dict]:
    """Perfiles cuya categoría aparece nombrada en el texto (sin tildes ni espacios:
    'pre quirúrgico' matchea la categoría 'Prequirúrgico'). Pura, sin I/O."""
    normalized_text = _normalize_for_category_match(text)
    if not normalized_text:
        return []
    matched = []
    for row in rows:
        category = _normalize_for_category_match(row.get("category") or "")
        # Categorías muy cortas quedan fuera: riesgo de matchear dentro de otra palabra.
        if len(category) >= 5 and category in normalized_text:
            matched.append(row)
    matched.sort(key=lambda r: (len(str(r.get("code") or "")), str(r.get("code") or "")))
    return matched


def list_catalog_profiles_matching_category(text: str, species: str | None = None,
                                            limit: int = 12) -> list[dict]:
    """Perfiles armados del catálogo cuya CATEGORÍA está nombrada en el texto del
    cliente (ej. 'prequirúrgico' -> perfiles 152-162). Defensivo: [] si falla."""
    try:
        query = (
            _client.table("catalog_profiles")
            .select("code, name, category, species, description, price")
            .eq("is_active", True)
            .limit(5000)
        )
        rows = query.execute().data or []
    except Exception:
        return []
    matched = filter_profiles_by_category_mention(rows, text)
    # Nombrar una categoría ("prequirúrgico") también es explícito, así que no se esconde
    # nada por especie (decisión 012). Pero los del paciente van PRIMERO: el menú sigue
    # siendo útil y los de otra especie quedan al final, disponibles si los pide.
    # El sort es estable, así que dentro de cada grupo se conserva el orden por código.
    species_key = (species or "").strip().lower()
    if species_key:
        matched.sort(key=lambda r: 0 if str(r.get("species") or "ambos").lower()
                     in (species_key, "ambos") else 1)
    return matched[:limit]


def list_conversation_messages(limit: int = 500) -> list[dict]:
    result = (
        _client.table("conversation_messages")
        .select("id, external_chat_id, role, content, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def fetch_rows(table: str, select: str = "*", limit: int = 500) -> list[dict]:
    result = _client.table(table).select(select).limit(limit).execute()
    return result.data or []


def insert_rows(table: str, rows: list[dict]) -> list[dict]:
    result = _client.table(table).insert(rows).execute()
    return result.data or []


def update_rows(table: str, filters: dict, payload: dict) -> list[dict]:
    query = _client.table(table).update(payload)
    for field, value in filters.items():
        query = query.eq(field, value)
    result = query.execute()
    return result.data or []


def list_column_prefs(user_key: str) -> list[dict]:
    result = (
        _client.table("dashboard_column_prefs")
        .select("table_id, prefs")
        .eq("user_key", user_key)
        .execute()
    )
    return result.data or []


def upsert_column_prefs(user_key: str, table_id: str, prefs: dict) -> None:
    _client.table("dashboard_column_prefs").upsert({
        "user_key": user_key,
        "table_id": table_id,
        "prefs": prefs,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="user_key,table_id").execute()


# --------------------------- Cache de facturas (Alegra) ---------------------------

_INVOICE_ORDER_FIELDS = {
    "invoice_date", "number", "client_name", "total", "tax", "subtotal", "status", "synced_at",
}


def upsert_invoices_cache(rows: list[dict]) -> int:
    """Inserta/actualiza filas de facturas en el cache (clave alegra_invoice_id)."""
    if not rows:
        return 0
    _client.table("invoices_cache").upsert(rows, on_conflict="alegra_invoice_id").execute()
    return len(rows)


def list_cached_invoices(
    filters: dict | None = None,
    page: int = 1,
    per_page: int = 50,
    order_field: str = "invoice_date",
    order_desc: bool = True,
) -> tuple[list[dict], int]:
    """Lista facturas del cache con filtros, orden y paginación del lado servidor.
    Devuelve (filas, total)."""
    f = filters or {}
    query = _client.table("invoices_cache").select("*", count="exact")
    if f.get("status"):
        query = query.eq("status", f["status"])
    if f.get("document_type"):
        query = query.eq("document_type", f["document_type"])
    if f.get("client_nit"):
        query = query.ilike("client_nit", f"%{f['client_nit']}%")
    if f.get("number"):
        query = query.ilike("number", f"%{f['number']}%")
    if f.get("date_from"):
        query = query.gte("invoice_date", f["date_from"])
    if f.get("date_to"):
        query = query.lte("invoice_date", f["date_to"])
    if f.get("total_min") is not None:
        query = query.gte("total", f["total_min"])
    if f.get("total_max") is not None:
        query = query.lte("total", f["total_max"])
    if f.get("search"):
        term = str(f["search"]).replace(",", " ").strip()
        if term:
            query = query.or_(
                f"number.ilike.%{term}%,client_name.ilike.%{term}%,client_nit.ilike.%{term}%"
            )
    field = order_field if order_field in _INVOICE_ORDER_FIELDS else "invoice_date"
    query = query.order(field, desc=order_desc)
    start = max(page - 1, 0) * per_page
    query = query.range(start, start + per_page - 1)
    result = query.execute()
    return result.data or [], (result.count or 0)


def list_all_cached_invoices(columns: str = "*", limit: int = 10000) -> list[dict]:
    """Lee el cache completo (acotado) para métricas y exportación."""
    result = _client.table("invoices_cache").select(columns).limit(limit).execute()
    return result.data or []


def get_cached_invoice(invoice_id: str) -> dict | None:
    """Devuelve una factura del cache por su id de Alegra, o None."""
    result = _client.table("invoices_cache").select("*").eq("alegra_invoice_id", invoice_id).limit(1).execute()
    rows = result.data or []
    return rows[0] if rows else None


def list_custom_profiles(client_id: str | None = None, limit: int = 100) -> list[dict]:
    query = _client.table("client_custom_profiles").select("*, clients(clinic_name)").order("created_at", desc=True).limit(limit)
    if client_id:
        query = query.eq("client_id", client_id)
    result = query.execute()
    rows = result.data or []
    for row in rows:
        client = row.get("clients") if isinstance(row.get("clients"), dict) else {}
        row["client_name"] = client.get("clinic_name") or "Cliente"
    return rows


def save_custom_profile(payload: dict) -> dict:
    result = _client.table("client_custom_profiles").insert(payload).execute()
    return (result.data or [{}])[0]


def update_catalog_item(tabla: str, code: str, cambios: dict) -> dict | None:
    """Edita un ítem del catálogo (precio y/o etiqueta de especie) desde el dashboard.

    Hasta ahora el catálogo era de SOLO LECTURA: cambiar un precio exigía SQL a mano. A3 lo
    pidió el 07/04 (es el pendiente más antiguo) y la etiqueta de especie el 28/07 — sin ella
    no pueden marcar qué perfiles son exclusivos, que es lo que hace útil la decisión 012.

    `tabla` se valida contra una lista blanca: viene de la request y nunca puede componer el
    nombre libremente. Devuelve la fila actualizada o None si no existe.
    """
    if tabla not in ("catalog_tests", "catalog_profiles"):
        raise ValueError(f"tabla de catálogo no permitida: {tabla!r}")
    code = str(code or "").strip()
    if not code or not cambios:
        return None
    result = _client.table(tabla).update(cambios).eq("code", code).execute()
    return (result.data or [None])[0]


def log_catalog_change(tabla: str, code: str, antes: dict, despues: dict, por: str | None) -> None:
    """Registra un cambio de catálogo. Editar un precio mueve plata: tiene que rastrearse.

    No se usa `request_events` porque su `request_id` es NOT NULL y un cambio de catálogo no
    pertenece a ninguna orden (verificado contra la base). Nunca lanza: la auditoría es
    complementaria y el cambio ya se aplicó."""
    try:
        _client.table("catalog_audit").insert({
            "source_table": tabla,
            "code": str(code),
            "before_json": antes or {},
            "after_json": despues or {},
            "changed_by": por or "operator",
        }).execute()
    except Exception:
        return


def get_catalog_item(tabla: str, code: str) -> dict | None:
    """Fila actual de un ítem del catálogo. Se usa para registrar el valor ANTERIOR en la
    auditoría de un cambio de precio."""
    if tabla not in ("catalog_tests", "catalog_profiles"):
        raise ValueError(f"tabla de catálogo no permitida: {tabla!r}")
    result = _client.table(tabla).select("*").eq("code", str(code or "").strip()).limit(1).execute()
    return (result.data or [None])[0]


def delete_custom_profile(profile_id: str) -> bool:
    result = _client.table("client_custom_profiles").delete().eq("id", profile_id).execute()
    return bool(result.data)


# ── Perfiles favoritos por clínica (decisión 012 / pedido de A3 del 06/05) ──────
# El agente registra qué pide cada clínica y se lo reofrece la próxima vez. Todas estas
# funciones son DEFENSIVAS: corren dentro del cierre de una orden y de la identificación del
# cliente, así que un fallo no puede tumbar el turno.

def _items_signature(items: list[dict]) -> str:
    """Huella del conjunto de análisis, independiente del orden en que los pidió.
    Permite reconocer que la clínica volvió a pedir LO MISMO y sumar al contador en vez de
    duplicar la fila (`save_custom_profile` es un INSERT puro)."""
    codigos = sorted({str(i.get("code") or "").strip() for i in (items or []) if i.get("code")})
    return "|".join(codigos)


def record_custom_profile_use(client_id: str | None, items: list[dict], name: str) -> None:
    """Suma un uso al favorito de esta clínica, o lo crea si es la primera vez."""
    firma = _items_signature(items)
    if not client_id or not firma:
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        existente = (
            _client.table("client_custom_profiles")
            .select("id, usage_count")
            .eq("client_id", client_id)
            .eq("items_signature", firma)
            .limit(1)
            .execute()
        ).data or []
        if existente:
            fila = existente[0]
            _client.table("client_custom_profiles").update({
                "usage_count": int(fila.get("usage_count") or 1) + 1,
                "last_used_at": now,
            }).eq("id", fila["id"]).execute()
            return
        _client.table("client_custom_profiles").insert({
            "client_id": client_id,
            "name": name,
            "items_json": items,
            "items_signature": firma,
            "usage_count": 1,
            "last_used_at": now,
            "created_by": "agente",
        }).execute()
    except Exception:
        # Puede faltar la migración 019 (columnas nuevas) o caerse la red: registrar el
        # favorito es un extra, nunca puede romper el cierre de una orden.
        return


def list_favorite_profiles(client_id: str | None, limit: int = 3) -> list[dict]:
    """Los que esta clínica más pide, primero. Vacío si no hay o si algo falla."""
    if not client_id:
        return []
    try:
        result = (
            _client.table("client_custom_profiles")
            .select("id, name, items_json, usage_count")
            .eq("client_id", client_id)
            .order("usage_count", desc=True)
            .order("last_used_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def update_request(request_id: str, payload: dict) -> bool:
    result = _client.table("requests").update(payload).eq("id", request_id).execute()
    return bool(result.data)


def create_request_event(request_id: str, event_type: str, event_payload: dict) -> None:
    _client.table("request_events").insert({
        "request_id": request_id,
        "event_type": event_type,
        "event_payload": event_payload,
    }).execute()


def _as_catalog_item_list(value) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [value]
    else:
        return []
    return [str(item).strip() for item in raw_items if str(item or "").strip()]


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _catalog_description_items(description: str | None) -> list[str]:
    items = []
    current = []
    depth = 0
    for char in description or "":
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1

        if char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)

    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _event_test_rows(items: list[str]) -> list[dict]:
    rows = get_tests_by_codes_or_names(items)
    return [
        {
            "code": row.get("code"),
            "name": row.get("name"),
            "price": _as_int(row.get("price")),
        }
        for row in rows
    ]


def _profile_event_payload(fields: dict) -> dict | None:
    code = fields.get("_selected_profile_code")
    name = fields.get("_selected_profile_name") or fields.get("exam_type")
    if not code and not name:
        return None

    base_price = _as_int(fields.get("_selected_profile_price"))
    added_tests = _event_test_rows(_as_catalog_item_list(fields.get("selected_tests")))
    removed_tests = _event_test_rows(_as_catalog_item_list(fields.get("removed_tests")))
    if not code and not base_price and added_tests:
        # Perfil PERSONALIZADO (solo pruebas sueltas): el total persistido debe ser el
        # cotizado en el chat, que incluye el descuento por volumen (2026-07-16: la orden
        # quedaba registrada por $48.000 cuando al cliente se le cotizó $41.280).
        custom = calculate_custom_profile_total(added_tests)
        totals = {
            "base": 0,
            "added": custom["subtotal"],
            "removed": 0,
            "subtotal": custom["subtotal"],
            "volume_discount": custom["discount"],
            "total": custom["total"],
        }
    else:
        totals = calculate_profile_adjusted_total(
            base_price,
            [test["price"] for test in added_tests],
            [test["price"] for test in removed_tests],
        )

    return {
        "base_profile": {
            "code": code,
            "name": name,
            "price": base_price,
        },
        "included_tests": _catalog_description_items(fields.get("_selected_profile_description")),
        "added_tests": added_tests,
        "removed_tests": removed_tests,
        "total_estimated": totals["total"],
        "price_adjustment": totals,
    }


def _service_order_event_payload(fields: dict, requested_at: datetime) -> dict:
    return {
        "date": requested_at.date().isoformat(),
        "requesting_doctor": fields.get("requesting_doctor"),
        "clinic_name": fields.get("clinic_name") or fields.get("_client_display_name"),
        "clinic_phone": fields.get("_client_phone") or fields.get("clinic_phone"),
        "pickup_address": fields.get("pickup_address"),
        "patient": {
            "name": fields.get("patient_name"),
            "species": fields.get("species"),
            "breed": fields.get("breed"),
            "sex": fields.get("sex"),
            "age": fields.get("patient_age"),
            "owner_name": fields.get("owner_name"),
        },
        "exam_type": fields.get("exam_type"),
        "observations": fields.get("observations"),
        "payment_method": fields.get("payment_method"),
    }


def get_courier_for_client(client_id: str) -> dict | None:
    result = (
        _client.table("client_courier_assignment")
        .select("courier_id, couriers(id, name, phone, availability)")
        .eq("client_id", client_id)
        .execute()
    )
    if result.data:
        return result.data[0].get("couriers")
    return None


def list_active_couriers(limit: int = 500) -> list[dict]:
    result = (
        _client.table("couriers")
        .select("id, name, phone, availability, is_active")
        .eq("is_active", True)
        .order("name")
        .limit(limit)
        .execute()
    )
    return result.data or []


def update_courier_phone(courier_id: str, phone: str) -> bool:
    result = _client.table("couriers").update({"phone": phone}).eq("id", courier_id).execute()
    return bool(result.data)


def update_courier(courier_id: str, payload: dict) -> bool:
    result = _client.table("couriers").update(payload).eq("id", courier_id).execute()
    return bool(result.data)


def list_courier_locality_coverage(limit: int = 500) -> list[dict]:
    result = (
        _client.table("courier_locality_coverage")
        .select("locality_code, locality_name, courier_id, assigned_by, assigned_at, couriers(id, name, phone, availability)")
        .limit(limit)
        .execute()
    )
    return result.data or []


def list_territorial_zones(limit: int = 100) -> list[dict]:
    result = (
        _client.table("territorial_zones")
        .select("*")
        .order("zone_number")
        .limit(limit)
        .execute()
    )
    return result.data or []


def list_territorial_neighborhoods(limit: int = 3000) -> list[dict]:
    result = (
        _client.table("territorial_neighborhoods")
        .select("locality_code, locality_name, zone_number, courier_name, cantidad_barrios")
        .limit(limit)
        .execute()
    )
    return result.data or []


def upsert_courier_locality_coverage(
    *,
    locality_code: str,
    locality_name: str,
    courier_id: str,
    assigned_by: str,
) -> None:
    _client.table("courier_locality_coverage").upsert({
        "locality_code": locality_code,
        "locality_name": locality_name,
        "courier_id": courier_id,
        "assigned_by": assigned_by,
    }, on_conflict="locality_code").execute()


def delete_courier_locality_coverage(locality_code: str) -> bool:
    result = _client.table("courier_locality_coverage").delete().eq("locality_code", locality_code).execute()
    return bool(result.data)


def upsert_client_assignment(client_id: str, courier_id: str | None, assigned_by: str) -> None:
    if courier_id:
        _client.table("client_courier_assignment").upsert({
            "client_id": client_id,
            "courier_id": courier_id,
            "assigned_by": assigned_by,
        }, on_conflict="client_id").execute()
    else:
        _client.table("client_courier_assignment").delete().eq("client_id", client_id).execute()


def update_client_profile(client_id: str, payload: dict) -> bool:
    result = _client.table("clients").update(payload).eq("id", client_id).execute()
    return bool(result.data)


def list_a3_knowledge_index(limit: int = 20000) -> list[dict]:
    """Fichas de knowledge, paginando de a 1000 (tope por request de Supabase).

    Con `.limit(5000)` a secas devolvía 1000 de 1427 y al dashboard le faltaban 427 fichas
    (correo, nombre comercial, régimen) sin ningún error visible.
    """
    PAGE = 1000
    rows: list[dict] = []
    while len(rows) < limit:
        batch = (
            _client.table("clients_a3_knowledge")
            .select("*")
            .range(len(rows), min(len(rows) + PAGE, limit) - 1)
            .execute()
            .data
        ) or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
    return rows


def find_clients_by_professional(name: str | None, limit: int = 5) -> list[dict]:
    """Clientes donde trabaja el médico buscado, para identificar por el nombre del veterinario.

    El agente identifica CLIENTES (clínicas) contra `clients`, así que un veterinario que dice
    su propio nombre no se encontraba nunca aunque estuviera cargado: vive en
    `clients_a3_professionals`. Devuelve las clínicas del médico que SÍ son clientes activos,
    con la misma forma que `find_client_matches` para reusar el menú de selección.
    """
    query = _normalize_lookup_key(name)
    if not query or len(query) < 4:
        return []
    q_tokens = [t for t in query.split("_") if t and t not in _CLIENT_QUERY_STOPWORDS]
    if not q_tokens:
        return []
    q_compact = "".join(q_tokens)

    scored: list[tuple[float, str]] = []
    for row in list_client_professionals():
        score = _name_match_score(q_tokens, q_compact, row.get("professional_name"))
        if score:
            scored.append((score, _normalize_lookup_key(row.get("clinic_key"))))
    if not scored:
        return []

    best_by_clinic: dict[str, float] = {}
    for score, clinic_key in scored:
        if clinic_key and score > best_by_clinic.get(clinic_key, 0.0):
            best_by_clinic[clinic_key] = score

    clients_by_key = {
        _normalize_lookup_key(c["clinic_name"]): c
        for c in _fetch_all_active_clients("id, clinic_name, tax_id, phone, address, zone, email")
    }
    matches = [
        (score, clients_by_key[clinic_key])
        for clinic_key, score in best_by_clinic.items()
        if clinic_key in clients_by_key
    ]
    matches.sort(key=lambda pair: (-pair[0], pair[1]["clinic_name"]))
    return [client for _score, client in matches[:limit]]


def list_client_professionals(limit: int = 20000) -> list[dict]:
    """Médicos por clínica (clinic_key → profesional), paginando de a 1000.

    Supabase corta cada request en 1000 filas: con `.limit(5000)` a secas devolvía 1000 de
    1554 y los médicos del último tramo no se encontraban nunca (ni en la identificación por
    nombre del veterinario, ni en la ficha del dashboard).
    """
    PAGE = 1000
    rows: list[dict] = []
    while len(rows) < limit:
        batch = (
            _client.table("clients_a3_professionals")
            .select("clinic_key, professional_name, professional_card")
            .order("professional_name")
            .range(len(rows), min(len(rows) + PAGE, limit) - 1)
            .execute()
            .data
        ) or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
    return rows


def upsert_client_profile(payload: dict) -> None:
    _client.table("clients_a3_knowledge").upsert(payload, on_conflict="clinic_key").execute()


def list_clients_with_assignment(limit: int = 5000) -> list[dict]:
    """Todos los clientes con su motorizado, paginando de a 1000 (tope por request de Supabase).

    Antes traía solo `limit=500` de 804 clientes: el dashboard no mostraba a los 304 que caían
    después de la "L" por orden alfabético, y con ellos quedaban invisibles altas pendientes
    que recepción no podía aprobar.
    """
    PAGE = 1000
    rows: list[dict] = []
    while len(rows) < limit:
        batch = (
            _client.table("clients")
            .select(
                "id, clinic_name, tax_id, phone, address, zone, billing_type, is_active, email, "
                "client_courier_assignment(courier_id, couriers(id, name, phone, availability, is_active))"
            )
            .order("clinic_name")
            .range(len(rows), min(len(rows) + PAGE, limit) - 1)
            .execute()
            .data
        ) or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
    return rows


def list_requests(limit: int = 500, status: str | None = None) -> list[dict]:
    query = (
        _client.table("requests")
        .select("*, clients(clinic_name), couriers(name)")
        .order("requested_at", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return result.data or []


def list_sessions(limit: int = 500) -> list[dict]:
    result = (
        _client.table("telegram_sessions")
        .select(
            "external_chat_id, client_id, phase_current, intent_current, requires_handoff, "
            "handoff_area, captured_fields, updated_at, clients(clinic_name, phone)"
        )
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def list_request_events(request_id: str, limit: int = 20) -> list[dict]:
    result = (
        _client.table("request_events")
        .select("id, request_id, event_type, event_payload, created_at")
        .eq("request_id", request_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def update_request_status(
    request_id: str,
    status: str,
    assigned_courier_id: str | None = None,
    fallback_reason: str | None = None,
) -> dict | None:
    payload: dict = {"status": status}
    if assigned_courier_id is not None:
        payload["assigned_courier_id"] = assigned_courier_id
    if fallback_reason is not None:
        payload["fallback_reason"] = fallback_reason

    result = (
        _client.table("requests")
        .update(payload)
        .eq("id", request_id)
        .execute()
    )
    if not result.data:
        return None

    updated = result.data[0]
    _client.table("request_events").insert({
        "request_id": request_id,
        "event_type": "status_updated",
        "event_payload": {
            "source": "platform_api",
            "status": updated.get("status"),
            "assigned_courier_id": updated.get("assigned_courier_id"),
            "fallback_reason": updated.get("fallback_reason"),
        },
    }).execute()
    return updated


# ── Requests ──────────────────────────────────────────────────────────────────

# La columna requests.entry_channel tiene un CHECK constraint (requests_entry_channel_check)
# que hoy solo admite "telegram". El cliente entra por Telegram aunque el agente opere vía
# Chatwoot, así que el valor en la columna se mantiene dentro de lo permitido y el canal real
# del agente se preserva en el event_payload (source). Sin esto, cerrar una orden por Chatwoot
# lanzaba APIError 23514 y el turno final no respondía. Para distinguir Chatwoot también en la
# columna, migrar el constraint (db/migrations) y agregar "chatwoot" aquí.
_ALLOWED_ENTRY_CHANNELS = {"telegram"}


def create_request(chat_id: str, session: dict, ai_response: dict,
                   pedido_id: str | None = None) -> str | None:
    """Crea la orden. `pedido_id` la asocia a un pedido (decisión 011); si es None la orden
    queda suelta y se comporta exactamente como antes — así entran las del portal y las
    históricas."""
    intent = ai_response["intent"]
    fields = ai_response.get("captured_fields", {})
    client_id = session.get("client_id")
    now = datetime.now(timezone.utc)
    source_channel = session.get("channel") or "telegram"
    entry_channel = source_channel if source_channel in _ALLOWED_ENTRY_CHANNELS else "telegram"

    request_data = {
        "client_id":           client_id,
        "entry_channel":       entry_channel,
        "service_area":        INTENT_TO_SERVICE_AREA.get(intent, "unknown"),
        "intent":              intent,
        "priority":            "normal",
        "status":              "received",
        "exam_type":           fields.get("exam_type"),
        "patient_name":        fields.get("patient_name"),
        "species":             fields.get("species"),
        "patient_age":         fields.get("patient_age"),
        "owner_name":          fields.get("owner_name"),
        "pickup_address":      fields.get("pickup_address"),
        "requested_at":        now.isoformat(),
        "fallback_reason":     None,
        "assigned_courier_id": None,
        "scheduled_pickup_date": None,
    }

    if intent == "route_scheduling" and client_id:
        courier = get_courier_for_client(client_id)
        if courier:
            request_data["assigned_courier_id"] = courier["id"]
            request_data["status"] = "assigned"
            request_data["scheduled_pickup_date"] = get_scheduled_pickup_date(now).isoformat()
        else:
            request_data["status"] = "error_pending_assignment"
            request_data["fallback_reason"] = "no_courier_assigned"

    elif intent in ("accounting", "new_client"):
        request_data["status"] = "received"
        request_data["fallback_reason"] = ai_response.get("handoff_area")

    if pedido_id:
        request_data["pedido_id"] = pedido_id

    result = _client.table("requests").insert(request_data).execute()
    if not result.data:
        return None

    request_id = result.data[0]["id"]
    if pedido_id:
        touch_pedido(pedido_id)
    order_number = result.data[0].get("order_number")  # generado por la BB (None si falta la migración)
    event_payload = {
        "source":   source_channel,
        "chat_id":  chat_id,
        "intent":   intent,
        "priority": "normal",
        "payment_method": fields.get("payment_method"),
    }
    if intent == "route_scheduling":
        event_payload["service_order"] = _service_order_event_payload(fields, now)
    profile_payload = _profile_event_payload(fields)
    if profile_payload:
        event_payload["profile"] = profile_payload

    _client.table("request_events").insert({
        "request_id":     request_id,
        "event_type":     "created",
        "event_payload":  event_payload,
    }).execute()

    # Se devuelve el event_payload (con `profile` y `service_order`) para que la capa de
    # facturación (app/billing.py) arme las líneas sin reconstruir la lógica de catálogo.
    return {"request_id": request_id, "order_number": order_number, "event_payload": event_payload}


# ── Pedidos (decisión 011) ──────────────────────────────────────────────────────
# El PEDIDO agrupa las órdenes de una sesión de carga y es la unidad que se factura: una
# forma de pago y una factura para todas sus órdenes. Estas funciones son la capa de datos;
# el flujo conversacional las usa en una etapa posterior. Con `pedido_id` NULL una orden se
# comporta exactamente como antes, así que nada de esto altera el comportamiento actual.

def create_pedido(client_id: str | None, chat_id: str, entry_channel: str = "telegram") -> dict | None:
    """Abre un pedido. Devuelve {id, pedido_number} o None si la inserción falla."""
    result = _client.table("pedidos").insert({
        "client_id":        client_id,
        "external_chat_id": chat_id,
        "entry_channel":    entry_channel,
        "status":           "abierto",
    }).execute()
    if not result.data:
        return None
    row = result.data[0]
    return {"id": row["id"], "pedido_number": row.get("pedido_number")}


def get_open_pedido(chat_id: str) -> dict | None:
    """Pedido abierto de un chat, si lo hay. Un chat tiene a lo sumo uno."""
    if not chat_id:
        return None
    result = (
        _client.table("pedidos")
        .select("*")
        .eq("external_chat_id", chat_id)
        .eq("status", "abierto")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def touch_pedido(pedido_id: str) -> None:
    """Marca actividad en el pedido. Es la base del cierre por inactividad: sin esto, un
    pedido con órdenes agregadas parecería abandonado desde su creación."""
    if not pedido_id:
        return
    _client.table("pedidos").update(
        {"updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", pedido_id).execute()


def close_pedido(pedido_id: str, payment_method: str | None = None) -> dict | None:
    """Cierra el pedido: ya no admite más órdenes. La factura se emite aparte, y recién
    cuando se emite el estado pasa a 'facturado' (ver mark_pedido_invoiced)."""
    if not pedido_id:
        return None
    now = datetime.now(timezone.utc).isoformat()
    payload = {"status": "cerrado", "closed_at": now, "updated_at": now}
    if payment_method:
        payload["payment_method"] = payment_method
    result = _client.table("pedidos").update(payload).eq("id", pedido_id).execute()
    return result.data[0] if result.data else None


def mark_pedido_invoiced(pedido_id: str, alegra_invoice_id: str | None) -> None:
    """Deja el id de la factura en el pedido. Separado de close_pedido a propósito: un
    pedido puede quedar cerrado y sin facturar si Alegra falla, y eso tiene que verse."""
    if not pedido_id:
        return
    _client.table("pedidos").update({
        "status":            "facturado",
        "alegra_invoice_id": alegra_invoice_id,
        "updated_at":        datetime.now(timezone.utc).isoformat(),
    }).eq("id", pedido_id).execute()


def list_pedidos_for_dashboard(limit: int = 60) -> list[dict]:
    """Pedidos con el nombre del cliente y sus órdenes, para la plataforma.

    Hasta ahora el pedido solo existía dentro del agente: el dashboard no lo conocía. Eso
    dejaba sin respaldo humano al barrido automático — un pedido abandonado sin tráfico
    posterior quedaba abierto e invisible. Los `abierto` van primero porque son los que
    alguien tiene que mirar."""
    try:
        pedidos = (
            _client.table("pedidos")
            .select("*, clients(clinic_name)")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ).data or []
    except Exception:
        return []
    if not pedidos:
        return []

    ids = [p["id"] for p in pedidos]
    try:
        ordenes = (
            _client.table("requests")
            .select("id, pedido_id, order_number, patient_name, species, exam_type, status")
            .in_("pedido_id", ids)
            .order("requested_at")
            .execute()
        ).data or []
    except Exception:
        ordenes = []

    por_pedido: dict[str, list[dict]] = {}
    for orden in ordenes:
        por_pedido.setdefault(orden.get("pedido_id"), []).append(orden)

    for pedido in pedidos:
        cliente = pedido.get("clients") if isinstance(pedido.get("clients"), dict) else {}
        pedido["client_name"] = cliente.get("clinic_name") or "Cliente"
        pedido["orders"] = por_pedido.get(pedido["id"], [])
        pedido["orders_count"] = len(pedido["orders"])
    pedidos.sort(key=lambda p: (p.get("status") != "abierto", p.get("created_at") or ""), reverse=False)
    return pedidos


def get_pedido_profiles(pedido_id: str, con_request_id: bool = False) -> list:
    """Los `profile` de cada orden del pedido, reconstruidos desde `request_events`.

    El agente los lleva en la sesión (`_pedido_profiles`) mientras la conversación está viva,
    pero el dashboard no tiene ese estado: para facturar un pedido a mano hay que releerlos
    del evento `created`, donde quedaron ya resueltos contra el catálogo.

    Con `con_request_id=True` devuelve `(request_id, profile)` para poder poner el paciente
    de CADA orden en su línea de la factura."""
    ordenes = list_pedido_requests(pedido_id)
    if not ordenes:
        return []
    try:
        eventos = (
            _client.table("request_events")
            .select("request_id, event_type, event_payload")
            .in_("request_id", [o["id"] for o in ordenes])
            .eq("event_type", "created")
            .execute()
        ).data or []
    except Exception:
        return []
    perfiles = []
    for evento in eventos:
        perfil = (evento.get("event_payload") or {}).get("profile")
        if perfil:
            perfiles.append((evento.get("request_id"), perfil) if con_request_id else perfil)
    return perfiles


def get_pedido(pedido_id: str) -> dict | None:
    if not pedido_id:
        return None
    try:
        result = _client.table("pedidos").select("*").eq("id", pedido_id).limit(1).execute()
        return (result.data or [None])[0]
    except Exception:
        return None


def list_stale_pedidos(horas: int = 1, limit: int = 20) -> list[dict]:
    """Pedidos ABIERTOS sin actividad hace más de `horas`.

    El cliente que carga órdenes y se va sin cerrar deja el pedido abierto y sin facturar.
    Decisión del usuario (2026-08-12): pasada una hora se cierra y se factura como si hubiera
    terminado, y se avisa a operaciones. `touch_pedido` mantiene `updated_at` al día, así que
    un pedido con órdenes agregadas no se considera abandonado desde que nació."""
    corte = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    try:
        result = (
            _client.table("pedidos")
            .select("*")
            .eq("status", "abierto")
            .lt("updated_at", corte)
            .order("updated_at")
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def list_pedido_requests(pedido_id: str) -> list[dict]:
    """Órdenes del pedido, en orden de carga. Es lo que se factura junto."""
    if not pedido_id:
        return []
    result = (
        _client.table("requests")
        .select("*")
        .eq("pedido_id", pedido_id)
        .order("requested_at")
        .execute()
    )
    return result.data or []


def get_last_order_for_client(client_id: str) -> dict | None:
    """Última solicitud del cliente, para devolver su número de orden por chat."""
    if not client_id:
        return None
    result = (
        _client.table("requests")
        .select("*")
        .eq("client_id", client_id)
        .order("requested_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
