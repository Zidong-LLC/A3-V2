"""Arma el PDF de veterinarias sin NIT para entregarle a A3.

Sin NIT una veterinaria no puede entrar al portal (se accede con el nombre de la clínica y
el NIT) ni recibir factura electrónica. Este PDF es la planilla para que A3 complete el dato.

Ordena por PRIORIDAD, no alfabéticamente: primero las que ya tienen actividad en el
laboratorio (informes en Anarvet, motorizado asignado o dirección cargada), porque son las
que hoy están operando sin poder entrar al portal.

    python tools/scripts/pdf_clientes_sin_nit.py

Genera data/veterinarias-sin-nit.pdf con Chromium (mismo motor que app/services/pdf.py).
"""

import io
import re
import sys
from datetime import date
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.db import _client  # noqa: E402

EXCEL_DOCTORES = ROOT / "Documentos de actualizacion" / "Clientes y Doctores A3.xlsx"
SALIDA_HTML = ROOT / "data" / "veterinarias-sin-nit.html"
SALIDA_PDF = ROOT / "data" / "veterinarias-sin-nit.pdf"

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _clave(texto) -> str:
    return re.sub(r"[^a-z0-9]", "", str(texto or "").lower())


def _medicos_del_excel() -> dict[str, str]:
    """Nombre de veterinaria -> médico, de la lista que A3 pasó el 22/07."""
    if not EXCEL_DOCTORES.exists():
        return {}
    hoja = openpyxl.load_workbook(EXCEL_DOCTORES, data_only=True)["Hoja1"]
    medicos: dict[str, str] = {}
    for nombre, medico in list(hoja.iter_rows(values_only=True))[1:]:
        if nombre and medico:
            medicos[_clave(nombre)] = str(medico).strip()
    return medicos


def _sin_nit() -> list[dict]:
    campos = ("id, clinic_name, address, zone, external_code, "
              "client_courier_assignment(couriers(name))")
    filas: list[dict] = []
    while True:
        lote = (_client.table("clients").select(campos + ", tax_id").eq("is_active", True)
                .order("clinic_name").range(len(filas), len(filas) + 999).execute().data) or []
        filas.extend(lote)
        if len(lote) < 1000:
            break
    return [f for f in filas if not str(f.get("tax_id") or "").strip()]


def _motorizado(fila: dict) -> str:
    asignacion = fila.get("client_courier_assignment")
    if isinstance(asignacion, list):
        asignacion = asignacion[0] if asignacion else None
    if not isinstance(asignacion, dict):
        return ""
    return (asignacion.get("couriers") or {}).get("name") or ""


