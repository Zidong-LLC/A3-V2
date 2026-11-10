"""Red de seguridad de la carga de informes: el NIT impreso en el PDF (app/informe_pdf.py).

Los textos imitan lo que pypdf saca de un informe real de A3 (Varvet, 09/11/2026): el NIT
de la veterinaria viene pegado a la etiqueta («901915997-3Nit») y el de A3 en el encabezado.
"""
from app import informe_pdf

# Recorte fiel del texto de un informe real, con el NIT de la veterinaria y el de A3.
TEXTO_VARVET = (
    "Veterinaria\nLuz  Pineda\nVarvet Emergencias Veterinarias SAS\n20103092\n09/11/2026\n"
    "23508N° Tarjeta Profesional\ninfo@a3laboratorio.com\nCalle 27 sur # 34-47\n"
    "A3 Laboratorio clinico veterinario Nit: 900.296.338-9 \nPBX: 3208928627\n"
    "www.a3laboratorio.co\n901915997-3Nit\nFecha Emisión09/11/2026Fecha Ensayo 09/11/2026\n"
    "Nitrógeno ureico (BUN) 23.4 mg/dL\nPlaquetas 298 x10e9/L 211 621\n"
)


def _pdf_con_texto(texto: str) -> bytes:
    """Un PDF mínimo de verdad, con el texto en la primera página."""
    contenido = f"BT /F1 10 Tf 20 200 Td ({texto}) Tj ET".encode("latin-1")
    objetos = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 400 300]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>stream\n" % len(contenido) + contenido + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    salida, posiciones = b"%PDF-1.4\n", []
    for numero, objeto in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % numero + objeto + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
    salida += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % (len(objetos) + 1, xref)
    return salida


def test_encuentra_el_nit_de_la_veterinaria_y_descarta_el_de_a3():
    assert informe_pdf.nits_en_texto(TEXTO_VARVET) == {"901915997"}


def test_no_confunde_valores_solicitud_ni_nitrogeno_con_un_nit():
    texto = "Solicitud\n20103092\nPBX: 3208928627\nNitrógeno ureico 123456789 mg/dL\n"
    assert informe_pdf.nits_en_texto(texto) == set()


def test_nit_con_puntos_y_etiqueta_antes():
    assert informe_pdf.nits_en_texto("Cliente: Hocicos  NIT: 830.123.456-1") == {"830123456"}


def test_informe_de_la_misma_veterinaria_pasa():
    assert informe_pdf.nit_ajeno(TEXTO_VARVET, "901915997") is None
    assert informe_pdf.nit_ajeno(TEXTO_VARVET, "901915997-3") is None


def test_verificador_pegado_sin_guion_es_el_mismo_contribuyente():
    assert informe_pdf.nit_ajeno(TEXTO_VARVET, "9019159973") is None


def test_informe_de_otra_veterinaria_se_frena():
    assert informe_pdf.nit_ajeno(TEXTO_VARVET, "830123456-1") == "901915997"


def test_varvet_subido_a_a3_como_cliente_tambien_se_frena():
    """El cliente «A3» de prueba existe: un informe de Varvet no es suyo."""
    assert informe_pdf.nit_ajeno(TEXTO_VARVET, "900296338-9") == "901915997"


def test_sin_nit_en_el_informe_o_en_el_cliente_decide_la_persona():
    assert informe_pdf.nit_ajeno("Paciente Skay\nHemograma", "901915997") is None
    assert informe_pdf.nit_ajeno(TEXTO_VARVET, None) is None
    assert informe_pdf.nit_ajeno(TEXTO_VARVET, "") is None


def test_solo_el_nit_de_a3_no_frena():
    assert informe_pdf.nit_ajeno("A3 Laboratorio Nit: 900.296.338-9", "901915997") is None


def test_lee_el_texto_de_un_pdf_real():
    texto = informe_pdf.texto_de(_pdf_con_texto("901915997-3Nit Varvet"))
    assert "901915997-3Nit" in texto
    assert informe_pdf.nits_en_texto(texto) == {"901915997"}


def test_un_pdf_ilegible_devuelve_texto_vacio_sin_romper():
    assert informe_pdf.texto_de(b"%PDF-1.4 contenido roto") == ""
    assert informe_pdf.texto_de(b"") == ""
