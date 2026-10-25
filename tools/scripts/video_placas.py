"""Placas, subtítulos y resaltados para el video-recorrido de la plataforma A3."""

_ESTILO = """
#__cap{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:2147483647;
 max-width:1120px;width:calc(100% - 80px);display:flex;gap:14px;align-items:center;
 background:rgba(28,25,23,.93);color:#fff;padding:13px 18px;border-radius:12px;
 font:500 18px/1.35 "Segoe UI",Arial,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.35)}
#__cap .chip{flex:none;font:800 12px "Segoe UI",Arial,sans-serif;letter-spacing:.06em;
 text-transform:uppercase;padding:5px 10px;border-radius:999px}
#__cap .ok{background:#16a34a}#__cap .part{background:#d97706}#__cap .dev{background:#2563eb}
.__hl{outline:4px solid #e11d48!important;outline-offset:4px!important;border-radius:6px}
"""
_CHIPS = {"ok": "Disponible", "part": "Se completa", "dev": "Se desarrolla"}

_PLACA = """<html><head><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
 background:linear-gradient(160deg,#4c0814,#7a0d20 60%,#9a2038);color:#fff;font-family:"Segoe UI",Arial,sans-serif}
.box{width:1080px}.k{letter-spacing:.18em;text-transform:uppercase;font-size:15px;font-weight:700;opacity:.8}
h1{font-size:46px;margin:12px 0 10px;line-height:1.1}p{font-size:21px;opacity:.92;margin:0 0 22px}
.cols{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.col{background:rgba(255,255,255,.1);border-radius:12px;padding:16px 18px}
.col b{display:block;font-size:17px;margin-bottom:8px}.col li{font-size:15.5px;margin:0 0 5px}
ul{margin:0;padding-left:18px}.chip{display:inline-block;padding:5px 12px;border-radius:999px;
 font-weight:800;font-size:13px;letter-spacing:.06em;text-transform:uppercase;margin-right:8px}
.ok{background:#16a34a}.part{background:#d97706}.dev{background:#2563eb}
</style></head><body><div class="box">__CONTENIDO__</div></body></html>"""


def _placa(page, contenido: str, espera: int) -> None:
    page.set_content(_PLACA.replace("__CONTENIDO__", contenido))
    page.wait_for_timeout(espera)


def portada(page) -> None:
    _placa(page, """<div class="k">A3 Laboratorio Veterinario · Octubre de 2026</div>
<h1>Recorrido de la plataforma</h1>
<p>Qué funciona hoy y qué se completa en el cronograma acordado. Datos reales de A3, en modo solo consulta: en este video no se modifica ningún registro.</p>
<p><span class="chip ok">Disponible</span> funciona hoy &nbsp; <span class="chip part">Se completa</span> existe y se amplía &nbsp; <span class="chip dev">Se desarrolla</span> nuevo</p>
<p style="font-size:17px;opacity:.8">Los códigos (A2, A5…) corresponden al documento de pendientes y cronograma.</p>""", 9000)


def cierre(page) -> None:
    _placa(page, """<div class="k">Resumen y fechas</div><h1>Plan hasta la puesta en marcha</h1>
<div class="cols">
<div class="col"><b><span class="chip ok">Disponible</span></b><ul>
<li>Clientes, catálogo, precios y motorizados</li><li>Cargas masivas con vista previa</li>
<li>Agenda y reasignación de recogidas</li><li>Facturación con Alegra y cartera</li>
<li>Resultados de Anarvet</li><li>Portal de clientes</li></ul></div>
<div class="col"><b><span class="chip part">Pendientes</span> entrega 23/10</b><ul>
<li>Usuarios y perfiles · historial de cambios</li><li>Municipios en mapa y cobertura</li>
<li>Reemplazo de motorizado por día o zona</li><li>Plantillas y exportación de cargas</li>
<li>Acceso desde la web · depuración de NIT</li><li>Autorización de datos en WhatsApp</li></ul></div>
<div class="col"><b><span class="chip dev">Hito 1</span> hasta 27/10</b><ul>
<li>Factura electrónica automática</li><li>Pago en línea con Wompi</li>
<li>Enlace de pago en chat, portal y plataforma</li><li>Pago aplicado en Alegra</li></ul>
<b style="margin-top:12px">Pruebas de A3: 28 y 29/10</b><b>Puesta en marcha: 30/10</b></div>
</div>""", 12000)


def subtitulo(page, chip: str, texto: str) -> None:
    page.evaluate("""([css, etiqueta, clase, texto]) => {
      if (!document.getElementById('__capcss')) {
        const s = document.createElement('style'); s.id = '__capcss'; s.textContent = css; document.head.appendChild(s);
      }
      let el = document.getElementById('__cap');
      if (!el) { el = document.createElement('div'); el.id = '__cap'; document.body.appendChild(el); }
      el.innerHTML = '';
      const c = document.createElement('span'); c.className = 'chip ' + clase; c.textContent = etiqueta;
      const t = document.createElement('span'); t.textContent = texto;
      el.append(c, t);
    }""", [_ESTILO, _CHIPS[chip], chip, texto])


def resaltar(page, selector: str) -> None:
    page.evaluate("""(sel) => {
      const e = document.querySelector(sel); if (!e) return;
      e.scrollIntoView({behavior: 'smooth', block: 'center'}); e.classList.add('__hl');
    }""", selector)
    page.wait_for_timeout(1500)


def desplazar(page, pasos: int) -> None:
    for _ in range(pasos):
        page.mouse.wheel(0, 320)
        page.wait_for_timeout(900)
