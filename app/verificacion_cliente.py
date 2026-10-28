"""¿Quien escribe es de esta veterinaria? Nombre Y NIT concordantes (ERR-187).

Regla del usuario (2026-10-28): «que solo pueda dar los PDFs del NIT que te dio, que el
nombre de la clínica y el NIT concuerden; si te dicen el nombre sin NIT, que pida el dato
faltante y que sea el correcto». Antes alcanzaba con decir el nombre de una clínica en el
chat para recibir sus resultados.

La misma vara endurece el login del portal: con el NIT y una palabra cualquiera del
nombre («veterinaria») se entraba a cualquier sede. Lógica pura: sin base, sin red.
"""
import re
import unicodedata

# Palabras que cualquiera escribe y no distinguen a una clínica de otra.
GENERICAS = frozenset((
    "veterinaria veterinarias veterinario veterinarios vet vets vete veterinary clinica clinicas "
    "clinic clinical centro medico medica hospital consultorio doctor doctora dr dra sede pet pets "
    "mascota mascotas animal animales shop tienda sas ltda cia y de del la las el los e en"
).split())


def _tokens(texto: str | None) -> list[str]:
    plano = unicodedata.normalize("NFKD", (texto or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", plano)


def _coincide(escrito: str, real: str) -> bool:
    """Igual, en singular/plural ('pet' por 'pets', L58), o uno empieza con el otro con al
    menos 4 letras ('maximascota' por 'maximascotas')."""
    if escrito == real or real in (escrito + "s", escrito + "es") or escrito in (real + "s", real + "es"):
        return True
    return min(len(escrito), len(real)) >= 4 and (real.startswith(escrito) or escrito.startswith(real))


def nombre_concuerda(escrito: str | None, real: str | None) -> bool:
    """¿Lo escrito nombra a ESTA clínica? Alcanza una palabra propia de su nombre
    ('Maximascotas' por 'Veterinaria Maximascotas Lulu'). Si el nombre es todo genérico
    ('Animal Pets'), tienen que aparecer todas sus palabras."""
    escritos, reales = _tokens(escrito), _tokens(real)
    if not escritos or not reales:
        return False
    if "".join(reales) in "".join(escritos):  # el nombre completo, tal cual ('S.O.S. Animal')
        return True
    propias = [t for t in reales if t not in GENERICAS and len(t) >= 3]
    if propias:
        # Una palabra genérica escrita nunca cuenta como propia ('veterinaria' ≠ 'Vete…').
        return any(_coincide(e, p) for e in escritos if e not in GENERICAS for p in propias)
    # Nombre todo genérico: van todas sus palabras, iniciales incluidas ('J.G.').
    return all(any(_coincide(e, r) for e in escritos) for r in reales if r not in ("y", "e"))


def _numeros(texto: str | None) -> list[str]:
    """Los números del texto, con los puntos, espacios y guiones del medio pegados
    ('900.123.456-7' → '9001234567')."""
    pegado = re.sub(r"(?<=\d)[.\s-](?=\d)", "", texto or "")
    return re.findall(r"\d+", pegado)


def nit_en_texto(texto: str | None, nit_real: str | None) -> bool:
    """¿El texto trae ESTE NIT? Con o sin dígito de verificación, con puntos o espacios."""
    crudo = str(nit_real or "").strip()
    if crudo.endswith(".0"):  # artefacto de Excel (ERR-121)
        crudo = crudo[:-2]
    limpio = re.sub(r"\D", "", crudo)
    base = re.sub(r"\D", "", crudo.split("-", 1)[0])
    if len(base) < 6:  # NIT de relleno ('1', '0'): no verifica a nadie
        return False
    aceptados = {limpio, base}
    for numero in _numeros(texto):
        # Escrito con el DV que la base no guarda, o sin el DV que la base sí guarda pegado.
        if numero in aceptados or numero[:-1] == limpio or (len(numero) >= 8 and numero == limpio[:-1]):
            return True
    return False


def trae_el_dato(texto: str | None, cliente: dict, dato: str) -> bool:
    """¿El texto trae, y correcto, el dato que se le pidió ('nit' o 'nombre')?"""
    if dato == "nit":
        return nit_en_texto(texto, cliente.get("tax_id"))
    return nombre_concuerda(texto, cliente.get("clinic_name"))


def dato_faltante(textos_del_usuario: list[str], cliente: dict) -> str | None:
    """None si lo que escribió el usuario ya trae el nombre Y el NIT de este cliente; si
    no, 'nit' o 'nombre' — el NIT primero, que es el dato que no está a la vista."""
    if not any(nit_en_texto(t, cliente.get("tax_id")) for t in textos_del_usuario):
        return "nit"
    if not any(nombre_concuerda(t, cliente.get("clinic_name")) for t in textos_del_usuario):
        return "nombre"
    return None
