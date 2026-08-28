"""Búsqueda y filtros de la tabla de Clientes del dashboard.

Lógica pura sobre las filas que arma `_build_client_rows`, sin I/O.

Vive acá y no en el navegador porque la tabla se pagina de a 15 sobre 992 clientes:
filtrar en el navegador solo mira la página que se está viendo, y buscar «animal pet»
devolvía cero aunque el cliente exista en la página 40. Se filtra ANTES de paginar.

La búsqueda exige que estén TODAS las palabras, en cualquier orden: «animal pet»
encuentra «Animal Pets» y también «Pet Shop Animal», y los espacios de más no cuentan.
"""
import re

# Los mismos campos que la tabla concatenaba en `data-search`, para que buscar en el
# servidor encuentre exactamente lo que el usuario ve en la fila.
CAMPOS = ("display_name", "secondary_name", "clinic_name", "commercial_name", "client_code",
          "tax_id", "phone", "email", "billing_email", "address", "zone", "courier_name",
          "doctors_label")

_ACENTOS = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")


def normalizar(texto) -> str:
    """Minúsculas, sin tildes y sin espacios de más."""
    limpio = str(texto or "").translate(_ACENTOS).lower()
    return re.sub(r"\s+", " ", limpio).strip()


def texto_busqueda(row: dict) -> str:
    """Todo lo buscable de una fila, en un solo texto normalizado."""
    return normalizar(" ".join(str(row.get(campo) or "") for campo in CAMPOS))


def filtrar(rows: list[dict], q: str = "", tipo: str = "all", estado: str = "all",
            motorizado: str = "all", fe: str = "all") -> list[dict]:
    """Aplica búsqueda y filtros sobre la lista COMPLETA de clientes.

    Sin criterios devuelve la lista intacta. `estado` usa 'activo'/'inactivo',
    `motorizado` 'yes'/'no' y `fe` 'si'/'no'/'sin_dato', los mismos valores que ya
    manejaban los desplegables."""
    palabras = normalizar(q).split()
    filtradas = []
    for row in rows:
        if palabras:
            texto = texto_busqueda(row)
            if not all(palabra in texto for palabra in palabras):
                continue
        if tipo != "all" and str(row.get("client_type") or "") != tipo:
            continue
        if estado != "all" and normalizar(row.get("client_status")) != estado:
            continue
        if motorizado != "all":
            tiene = "yes" if row.get("assigned_courier_id") else "no"
            if tiene != motorizado:
                continue
        if fe != "all" and str(row.get("electronic_invoicing_option") or "sin_dato") != fe:
            continue
        filtradas.append(row)
    return filtradas


def desde_args(args) -> dict:
    """Los criterios tal como llegan en la URL, listos para filtrar, para repoblar el
    formulario y para colgarlos de los enlaces de paginación. Solo se devuelven los
    que están activos: así la URL no se llena de `tipo=all&estado=all`."""
    crudos = {
        "q": (args.get("q") or "").strip(),
        "tipo": (args.get("tipo") or "all").strip() or "all",
        "estado": (args.get("estado") or "all").strip() or "all",
        "motorizado": (args.get("motorizado") or "all").strip() or "all",
        "fe": (args.get("fe") or "all").strip() or "all",
    }
    return {k: v for k, v in crudos.items() if v and v != "all"}
