"""Lectura de cualquier archivo de carga masiva y mapeo de sus columnas.

Pedido de A3 (cierre v1): «que funcione con cualquier CSV». Acepta CSV con coma, punto
y coma, tabulación o barra; en UTF-8 o en la codificación con la que guarda Excel en
Windows; y también .xlsx (primera hoja). Las columnas se reconocen por su nombre, y lo
que no se reconozca lo elige la persona en la pantalla: así sirve cualquier estructura.
Lógica pura, sin I/O.
"""
import csv
import io

from app.imports import ALIAS, norm

# Datos que puede traer cada tipo de carga, en el orden en que se muestran.
CAMPOS = {
    "precios": ("code", "price", "name"),
    "portafolio": ("code", "name", "price", "kind", "category", "species", "sample"),
    "clientes": ("name", "tax_id", "phone", "address", "city", "email", "courier"),
    "motorizados": ("name", "phone"),
}
OBLIGATORIOS = {"precios": ("code", "price"), "portafolio": ("code", "name", "price"),
                "clientes": (), "motorizados": ("name",)}
ETIQUETAS = {"code": "Código", "price": "Precio", "name": "Nombre", "kind": "Tipo (análisis/perfil)",
             "category": "Categoría", "species": "Especie", "sample": "Muestra", "tax_id": "NIT",
             "phone": "Teléfono", "address": "Dirección", "city": "Municipio o ciudad",
             "email": "Correo", "courier": "Motorizado"}
_SEPARADORES = ",;\t|"
# Columnas que solo trae ese tipo: «nombre;telefono» es de motorizados, no de clientes, y
# «codigo;nombre;precio;especie» (la exportación de precios) no es portafolio nuevo.
_PROPIAS = {"clientes": {"tax_id", "address", "city", "email"}, "portafolio": {"category", "sample"}}


def _texto(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")  # CSV guardado por Excel en Windows


def _separador(muestra: str) -> str:
    try:
        return csv.Sniffer().sniff(muestra, delimiters=_SEPARADORES).delimiter
    except csv.Error:
        return max(_SEPARADORES, key=muestra.count)


def _celda(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))  # Excel guarda 95000 como 95000.0
    return str(valor).strip()


def _leer_xlsx(data: bytes) -> list[list[str]]:
    from openpyxl import load_workbook
    libro = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    hoja = libro.worksheets[0]
    filas = [[_celda(v) for v in fila] for fila in hoja.iter_rows(values_only=True)]
    libro.close()
    return filas


def leer_tabla(data: bytes, nombre: str = "") -> tuple[list[str], list[list[str]]]:
    """Encabezados y filas (sin las vacías) de un CSV o un .xlsx."""
    if nombre.lower().endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        brutas = _leer_xlsx(data)
    else:
        texto = _texto(data)
        brutas = list(csv.reader(io.StringIO(texto), delimiter=_separador(texto[:4096])))
    brutas = [[(c or "").strip() for c in f] for f in brutas if any((c or "").strip() for c in f)]
    if not brutas:
        return [], []
    return brutas[0], brutas[1:]


def mapa_automatico(encabezados: list[str], tipo: str) -> dict[str, int]:
    """Columna de cada dato reconocida por el nombre del encabezado (alias)."""
    mapa: dict[str, int] = {}
    for indice, bruto in enumerate(encabezados):
        limpio = norm(bruto)
        for campo in CAMPOS.get(tipo, ()):
            alias = ALIAS.get(campo, ())
            if campo not in mapa and (limpio in alias or any(limpio.startswith(a) for a in alias)):
                mapa[campo] = indice
                break
    return mapa


def faltantes(mapa: dict[str, int], tipo: str) -> list[str]:
    falta = [ETIQUETAS[c] for c in OBLIGATORIOS.get(tipo, ()) if c not in mapa]
    if tipo == "clientes" and "name" not in mapa and "tax_id" not in mapa:
        falta.append("Nombre o NIT")
    return falta


def filas_con_mapa(filas: list[list[str]], mapa: dict[str, int]) -> list[dict]:
    salida = []
    for bruta in filas:
        fila = {campo: (bruta[i].strip() if i < len(bruta) else "") for campo, i in mapa.items()}
        if any(fila.values()):
            salida.append(fila)
    return salida


def detectar_tipo(encabezados: list[str], permitidos: list[str]) -> str | None:
    """El tipo de carga que mejor calza con las columnas: entre los que tienen todo lo
    obligatorio, el que reconoce más columnas; en empate, el primero de `permitidos`
    (código + nombre + precio calza con precios y con portafolio: manda precios).
    None si ninguno calza."""
    candidatos = []
    for i, tipo in enumerate(permitidos):
        mapa = mapa_automatico(encabezados, tipo) if tipo in CAMPOS else {}
        if not mapa or faltantes(mapa, tipo) or (tipo in _PROPIAS and not _PROPIAS[tipo] & set(mapa)):
            continue
        candidatos.append((len(mapa), -i, tipo))
    return max(candidatos)[2] if candidatos else None
