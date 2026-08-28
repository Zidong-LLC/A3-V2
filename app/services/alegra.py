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

from app.config import ALEGRA_EMAIL, ALEGRA_API_TOKEN, ALEGRA_BASE_URL, ALEGRA_COUNTRY

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

# Campos que exige Alegra ARGENTINA en su lugar: identificación CUIT (acepta el NIT
# colombiano tal cual, no valida el dígito verificador), condición de IVA obligatoria
# en el contacto y unidad de medida obligatoria en el ítem.
DEFAULT_IVA_CONDITION = "IVA_RESPONSABLE"
DEFAULT_UNIT = "unit"

_country: str | None = None


def account_country() -> str:
    """País de la cuenta ('colombia' | 'argentina' | ...). Define qué campos exige
    Alegra al CREAR contactos e ítems. Se resuelve una sola vez: ALEGRA_COUNTRY manda,
    si no se lee de /company. Ante cualquier falla asume Colombia, que es el negocio
    real de A3. Solo se invoca en los caminos de creación, nunca en las búsquedas."""
    global _country
    if ALEGRA_COUNTRY:
        return ALEGRA_COUNTRY
    if _country is None:
        try:
            company = _request("GET", "/company")
            version = (company or {}).get("applicationVersion") if isinstance(company, dict) else None
            _country = str(version or "colombia").strip().lower()
        except AlegraError:
            _country = "colombia"
    return _country


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
    if account_country() == "argentina":
        body = {
            "name": clinic_name,
            "identificationObject": {"number": number, "type": "CUIT"},
            "ivaCondition": DEFAULT_IVA_CONDITION,
            "type": ["client"],
        }
    else:
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
    if account_country() == "argentina":
        body["unit"] = DEFAULT_UNIT
    created = _request("POST", "/items", body)
    return created if isinstance(created, dict) else {}


def list_invoices(
    start: int = 0,
    limit: int = 30,
    order_field: str = "date",
    order_direction: str = "DESC",
    filters: dict | None = None,
) -> list[dict]:
    """Lista facturas de venta (solo lectura) con paginación y orden.

    `filters` admite las claves que soporta la API de Alegra: `date` (YYYY-MM-DD),
    `dueDate`, `client` (id de contacto), `status`. Devuelve la lista de facturas crudas;
    el mapeo a fila de dashboard vive en `app/billing.py`. No emite ni modifica nada."""
    params = {
        "start": start,
        "limit": limit,
        "order_field": order_field,
        "order_direction": order_direction,
    }
    for key, value in (filters or {}).items():
        if value not in (None, ""):
            params[key] = value
    query = urllib.parse.urlencode(params)
    result = _request("GET", f"/invoices?{query}")
    return result if isinstance(result, list) else result.get("data", [])


def get_invoice(invoice_id: int | str) -> dict:
    """Trae el detalle completo de una factura por id (solo lectura)."""
    result = _request("GET", f"/invoices/{urllib.parse.quote(str(invoice_id))}")
    return result if isinstance(result, dict) else {}


def get_invoice_pdf_url(invoice: dict) -> str | None:
    """Resuelve la URL del PDF desde el objeto factura de Alegra, si está disponible.

    Alegra expone el PDF en distintos lugares según el plan/estado; se prueban las claves
    conocidas en orden. Devuelve None si la factura (p. ej. un borrador) aún no tiene PDF."""
    if not isinstance(invoice, dict):
        return None
    candidates = [
        invoice.get("pdf"),
        (invoice.get("files") or {}).get("pdf") if isinstance(invoice.get("files"), dict) else None,
    ]
    printed = invoice.get("printedTemplate") or invoice.get("printTemplate")
    if isinstance(printed, dict):
        candidates.append(printed.get("url"))
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def create_invoice(
    client_id: int | str,
    items: list[dict],
    date: str,
    due_date: str | None = None,
    status: str | None = None,
    anotation: str | None = None,
) -> dict:
    """Crea una factura de venta. `items` son líneas ya mapeadas:
    [{"id": <alegra_item_id>, "quantity": int, "price": int}]. El mapeo del catálogo vive
    fuera de este módulo (capa de negocio). Sin `status`, Alegra la deja en borrador para
    cuentas sin facturación electrónica: la emisión DIAN se habilita aparte.

    `anotation` es el campo «Notas» que se imprime en la factura. A3 lo usa para escribir
    la veterinaria o el médico cuando la factura sale a Consumidor Final."""
    body = {
        "date": date,
        "dueDate": due_date or date,
        "client": client_id,
        "items": items,
    }
    if status:
        body["status"] = status
    if anotation:
        body["anotation"] = anotation
    return _request("POST", "/invoices", body)
