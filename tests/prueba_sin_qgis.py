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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import pyogrio

from motor.pipeline import Trabajo, ejecutar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTREGA = r"C:/Dani/Carto_Malambo/BASE_CATASTRAL_MALAMBO/PRIMERA ENTREGA_2025/01.SHAPEFILE"
EXCEL = r"C:/Dani/Carto_Malambo/REC_Tesoro/LEVANTAMIENTO EL TESORO MB OK OK.xlsx"


def main():
    for modulo in ("qgis", "osgeo"):
        assert modulo not in sys.modules, modulo
    carpeta = os.path.join(RAIZ, "trabajos", "_prueba_sin_qgis")
    shutil.rmtree(carpeta, ignore_errors=True)
    t0 = time.time()
    inf = ejecutar(Trabajo(carpeta=carpeta, excel=[EXCEL], dxf=os.path.join(RAIZ, "tests", "datos", "TESORO_reconstruido.dxf"),
                           nombre="PRUEBA"), registrar=lambda *_: None)
    seg = time.time() - t0
    ok = lambda cond, txt: print(("  OK   " if cond else "  FALLA ") + txt) or (cond or sys.exit(1))
    ok("qgis" not in sys.modules and "osgeo" not in sys.modules, "no se cargó QGIS ni GDAL del sistema")
    ok(inf["etapas"]["atlas"].get("motor") == "propio" and inf["etapas"]["atlas"]["archivos"] == 22, f"22 PDF con el render propio en {seg:.0f} s")
    for capa in ("LEVANTAMIENTO_01", "COTAS", "COORDENADAS"):
        a = pyogrio.read_info(os.path.join(carpeta, "01.SHAPEFILE", capa + ".shp"))
        b = pyogrio.read_info(os.path.join(ENTREGA, capa + ".shp"))
        ok(list(a["fields"]) == list(b["fields"]) and list(a["dtypes"]) == list(b["dtypes"]), f"{capa}: mismos campos y tipos que la entrega")
    import fitz
    pdf = fitz.open(os.path.join(carpeta, "02.PDF", "T11.pdf"))
    texto = pdf[0].get_text()
    ok(len(pdf) == 1 and "CERTIFICADO PLANO PREDIAL CATASTRAL" in texto and texto.count(" AL ") == 10, "T11.pdf: una hoja, con título y sus 10 tramos")
    ok(os.path.isfile(os.path.join(carpeta, "PRUEBA.zip")), "ZIP de entrega")
    shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    main()
