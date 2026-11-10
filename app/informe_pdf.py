"""¿El informe en PDF es de la veterinaria a la que se le está subiendo?

A3 elige a mano la veterinaria de cada carga (pedido del 10/11: la plataforma no reparte
informes por su cuenta). Esto es la red de abajo: los informes de A3 traen impreso el NIT de
la veterinaria pegado a la palabra «Nit». Si el PDF muestra el NIT de OTRA, se frena antes de
llegar al portal equivocado — el error típico de arrastrar cien archivos y que se cuele uno de
otra clínica. Si el PDF no trae un NIT legible (escaneado, otro formato), manda la persona.
"""
import io
import logging
import re

logger = logging.getLogger(__name__)

# El NIT de A3 sale en el encabezado de todos sus informes: no dice de quién es el informe.
NIT_A3 = "900296338"

# Con puntos de miles (900.296.338) o corrido (901915997), con o sin dígito de verificación.
_NUMERO = r"(\d{1,3}(?:\.\d{3}){2,3}|\d{6,12})(?:\s?-\s?\d)?"
# Solo el número PEGADO a la etiqueta: Anarvet imprime «901915997-3Nit» y «Nit: 900.296.338-9».
# Un número suelto no sirve: el informe está lleno de valores, fechas y n° de solicitud.
# «nit\b» deja afuera a «Nitrógeno», que aparece en casi todos los perfiles.
_JUNTO_A_NIT = re.compile(rf"\bnit\b\W{{0,3}}{_NUMERO}|{_NUMERO}\W{{0,3}}nit\b", re.IGNORECASE)


def _base(nit: str | None) -> str:
    """Solo dígitos y sin el verificador de después del guion."""
    return re.sub(r"\D", "", str(nit or "").split("-")[0])


def _mismo(a: str, b: str) -> bool:
    """Mismo contribuyente: iguales, o uno es el otro con el verificador pegado sin guion."""
    if a == b:
        return True
    corto, largo = sorted((a, b), key=len)
    return len(largo) == len(corto) + 1 and largo.startswith(corto)


def nits_en_texto(texto: str) -> set[str]:
    """Los NIT que el informe muestra junto a la etiqueta «Nit», sin el de A3."""
    encontrados = set()
    for match in _JUNTO_A_NIT.finditer(texto or ""):
        base = _base(match.group(1) or match.group(2))
        if base and not _mismo(base, NIT_A3):
            encontrados.add(base)
    return encontrados


def nit_ajeno(texto: str, nit_cliente: str | None) -> str | None:
    """El NIT de otra veterinaria que muestra el informe, o None si no hay por qué frenar.

    Sin NIT en el informe o sin NIT del cliente no hay contra qué comparar: decide la persona."""
    nits = nits_en_texto(texto)
    cliente = _base(nit_cliente)
    if not nits or not cliente or any(_mismo(n, cliente) for n in nits):
        return None
    return sorted(nits)[0]


def texto_de(pdf: bytes) -> str:
    """Texto de la primera página, donde va el encabezado con el NIT. Vacío si no se lee."""
    try:
        from pypdf import PdfReader

        paginas = PdfReader(io.BytesIO(pdf)).pages
        return (paginas[0].extract_text() or "") if len(paginas) else ""
    except Exception as exc:  # noqa: BLE001 — un PDF raro no frena la carga: decide la persona
        logger.warning("No se pudo leer el texto del informe para verificar el NIT: %s", exc)
        return ""
