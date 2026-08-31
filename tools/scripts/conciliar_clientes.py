"""Compara una lista de clientes de A3 contra el padrón de la base.

Pensado para cuando A3 pasa una lista actualizada: responde las tres preguntas que importan,
sin tocar nada de la base.

  1. ¿Qué clientes son NUEVOS? — están en la lista y no en el sistema.
  2. ¿Qué DATOS NUEVOS trae? — clientes que ya existen y la lista completa algo que nos
     falta, sobre todo el NIT, que habilita el portal y la facturación.
  3. ¿Quiénes YA NO ESTÁN en la lista? — candidatos a baja, para que A3 confirme.

    python tools/scripts/conciliar_clientes.py "Documentos de actualizacion/lista.xlsx"
    python tools/scripts/conciliar_clientes.py lista.csv --hoja "Hoja1"

Acepta .xlsx y .csv, y reconoce las columnas por su nombre aunque cambie el encabezado
(«Nombre», «Cliente», «Veterinaria»… / «NIT», «Identificación», «Cédula»…).

**Solo lectura**: nunca escribe en la base. Deja un CSV por grupo en
data/conciliacion-<fecha>/ para revisar y decidir qué aplicar.
"""

import argparse
import csv
import io
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.db import _client, client_name_matches  # noqa: E402

# Cada campo nuestro y los encabezados con los que puede venir en la lista de A3.
ALIAS = {
    "nombre": ("nombre", "cliente", "clientes", "veterinaria", "clinica", "razon social",
               "nombre comercial", "establecimiento"),
    "tax_id": ("nit", "identificacion", "cedula", "documento", "nit/cc", "rut"),
    "phone": ("telefono", "celular", "movil", "contacto", "telefono 1"),
    "address": ("direccion", "domicilio"),
    "city": ("ciudad", "municipio"),
    "email": ("correo", "email", "e-mail", "correo electronico"),
    "medico": ("medico", "medico veterinario", "doctor", "profesional"),
}


def _norm(texto) -> str:
    """Minúsculas sin tildes ni dobles espacios, para comparar encabezados."""
    t = str(texto or "").strip().lower()
    for con, sin in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        t = t.replace(con, sin)
    return re.sub(r"\s+", " ", t).strip()


def _solo_digitos(valor) -> str:
    """NIT comparable: sin puntos, guiones ni dígito de verificación."""
    return re.sub(r"[^0-9]", "", str(valor or "").split("-")[0])


def _mapear_columnas(encabezados: list[str]) -> dict[str, int]:
    """Encabezado de la lista -> campo nuestro. Lo que no reconoce, lo ignora."""
    mapa: dict[str, int] = {}
    for indice, bruto in enumerate(encabezados):
        limpio = _norm(bruto)
        for campo, alias in ALIAS.items():
            if campo in mapa:
                continue
            if limpio in alias or any(limpio.startswith(a) for a in alias):
                mapa[campo] = indice
                break
    return mapa


def _leer_lista(ruta: Path, hoja: str | None) -> tuple[list[dict], dict[str, int]]:
    if ruta.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        libro = openpyxl.load_workbook(ruta, data_only=True)
        pagina = libro[hoja] if hoja else libro.worksheets[0]
        filas = [list(f) for f in pagina.iter_rows(values_only=True)]
    else:
        with io.open(ruta, encoding="utf-8-sig", newline="") as fh:
            muestra = fh.read(4096)
            fh.seek(0)
            try:
                dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t")
            except csv.Error:
                dialecto = csv.excel
            filas = list(csv.reader(fh, dialecto))
    if not filas:
        return [], {}

    mapa = _mapear_columnas([str(c or "") for c in filas[0]])
    registros = []
    for fila in filas[1:]:
        item = {
            campo: (str(fila[i]).strip() if i < len(fila) and fila[i] is not None else "")
            for campo, i in mapa.items()
        }
        if item.get("nombre"):
            registros.append(item)
    return registros, mapa


def _padron() -> list[dict]:
    campos = "id, clinic_name, tax_id, phone, address, city, email, is_active"
    filas: list[dict] = []
    while True:
        lote = (_client.table("clients").select(campos).order("clinic_name")
                .range(len(filas), len(filas) + 999).execute().data) or []
        filas.extend(lote)
        if len(lote) < 1000:
            return filas


