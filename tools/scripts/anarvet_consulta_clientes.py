"""Documento imprimible con las dudas de emparejamiento de clientes, para consultarle a A3.

Anarvet entrega el NOMBRE de la veterinaria pero no su NIT, así que hay nombres que no se
pueden vincular a un cliente sin preguntarle a A3. Este script arma un documento con todo lo
que sí sabemos de cada caso —código, fechas, pacientes, propietarios y los candidatos de la
base con su NIT y dirección— para que puedan reconocerlas y respondernos.

Tres bloques:
  1. Las que no pudimos identificar.
  2. Mismo NIT en dos direcciones: ¿son sucursales? Elegimos una sede, que confirmen.
  3. Duplicados de su base (mismo NIT y misma dirección), para que los unifiquen.

Uso:
    python tools/scripts/anarvet_consulta_clientes.py [--salida ruta.html]

Genera HTML; para el PDF, abrirlo e imprimir, o usar Chrome:
    chrome --headless --no-pdf-header-footer --print-to-pdf=salida.pdf file:///...html
"""
import argparse
import html as H
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app import anarvet_map  # noqa: E402
from app.services import db  # noqa: E402

e = H.escape
LIMITE_PACIENTES = 8
LIMITE_DUENOS = 5


def _opciones(candidatos: list[dict]) -> str:
    return "".join(
        '<div class="op"><b>{}</b><span>NIT {} &middot; {}</span></div>'.format(
            e(str(c.get("clinic_name") or "?")),
            e(str(c.get("tax_id") or "sin NIT")),
            e(str(c.get("address") or "sin direccion")))
        for c in candidatos)


def _detalle_anarvet(cod_cliente: str) -> dict:
    """Pacientes, propietarios y fechas de ese código: con eso A3 lo reconoce."""
    filas = (
        db._client.table("anarvet_results")
        .select("mascota,nombre_propietario,fecha_solicitud")
        .eq("cod_cliente", cod_cliente).limit(500).execute().data
    ) or []
    pacientes = sorted({(f.get("mascota") or "").strip() for f in filas if f.get("mascota")})
    duenos = sorted({(f.get("nombre_propietario") or "").strip()
                     for f in filas if f.get("nombre_propietario")})
    fechas = sorted({str(f["fecha_solicitud"]) for f in filas if f.get("fecha_solicitud")})
    return {
        "pacientes": pacientes[:LIMITE_PACIENTES],
        "duenos": duenos[:LIMITE_DUENOS],
        "fechas": f"{fechas[0]} a {fechas[-1]}" if fechas else "sin fecha",
    }


def recolectar() -> dict:
    """Los tres grupos de dudas, leyendo el estado real del mapeo."""
    activos = [c for c in db.list_clients_with_assignment()
               if c.get("is_active", True) and (c.get("clinic_name") or "").strip()]
    mapa = db.list_anarvet_client_map()
    informes = db.count_anarvet_informes_por_cliente()
    por_id = {str(c["id"]): c for c in activos}

    sin_identificar, sedes, duplicados = [], [], []
    for fila in mapa:
        cod = str(fila.get("cod_cliente") or "")
        nombre = fila.get("nombre_cliente")
        candidatos = anarvet_map.candidatos_para(nombre, activos)
        base = {"nombre": nombre, "cod": cod, "informes": informes.get(cod, 0)}

        if not fila.get("client_id"):
            if not candidatos:
                candidatos = [s["cliente"] for s in anarvet_map.sugerencias(nombre, activos, 3)]
                etiqueta = "&iquest;Es alguna de estas?" if candidatos else "No aparece en su base"
            else:
                etiqueta = "Hay dos registros suyos" if len(candidatos) > 1 else "Confirmar"
            sin_identificar.append({**base, **_detalle_anarvet(cod),
                                    "candidatos": candidatos, "etiqueta": etiqueta})
            continue

        if len(candidatos) < 2:
            continue  # emparejada sin competencia: no hay nada que preguntar
        elegido = por_id.get(str(fila["client_id"]))
        direcciones = {anarvet_map._direccion_normalizada(c.get("address")) for c in candidatos}
        destino = sedes if len(direcciones) > 1 else duplicados
        destino.append({**base, "candidatos": candidatos,
                        "asignado": elegido["clinic_name"] if elegido else "?"})

    sin_identificar.sort(key=lambda x: -x["informes"])
    sedes.sort(key=lambda x: -x["informes"])
    duplicados.sort(key=lambda x: -x["informes"])
    emparejadas = sum(1 for m in mapa if m.get("client_id"))
    return {"sin_identificar": sin_identificar, "sedes": sedes, "duplicados": duplicados,
            "total_mapa": len(mapa), "emparejadas": emparejadas}


