"""Municipios cercanos a Bogotá en la cobertura (cierre v1). Lógica pura, sin I/O.

Un municipio funciona como una localidad más: su motorizado vive en
courier_locality_coverage con el código «mun_<nombre>». Para reconocerlo se mira primero
el campo municipio/ciudad del cliente; la dirección solo se usa cuando la cascada de
barrios de Bogotá no encontró nada (una calle o un barrio de Bogotá puede llamarse
«Madrid» o «Cota»).
"""
import re

from app.territory import normalize_key

PREFIJO = "mun_"

# Coordenadas de los municipios de la Sabana, para ubicarlos en el mapa cuando A3 agrega
# uno nuevo desde la pantalla. Uno que no esté acá se lista igual, sin punto en el mapa.
CONOCIDOS = {
    "soacha": (4.5794, -74.2168), "chia": (4.8633, -74.0303), "sibate": (4.4919, -74.2594),
    "mosquera": (4.7078, -74.2328), "funza": (4.7163, -74.2116), "madrid": (4.7322, -74.2643),
    "cota": (4.8093, -74.0985), "cajica": (4.9186, -74.0281), "zipaquira": (5.0221, -73.9947),
    "la_calera": (4.7206, -73.9686), "facatativa": (4.8136, -74.3545), "tocancipa": (4.9653, -73.9128),
    "sopo": (4.9078, -73.9381), "tabio": (4.9166, -74.0959), "tenjo": (4.8717, -74.1442),
    "fusagasuga": (4.3365, -74.3638), "gachancipa": (4.9906, -73.8722), "bojaca": (4.7337, -74.3424),
    "el_rosal": (4.8531, -74.2628), "subachoque": (4.9293, -74.1735), "granada": (4.5180, -74.3510),
}


def codigo(nombre: str | None) -> str:
    return PREFIJO + normalize_key(nombre)


def es_municipio(locality_code: str | None) -> bool:
    return str(locality_code or "").startswith(PREFIJO)


def coordenadas(nombre: str | None) -> tuple[float, float] | tuple[None, None]:
    return CONOCIDOS.get(normalize_key(nombre), (None, None))


def coincide(texto: str | None, municipios: list[dict]) -> dict | None:
    """El municipio activo cuyo nombre aparece como palabra completa en el texto."""
    limpio = f"_{normalize_key(texto)}_"
    for municipio in municipios:
        clave = normalize_key(municipio.get("name"))
        if municipio.get("is_active", True) and clave and re.search(rf"_{re.escape(clave)}_", limpio):
            return municipio
    return None
