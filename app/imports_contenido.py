"""Reconocer las columnas por su CONTENIDO cuando el archivo no trae encabezado.

Pregunta del cliente (29/10): «si cargo la lista con el número del análisis y al lado el
precio, ¿lo detecta?». Sin encabezado, la primera fila son datos y antes no se reconocía
nada. Acá se mira qué hay en cada columna (códigos, precios, NIT, celulares, correos,
direcciones, texto) y se inventan los encabezados que la carga ya entiende.
Lógica pura, sin I/O.
"""
import re

from app.imports import precio

_FILAS_A_MIRAR = 30
_MINIMO = 0.6  # proporción de celdas (no vacías) que deben coincidir para asignar el rol
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DIRECCION = re.compile(r"(#|\bn[°º]|^(cl|cll|calle|cra|kr|cr|carrera|av|avenida|dg|diag|diagonal|tv|transv)\b)", re.IGNORECASE)
_CODIGO_AL_INICIO = re.compile(r"^\s*(\d{3,5})\s*[-–:.)]?\s*(.*)$")


def _rol(valor: str) -> str | None:
    v = (valor or "").strip()
    if not v:
        return None
    if _CORREO.match(v):
        return "correo"
    digitos = re.sub(r"[^0-9]", "", v.split("-")[0])
    if re.fullmatch(r"\d{10}", digitos) and v.startswith("3") and "-" not in v:
        return "telefono"
    if re.fullmatch(r"\d{8,11}", digitos) and re.fullmatch(r"[\d.\-\s]+", v):
        return "nit"
    if re.fullmatch(r"\d{3,5}", v):
        return "codigo"
    if ("$" in v or re.search(r"\d[.,]\d{3}\b", v)) and precio(v) is not None:
        return "precio"
    if re.fullmatch(r"\d{4,}([.,]\d{1,2})?", v) and precio(v) is not None:
        return "precio"
    if _DIRECCION.search(v):
        return "direccion"
    return "texto"


def _rol_columna(valores: list[str]) -> str | None:
    presentes = [v for v in valores if (v or "").strip()]
    if not presentes:
        return None
    conteo: dict[str, int] = {}
    for v in presentes:
        conteo[_rol(v)] = conteo.get(_rol(v), 0) + 1
    rol, n = max(conteo.items(), key=lambda kv: kv[1])
    return rol if n / len(presentes) >= _MINIMO else None


def encabezado_por_contenido(filas: list[list[str]]) -> list[str] | None:
    """Encabezados inventados a partir de lo que hay en las columnas, o None si no se
    reconoce nada útil (se deja la lectura como estaba)."""
    muestra = filas[:_FILAS_A_MIRAR]
    if not muestra:
        return None
    ancho = max(len(f) for f in muestra)
    roles = [_rol_columna([f[i] if i < len(f) else "" for f in muestra]) for i in range(ancho)]
    # Dos columnas de números enteros ("1101 | 14000"): la de la izquierda es el código y la
    # otra el precio, que es como se escribe una lista de precios.
    numericas = [i for i, r in enumerate(roles) if r in ("codigo", "precio")]
    if len(numericas) >= 2 and all(roles[i] == roles[numericas[0]] for i in numericas):
        roles[numericas[0]], roles[numericas[1]] = "codigo", "precio"
    encabezados, usados = [], set()
    for rol in roles:
        nombre = {"texto": "nombre"}.get(rol, rol) or ""
        if nombre in usados:
            nombre = ""
        encabezados.append(nombre)
        usados.add(nombre)
    reconocidas = {e for e in encabezados if e}
    if len(reconocidas) < 2 or not (reconocidas & {"codigo", "precio", "nit", "telefono", "correo"}):
        return None
    return encabezados


def separar_codigo(valor: str) -> tuple[str, str]:
    """«1101 - Cuadro Hemático» → ('1101', 'Cuadro Hemático'); sin código al inicio → ('', valor)."""
    m = _CODIGO_AL_INICIO.match(valor or "")
    if not m:
        return "", (valor or "").strip()
    return m.group(1), m.group(2).strip()


def nombres_traen_codigo(valores: list[str]) -> bool:
    presentes = [v for v in valores if (v or "").strip()]
    return bool(presentes) and sum(1 for v in presentes if separar_codigo(v)[0]) / len(presentes) >= _MINIMO
