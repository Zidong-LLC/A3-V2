"""Modelo de dominio de ANIMALES (Fase 3.4 — extraído de `agent.py`).

A3 atiende TODAS las especies (grandes y pequeñas). Cada palabra coloquial normaliza a una
especie canónica y, cuando es inequívoca, a su sexo (toro=Macho, vaca=Hembra). Las formas
genéricas (perro, cerdo, caballo) NO asumen sexo. De aquí se derivan la recuperación de
especie y la inferencia de campos implícitos: así "toro"/"vaca"/"cerdo"/"conejo" se
interpretan igual de bien que "perro"/"gato" (no dependen del criterio del LLM). Fuente única
de verdad para especie/sexo.
"""
from app.text import tokenize, ACCENT_TRANSLATION

ANIMAL_DOMAIN: dict[str, tuple[str, str | None]] = {
    # Caninos
    "perro": ("Canino", None), "perrito": ("Canino", None), "cachorro": ("Canino", None),
    "canino": ("Canino", None), "can": ("Canino", None), "kanino": ("Canino", None),
    "perra": ("Canino", "Hembra"), "perrita": ("Canino", "Hembra"), "canina": ("Canino", "Hembra"),
    # Felinos
    "gato": ("Felino", None), "gatito": ("Felino", None), "michi": ("Felino", None),
    "minino": ("Felino", None), "felino": ("Felino", None),
    "gata": ("Felino", "Hembra"), "gatita": ("Felino", "Hembra"), "felina": ("Felino", "Hembra"),
    # Bovinos
    "bovino": ("Bovino", None), "res": ("Bovino", None), "cebu": ("Bovino", None),
    "toro": ("Bovino", "Macho"), "novillo": ("Bovino", "Macho"), "buey": ("Bovino", "Macho"),
    "ternero": ("Bovino", "Macho"), "becerro": ("Bovino", "Macho"),
    "vaca": ("Bovino", "Hembra"), "vaquilla": ("Bovino", "Hembra"), "novilla": ("Bovino", "Hembra"),
    "ternera": ("Bovino", "Hembra"), "becerra": ("Bovino", "Hembra"),
    # Porcinos
    "porcino": ("Porcino", None), "cerdo": ("Porcino", None), "puerco": ("Porcino", None),
    "cochino": ("Porcino", None), "chancho": ("Porcino", None), "marrano": ("Porcino", None),
    "lechon": ("Porcino", None), "verraco": ("Porcino", "Macho"),
    "cerda": ("Porcino", "Hembra"), "puerca": ("Porcino", "Hembra"), "cochina": ("Porcino", "Hembra"),
    "marrana": ("Porcino", "Hembra"),
    # Equinos
    "equino": ("Equino", None), "caballo": ("Equino", None), "burro": ("Equino", None),
    "potro": ("Equino", "Macho"), "potrillo": ("Equino", "Macho"), "semental": ("Equino", "Macho"),
    "yegua": ("Equino", "Hembra"), "potranca": ("Equino", "Hembra"), "burra": ("Equino", "Hembra"),
    "mula": ("Equino", "Hembra"),
    # Ovinos / Caprinos
    "ovino": ("Ovino", None), "cordero": ("Ovino", None), "borrego": ("Ovino", None),
    "oveja": ("Ovino", "Hembra"), "carnero": ("Ovino", "Macho"), "borrega": ("Ovino", "Hembra"),
    "caprino": ("Caprino", None), "cabrito": ("Caprino", None), "cabro": ("Caprino", "Macho"),
    "cabra": ("Caprino", "Hembra"), "chivo": ("Caprino", "Macho"), "chiva": ("Caprino", "Hembra"),
    # Conejos / roedores / pequeños
    "conejo": ("Conejo", None), "conejito": ("Conejo", None), "gazapo": ("Conejo", None),
    "coneja": ("Conejo", "Hembra"),
    "cuy": ("Roedor", None), "cobayo": ("Roedor", None), "curi": ("Roedor", None),
    "hamster": ("Roedor", None), "raton": ("Roedor", None), "huron": ("Hurón", None),
    "cobaya": ("Roedor", "Hembra"),
    # Aves
    "ave": ("Ave", None), "pajaro": ("Ave", None), "pollo": ("Ave", None), "loro": ("Ave", None),
    "canario": ("Ave", None), "perico": ("Ave", None), "pato": ("Ave", None), "pavo": ("Ave", None),
    "paloma": ("Ave", None), "cotorra": ("Ave", None),
    "gallina": ("Ave", "Hembra"), "gallo": ("Ave", "Macho"),
    # Reptiles
    "reptil": ("Reptil", None), "reptiles": ("Reptil", None), "tortuga": ("Reptil", None),
    "iguana": ("Reptil", None), "serpiente": ("Reptil", None), "culebra": ("Reptil", None),
    # Exóticos: cada uno es su propia especie (la lista del cliente los trae sueltos, sin raza).
    "erizo": ("Erizo", None), "chinchilla": ("Chinchilla", None),
    "glider": ("Sugar Glider", None), "petauro": ("Sugar Glider", None),
    "degu": ("Degú", None), "axolote": ("Axolote", None), "ajolote": ("Axolote", None),
}
# Derivados: recuperación de especie (palabra → especie canónica) y campos implícitos.
RECOVERABLE_SPECIES = {word: spec for word, (spec, _sex) in ANIMAL_DOMAIN.items()}
IMPLIED_ANIMAL_FIELDS = ANIMAL_DOMAIN
RECOVERABLE_SEX = {
    "macho": "Macho", "masho": "Macho", "machito": "Macho", "m": "Macho",
    "hembra": "Hembra", "embra": "Hembra", "hembrita": "Hembra", "h": "Hembra",
}


def apply_implied_animal_fields(fields: dict, user_message: str) -> None:
    """Normaliza especie (y sexo, si es inequívoco) desde la palabra que usó el cliente,
    sin pisar un dato que el cliente ya dio de forma explícita."""
    for token in (t.translate(ACCENT_TRANSLATION) for t in tokenize(user_message)):
        implied = IMPLIED_ANIMAL_FIELDS.get(token)
        if not implied:
            continue
        species, sex = implied
        current_species = str(fields.get("species") or "").lower().translate(ACCENT_TRANSLATION)
        if not fields.get("species") or current_species in RECOVERABLE_SPECIES:
            fields["species"] = species
        current_sex = str(fields.get("sex") or "").lower().translate(ACCENT_TRANSLATION)
        if sex and (not fields.get("sex") or current_sex in RECOVERABLE_SEX):
            fields["sex"] = sex
        break
