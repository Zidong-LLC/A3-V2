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
    "tax_id": ("nit", "identificacion", "cedula", "documento", "nit/cc", "rut"),
    "phone": ("telefono", "celular", "movil", "telefono 1"),
    "address": ("direccion", "domicilio"),
    "city": ("ciudad", "municipio"),
    "email": ("correo", "email", "e-mail", "correo electronico"),
}

CAMPOS_CLIENTE = ("tax_id", "phone", "address", "city", "email")


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
        nuevo = precio(fila.get("price"))
        if not code:
            errores.append(f"Fila {numero}: sin código")
            continue
        item = catalogo.get(code)
        if not item:
            errores.append(f"Fila {numero}: el código {code} no existe en el catálogo")
            continue
        if nuevo is None:
            errores.append(f"Fila {numero}: precio ilegible para {code}")
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
        valor = precio(fila.get("price"))
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
            errores.append(f"Fila {numero}: precio ilegible para {code}")
            continue
        vistos.add(code)
        es_perfil = norm(fila.get("kind")).startswith("perfil")
        nuevos.append({
            "tabla": "catalog_profiles" if es_perfil else "catalog_tests",
            "code": code, "name": nombre, "price": valor,
            "category": (fila.get("category") or "").strip() or None,
            "species": (fila.get("species") or "").strip() or None,
            "sample": (fila.get("sample") or "").strip() or None,
        })
    return {"tipo": "portafolio", "crear": nuevos, "actualizar": [], "iguales": existentes,
            "errores": errores}


def plan_clientes(filas: list[dict], clientes: list[dict], nombre_coincide) -> dict:
    """Clientes a crear y datos que la lista completa en los que ya existen.

    Nunca pisa un dato que la base ya tiene: solo rellena los vacíos. Cruza por
    NIT y, si no hay, por nombre con la MISMA regla del agente y del portal."""
    por_nit = {}
    for cliente in clientes:
        clave = solo_digitos(cliente.get("tax_id"))
        if clave:
            por_nit.setdefault(clave, []).append(cliente)

    nuevos, completar, errores = [], [], []
    for numero, fila in enumerate(filas, start=2):
        nombre = (fila.get("name") or "").strip()
        nit = solo_digitos(fila.get("tax_id"))
        if not nombre and not nit:
            errores.append(f"Fila {numero}: sin nombre ni NIT")
            continue

        candidatos = por_nit.get(nit) or []
        if not candidatos and nombre:
            candidatos = [c for c in clientes if nombre_coincide(nombre, c.get("clinic_name"))]
        if len(candidatos) > 1:
            errores.append(f"Fila {numero}: «{nombre or nit}» coincide con {len(candidatos)} "
                           "clientes, se deja para revisión manual")
            continue

        if not candidatos:
            nuevos.append({"clinic_name": nombre or f"Sin nombre ({nit})",
                           **{c: (fila.get(c) or "").strip() for c in CAMPOS_CLIENTE if fila.get(c)}})
            continue

        actual = candidatos[0]
        faltantes = {campo: (fila.get(campo) or "").strip()
                     for campo in CAMPOS_CLIENTE
                     if (fila.get(campo) or "").strip() and not (actual.get(campo) or "").strip()}
        if faltantes:
            completar.append({"id": actual["id"], "clinic_name": actual.get("clinic_name"),
                              "cambios": faltantes})
    return {"tipo": "clientes", "crear": nuevos, "actualizar": completar,
            "iguales": len(filas) - len(nuevos) - len(completar) - len(errores),
            "errores": errores}
