"""Cliente de la API de Alegra (facturación electrónica DIAN).

Aislado: no importa `app/agent.py` ni `app/rules.py` (ver app/services/CLAUDE.md).
Solo I/O y manejo de errores; la lógica de negocio vive fuera. La integración avanza
por fases (ver docs/decisions/009). Esta entrega cubre la Fase 1: conectividad y
sincronización de contactos por NIT. La facturación llega en la Fase 2.

Autenticación: HTTP Basic `base64(email:api_token)` contra ALEGRA_BASE_URL.
El feature flag ALEGRA_ENABLED lo evalúa el llamador (el agente); este módulo solo
ejecuta I/O cuando se le invoca, igual que los scripts de prueba.
"""

import json
import base64
import urllib.error
import urllib.parse
import urllib.request

from app.config import ALEGRA_EMAIL, ALEGRA_API_TOKEN, ALEGRA_BASE_URL

_AUTH = base64.b64encode(f"{ALEGRA_EMAIL}:{ALEGRA_API_TOKEN}".encode()).decode()
_HEADERS = {
    "Authorization": f"Basic {_AUTH}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


class AlegraError(RuntimeError):
    """Falla al hablar con la API de Alegra. Lleva contexto útil para el log."""


def _request(method: str, path: str, body: dict | None = None) -> dict | list:
    """Llama a la API y devuelve el JSON parseado. Re-lanza con contexto en error."""
    data = json.dumps(body).encode() if body is not None else None
    url = f"{ALEGRA_BASE_URL}{path}"
    req = urllib.request.Request(url, data=data, headers=_HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise AlegraError(f"Alegra {method} {path} -> HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise AlegraError(f"Alegra {method} {path} -> red: {e.reason}") from e


def ping() -> bool:
    """Valida credenciales/conectividad con una lectura mínima de contactos.
    Lanza AlegraError si las credenciales o la red fallan."""
    _request("GET", "/contacts?limit=1")
    return True


def find_contact_by_nit(tax_id: str) -> dict | None:
    """Busca un contacto por su identificación (NIT). Devuelve el primero o None."""
    if not tax_id:
        return None
    nit = str(tax_id).strip()
    result = _request("GET", f"/contacts?identification={urllib.parse.quote(nit)}")
    rows = result if isinstance(result, list) else result.get("data", [])
    return rows[0] if rows else None


# Campos fiscales que Alegra Colombia exige al crear un contacto. Estructura tomada del
# ejemplo oficial de Colombia (identificationObject + regime + kindOfPerson). Son datos
# del cliente que Supabase no guarda; se usan estos defaults y se sobrescriben por contacto.
#   - identificationObject: {number, dv, type:"NIT"} — guarda el NIT y permite buscarlo luego.
#   - regime (condición frente al IVA): SIMPLIFIED_REGIME ("No responsable del IVA") |
#     COMMON_REGIME ("Responsable del IVA") | NATIONAL_CONSUMPTION_TAX | etc.
#   - kindOfPerson: LEGAL_ENTITY (persona jurídica) | PERSON_ENTITY (natural) | OTHER_ENTITY.
#
# PENDIENTE DE VALIDAR contra una cuenta Alegra de COLOMBIA. La cuenta de pruebas usada
# resultó ser de Argentina (company.applicationVersion="argentina"): rechazaba los tipos
# de identificación colombianos (error 2039) y descartaba el NIT. Confirmar estos campos
# y valores cuando exista la cuenta Colombia (la del cliente ya lo es).
DEFAULT_REGIME = "SIMPLIFIED_REGIME"
DEFAULT_KIND_OF_PERSON = "LEGAL_ENTITY"


def _split_nit(tax_id: str) -> tuple[str, str | None]:
    """Separa un NIT colombiano en número y dígito de verificación. '900123456-7'
    -> ('900123456', '7'); '900123456' -> ('900123456', None)."""
    raw = str(tax_id).strip()
    if "-" in raw:
        number, dv = raw.rsplit("-", 1)
        return number.strip(), dv.strip() or None
    return raw, None


def get_or_create_contact(
    tax_id: str,
    clinic_name: str,
    extra: dict | None = None,
    regime: str = DEFAULT_REGIME,
    kind_of_person: str = DEFAULT_KIND_OF_PERSON,
) -> dict:
    """Idempotente por NIT: devuelve el contacto existente o lo crea.

    No registra clientes nuevos del negocio (eso siempre escala a recepción); solo
    asegura que un cliente YA identificado en Supabase exista como contacto en Alegra
    para poder facturarle. `extra` permite enriquecer (email, teléfono, dirección).
    `regime`/`kind_of_person` son los campos fiscales que Colombia exige."""
    existing = find_contact_by_nit(tax_id)
    if existing:
        return existing
    number, dv = _split_nit(tax_id)
    if number != str(tax_id).strip():
        existing = find_contact_by_nit(number)
        if existing:
            return existing
    identification = {"number": number, "type": "NIT"}
    if dv:
        identification["dv"] = dv
    body = {
        "name": clinic_name,
        "identificationObject": identification,
        "regime": regime,
        "kindOfPerson": kind_of_person,
        "type": ["client"],
    }
    if extra:
        body.update({k: v for k, v in extra.items() if v})
    created = _request("POST", "/contacts", body)
    return created if isinstance(created, dict) else {}


def find_item_by_reference(reference: str) -> dict | None:
    """Busca un ítem facturable por su código de referencia (el código del análisis/perfil
    de A3). Devuelve el primero o None."""
    if not reference:
        return None
    ref = str(reference).strip()
    result = _request("GET", f"/items?reference={urllib.parse.quote(ref)}")
    rows = result if isinstance(result, list) else result.get("data", [])
    return rows[0] if rows else None


def get_or_create_item(reference: str, name: str, price: int) -> dict:
    """Idempotente por `reference`: devuelve el ítem existente en Alegra o lo crea con su
    precio. Así el catálogo de Supabase (catalog_tests/catalog_profiles) se mapea a ítems
    facturables una sola vez y se reusa por su código."""
    existing = find_item_by_reference(reference)
    if existing:
        return existing
    body = {"name": name, "reference": str(reference), "price": price}
    created = _request("POST", "/items", body)
    return created if isinstance(created, dict) else {}


def create_invoice(
    client_id: int | str,
    items: list[dict],
    date: str,
    due_date: str | None = None,
    status: str | None = None,
) -> dict:
    """Crea una factura de venta. `items` son líneas ya mapeadas:
    [{"id": <alegra_item_id>, "quantity": int, "price": int}]. El mapeo del catálogo vive
    fuera de este módulo (capa de negocio). Sin `status`, Alegra la deja en borrador para
    cuentas sin facturación electrónica: la emisión DIAN se habilita aparte."""
    body = {
        "date": date,
        "dueDate": due_date or date,
        "client": client_id,
        "items": items,
    }
    if status:
        body["status"] = status
    return _request("POST", "/invoices", body)
