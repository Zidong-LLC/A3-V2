# -*- coding: utf-8 -*-
"""Auditoría de cobertura: PDF 'A3 - Catalogo 2025' vs seeds del repo.

Tabla canónica transcrita del PDF (págs. 3-18: análisis, convenios SERVIPAT/LMV y
perfiles diagnósticos). Mascolab (págs. 19-27) queda FUERA a propósito: decisión
2026-08-21, doble precio pendiente de A3 (docs/catalogo-mascolab-pendiente.md).

Compara: códigos faltantes/sobrantes y precios (dinero) contra
db/seeds/002_catalog_tests.sql y db/seeds/001_catalog_profiles.sql.
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# ── ANÁLISIS del PDF: code -> (precio, nombre corto del PDF) ────────────────────
PDF_TESTS = {
    # Hematología (pág. 3)
    "1101": (14000, "Cuadro Hemático Completo"), "1102": (28000, "Prueba Cruzada de Coombs"),
    "1109": (28000, "Prueba de Coombs"), "1103": (7000, "Recuento de Plaquetas"),
    "1104": (8000, "Recuento de Reticulocitos"), "1105": (10000, "Hemoparásitos"),
    "1106": (8000, "Hemoglobina y Hematocrito"), "1107": (22000, "Células L.E."),
    "1108": (18000, "Hemocitología"), "2225": (8000, "Suero Autólogo"),
    # Coagulación
    "1201": (18000, "PT Tiempo de Protrombina"), "1202": (18000, "PTT Tiempo parcial de Tromboplastina"),
    "1203": (65000, "Dímero D Vcheck"), "1204": (74000, "Panel Test de Coagulación"),
    "1205": (33000, "PT y PTT"),
    # Química (págs. 3-4)
    "1301": (20000, "Ácido Úrico"), "1302": (12000, "ALT GPT"), "1303": (12000, "AST GOT"),
    "1304": (12000, "Albúmina"), "1305": (12000, "Amilasa"), "1306": (12000, "Bilirrubina Total"),
    "1307": (15000, "Bilirrubinas Diferenciadas"), "1308": (12000, "Colesterol Total"),
    "1309": (12000, "Creatinina"), "1310": (16000, "Creatina Quinasa MB"),
    "1311": (14000, "Creatina Quinasa NAC"), "1312": (14000, "LDH"),
    "1313": (12000, "Fosfatasa Alcalina"), "1314": (15000, "Fructosamina"),
    "1315": (12000, "GGT"), "1316": (12000, "Glucosa"), "1317": (20000, "Glucosa Pre y Pos"),
    "1318": (21000, "Lipasa Cuantitativa"), "1319": (12000, "Triglicéridos"),
    "1320": (12000, "Urea Sanguínea"), "1321": (12000, "BUN"), "1322": (8000, "Proteínas Totales"),
    "1323": (17000, "Proteínas Diferenciadas"), "1324": (42000, "Amonio"),
    "1325": (18000, "Colesterol HDL"), "1326": (18000, "Colesterol LDL"),
    "1327": (22000, "Colinesterasa"), "2202": (44000, "Ácidos Biliares"),
    "2203": (85000, "Ácidos Biliares Pre y Pos"),
    "1328": (64000, "Lipasa Pancreática Felina Vcheck"), "1329": (62000, "Lipasa Pancreática Canina Vcheck"),
    # Paneles de química liofilizada
    "1330": (108000, "Control de salud"), "1331": (90000, "Función hepática"),
    "1332": (90000, "Función renal"), "1333": (90000, "Pre-operativos"),
    "1334": (90000, "Inflamación canina"), "1335": (90000, "Inflamación felina"),
    "1336": (95000, "Comprensivo"), "1337": (108000, "Diagnóstico Primario"),
    "1338": (90000, "Diabetes"), "1339": (155000, "Generales de Salud"),
    # Minerales (pág. 5)
    "1401": (12000, "Calcio Total"), "1402": (12000, "Fósforo"), "1403": (12000, "Magnesio"),
    "1404": (12000, "Potasio"), "1405": (12000, "Sodio"), "1406": (12000, "Cloro"),
    "1407": (90000, "Electrolitos"), "1408": (90000, "Gases sanguíneos Plus"),
    # Hormonas
    "1501": (36000, "T3 Total"), "1502": (36000, "T4 Total"), "1503": (35000, "T4 Total Canino"),
    "1504": (33000, "TSH"), "1505": (36000, "Cortisol"), "1506": (95000, "Cortisol 3 muestras"),
    "1521": (60000, "Cortisol Pre y Post"), "1507": (33000, "Cortisol en Orina"),
    "1508": (35000, "Estradiol"), "1509": (38000, "Progesterona"), "1510": (36000, "Insulina"),
    "1511": (43000, "Insulina Glucosa"), "1512": (45000, "Testosterona"),
    "1513": (64000, "Progesterona Canina Vcheck"), "1514": (64000, "Cortisol Canina Vcheck"),
    "1515": (64000, "T4 Total Felina Vcheck"), "1516": (64000, "T4 Total Canina Vcheck"),
    "1517": (64000, "TSH Canina Vcheck"), "1518": (180000, "Cortisol Canina 3 muestras Vcheck"),
    # Uroanálisis
    "1601": (16000, "Parcial de Orina"), "1602": (7000, "Lectura Sedimento Urinario"),
    "1604": (22000, "Parcial de Orina y Tinción de Wright"),
    "1605": (22000, "Parcial de Orina y Tinción de Gram"),
    "1606": (30000, "Parcial de Orina Tinción de Gram y Wright"),
    "1603": (83000, "Estudio de Cálculo"),
    # Parasitología (págs. 5-6)
    "1701": (12000, "Coprológico"), "1702": (15000, "Coproscópico"),
    "1703": (13000, "Tripsina en Materia Fecal"), "1704": (7000, "Sangre Oculta"),
    "1705": (20000, "Coproscópico con flotación"),
    # Dermatología
    "1801": (10000, "Raspado de Piel y Pelos"), "1802": (15000, "Raspado de Piel Gram y Wright"),
    "1803": (7000, "Identificación de Ácaro"), "1804": (7000, "Identificación de Ectoparásito"),
    # Citología
    "1901": (15000, "Citología Vaginal"), "1902": (15000, "Citología Malassezia y oído"),
    "1904": (30000, "Citología Líquido Ascítico Pleura"), "1908": (15000, "Citología TVT"),
    "1909": (15000, "Citología Piel"), "1910": (44000, "Espermograma Básico"),
    "1911": (15000, "Citología para Chlamydia Ojo"), "1912": (15000, "Citología Nasal"),
    # Líquidos
    "1905": (52000, "Líquido Cefalorraquídeo"), "1906": (52000, "Líquido Ascítico Pleural"),
    "1907": (52000, "Líquido Sinovial"),
    # Inmunológicos perros (págs. 6-7)
    "2001": (49000, "Brucella Canis"), "2002": (47000, "Coronavirus Canino Antígeno"),
    "2003": (45000, "Dirofilaria Immitis"), "2004": (45000, "Distemper Canino Antígeno"),
    "2005": (36000, "Parvovirus Canino Antígeno"), "2008": (49000, "Ehrlichia Canis"),
    "2009": (135000, "Snap 4DX"), "2012": (82000, "Parvo Corona Giardia"),
    "2013": (77000, "Ehrlichia y Anaplasma"), "2014": (70000, "Lehismania"),
    "2015": (58000, "Parvovirus y Coronavirus"), "2016": (60000, "Preñez Relaxina Canina"),
    "2017": (70000, "Distemper y Adenovirus"),
    "2018": (61000, "Coronavirus Canino Vcheck"), "2019": (50000, "Parvovirus Canino Vcheck"),
    "2020": (61000, "Distemper Canino Anticuerpo Vcheck"), "2021": (61000, "Parvovirus Canino Anticuerpo Vcheck"),
    "2022": (61000, "Adenovirus-1 Canino Vcheck"), "2023": (61000, "Distemper Canino Antígeno Vcheck"),
    "2024": (70000, "Parvo y Corona Vcheck"),
    # Gatos (pág. 7)
    "2052": (130000, "Snap Triple Felina"), "2053": (58000, "FIV y FeLV"),
    "2054": (105000, "Coronavirus Felino PIF Inmunocomb"), "2055": (55000, "Toxoplasma Gondii"),
    "2056": (60000, "Preñez Relaxina Felina"), "2057": (55000, "Panleucopenia Felina Antígeno"),
    "2061": (54000, "Calicivirus Felino Antígeno"), "2062": (62000, "Toxoplasma IgG IgM"),
    "2063": (83000, "Coronavirus Felino PIF Prueba Rápida"),
    "2064": (61000, "Herpesvirus Felino Vcheck"), "2065": (61000, "Panleucopenia Anticuerpo Vcheck"),
    "2066": (61000, "Calicivirus Anticuerpo Vcheck"), "2067": (63000, "Panleucopenia Antígeno Vcheck"),
    # Microbiología
    "2101": (80000, "Cultivo y Antibiograma de Secreciones"), "2102": (80000, "Urocultivo y Antibiograma"),
    "2103": (80000, "Hemocultivo y Antibiograma"), "2104": (80000, "Coprocultivo y Antibiograma"),
    "2105": (45000, "Cultivo y Antibiograma Piel"), "2106": (55000, "Cultivo de Hongos"),
    "2107": (12000, "Coloración de Gram"), "2108": (28000, "Antibiograma Adicional"),
    "2109": (70000, "Cultivo y Antifungigrama"), "2110": (35000, "Cultivo de Bacterias"),
    # Otros (págs. 7-8)
    "2201": (60000, "Fenobarbital"), "2204": (84000, "Tripsina Inmunorreactiva"),
    "2218": (60000, "Cianocobalamina Vitamina B12"), "2219": (60000, "Ácido Fólico"),
    "2205": (65000, "Hemoglobina Glicosilada"), "2206": (30000, "Proteína C reactiva Aglutinación"),
    "2207": (72000, "Test Troponina I Vcheck"), "2208": (159000, "SDMA Vcheck"),
    "2209": (58000, "Proteína C Reactiva Vcheck"), "2210": (63000, "Amiloide Sérico A Felino"),
    "2211": (90000, "NT-ProBNP Canino"), "2212": (83000, "NT-ProBNP Felino"),
    "2213": (150000, "Blood Typing Canine DEA1"), "2214": (150000, "Blood Typing Feline A+B"),
    "2215": (198000, "DAT Canine Anemia Hemolítica"),
    "2216": (227000, "Crossmatch Canine"), "2217": (227000, "Crossmatch Feline"),
    # Convenio SERVIPAT (pág. 9)
    "1903": (52000, "Citología PAF"), "2501": (95000, "Histopatológico Rutina"),
    "2508": (87000, "Coloraciones especiales"), "2509": (None, "Inmunohistoquímicas (85-150k)"),
    "2504": (200000, "Necropsia <500g"), "2505": (250000, "Necropsia 500g-10kg"),
    "2506": (300000, "Necropsia >10kg"), "2507": (12000, "Disposición de cadáver por kilo"),
    "2226": (1200000, "Serología de Rabia"),
    # Convenio LMV (pág. 18)
    "2301": (85000, "Brucella canis 2-Mercaptoetanol"), "2302": (104000, "Brucella canis IgG IFA"),
    "2303": (104000, "Ehrlichia canis IgG IFA"), "2304": (119000, "Leishmaniasis canina IgG IFA"),
    "2305": (95000, "Leptospira 6 serovariedades"), "2306": (124000, "Moquillo Distemper IgM IFA"),
    "2307": (104000, "Neospora caninum IgG IFA"), "2308": (127000, "Babesia canis IgG IFA"),
    "2309": (104000, "PIF IgG IFA"), "2310": (104000, "Toxoplasma gondii IgG IFA"),
    "2311": (104000, "Calicivirus Felino IFA"), "2312": (119000, "Panleucopenia Felina IFA"),
    "2314": (104000, "Anaplasma Canino IFA"), "2315": (104000, "Herpes Felino IFA"),
    "2316": (166000, "Bartonella Felino IFA"),
}

# ── PERFILES del PDF: code -> (precio, nombre) (págs. 10-17) ────────────────────
PDF_PROFILES = {
    "101": (30000, "Parasitológico I"), "102": (23000, "Parasitológico II"),
    "103": (40000, "Parasitológico III"), "104": (25000, "Parasitológico IV"),
    "151": (32000, "General"),
    "152": (24000, "Prequirúrgico I"), "153": (36000, "Prequirúrgico II"),
    "154": (38000, "Prequirúrgico III"), "155": (36000, "Prequirúrgico IV"),
    "156": (27000, "Prequirúrgico V"), "157": (30000, "Prequirúrgico VI"),
    "158": (58000, "Prequirúrgico VII"), "159": (48000, "Prequirúrgico VIII"),
    "160": (55000, "Prequirúrgico IX"), "161": (90000, "Prequirúrgico X"),
    "162": (20000, "Prequirúrgico XI"),
    "201": (39000, "Cachorros I"), "202": (46000, "Cachorros II"), "203": (113000, "Cachorros III"),
    "204": (65000, "Cachorros IV"), "205": (80000, "Cachorros V"), "206": (53000, "Cachorros VI"),
    "207": (19000, "Cachorros VII"), "208": (75000, "Cachorros VIII"), "209": (52000, "Cachorros IX"),
    "210": (89000, "Cachorros X"), "211": (75000, "Cachorros XI"), "212": (26000, "Cachorros XII"),
    "251": (140000, "Hemoparásitos I"), "252": (62000, "Hemoparásitos II"),
    "253": (55000, "Hemoparásitos III"), "254": (20000, "Hemoparásitos IV"),
    "255": (88000, "Hemoparásitos V"),
    "301": (43000, "Felinos I"), "302": (27000, "Felino II"), "303": (20000, "Felino III"),
    "304": (32000, "Felino IV"), "305": (80000, "Felino V"),
    "351": (140000, "Infecciosas Felinas I"), "352": (65000, "Infecciosas Felinas II"),
    "353": (60000, "Infecciosas Felinas III"), "354": (165000, "Infecciosas Felinas IV"),
    "355": (235000, "Infecciosas Felinas V"), "356": (60000, "Infecciosas Felina VI"),
    "357": (150000, "Infecciosas Felina VII"), "358": (220000, "Infecciosas Felina VIII"),
    "359": (70000, "Infecciosas Felina IX"), "360": (160000, "Infecciosas Felina X"),
    "361": (150000, "Infecciosas Felina XI"),
    "401": (37000, "Hepático Canino I"), "402": (38000, "Hepático Canino II"),
    "403": (53000, "Hepático Canino III"), "404": (44000, "Hepático Canino IV"),
    "451": (37000, "Hepático Felino I"), "452": (38000, "Hepático Felino II"),
    "453": (49000, "Hepático Felino III"), "454": (44000, "Hepático Felino IV"),
    "455": (35000, "Hepático Felino V"),
    "501": (34000, "Renal I"), "502": (25000, "Renal II"), "503": (18000, "Renal III"),
    "504": (22000, "Renal IV"), "505": (155000, "Renal V"), "506": (151000, "Renal VI"),
    "507": (65000, "Renal VII"), "508": (162000, "Renal VIII"),
    "551": (37000, "Pancreático I"), "552": (28000, "Pancreático II"),
    "553": (45000, "Pancreático III"), "554": (70000, "Pancreático IV"),
    "555": (72000, "Pancreático V"), "556": (74000, "Pancreático VI"),
    "557": (76000, "Pancreático VII"),
    "601": (62000, "Tiroideo Felino I"), "602": (39000, "Tiroideo Canino I"),
    "603": (60000, "Tiroideo Canino II"), "604": (70000, "Tiroideo Canino III"),
    "605": (80000, "Tiroideo Canino IV"), "606": (120000, "Tiroideo Canino V"),
    "607": (135000, "Tiroideo Canino VI"), "608": (88000, "Tiroideo Felino II"),
    "609": (80000, "Tiroideo Felino III"), "610": (49000, "Tiroideo Canino VII"),
    "651": (39000, "Senior Canino I"), "652": (73000, "Senior Canino II"),
    "653": (58000, "Senior Canino III"), "654": (59000, "Senior Canino IV"),
    "655": (130000, "Senior Canino V"), "656": (46000, "Senior Canino VI"),
    "657": (75000, "Senior Felino I"), "658": (130000, "Senior Felino II"),
    "701": (16000, "Diabético I"), "702": (40000, "Diabético II"), "703": (47000, "Diabético III"),
    "704": (59000, "Diabético IV"), "705": (50000, "Diabético V"),
    "751": (70000, "Dermatológico I"), "752": (52000, "Dermatológico II"),
    "753": (17000, "Dermatológico III"), "754": (80000, "Dermatológico IV"),
    "755": (70000, "Dermatológico Felino I"), "756": (80000, "Dermatológico Felino II"),
    "801": (28000, "Electrolitos I"), "802": (19000, "Electrolitos II"),
    "803": (28000, "Electrolitos III"), "804": (60000, "Electrolitos IV"),
    "851": (112000, "Convulsivo Canino I"), "852": (93000, "Convulsivo Canino II"),
    "861": (100000, "Convulsivo Felino"),
    "901": (43000, "Cardíaco I"), "902": (20000, "Cardíaco II"), "903": (55000, "Cardíaco III"),
    "951": (36000, "Toxicológico Warfarina"), "952": (90000, "Toxicológico Órgano Fosforados"),
    "953": (69000, "Toxicológico Chocolate y Metilxantinas"),
    "954": (93000, "Toxicológico Ácido Acetil Salicílico"),
    "955": (78000, "Toxicológico Metaldehído"), "956": (58000, "Toxicológico Felinos"),
    "980": (42000, "Control Estro I"), "981": (65000, "Control Estro II"),
    "985": (90000, "Control Preñez Canina I"), "986": (65000, "Control Preñez Canina II"),
    "987": (90000, "Control Preñez Felina"),
}

ROW_RE = re.compile(r"^\('(\d+)',\s*'((?:[^']|'')*)',\s*'((?:[^']|'')*)'.*?,\s*(\d+|NULL)\)[,;]?\s*(?:--.*)?$")


def parse_seed(path: Path) -> dict:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line.strip())
        if m:
            code, name, cat, price = m.groups()
            rows[code] = (None if price == "NULL" else int(price), name.replace("''", "'"), cat)
    return rows


def compare(kind: str, pdf: dict, seed: dict) -> int:
    problemas = 0
    faltan = sorted(set(pdf) - set(seed), key=int)
    sobran = sorted(set(seed) - set(pdf), key=int)
    if faltan:
        problemas += len(faltan)
        print(f"\n[{kind}] FALTAN en el seed ({len(faltan)}):")
        for c in faltan:
            print(f"  {c}  {pdf[c][1]}  ${pdf[c][0]:,}" if pdf[c][0] else f"  {c}  {pdf[c][1]}  (precio rango)")
    if sobran:
        print(f"\n[{kind}] En el seed pero NO en el PDF ({len(sobran)}) — verificar origen:")
        for c in sobran:
            print(f"  {c}  {seed[c][1]}  (cat: {seed[c][2]})")
    for c in sorted(set(pdf) & set(seed), key=int):
        p_pdf, p_seed = pdf[c][0], seed[c][0]
        if p_pdf is not None and p_seed is not None and p_pdf != p_seed:
            problemas += 1
            print(f"\n[{kind}] PRECIO distinto {c} ({seed[c][1]}): PDF ${p_pdf:,} vs seed ${p_seed:,}")
    return problemas


def main():
    tests_seed = parse_seed(RAIZ / "db" / "seeds" / "002_catalog_tests.sql")
    profiles_seed = parse_seed(RAIZ / "db" / "seeds" / "001_catalog_profiles.sql")
    print(f"PDF: {len(PDF_TESTS)} análisis + {len(PDF_PROFILES)} perfiles (sin Mascolab)")
    print(f"Seeds: {len(tests_seed)} análisis, {len(profiles_seed)} perfiles")
    # Cruce por CÓDIGO sin importar la tabla: los paneles 1330-1339 del PDF viven como
    # perfiles (catalog_profiles/Bioquímica) — modelado válido, lo que importa es que el
    # código exista con el precio correcto en ALGUNA de las dos.
    pdf_all = {**PDF_TESTS, **PDF_PROFILES}
    seed_all = {**tests_seed, **profiles_seed}
    dup_seed = set(tests_seed) & set(profiles_seed)
    if dup_seed:
        print(f"\n⚠️ Códigos en AMBAS tablas del seed: {sorted(dup_seed)}")
    p = compare("CATÁLOGO", pdf_all, seed_all)
    print(f"\n{'OK: cobertura y precios coinciden' if p == 0 else f'PROBLEMAS: {p}'}")
    return 0 if p == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
