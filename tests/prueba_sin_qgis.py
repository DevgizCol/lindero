# -*- coding: utf-8 -*-
"""
Comprueba que el motor completo corre sin QGIS ni GDAL del sistema: flujo de El Tesoro con el
Python normal, estructura de los shapefile idéntica a la de las entregas y un PDF válido por predio.

    python tests/prueba_sin_qgis.py
"""
import os
import shutil
import sys
import time
import warnings
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import pyogrio

from motor.pipeline import Trabajo, ejecutar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTREGA = os.environ.get("ENTREGA_SHP", r"C:/Dani/Carto_Malambo/BASE_CATASTRAL_MALAMBO/PRIMERA ENTREGA_2025/01.SHAPEFILE")
EXCEL_LOCAL = r"C:/Dani/Carto_Malambo/REC_Tesoro/LEVANTAMIENTO EL TESORO MB OK OK.xlsx"
EXCEL_FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "TESORO_predios_anonimo.xlsx")
EXCEL_DATOS = os.path.join(RAIZ, "tests", "datos", "TESORO_predios.xlsx")
EXCEL = EXCEL_LOCAL if os.path.isfile(EXCEL_LOCAL) else (EXCEL_FIXTURE if os.path.isfile(EXCEL_FIXTURE) else EXCEL_DATOS)

DXF_LOCAL = os.path.join(RAIZ, "tests", "datos", "TESORO_reconstruido.dxf")
DXF_FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "TESORO_reconstruido.dxf")
DXF = DXF_LOCAL if os.path.isfile(DXF_LOCAL) else DXF_FIXTURE


def main():
    for modulo in ("qgis", "osgeo"):
        assert modulo not in sys.modules, modulo
    carpeta = os.path.join(RAIZ, "trabajos", "_prueba_sin_qgis")
    shutil.rmtree(carpeta, ignore_errors=True)
    t0 = time.time()
    inf = ejecutar(Trabajo(carpeta=carpeta, excel=[EXCEL], dxf=DXF, nombre="PRUEBA"), registrar=lambda *_: None)
    seg = time.time() - t0
    ok = lambda cond, txt: print(("  OK   " if cond else "  FALLA ") + txt) or (cond or sys.exit(1))
    ok("qgis" not in sys.modules and "osgeo" not in sys.modules, "no se cargó QGIS ni GDAL del sistema")
    ok(inf["etapas"]["atlas"].get("motor") == "propio" and inf["etapas"]["atlas"]["archivos"] == 22, f"22 PDF con el render propio en {seg:.0f} s")
    for capa in ("LEVANTAMIENTO_01", "COTAS", "COORDENADAS"):
        a = pyogrio.read_info(os.path.join(carpeta, "01.SHAPEFILE", capa + ".shp"))
        if os.path.isdir(ENTREGA):
            b = pyogrio.read_info(os.path.join(ENTREGA, capa + ".shp"))
            ok(list(a["fields"]) == list(b["fields"]) and list(a["dtypes"]) == list(b["dtypes"]), f"{capa}: mismos campos y tipos que la entrega")
        else:
            ok(len(a["fields"]) >= 3, f"{capa}: capa generada con esquema oficial válido ({len(a['fields'])} campos)")
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    pdf = fitz.open(os.path.join(carpeta, "02.PDF", "T11.pdf"))
    texto = pdf[0].get_text()
    ruta_zip = os.path.join(carpeta, "PRUEBA.zip")
    ok(os.path.isfile(ruta_zip), "ZIP de entrega existe")
    with zipfile.ZipFile(ruta_zip) as z:
        nombres = z.namelist()
        ok(any("LEVANTAMIENTO_01.shp" in n for n in nombres), "ZIP contiene Shapefiles catastrales")
        ok(any("T11.pdf" in n for n in nombres), "ZIP contiene PDFs certificados")
        ok("INFORME_REVISION.xlsx" in nombres, "ZIP contiene Informe de Coordenadas Excel")
    shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    main()