def _escapar(texto: str) -> str:
    return (str(texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main() -> int:
    medicos = _medicos_del_excel()
    clientes = _sin_nit()
    con_informes = {m["client_id"] for m in
                    _client.table("anarvet_client_map").select("client_id").limit(500).execute().data
                    if m.get("client_id")}

    registros = []
    for fila in clientes:
        senales = []
        if fila["id"] in con_informes:
            senales.append("informes")
        if _motorizado(fila):
            senales.append("motorizado")
        if str(fila.get("address") or "").strip() and "sin direcc" not in str(fila.get("address")).lower():
            senales.append("dirección")
        registros.append({
            "nombre": fila.get("clinic_name") or "",
            "medico": medicos.get(_clave(fila.get("clinic_name")), ""),
            "senales": senales,
        })
    # Prioridad: primero las que muestran actividad; dentro de cada grupo, alfabético.
    prioritarias = sorted([r for r in registros if r["senales"]], key=lambda r: r["nombre"].lower())
    resto = sorted([r for r in registros if not r["senales"]], key=lambda r: r["nombre"].lower())

    hoy = date.today()
    fecha = f"{hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}"

    def tabla(items: list[dict], desde: int) -> str:
        filas_html = []
        for i, r in enumerate(items, desde):
            senal = ", ".join(r["senales"])
            filas_html.append(
                f'<tr><td class="n">{i}</td><td class="vet">{_escapar(r["nombre"])}'
                + (f'<span class="senal">{_escapar(senal)}</span>' if senal else "")
                + f'</td><td class="med">{_escapar(r["medico"]) or "—"}</td><td class="nit"></td></tr>'
            )
        return "\n".join(filas_html)

    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Veterinarias sin NIT — A3</title>
<style>
  @page {{ size: A4; margin: 14mm 12mm 16mm; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:"Public Sans","Segoe UI",Arial,sans-serif; color:#171717; font-size:10pt; }}
  .cab {{ display:flex; align-items:center; gap:12px; border-bottom:2px solid #7a0d20; padding-bottom:10px; margin-bottom:14px; }}
  .logo {{ width:38px; height:38px; border-radius:50%; background:#7a0d20; color:#fff; display:flex;
           align-items:center; justify-content:center; font-weight:800; font-size:13pt; }}
  .cab h1 {{ margin:0; font-size:16pt; font-weight:800; letter-spacing:-.02em; }}
  .cab p {{ margin:2px 0 0; font-size:9pt; color:#67676f; }}
  .intro {{ background:#f7ebee; border:1px solid #7a0d20; border-radius:4px; padding:10px 12px; margin-bottom:14px; }}
  .intro p {{ margin:0 0 6px; font-size:9.5pt; line-height:1.5; }}
  .intro p:last-child {{ margin-bottom:0; }}
  .intro b {{ color:#7a0d20; }}
  h2 {{ font-size:11pt; margin:16px 0 6px; padding-bottom:4px; border-bottom:1px solid #d3d4d9; }}
  h2 span {{ font-weight:400; color:#67676f; font-size:9pt; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ font-size:7.5pt; text-transform:uppercase; letter-spacing:.06em; color:#67676f; text-align:left;
        border-bottom:1px solid #171717; padding:4px 6px; }}
  td {{ padding:5px 6px; border-bottom:1px solid #e6e6ea; font-size:9pt; vertical-align:middle; }}
  td.n {{ width:24px; color:#87878f; font-size:8pt; }}
  td.vet {{ font-weight:600; }}
  td.med {{ color:#3f3f46; width:33%; }}
  td.nit {{ width:24%; border-bottom:1px solid #171717; }}
  .senal {{ display:block; font-weight:400; font-size:7.5pt; color:#7a0d20; text-transform:uppercase; letter-spacing:.05em; }}
  tr {{ page-break-inside:avoid; }}
  .pie {{ margin-top:16px; padding-top:8px; border-top:1px solid #d3d4d9; font-size:8pt; color:#67676f; }}
</style></head><body>

<div class="cab">
  <div class="logo">A3</div>
  <div>
    <h1>Veterinarias sin NIT registrado</h1>
    <p>{len(registros)} clientes activos · {fecha}</p>
  </div>
</div>

<div class="intro">
  <p><b>Para qué es esta lista.</b> Estas {len(registros)} veterinarias están activas pero no tienen
  NIT en el sistema. Sin ese dato <b>no pueden entrar al portal</b> —se accede con el nombre de la
  clínica y el NIT— y <b>no se les puede emitir factura electrónica</b>. Siguen pidiendo por
  Telegram con normalidad.</p>
  <p><b>De dónde salen.</b> {len(registros) - 7} de ellas entraron el 22 de julio desde la lista
  «Clientes y Doctores A3», que solo traía el nombre y el médico: por eso no tienen NIT, ni
  teléfono, ni dirección.</p>
  <p><b>Cómo completarla.</b> Escribir el NIT en la columna de la derecha. Las del primer grupo
  son las urgentes: ya tienen movimiento en el laboratorio.</p>
</div>

<h2>Con actividad en el laboratorio <span>— completar primero ({len(prioritarias)})</span></h2>
<table>
  <thead><tr><th></th><th>Veterinaria</th><th>Médico veterinario</th><th>NIT</th></tr></thead>
  <tbody>
{tabla(prioritarias, 1)}
  </tbody>
</table>

<h2>Resto de la lista <span>— sin movimiento registrado ({len(resto)})</span></h2>
<table>
  <thead><tr><th></th><th>Veterinaria</th><th>Médico veterinario</th><th>NIT</th></tr></thead>
  <tbody>
{tabla(resto, len(prioritarias) + 1)}
  </tbody>
</table>

<p class="pie">A3 Laboratorio Clínico Veterinario · Generado desde la plataforma el {fecha}.
«Con actividad» significa que la veterinaria tiene informes en Anarvet, motorizado asignado o
dirección cargada.</p>

</body></html>"""

    SALIDA_HTML.parent.mkdir(parents=True, exist_ok=True)
    io.open(SALIDA_HTML, "w", encoding="utf-8").write(html)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        navegador = pw.chromium.launch()
        pagina = navegador.new_page()
        pagina.goto(SALIDA_HTML.as_uri(), wait_until="load")
        pagina.wait_for_timeout(600)
        pagina.pdf(path=str(SALIDA_PDF), format="A4", print_background=True,
                   margin={"top": "14mm", "bottom": "16mm", "left": "12mm", "right": "12mm"})
        navegador.close()

    print(f"veterinarias sin NIT : {len(registros)}")
    print(f"  con actividad      : {len(prioritarias)}  (van primero)")
    print(f"  sin movimiento     : {len(resto)}")
    print(f"  con médico conocido: {sum(1 for r in registros if r['medico'])}")
    print(f"\nPDF: {SALIDA_PDF.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
