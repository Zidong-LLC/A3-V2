"""Cargas masivas por CSV: lectura del archivo y PLAN de lo que se va a hacer.

Lógica pura, sin I/O: recibe los bytes del archivo y los datos actuales, y
devuelve qué se crearía, qué se actualizaría y qué queda igual. Quien escribe en
la base es `app/dashboard_import.py`, y solo después de que una persona vea el
plan y confirme. Ese es el punto: una carga masiva a ciegas puede pisar 300
precios sin que nadie lo note.

Pedido de A3 (llamada 4): precios, clientes y portafolio.
"""
import csv
import io
import re

# Encabezado del archivo -> campo nuestro. Mismos alias que usa el script de
# conciliación del padrón, para que A3 pueda mandar el mismo archivo a los dos.
ALIAS = {
    "code": ("codigo", "code", "cod", "codigo analisis", "codigo examen"),
    "name": ("nombre", "analisis", "examen", "perfil", "descripcion", "cliente",
             "veterinaria", "clinica", "razon social", "nombre comercial"),
    "price": ("precio", "valor", "tarifa", "precio venta"),
    "kind": ("tipo", "clase"),
    "category": ("categoria", "area", "grupo"),
    "species": ("especie", "especies"),
    "sample": ("muestra", "tipo de muestra"),
    "tax_id": ("nit", "n.i.t.", "n.i.t", "identificacion", "cedula", "documento", "nit/cc", "rut"),
    "phone": ("telefono", "celular", "movil", "telefono 1", "tel", "cel", "whatsapp"),
    "address": ("direccion", "domicilio"),
    # Zona/localidad: con ella el bot asigna motorizado (ERR-193: 571 clientes sin zona).
    "zone": ("zona", "localidad", "barrio", "sector"),
    "city": ("ciudad", "municipio"),
    "email": ("correo", "email", "e-mail", "correo electronico"),
    # Decide a nombre de quién se factura (clients.electronic_invoice, app/billing.py).
    "electronic_invoice": ("factura electronica", "facturacion electronica", "electronica", "factura"),
    "courier": ("motorizado", "mensajero", "domiciliario", "courier"),
}

CAMPOS_CLIENTE = ("tax_id", "phone", "address", "zone", "city", "email", "electronic_invoice")
_SI = {"si", "sí", "s", "true", "1", "x", "verdadero"}
_NO = {"no", "n", "false", "0", "falso"}


def si_no(valor) -> bool | None:
    """«sí/no» de una celda a booleano. None si no se entiende (se ignora la celda)."""
    limpio = norm(valor)
    return True if limpio in _SI else False if limpio in _NO else None


def _valor_cliente(campo: str, valor) -> object:
    """El valor de una celda como lo guarda la tabla: texto, o booleano para la factura."""
    if campo == "electronic_invoice":
        return si_no(valor)
    return (valor or "").strip()


def _vacio(actual: dict, campo: str) -> bool:
    tiene = actual.get(campo)
    return tiene is None or (isinstance(tiene, str) and not tiene.strip())


def _distinto(actual: dict, campo: str, valor) -> bool:
    tiene = actual.get(campo)
    return valor != (tiene.strip() if isinstance(tiene, str) else tiene)
PRECIO_MAXIMO = 20_000_000  # el análisis más caro del catálogo vale 1,2 millones
# Especie como la guarda el catálogo: el agente ofrece a cada mascota lo de su especie y
# lo de «ambos». Un «Perro» guardado tal cual dejaba el análisis invisible para todos.
_ESPECIES = {"canino": ("canino", "canina", "caninos", "perro", "perros"),
             "felino": ("felino", "felina", "felinos", "gato", "gatos"),
             "ambos": ("ambos", "ambas", "todos", "todas", "canino y felino", "caninos y felinos",
                       "perro y gato", "perros y gatos")}


def norm(texto) -> str:
    """Minúsculas sin tildes ni dobles espacios, para comparar encabezados."""
    t = str(texto or "").strip().lower()
    for con, sin in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        t = t.replace(con, sin)
    return re.sub(r"\s+", " ", t).strip()


def solo_digitos(valor) -> str:
    """NIT comparable: sin puntos, guiones ni dígito de verificación."""
    return re.sub(r"[^0-9]", "", str(valor or "").split("-")[0])


def precio(valor) -> int | None:
    """'$ 85.000' y '85000,00' son el mismo precio. Devuelve None si no es un número."""
    limpio = re.sub(r"[^0-9,.]", "", str(valor or ""))
    if not limpio:
        return None
    # Separador decimal: la última coma o punto seguido de 1-2 dígitos al final.
    limpio = re.sub(r"[.,]\d{1,2}$", "", limpio)
    limpio = re.sub(r"[^0-9]", "", limpio)
    return int(limpio) if limpio else None