_ESTILO = """
 :root{--vino:#7a1725;--vino2:#9b2233;--tinta:#1c1c1e;--gris:#6b6b70;--linea:#e2e2e6;--suave:#f7f7f9}
 *{box-sizing:border-box}
 body{margin:0;background:#ececed;color:var(--tinta);
   font-family:'Public Sans',system-ui,-apple-system,'Segoe UI',sans-serif;font-size:10.5px;line-height:1.4}
 .hoja{width:210mm;margin:14px auto;padding:12mm;background:#fff;box-shadow:0 8px 26px rgba(0,0,0,.12)}
 .cab{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;
   border-bottom:3px solid var(--vino);padding-bottom:9px}
 .marca{display:flex;align-items:center;gap:10px}
 .sello{width:42px;height:42px;border-radius:50%;background:var(--vino);color:#fff;display:flex;
   align-items:center;justify-content:center;font-weight:800;font-size:17px}
 .marca h1{margin:0;font-size:16px;font-weight:800}
 .marca span{display:block;font-size:9.5px;color:var(--vino2);font-weight:600;
   text-transform:uppercase;letter-spacing:1px}
 .contacto{text-align:right;font-size:9px;color:var(--gris);line-height:1.55}
 h2.doc{margin:11px 0 3px;font-size:14px;letter-spacing:2px;text-transform:uppercase;color:var(--vino)}
 .intro{margin:0 0 6px;color:var(--gris);max-width:64ch}
 h3.sec{margin:14px 0 3px;font-size:12px;color:var(--vino);border-bottom:1px solid var(--linea);
   padding-bottom:3px;break-after:avoid;page-break-after:avoid}
 .sec-nota{margin:0 0 7px;color:var(--gris);font-size:10px}
 .caso{border:1px solid var(--linea);border-radius:7px;padding:8px 10px;margin-bottom:6px;
   break-inside:avoid;page-break-inside:avoid}
 .caso-cab{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;margin-bottom:5px}
 .titulo{font-size:12px}
 .sub{display:block;color:var(--gris);font-size:9px}
 .derecha{display:flex;align-items:center;gap:7px;flex-shrink:0}
 .cuenta{background:var(--vino);color:#fff;border-radius:100px;padding:2px 8px;font-weight:700;font-size:10px}
 .etq{background:var(--suave);border:1px solid var(--linea);border-radius:100px;padding:2px 7px;
   font-size:9px;color:var(--gris);white-space:nowrap}
 .grid2{display:grid;grid-template-columns:1fr 1fr;gap:11px;border-top:1px solid var(--suave);padding-top:6px}
 .rot{display:block;font-size:8.5px;letter-spacing:1px;text-transform:uppercase;color:var(--gris);
   font-weight:700;margin-bottom:1px}
 .grid2 p{margin:0 0 6px}
 .op{background:var(--suave);border-radius:5px;padding:4px 7px;margin-bottom:3px}
 .op b{display:block}
 .op span{color:var(--gris);font-size:9.5px}
 .op.vacio{color:var(--gris);font-style:italic}
 .aclara{margin:0 0 5px}
 .responder{margin-top:6px;border-top:1px dashed var(--linea);padding-top:5px}
 .responder .linea{border-bottom:1px solid var(--tinta);height:13px}
 .pie{margin-top:14px;padding-top:8px;border-top:1px solid var(--linea);color:var(--gris);
   font-size:9.5px;display:flex;justify-content:space-between}
 @page{size:A4;margin:0}
 @media print{body{background:#fff}.hoja{margin:0;box-shadow:none;width:auto;padding:10mm 11mm}}
"""

_DOC = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>A3 - Veterinarias por identificar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{estilo}</style></head><body>
<div class="hoja">
 <header class="cab">
   <div class="marca"><div class="sello">A3</div>
     <div><h1>A3 Laboratorio</h1><span>Cl&iacute;nico Veterinario</span></div></div>
   <div class="contacto"><b>Calle 27 sur 34 - 47 Piso 1</b><br>Bogot&aacute; D.C. &middot; Tel 601 794 5741<br>
     info@a3laboratorio.co</div>
 </header>
 <h2 class="doc">Veterinarias por identificar</h2>
 <p class="intro">Estamos conectando los resultados de Anarvet con las veterinarias de su base
   para que cada una vea los suyos en el portal. Anarvet nos entrega el <b>nombre</b> del
   cliente pero <b>no su NIT</b>, as&iacute; que en estos casos no podemos determinar de
   qui&eacute;n son sin su ayuda. El n&uacute;mero en vino es la cantidad de informes en juego.</p>
 <h3 class="sec">1 &middot; No pudimos identificarlas ({n1})</h3>
 <p class="sec-nota">Hasta saber a qui&eacute;n corresponden, estos resultados no se le muestran
   a nadie. Incluimos pacientes y propietarios para que puedan reconocerlas.</p>
 {b1}
 <h3 class="sec">2 &middot; Mismo NIT, dos direcciones &mdash; &iquest;son sucursales? ({n2})</h3>
 <p class="sec-nota">Elegimos una sede para no dejar los resultados sin due&ntilde;o.
   Conf&iacute;rmennos si es la correcta.</p>
 {b2}
 <h3 class="sec">3 &middot; Clientes duplicados en su base ({n3})</h3>
 <p class="sec-nota">Mismo NIT y misma direcci&oacute;n, cargados dos veces. No afecta a los
   resultados &mdash;los asignamos a la ficha que tiene motorizado&mdash; pero conviene unificarlos.</p>
 {b3}
 <footer class="pie"><span>De {total} veterinarias en Anarvet ya identificamos {ok}.</span>
   <span>{fecha}</span></footer>
