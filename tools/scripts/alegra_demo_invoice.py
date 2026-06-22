"""Demo END-TO-END de facturación en Alegra (Fase 2), camino de escritura.

Simula el `event_payload.profile` de una orden YA cerrada (perfil base + un análisis
agregado, como lo arma `db.create_request`) y crea la factura BORRADOR en Alegra usando la
misma capa que el agente (`app/billing.py`). No toca Supabase ni producción: solo escribe
en la cuenta cuyas credenciales estén en el .env (usar la de PRUEBAS).

Uso:
    PYTHONPATH=. python scripts/alegra_demo_invoice.py
"""

from datetime import datetime

from app import billing
from app.config import APP_TIMEZONE
from app.services import alegra

# Cliente YA identificado (regla de negocio: el bot NO da de alta clientes nuevos; factura
# a uno existente con NIT). Reusa el contacto demo del smoke test.
CLIENT_NIT = "900123456"
CLIENT_NAME = "Veterinaria Demo A3"

# `profile` tal como lo persiste db._profile_event_payload al cerrar una orden:
# perfil base 401 ($40k) + análisis agregado 0201 Glucosa ($18k) = $58k.
PROFILE_PAYLOAD = {
    "base_profile": {"code": "401", "name": "Perfil Canino I", "price": 40000},
    "added_tests": [{"code": "0201", "name": "Glucosa", "price": 18000}],
    "removed_tests": [],
    "total_estimated": 58000,
}


def main() -> int:
    print(f"-> Facturando una orden demo para NIT {CLIENT_NIT} ({CLIENT_NAME})\n")

    lines = billing.build_invoice_lines(PROFILE_PAYLOAD)
    print("Líneas de factura armadas desde el perfil de la orden:")
    for ln in lines:
        print(f"  - {ln['reference']:<14} {ln['name']:<22} x{ln['quantity']}  ${ln['price']:,}")
    total = sum(ln["price"] * ln["quantity"] for ln in lines)
    print(f"  TOTAL líneas: ${total:,}\n")

    try:
        result = billing.invoice_order(
            CLIENT_NIT, CLIENT_NAME, lines,
            datetime.now(APP_TIMEZONE).date().isoformat(),
            {"email": "demo@a3.test"},
        )
    except alegra.AlegraError as e:
        print(f"[FALLO] Alegra rechazó la factura:\n  {e}")
        return 1

    if not result:
        print("[FALLO] No se generó factura (¿sin líneas o sin NIT?).")
        return 1

    print("[OK] Factura BORRADOR creada en Alegra:")
    print(f"  contact_id : {result['contact_id']}")
    print(f"  invoice_id : {result['invoice_id']}")
    print(f"  número     : {result['number']}")
    print(f"  total      : {result['total']}")

    # Releer la factura para confirmar el estado (borrador) directamente desde Alegra.
    fetched = alegra._request("GET", f"/invoices/{result['invoice_id']}")
    print(f"  estado     : {fetched.get('status')}")
    print("\nEste mismo `result` es lo que el agente guarda como evento 'alegra_invoiced' "
          "en request_events para que la plataforma lo refleje.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