def precio_valido(valor) -> int | None:
    """Precio legible y razonable: un cero de más no puede llegar al catálogo."""
    numero = precio(valor)
    return numero if numero is not None and 0 < numero <= PRECIO_MAXIMO else None


def especie(valor) -> str | None:
    """canino, felino o ambos (vacía = ambos). None si no se reconoce."""
    limpio = norm(valor)
    if not limpio:
        return "ambos"
    return next((clave for clave, alias in _ESPECIES.items() if limpio in alias), None)


def leer_csv(data: bytes) -> tuple[list[dict], list[str]]:
    """Filas del archivo mapeadas a nuestros campos, y los encabezados que no se
    reconocieron. Acepta coma o punto y coma, con o sin BOM."""
    texto = data.decode("utf-8-sig", errors="replace")
    muestra = texto[:2048]
    delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
    lector = csv.reader(io.StringIO(texto), delimiter=delimitador)
    filas_brutas = [f for f in lector if any((c or "").strip() for c in f)]
    if not filas_brutas:
        return [], []

    encabezados = filas_brutas[0]
    mapa, ignorados = {}, []
    for indice, bruto in enumerate(encabezados):
        limpio = norm(bruto)
        for campo, alias in ALIAS.items():
            if campo not in mapa and (limpio in alias or any(limpio.startswith(a) for a in alias)):
                mapa[campo] = indice
                break
        else:
            if limpio:
                ignorados.append(bruto)

    filas = []
    for bruta in filas_brutas[1:]:
        fila = {campo: (bruta[i].strip() if i < len(bruta) else "")
                for campo, i in mapa.items()}
        if any(fila.values()):
            filas.append(fila)
    return filas, ignorados


def _catalogo_por_codigo(tests: list[dict], profiles: list[dict]) -> dict:
    catalogo = {}
    for tabla, filas in (("catalog_tests", tests), ("catalog_profiles", profiles)):
        for fila in filas:
            catalogo[str(fila.get("code") or "").strip()] = {"tabla": tabla, **fila}
    return catalogo


def plan_precios(filas: list[dict], tests: list[dict], profiles: list[dict]) -> dict:
    """Qué precios cambian. Un código que no existe NO se crea acá: eso es portafolio."""
    catalogo = _catalogo_por_codigo(tests, profiles)
    cambios, iguales, errores = [], 0, []
    for numero, fila in enumerate(filas, start=2):
        code = (fila.get("code") or "").strip()
        nuevo = precio_valido(fila.get("price"))
        if not code:
            errores.append(f"Fila {numero}: sin código")
            continue
        item = catalogo.get(code)
        if not item:
            errores.append(f"Fila {numero}: el código {code} no existe en el catálogo")
            continue
        if nuevo is None:
            errores.append(f"Fila {numero}: precio ilegible o fuera de rango para {code}")
            continue
        if int(item.get("price") or 0) == nuevo:
            iguales += 1
            continue
        cambios.append({"tabla": item["tabla"], "code": code, "name": item.get("name"),
                        "antes": int(item.get("price") or 0), "despues": nuevo})
    return {"tipo": "precios", "actualizar": cambios, "crear": [], "iguales": iguales,
            "errores": errores}


def plan_portafolio(filas: list[dict], tests: list[dict], profiles: list[dict]) -> dict:
    """Análisis y perfiles que todavía no están en el catálogo."""
    catalogo = _catalogo_por_codigo(tests, profiles)
    nuevos, existentes, errores = [], 0, []
    vistos = set()
    for numero, fila in enumerate(filas, start=2):
        code = (fila.get("code") or "").strip()
        nombre = (fila.get("name") or "").strip()
        valor = precio_valido(fila.get("price"))
        if not code or not nombre:
            errores.append(f"Fila {numero}: hacen falta código y nombre")
            continue
        if code in catalogo:
            existentes += 1
            continue
        if code in vistos:
            errores.append(f"Fila {numero}: el código {code} viene repetido en el archivo")
            continue
        if valor is None:
            errores.append(f"Fila {numero}: precio ilegible o fuera de rango para {code}")
            continue
        categoria, sp = (fila.get("category") or "").strip(), especie(fila.get("species"))
        if not categoria:  # la tabla la exige: sin esto la carga se cortaba a mitad
            errores.append(f"Fila {numero}: falta la categoría de {code}")
            continue
        if sp is None:
            errores.append(f"Fila {numero}: especie «{fila.get('species')}» no reconocida "
                           "(canino, felino o ambos)")
            continue
        vistos.add(code)
        es_perfil = norm(fila.get("kind")).startswith("perfil")
        nuevos.append({
            "tabla": "catalog_profiles" if es_perfil else "catalog_tests",
            "code": code, "name": nombre, "price": valor,
            "category": categoria, "species": sp,
            "sample": (fila.get("sample") or "").strip() or None,
        })
    return {"tipo": "portafolio", "crear": nuevos, "actualizar": [], "iguales": existentes,
            "errores": errores}


