import re
import difflib
from datetime import datetime, timezone
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from app.rules import INTENT_TO_SERVICE_AREA, calculate_profile_adjusted_total, get_scheduled_pickup_date

_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ── Session ───────────────────────────────────────────────────────────────────

def get_or_create_session(chat_id: str) -> dict:
    result = _client.table("telegram_sessions").select("*").eq("external_chat_id", chat_id).execute()
    if result.data:
        return result.data[0]
    new_session = {
        "channel":        "telegram",
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

    select_fields = "id, clinic_name, tax_id, phone, address, zone"
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

    covered = sum(
        1 for qt in q_tokens
        if any(qt == ct or (len(qt) >= 3 and ct.startswith(qt)) for ct in c_tokens)
    )
    coverage = covered / len(q_tokens)
    compact_hit = len(q_compact) >= 4 and q_compact in c_compact

    # Relevante solo si están todas las palabras, o el texto aparece pegado.
    if coverage < 1.0 and not compact_hit:
        return 0.0

    ratio = difflib.SequenceMatcher(None, q_compact, c_compact).ratio()
    return coverage + (0.5 if compact_hit else 0.0) + ratio * 0.5


def find_client_matches(name: str | None = None, limit: int = 5) -> list[dict]:
    """Coincidencias de clientes ordenadas por similitud al texto buscado.
    La más parecida queda primera (tolera errores de escritura y palabras sueltas
    como 'animal vet' -> 'Animal's Vet House Centenario')."""
    if not name:
        return []
    q = _normalize_lookup_key(name)
    q_tokens = [t for t in q.split("_") if t]
    q_compact = q.replace("_", "")
    if not q_tokens:
        return []

    scored: list[tuple[float, str, dict]] = []
    for c in _fetch_all_active_clients("id, clinic_name, tax_id, phone, address, zone"):
        score = _name_match_score(q_tokens, q_compact, c.get("clinic_name"))
        if score > 0:
            scored.append((score, c.get("clinic_name") or "", c))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [c for _, _, c in scored[:limit]]


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


def create_pending_client_review(client_payload: dict, review_payload: dict) -> dict:
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
        "entry_channel": "telegram",
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
    """Returns a compact catalog string for AI context injection."""
    query = _client.table("catalog_profiles").select("code, name, category, description, price").eq("is_active", True)
    if species and species.lower() in ("canino", "felino"):
        query = query.in_("species", [species.lower(), "ambos"])
    rows = query.order("code").execute().data
    if not rows:
        return ""

    from collections import defaultdict
    by_cat: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        description = r.get("description") or "sin detalle"
        by_cat[r["category"]].append(f"{r['code']}-{r['name']}: {description} ${r['price']//1000}k")

    label = f" ({species})" if species else ""
    lines = [f"Catálogo A3{label}:"]
    for cat, items in by_cat.items():
        lines.append(f"[{cat}] " + ", ".join(items))
    return "\n".join(lines)


def find_catalog_profile(value: str | None, species: str | None = None) -> dict | None:
    lookup = _normalize_lookup_key(value)
    if not lookup:
        return None

    query = (
        _client.table("catalog_profiles")
        .select("code, name, category, species, description, price")
        .eq("is_active", True)
        .limit(5000)
    )
    species_key = (species or "").strip().lower()
    if species_key in ("canino", "felino"):
        query = query.in_("species", [species_key, "ambos"])

    rows = query.execute().data or []
    for row in rows:
        if _catalog_profile_matches(value, row):
            return row
    return None


def find_catalog_profiles(value: str | None, species: str | None = None, limit: int = 20) -> list[dict]:
    lookup = _normalize_lookup_key(value)
    if not lookup:
        return []

    query = (
        _client.table("catalog_profiles")
        .select("code, name, category, species, description, price")
        .eq("is_active", True)
        .limit(5000)
    )
    species_key = (species or "").strip().lower()
    if species_key in ("canino", "felino"):
        query = query.in_("species", [species_key, "ambos"])

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
    clean_codes = [str(code).strip() for code in codes if str(code or "").strip()]
    if not clean_codes:
        return []

    query = (
        _client.table("catalog_profiles")
        .select("code, name, category, species, description, price")
        .in_("code", clean_codes)
        .eq("is_active", True)
    )
    species_key = (species or "").strip().lower()
    if species_key in ("canino", "felino"):
        query = query.in_("species", [species_key, "ambos"])

    rows = query.execute().data or []
    by_code = {str(row.get("code")): row for row in rows}
    return [by_code[code] for code in clean_codes if code in by_code]


def get_individual_tests_context(species: str | None = None) -> str:
    """Compact catalog of individual tests for AI context (custom profile flow)."""
    query = _client.table("catalog_tests").select("code, name, category, price").eq("is_active", True)
    if species and species.lower() in ("canino", "felino"):
        query = query.in_("species", [species.lower(), "ambos"])
    rows = query.order("code").execute().data
    if not rows:
        return ""

    from collections import defaultdict
    by_cat: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(f"{r['code']}-{r['name']} ${r['price']//1000}k")

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
            if lookup == code_key or lookup == name_key or lookup in name_key:
                code = row.get("code")
                if code and code not in seen:
                    matched.append(row)
                    seen.add(code)
                break
    return matched


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


def find_diagnostic_label(query: str | None) -> str | None:
    """Encuentra la etiqueta diagnóstica que mejor corresponde al texto del usuario.
    Coincidencia por clave normalizada (exacta o contenida)."""
    key = _normalize_lookup_key(query)
    if not key:
        return None
    labels = list_diagnostic_labels()
    label_keys = {label: _normalize_lookup_key(label) for label in labels}
    for label, lk in label_keys.items():
        if lk == key:
            return label
    # Solo si la etiqueta COMPLETA aparece en el texto (ej. "perfil convulsivo canino"),
    # no al revés (una palabra suelta como "canino" no debe matchear "convulsivo canino").
    for label, lk in label_keys.items():
        if lk and lk in key:
            return label
    return None


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


def delete_custom_profile(profile_id: str) -> bool:
    result = _client.table("client_custom_profiles").delete().eq("id", profile_id).execute()
    return bool(result.data)


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


def list_a3_knowledge_index(limit: int = 5000) -> list[dict]:
    result = _client.table("clients_a3_knowledge").select("*").limit(limit).execute()
    return result.data or []


def upsert_client_profile(payload: dict) -> None:
    _client.table("clients_a3_knowledge").upsert(payload, on_conflict="clinic_key").execute()


def list_clients_with_assignment(limit: int = 500) -> list[dict]:
    result = (
        _client.table("clients")
        .select(
            "id, clinic_name, tax_id, phone, address, zone, billing_type, is_active, "
            "client_courier_assignment(courier_id, couriers(id, name, phone, availability, is_active))"
        )
        .order("clinic_name")
        .limit(limit)
        .execute()
    )
    return result.data or []


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

def create_request(chat_id: str, session: dict, ai_response: dict) -> str | None:
    intent = ai_response["intent"]
    fields = ai_response.get("captured_fields", {})
    client_id = session.get("client_id")
    now = datetime.now(timezone.utc)

    request_data = {
        "client_id":           client_id,
        "entry_channel":       "telegram",
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

    result = _client.table("requests").insert(request_data).execute()
    if not result.data:
        return None

    request_id = result.data[0]["id"]
    order_number = result.data[0].get("order_number")  # generado por la BB (None si falta la migración)
    event_payload = {
        "source":   "telegram",
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

    return {"request_id": request_id, "order_number": order_number}


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