def _buscar(item: dict, padron: list[dict], por_nit: dict[str, list[dict]]) -> dict | None:
    """Primero por NIT, que es unívoco; si no hay o no aparece, por nombre.

    El match de nombre es el mismo que usa la identificación del agente y el login del
    portal (`client_name_matches`), para que los tres coincidan en criterio.
    """
    nit = _solo_digitos(item.get("tax_id"))
    if nit and por_nit.get(nit):
        return por_nit[nit][0]
    for cliente in padron:
        if client_name_matches(item["nombre"], cliente.get("clinic_name")):
            return cliente
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Concilia una lista de A3 contra el padrón.")
    ap.add_argument("archivo", help="lista de A3 (.xlsx o .csv)")
    ap.add_argument("--hoja", default=None, help="hoja del Excel (por defecto, la primera)")
    args = ap.parse_args()

    ruta = Path(args.archivo)
    if not ruta.is_absolute():
        ruta = ROOT / ruta
    if not ruta.exists():
        print(f"No encuentro el archivo: {ruta}")
        return 1

    lista, mapa = _leer_lista(ruta, args.hoja)
    if not lista:
        print("La lista está vacía o no tiene una columna de nombre reconocible.")
        print(f"Encabezados que reconozco: {', '.join(sorted(ALIAS))}")
        return 1

    padron = _padron()
    por_nit: dict[str, list[dict]] = {}
    for cliente in padron:
        clave = _solo_digitos(cliente.get("tax_id"))
        if clave:
            por_nit.setdefault(clave, []).append(cliente)

    nuevos: list[dict] = []
    con_datos: list[dict] = []
    encontrados: set[str] = set()
    for item in lista:
        cliente = _buscar(item, padron, por_nit)
        if not cliente:
            nuevos.append(item)
            continue
        encontrados.add(cliente["id"])
        # ¿La lista completa algo que hoy tenemos vacío?
        aportes = {}
        for campo in ("tax_id", "phone", "address", "city", "email"):
            valor = str(item.get(campo) or "").strip()
            actual = str(cliente.get(campo) or "").strip()
            if valor and not actual:
                aportes[campo] = valor
        if aportes:
            con_datos.append({"cliente": cliente, "aportes": aportes})

    activos = [c for c in padron if c.get("is_active")]
    ausentes = [c for c in activos if c["id"] not in encontrados]

    destino = ROOT / "data" / f"conciliacion-{date.today().strftime('%Y%m%d')}"
    destino.mkdir(parents=True, exist_ok=True)

    def escribir(nombre: str, columnas: list[str], filas: list[list]) -> None:
        with open(destino / nombre, "w", newline="", encoding="utf-8-sig") as fh:
            escritor = csv.writer(fh, delimiter=";")
            escritor.writerow(columnas)
            escritor.writerows(filas)

    escribir(
        "1-nuevos.csv",
        ["Veterinaria", "NIT", "Telefono", "Direccion", "Ciudad", "Correo", "Medico"],
        [[n.get("nombre", ""), n.get("tax_id", ""), n.get("phone", ""), n.get("address", ""),
          n.get("city", ""), n.get("email", ""), n.get("medico", "")] for n in nuevos],
    )
    escribir(
        "2-datos-nuevos.csv",
        ["Veterinaria en la base", "NIT actual", "Campo", "Valor que aporta la lista"],
        [[c["cliente"].get("clinic_name", ""), c["cliente"].get("tax_id", "") or "(vacio)",
          campo, valor] for c in con_datos for campo, valor in c["aportes"].items()],
    )
    escribir(
        "3-no-estan-en-la-lista.csv",
        ["Veterinaria", "NIT", "Telefono", "Ciudad"],
        [[a.get("clinic_name", ""), a.get("tax_id", ""), a.get("phone", ""), a.get("city", "")]
         for a in ausentes],
    )

    aportan_nit = sum(1 for c in con_datos if "tax_id" in c["aportes"])
    cobertura = (len(activos) - len(ausentes)) / len(activos) if activos else 0
    print(f"Lista           : {ruta.name} — {len(lista)} filas")
    print(f"Columnas leidas : {', '.join(sorted(mapa)) or '(ninguna)'}")
    print(f"Padron          : {len(padron)} clientes ({len(activos)} activos)")
    print(f"Cobertura       : la lista cubre el {cobertura:.0%} de los activos\n")
    print(f"1. NUEVOS, no estan en el sistema        : {len(nuevos)}")
    print(f"2. Ya existen y la lista completa datos  : {len(con_datos)}"
          + (f"   <- {aportan_nit} aportan el NIT que falta" if aportan_nit else ""))
    print(f"3. Activos que NO estan en la lista      : {len(ausentes)}")
    # Una lista parcial (solo los facturables, solo una zona) deja fuera a media base sin
    # que eso signifique nada. Sin este aviso, el grupo 3 se lee como «570 bajas».
    if cobertura < 0.6:
        print("\n   AVISO: la lista cubre menos del 60% del padron, asi que parece PARCIAL")
        print("   (solo los facturables, una zona, un periodo...). En ese caso el grupo 3")
        print("   NO son bajas: son clientes que esa lista no incluia. Confirmar con A3")
        print("   si la lista pretende ser el padron completo antes de dar de baja a nadie.")
    else:
        print("   (posibles bajas: confirmar con A3 antes de desactivar)")
    print(f"\nDetalle en: {destino.relative_to(ROOT)}")
    print("No se escribio nada en la base: revisar los CSV y decidir que aplicar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
