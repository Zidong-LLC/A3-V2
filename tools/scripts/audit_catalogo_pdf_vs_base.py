"""Compara el catálogo PDF de A3 contra los precios cargados en Supabase.

Distinto de `audit_catalogo_pdf.py`, que contrasta una transcripción manual contra los
seeds del repo: este lee el PDF de verdad y lo compara con la base viva, que es la que
cotiza el bot.

    python tools/scripts/audit_catalogo_pdf_vs_base.py "C:/ruta/A3 - Catalogo 2025.pdf"

Solo lectura: reporta diferencias, nunca escribe en la base.

Criterio de parseo: **precisión antes que cobertura**. Se lee línea a línea (en modo
`layout`, que conserva las columnas) y solo se toma el precio que está en la MISMA línea
del código. Los códigos cuyo precio quedó en otra línea se listan aparte para revisarlos
a mano, en vez de emparejarlos por cercanía —que es lo que hacía la primera versión de
este script y producía disparates como leer el código «2301» como un precio de $2.301.
"""

import io
import re
import sys
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.db import _client  # noqa: E402

# El convenio Mascolab (desde la pág. 19) NO se audita: son fichas descriptivas donde el
# precio aparece a varias líneas del código, y cualquier emparejamiento automático se
# desalinea. Sus precios se cargaron desde docs/catalogo-mascolab-pendiente.md
# (migración 030), transcritos a mano de ese mismo PDF.
MASCOLAB_DESDE = 19

# El PDF mezcla DOS formatos de precio: «85.000$» y «$ 85.000».
PRECIO_DERECHA = re.compile(r"([0-9][0-9.]{2,})\s*\$")
PRECIO_IZQUIERDA = re.compile(r"\$\s*([0-9][0-9.]{2,})")
FILA = re.compile(r"^\s*([0-9]{4})\b(.*)$")


def _texto_por_pagina(pdf: Path) -> list[str]:
    """Modo `layout`: preserva las columnas de la tabla, así el precio queda en la misma
    línea que su código. Con la extracción normal, 36 filas de nombre largo perdían el
    precio (el caso 2004 quedaba con la celda vacía); con layout bajan a 5.

    Ojo: las páginas de PERFILES sí necesitan la extracción normal — en layout salen
    desarmadas palabra por palabra. Por eso hay dos pasadas."""
    return [(p.extract_text(extraction_mode="layout") or "") for p in pypdf.PdfReader(str(pdf)).pages]


def _monto(texto: str) -> int | None:
    """Precio de UNA fila, en cualquiera de los dos formatos. None si no hay."""
    for patron in (PRECIO_IZQUIERDA, PRECIO_DERECHA):
        encontrado = patron.search(texto)
        if encontrado:
            valor = int(encontrado.group(1).replace(".", ""))
            if valor >= 1000:
                return valor
    return None


def _filas_del_pdf(texto: str) -> tuple[dict[str, int], list[str]]:
    """Devuelve (precios por código, códigos cuyo precio no estaba en su línea)."""
    precios: dict[str, int] = {}
    sin_precio: list[str] = []
    for linea in texto.splitlines():
        fila = FILA.match(linea)
        if not fila:
            continue
        codigo, resto = fila.group(1), fila.group(2)
        if not (100 <= int(codigo) <= 2599):
            continue
        monto = _monto(resto)
        if monto is None:
            sin_precio.append(codigo)
        else:
            precios[codigo] = monto
    return precios, sin_precio


PERFIL_FILA = re.compile(r"^\s*([0-9]{3})\s+PERFIL\b")


def _perfiles_del_pdf(texto_normal: str) -> dict[str, int]:
    """Precios de los PERFILES DIAGNÓSTICOS (págs. 9-17), que usan otro formato.

    Ahí el código y el nombre van en una línea y el precio en la siguiente:

        101 PERFIL PARASITOLÓGICO I
        3 muestras seriadas de Coprológico   30.000$

    Además esas páginas hay que leerlas en modo normal: en modo `layout` salen
    desarmadas palabra por palabra.
    """
    lineas = texto_normal.splitlines()
    precios: dict[str, int] = {}
    for i, linea in enumerate(lineas):
        fila = PERFIL_FILA.match(linea)
        if not fila:
            continue
        for siguiente in lineas[i + 1 : i + 3]:
            if PERFIL_FILA.match(siguiente):
                break
            monto = _monto(siguiente)
            if monto:
                precios[fila.group(1)] = monto
                break
    return precios


def _es_mascolab(codigo: str, nombre: str) -> bool:
    return "-" in codigo or "(Punto Final)" in nombre or "(Tiempo Real)" in nombre