</div></body></html>"""


def construir(datos: dict, fecha: str) -> str:
    b1 = "".join(
        '<div class="caso"><div class="caso-cab"><div><b class="titulo">{n}</b>'
        '<span class="sub">c&oacute;digo {cod} &middot; {fechas}</span></div>'
        '<div class="derecha"><span class="cuenta">{inf}</span><span class="etq">{etq}</span></div></div>'
        '<div class="grid2"><div><span class="rot">Pacientes</span><p>{pac}</p>'
        '<span class="rot">Propietarios</span><p>{due}</p></div>'
        '<div><span class="rot">En su base de clientes</span>{ops}</div></div>'
        '<div class="responder"><span class="rot">Su respuesta</span><div class="linea"></div></div></div>'
        .format(n=e(str(c["nombre"])), cod=e(c["cod"]), fechas=e(c["fechas"]), inf=c["informes"],
                etq=c["etiqueta"], pac=e(", ".join(c["pacientes"])) or "&mdash;",
                due=e(", ".join(c["duenos"])) or "&mdash;",
                ops=_opciones(c["candidatos"]) or
                    '<div class="op vacio">Ninguna veterinaria de su base se parece a este nombre.</div>')
        for c in datos["sin_identificar"])

    b2 = "".join(
        '<div class="caso"><div class="caso-cab"><div><b class="titulo">{n}</b>'
        '<span class="sub">c&oacute;digo {cod}</span></div>'
        '<div class="derecha"><span class="cuenta">{inf}</span></div></div>'
        '<p class="aclara">Mismo NIT en dos direcciones. Asignamos los resultados a <b>{asig}</b>. '
        '&iquest;Es la sede correcta?</p>{ops}'
        '<div class="responder"><span class="rot">Sede correcta</span><div class="linea"></div></div></div>'
        .format(n=e(str(c["nombre"])), cod=e(c["cod"]), inf=c["informes"],
                asig=e(str(c["asignado"])), ops=_opciones(c["candidatos"]))
        for c in datos["sedes"])

    b3 = "".join(
        '<div class="caso"><div class="caso-cab"><div><b class="titulo">{n}</b>'
        '<span class="sub">c&oacute;digo {cod}</span></div>'
        '<div class="derecha"><span class="cuenta">{inf}</span></div></div>{ops}'
        '<div class="responder"><span class="rot">Ficha que queda</span><div class="linea"></div></div></div>'
        .format(n=e(str(c["nombre"])), cod=e(c["cod"]), inf=c["informes"],
                ops=_opciones(c["candidatos"]))
        for c in datos["duplicados"])

    return _DOC.format(
        estilo=_ESTILO, b1=b1, b2=b2, b3=b3, fecha=fecha,
        n1=len(datos["sin_identificar"]), n2=len(datos["sedes"]), n3=len(datos["duplicados"]),
        total=datos["total_mapa"], ok=datos["emparejadas"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", default=str(RAIZ / "docs" / "anarvet-consulta-clientes.html"))
    parser.add_argument("--fecha", default="", help="Fecha del documento (por defecto, hoy)")
    args = parser.parse_args()

    from datetime import datetime

    from app.config import APP_TIMEZONE

    fecha = args.fecha or datetime.now(APP_TIMEZONE).strftime("%d de %B de %Y")
    datos = recolectar()
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(construir(datos, fecha), encoding="utf-8")
    print(f"-> {salida}")
    print(f"   {len(datos['sin_identificar'])} sin identificar, "
          f"{len(datos['sedes'])} sedes a confirmar, {len(datos['duplicados'])} duplicados")
    print(f"   {datos['emparejadas']}/{datos['total_mapa']} veterinarias ya emparejadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