def plan_clientes(filas: list[dict], clientes: list[dict], nombre_coincide, actualizar: bool = False,
                  motorizados: dict | None = None, asignaciones: dict | None = None) -> dict:
    """Clientes a crear y datos que la lista completa en los que ya existen.

    Por defecto no pisa un dato que la base ya tiene: solo rellena los vacíos. Con
    `actualizar` (casilla en la pantalla, cierre v1) también cambia los que difieren y
    muestra el antes/después. La columna Motorizado asigna por nombre (`motorizados`:
    nombre normalizado → id). Cruza por NIT y, si no hay, por nombre con la MISMA regla
    del agente y del portal."""
    motorizados, asignaciones = motorizados or {}, asignaciones or {}
    por_nit = {}
    for cliente in clientes:
        clave = solo_digitos(cliente.get("tax_id"))
        if clave:
            por_nit.setdefault(clave, []).append(cliente)

    nuevos, completar, errores, avisos, vistos, iguales = [], [], [], [], set(), 0
    for numero, fila in enumerate(filas, start=2):
        nombre = (fila.get("name") or "").strip()
        nit = solo_digitos(fila.get("tax_id"))
        if not nombre and not nit:
            errores.append(f"Fila {numero}: sin nombre ni NIT")
            continue
        # Dos veces en la lista = dos altas del mismo. La clave lleva NIT y nombre: las
        # SEDES comparten NIT con otro nombre (122 NIT para 261 clientes en el padrón) y
        # antes la segunda sede del archivo salía como «repetida».
        clave = (nit, norm(nombre)) if nit and nombre else (nit or norm(nombre))
        if clave in vistos:
            errores.append(f"Fila {numero}: «{nombre or nit}» viene repetido en el archivo")
            continue
        vistos.add(clave)

        candidatos = por_nit.get(nit) or []
        if len(candidatos) > 1:
            # Sedes que comparten NIT (caso Club Animals / ERR-157). Si la fila NOMBRA una de
            # las sedes, es esa y se trata como un cliente más (se completa o actualiza).
            por_nombre = [c for c in candidatos if nombre and nombre_coincide(nombre, c.get("clinic_name"))]
            if len(por_nombre) == 1:
                candidatos = por_nombre
            else:
                # Sin sede reconocible: el correo es un dato del NIT —ahí llega la factura
                # electrónica—, así que completa TODAS las sedes que no lo tengan. Teléfono y
                # dirección son de cada sede: esos no se tocan.
                correo, antes = (fila.get("email") or "").strip(), len(completar)
                for sede in candidatos:
                    if correo and not (sede.get("email") or "").strip():
                        completar.append({"id": sede["id"], "clinic_name": sede.get("clinic_name"),
                                          "cambios": {"email": correo}})
                iguales += len(completar) == antes
                continue
        if not candidatos and nombre:
            candidatos = [c for c in clientes if nombre_coincide(nombre, c.get("clinic_name"))]
        if len(candidatos) > 1:
            errores.append(f"Fila {numero}: «{nombre or nit}» coincide con {len(candidatos)} "
                           "clientes, se deja para revisión manual")
            continue

        courier_id = None
        if (fila.get("courier") or "").strip():
            courier_id = motorizados.get(norm(fila["courier"]))
            if not courier_id:
                avisos.append(f"Fila {numero}: el motorizado «{fila['courier']}» no existe; no se asigna")

        valores = {c: _valor_cliente(c, fila.get(c)) for c in CAMPOS_CLIENTE}
        valores = {c: v for c, v in valores.items() if v not in (None, "")}
        if not candidatos:
            nuevo = {"clinic_name": nombre or f"Sin nombre ({nit})", **valores}
            if courier_id:
                nuevo["courier_id"] = courier_id
            nuevos.append(nuevo)
            continue

        actual = candidatos[0]
        faltantes = {campo: valor for campo, valor in valores.items()
                     if (_distinto(actual, campo, valor) if actualizar else _vacio(actual, campo))}
        if courier_id and asignaciones.get(actual["id"]) != courier_id:
            faltantes["courier_id"] = courier_id
        if faltantes:
            completar.append({"id": actual["id"], "clinic_name": actual.get("clinic_name"),
                              "cambios": faltantes,
                              "antes": {c: actual.get(c) for c in faltantes if c != "courier_id"}})
        else:
            iguales += 1
    return {"tipo": "clientes", "crear": nuevos, "actualizar": completar, "iguales": iguales,
            "errores": errores + avisos}
