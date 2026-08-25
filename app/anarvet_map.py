"""Emparejar el `cod_cliente` de Anarvet con nuestros `clients` (Anarvet Fase 2).

Un informe del espejo no tiene dueño hasta que su `cod_cliente` apunta a un cliente
nuestro: sin eso no se puede publicar en el portal ni contar como suyo. La primera
corrida dejó 100 de 184 sin resolver porque el matcher exigía demasiado.

Medido contra la base (2026-08-25): **41% de los informes (329 de 797) estaban sin dueño**,
y el que más pesaba era Emergencias Veterinarias Integrales con 65 — un cliente que existe
en nuestra base con el nombre casi idéntico. Lo que separaba a los dos nombres era la
palabrería comercial: "Clínica", "Veterinaria", "SAS".

Regla de privacidad, la que manda sobre todo lo demás: **cuando hay más de un destino
posible NO se elige**. Un mapeo errado no es un dato mal puesto — le muestra los resultados
de un paciente a la veterinaria equivocada.
"""
import re
import unicodedata

# Formas jurídicas y palabras del rubro: las dos partes del nombre que no distinguen a una
# veterinaria de otra. "Clínica Veterinaria Zoopecas" y "Zoopecas SAS" son la misma.
_RUIDO = frozenset({
    "sas", "sa", "ltda", "eu", "sas.", "s.a.s", "cia", "compania",
    "clinica", "clinicas", "veterinaria", "veterinarias", "veterinario", "veterinarios",
    "centro", "medico", "medica", "consultorio", "hospital",
})


def normalizar(nombre: str | None) -> str:
    """Nombre comparable: sin tildes, sin puntuación y sin la palabrería comercial.

    'Clínica Veterinaria El Panda' y 'Veterinaria el Panda' → 'el panda'.
    Devuelve '' si al sacar el ruido no queda nada distintivo (p. ej. 'Veterinaria SAS'):
    un nombre vacío NUNCA matchea, que es lo correcto — no distingue a nadie.
    """
    texto = unicodedata.normalize("NFKD", str(nombre or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    palabras = [p for p in re.findall(r"[a-z0-9]+", texto) if p not in _RUIDO]
    return " ".join(palabras)


def candidatos_para(nombre_anarvet: str | None, clientes: list[dict]) -> list[dict]:
    """Clientes nuestros cuyo nombre normalizado coincide con el de Anarvet.

    Devuelve TODOS los que coinciden: quien llama decide si uno solo alcanza para asignar
    o si hace falta que un humano elija. `clientes` se recibe ya cargado para no pegarle a
    la base una vez por código.
    """
    clave = normalizar(nombre_anarvet)
    if not clave:
        return []
    return [c for c in clientes if normalizar(c.get("clinic_name")) == clave]


def sugerencias(nombre_anarvet: str | None, clientes: list[dict], limite: int = 5) -> list[dict]:
    """Clientes PARECIDOS, ordenados de mejor a peor, para cuando no hay coincidencia exacta.

    Es solo para que la pantalla proponga y un humano elija: nunca se asigna nada con esto.
    'Clinica Diagnostico Veterinario' encuentra así a 'Clinica De Diagnostico Veterinario',
    que difieren en un "de".
    """
    from difflib import SequenceMatcher

    clave = normalizar(nombre_anarvet)
    if not clave:
        return []
    puntuados = []
    for c in clientes:
        otra = normalizar(c.get("clinic_name"))
        if not otra:
            continue
        ratio = SequenceMatcher(None, clave, otra).ratio()
        if ratio >= 0.70:
            puntuados.append({"cliente": c, "similitud": round(ratio, 3)})
    puntuados.sort(key=lambda x: -x["similitud"])
    return puntuados[:limite]


def planificar(pendientes: list[dict], clientes: list[dict]) -> dict:
    """Clasifica los pendientes SIN escribir nada. Función pura: es lo que permite
    simular el automatch contra la base real antes de aplicarlo.

    - `automaticos`: un único destino → se pueden asignar solos.
    - `ambiguos`: varios destinos. En nuestra base casi siempre son el MISMO cliente
      cargado dos veces ('Zoopecas' y 'Zoopecas SAS'), así que la lista sirve además
      para devolverle a A3 los duplicados que quedaron por ordenar.
    - `sin_candidato`: no está en nuestra base; probablemente no es cliente del portal.
    """
    activos = [c for c in clientes
               if c.get("is_active", True) and (c.get("clinic_name") or "").strip()]
    automaticos, ambiguos, sin_candidato = [], [], []
    for fila in pendientes:
        opciones = candidatos_para(fila.get("nombre_cliente"), activos)
        if len(opciones) == 1:
            automaticos.append({"pendiente": fila, "cliente": opciones[0]})
        elif opciones:
            ambiguos.append({"pendiente": fila, "candidatos": opciones})
        else:
            sin_candidato.append({"pendiente": fila, "candidatos": []})
    return {"automaticos": automaticos, "ambiguos": ambiguos, "sin_candidato": sin_candidato}
