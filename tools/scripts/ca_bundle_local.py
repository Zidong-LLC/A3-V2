"""Certificados de confianza para correr la plataforma en un equipo con antivirus que
intercepta HTTPS (Kaspersky, Avast, ESET…) o detrás de un proxy corporativo.

Síntoma: el bot contesta el saludo y el menú (no usan IA) pero se calla en el primer
turno con IA; en el log de Flask: «openai.APIConnectionError … CERTIFICATE_VERIFY_FAILED:
self-signed certificate in certificate chain». El antivirus re-firma la conexión con su
propia raíz: Windows confía en ella, Python (certifi) no.

Arma `.certs/ca-bundle-local.pem` = certifi + raíces del almacén de Windows, y basta con
agregar al .env la línea que imprime (SSL_CERT_FILE). Solo para desarrollo local: el .env
no se sube y en Render no hay antivirus.

Uso: python tools/scripts/ca_bundle_local.py
"""
import ssl
import sys
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[2]
SALIDA = ROOT / ".certs" / "ca-bundle-local.pem"


def main() -> int:
    if not hasattr(ssl, "enum_certificates"):
        print("Solo hace falta en Windows: en Linux/Mac Python usa el almacén del sistema.")
        return 0
    raices = {ssl.DER_cert_to_PEM_cert(der) for almacen in ("ROOT", "CA")
              for der, codificacion, _ in ssl.enum_certificates(almacen) if codificacion == "x509_asn"}
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(Path(certifi.where()).read_text(encoding="utf-8") + "\n" + "\n".join(sorted(raices)),
                      encoding="utf-8")
    print(f"{len(raices)} certificados de Windows agregados a {SALIDA}")
    print(f"Agregar al .env:  SSL_CERT_FILE={SALIDA.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