def main() -> int:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not pdf or not pdf.exists():
        print("Uso: audit_catalogo_pdf_vs_base.py <ruta del PDF>")
        return 1

    paginas = _texto_por_pagina(pdf)
    del_pdf, sin_precio = _filas_del_pdf("\n".join(paginas[: MASCOLAB_DESDE - 1]))
    # Segunda pasada para los PERFILES DIAGNOSTICOS: otro formato y otra extraccion.
    normal = "\n".join(
        (p.extract_text() or "") for p in pypdf.PdfReader(str(pdf)).pages[: MASCOLAB_DESDE - 1]
    )
    del_pdf.update(_perfiles_del_pdf(normal))

    en_base: dict[str, tuple[int, str]] = {}
    for tabla in ("catalog_tests", "catalog_profiles"):
        for fila in _client.table(tabla).select("code,name,price").limit(2000).execute().data:
            en_base[str(fila["code"])] = (int(fila["price"] or 0), fila["name"] or "")

    distintos, faltan, solo_base = [], [], []
    for codigo, precio_pdf in sorted(del_pdf.items()):
        if codigo not in en_base:
            faltan.append((codigo, precio_pdf))
        elif en_base[codigo][0] != precio_pdf:
            distintos.append((codigo, en_base[codigo][1], en_base[codigo][0], precio_pdf))
    for codigo, (precio, nombre) in sorted(en_base.items()):
        if codigo not in del_pdf and not _es_mascolab(codigo, nombre):
            solo_base.append((codigo, nombre, precio))

    def plata(n: int) -> str:
        return "$" + format(n, ",d").replace(",", ".")

    print(f"PDF      : {pdf.name}  ({len(paginas)} paginas)")
    print(f"auditado : paginas 1-{MASCOLAB_DESDE - 1}. Mascolab queda fuera (ver nota del script)")
    print(f"codigos con precio leidos del PDF : {len(del_pdf)}")
    print(f"codigos en la base                : {len(en_base)}")
    if sin_precio:
        unicos = sorted(set(sin_precio))
        print(f"sin precio en su linea, revisar a mano ({len(unicos)}): {', '.join(unicos)}")

    print(f"\n[1] PRECIO DISTINTO ({len(distintos)}):")
    for codigo, nombre, base, pdf_precio in distintos:
        senal = "SUBE" if pdf_precio > base else "BAJA"
        print(f"   {codigo:<6} {nombre[:42]:<42} base {plata(base):>12} -> PDF {plata(pdf_precio):>12}  {senal}")
    if not distintos:
        print("   (ninguno: los precios del PDF coinciden con la base)")

    print(f"\n[2] EN EL PDF PERO NO EN LA BASE ({len(faltan)}):")
    for codigo, precio in faltan:
        print(f"   {codigo:<6} {plata(precio)}")
    if not faltan:
        print("   (ninguno)")

    print(f"\n[3] EN LA BASE PERO NO EN ESTAS PAGINAS DEL PDF ({len(solo_base)}):")
    for codigo, nombre, precio in solo_base[:25]:
        print(f"   {codigo:<6} {nombre[:44]:<44} {plata(precio)}")
    if len(solo_base) > 25:
        print(f"   ... y {len(solo_base) - 25} mas (ver el archivo de detalle)")

    salida = ROOT / "data" / "auditoria-catalogo-vs-pdf.txt"
    salida.parent.mkdir(parents=True, exist_ok=True)
    with io.open(salida, "w", encoding="utf-8") as fh:
        fh.write(f"PDF: {pdf.name} — auditadas las paginas 1-{MASCOLAB_DESDE - 1}\n")
        fh.write(f"\nPRECIO DISTINTO ({len(distintos)}):\n")
        for codigo, nombre, base, pdf_precio in distintos:
            fh.write(f"  {codigo}\t{nombre}\tbase {base}\tpdf {pdf_precio}\n")
        fh.write(f"\nSOLO EN EL PDF ({len(faltan)}):\n")
        for codigo, precio in faltan:
            fh.write(f"  {codigo}\t{precio}\n")
        fh.write(f"\nSOLO EN LA BASE ({len(solo_base)}):\n")
        for codigo, nombre, precio in solo_base:
            fh.write(f"  {codigo}\t{nombre}\t{precio}\n")
        fh.write(f"\nSIN PRECIO EN SU LINEA ({len(set(sin_precio))}):\n")
        for codigo in sorted(set(sin_precio)):
            fh.write(f"  {codigo}\n")
    print(f"\nDetalle completo: {salida.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
