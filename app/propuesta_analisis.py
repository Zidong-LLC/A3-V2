"""Anclar al catálogo los análisis que el propio bot nombra (ERR-198, prueba del 09/11).

Ante «análisis de sangre» el modelo propuso «Cuadro Hemático Completo $16.000» y, al «ese
está bien» del cliente, contestó «registro Cuadro Hemático…» sin guardar nada: la orden
seguía sin análisis y el bot volvía a preguntarlo en bucle. Lo que el bot propone o dice
haber registrado tiene que existir en el estado. Lógica pura, sin I/O.
"""
from app import catalog
from app.text import tokenize

_VERBOS_REGISTRO = frozenset({"registro", "registre", "registrado", "registrada", "registramos",
                              "agrego", "agregue", "agregado", "anoto", "anote", "anotado", "cargo", "incluyo"})
_AFIRMA = frozenset({"si", "ese", "esa", "eso", "este", "dale", "ok", "okay", "listo", "bien", "perfecto",
                     "claro", "vale", "mismo", "misma", "bueno", "correcto", "exacto", "hagale"})
_RELLENO = frozenset({"esta", "con", "el", "la", "lo", "solo", "nomas", "queda", "quedamos", "asi", "va",
                      "es", "gracias", "por", "favor", "quiero", "senor", "senora", "me", "parece", "muy"})

# Con estas palabras el mensaje pide OTRA cosa del catálogo («un perfil renal», «otro examen»):
# no es aceptar la propuesta aunque el modelo lo lea como «dio el dato pedido».
NOMBRA_OTRO_ANALISIS = frozenset({"perfil", "perfiles", "analisis", "examen", "examenes", "prueba", "pruebas",
                                  "otro", "otra", "otros", "otras", "panel", "quimica", "orina", "tambien"})


def acepta_la_propuesta(texto: str) -> bool:
    """¿El mensaje es SOLO un «sí, ese»? Con algo más adentro lo lee el pipeline."""
    tokens = set(tokenize(texto))
    return bool(tokens & _AFIRMA) and tokens <= _AFIRMA | _RELLENO


def afirma_registro(reply: str) -> bool:
    return bool(set(tokenize(reply)) & _VERBOS_REGISTRO)


def nombrados(reply: str, rows: list[dict]) -> list[dict]:
    """Análisis del catálogo cuyo nombre COMPLETO aparece en el texto. Si un nombre contiene a
    otro («Coproscópico con flotación» y «Coproscópico»), queda el más largo."""
    texto = f" {catalog._norm(reply)} "
    hallados = [(catalog._norm(r.get("name")), r) for r in rows if r.get("code")]
    hallados = [(n, r) for n, r in hallados if len(n) >= 5 and f" {n} " in texto]
    nombres = {n for n, _ in hallados}
    limpios, vistos = [], set()
    for nombre, fila in hallados:
        if any(nombre != otro and f" {nombre} " in f" {otro} " for otro in nombres):
            continue
        if fila["code"] not in vistos:
            vistos.add(fila["code"])
            limpios.append(fila)
    return limpios


def sin_nombres_repetidos(filas: list[dict]) -> bool:
    """Dos códigos con el mismo nombre (Mascolab por especie) no se pueden elegir solos."""
    nombres = [catalog._norm(f.get("name")) for f in filas]
    return len(nombres) == len(set(nombres))
