"""Plantillas y exportaciones de las cargas masivas (cierre v1).

Los encabezados son los mismos que reconoce la carga: se puede exportar una lista,
corregirla en Excel y volver a cargarla tal cual. Separador punto y coma para que Excel
en español la abra en columnas.
"""
import csv
import io

from app.services import db, maestros_db
from app.text import celda_csv

_PLANTILLAS = {
    "precios": (["codigo", "precio"], ["952", "35000"]),
    "portafolio": (["codigo", "nombre", "precio", "tipo", "categoria", "especie", "muestra"],
                   ["9999", "Análisis de ejemplo", "45000", "analisis", "Hematología", "ambos", "Sangre EDTA"]),
    "clientes": (["nombre", "nit", "telefono", "direccion", "municipio", "correo", "motorizado"],
                 ["Veterinaria Ejemplo", "900123456-1", "3001234567", "Cl 1 # 2-3", "Soacha",
                  "facturas@ejemplo.co", "Javier"]),
    "motorizados": (["nombre", "telefono"], ["Nombre Apellido", "3001234567"]),
}


def _a_texto(encabezados: list[str], filas: list[list]) -> str:
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(encabezados)
    escritor.writerows([["" if v is None else celda_csv(v) for v in fila] for fila in filas])
    return salida.getvalue()


def plantilla(tipo: str) -> str:
    encabezados, ejemplo = _PLANTILLAS[tipo]
    return _a_texto(encabezados, [ejemplo])


def exportar(tipo: str) -> str:
    if tipo == "precios":
        filas = [[t.get("code"), t.get("name"), t.get("price"), "analisis", t.get("species")]
                 for t in db.list_catalog_tests(limit=5000)]
        filas += [[p.get("code"), p.get("name"), p.get("price"), "perfil", p.get("species")]
                  for p in db.list_catalog_profiles(limit=5000)]
        return _a_texto(["codigo", "nombre", "precio", "tipo", "especie"], filas)
    if tipo == "motorizados":
        return _a_texto(["nombre", "telefono", "activo"],
                        [[c.get("name"), c.get("phone"), "si" if c.get("is_active") else "no"]
                         for c in db.list_couriers()])
    nombres = {c["id"]: c.get("name") for c in db.list_couriers()}
    asignados = maestros_db.asignaciones()
    filas = [[c.get("clinic_name"), c.get("tax_id"), c.get("phone"), c.get("address"), c.get("city"),
              c.get("email"), nombres.get(asignados.get(c["id"]), ""), "si" if c.get("is_active") else "no"]
             for c in db.list_clients_basic()]
    return _a_texto(["nombre", "nit", "telefono", "direccion", "municipio", "correo", "motorizado", "activo"], filas)
