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
    "clientes": ("name", "tax_id", "phone", "address", "zone", "city", "email", "electronic_invoice", "courier"),
    "motorizados": ("name", "phone"),
}
OBLIGATORIOS = {"precios": ("code", "price"), "portafolio": ("code", "name", "price"),
                "clientes": (), "motorizados": ("name",)}
ETIQUETAS = {"code": "Código", "price": "Precio", "name": "Nombre", "kind": "Tipo (análisis/perfil)",
             "category": "Categoría", "species": "Especie", "sample": "Muestra", "tax_id": "NIT",
             "phone": "Teléfono", "address": "Dirección", "zone": "Zona o localidad",
             "city": "Municipio o ciudad", "email": "Correo",
             "electronic_invoice": "Factura electrónica (sí/no)", "courier": "Motorizado"}
_SEPARADORES = ",;\t|"
# Columnas que solo trae ese tipo: «nombre;telefono» es de motorizados, no de clientes, y
# «codigo;nombre;precio;especie» (la exportación de precios) no es portafolio nuevo.
_PROPIAS = {"clientes": {"tax_id", "address", "zone", "city", "email", "electronic_invoice"},
            "portafolio": {"category", "sample"}}
_FILAS_A_MIRAR = 15  # un título o notas arriba del encabezado no pasan de unas pocas filas


def _puntaje_encabezado(fila: list[str]) -> int:
    """Cuántas celdas de la fila se reconocen como encabezado de algún dato."""
    campos = {c for tipo in CAMPOS for c in CAMPOS[tipo]}
    puntaje = 0
    for bruto in fila:
        limpio = norm(bruto)
        if limpio and any(limpio in ALIAS.get(c, ()) or any(limpio.startswith(a) for a in ALIAS.get(c, ()))
                          for c in campos):
            puntaje += 1
    return puntaje


def _fila_encabezado(filas: list[list[str]]) -> int:
    """Índice de la fila que mejor se parece a un encabezado entre las primeras.

    La gente manda el archivo con un título («LISTA DE CLIENTES 2026»), notas o filas vacías
    arriba, y antes eso se tomaba como encabezado: no se reconocía ninguna columna. Gana la
    primera fila con 2 o más columnas reconocidas; sin ninguna, la primera fila, como antes."""
    mejor, mejor_puntaje = 0, 0
    for indice, fila in enumerate(filas[:_FILAS_A_MIRAR]):
        puntaje = _puntaje_encabezado(fila)
        if puntaje >= 2:
            return indice
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = indice, puntaje
    return mejor


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


def _sin_vacias(brutas: list[list]) -> list[list[str]]:
    return [[(c or "").strip() for c in f] for f in brutas if any((c or "").strip() for c in f)]


def _leer_xlsx(data: bytes) -> list[list[str]]:
    """Las filas de la hoja que mejor se reconoce. Un libro suele traer una portada o una hoja
    de notas primero y los datos en la segunda: antes solo se leía la primera y no se
    reconocía nada. Se elige la hoja cuyo encabezado reconoce más columnas."""
    from openpyxl import load_workbook
    libro = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    mejor, mejor_puntaje = [], -1
    for hoja in libro.worksheets:
        filas = _sin_vacias([[_celda(v) for v in fila] for fila in hoja.iter_rows(values_only=True)])
        if not filas:
            continue
        puntaje = _puntaje_encabezado(filas[_fila_encabezado(filas)])
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = filas, puntaje
    libro.close()
    return mejor


def leer_tabla(data: bytes, nombre: str = "") -> tuple[list[str], list[list[str]]]:
    """Encabezados y filas (sin las vacías) de un CSV o un .xlsx."""
    if nombre.lower().endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        brutas = _leer_xlsx(data)
    else:
        texto = _texto(data)
        brutas = list(csv.reader(io.StringIO(texto), delimiter=_separador(texto[:4096])))
    brutas = _sin_vacias(brutas)
    if not brutas:
        return [], []
    inicio = _fila_encabezado(brutas)
    if _puntaje_encabezado(brutas[inicio]) < 2:
        # Sin encabezado («1101 | 14000» desde la primera fila): se reconocen las columnas por
        # lo que traen y todas las filas son datos.
        from app.imports_contenido import encabezado_por_contenido
        inventado = encabezado_por_contenido(brutas)
        if inventado:
            return inventado, brutas
    return brutas[inicio], brutas[inicio + 1:]


def separar_codigo_del_nombre(encabezados: list[str], filas: list[list[str]], tipo: str) -> tuple[list[str], list[list[str]]]:
    """Si no hay columna de código pero los nombres lo traen adelante («1101 - Cuadro
    Hemático»), se parte en dos columnas: «codigo» y el nombre limpio. Así la carga de
    precios/portafolio lo reconoce igual que una lista con el código aparte."""
    from app.imports_contenido import nombres_traen_codigo, separar_codigo
    mapa = mapa_automatico(encabezados, tipo)
    if "code" in mapa or "name" not in mapa or "code" not in CAMPOS.get(tipo, ()):
        return encabezados, filas
    col = mapa["name"]
    if not nombres_traen_codigo([f[col] if col < len(f) else "" for f in filas]):
        return encabezados, filas
    nuevas = []
    for f in filas:
        codigo, nombre = separar_codigo(f[col] if col < len(f) else "")
        fila = list(f) + [""] * (len(encabezados) - len(f))
        fila[col] = nombre
        nuevas.append([codigo] + fila)
    return ["codigo"] + list(encabezados), nuevas


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
