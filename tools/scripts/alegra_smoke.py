"""Prueba de humo de la integración con Alegra (Fase 0/1).

Valida credenciales y conectividad contra la cuenta configurada en .env y, opcionalmente,
prueba el alta idempotente de un contacto por NIT. NO toca producción: solo lee/escribe
en la cuenta cuyas credenciales estén en ALEGRA_EMAIL/ALEGRA_API_TOKEN (usar la cuenta
de PRUEBAS primero).

Uso:
    python scripts/alegra_smoke.py                 # solo ping de conectividad
    python scripts/alegra_smoke.py --contact       # ping + get_or_create de un contacto demo
"""

import sys

from app.config import ALEGRA_EMAIL, ALEGRA_BASE_URL
from app.services import alegra


def main() -> int:
    if not ALEGRA_EMAIL:
        print("[FALLO] Falta ALEGRA_EMAIL en .env. Completa las credenciales de la cuenta de pruebas.")
        return 1

    print(f"-> Probando Alegra como '{ALEGRA_EMAIL}' contra {ALEGRA_BASE_URL}")
    try:
        alegra.ping()
        print("[OK] Conectividad y credenciales OK (GET /contacts).")
    except alegra.AlegraError as e:
        print(f"[FALLO] No se pudo conectar con Alegra:\n  {e}")
        return 1

    if "--contact" in sys.argv:
        nit = "900123456"
        try:
            contact = alegra.get_or_create_contact(nit, "Veterinaria Demo A3", {"email": "demo@a3.test"})
            print(f"[OK] Contacto NIT {nit} -> id={contact.get('id')} name={contact.get('name')}")
        except alegra.AlegraError as e:
            print(f"[FALLO] get_or_create_contact:\n  {e}")
            return 1

    print("Listo. Cuando esto pase contra tu cuenta de pruebas, conectamos las Fases 2-4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
