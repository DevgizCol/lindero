# -*- coding: utf-8 -*-
"""
Reconstruye cómo debería llegar el plano de El Tesoro: un DXF en las coordenadas del topógrafo
(origen Bogotá, EPSG:3116, sin el corrimiento hecho a ojo) con cada predio como polilínea cerrada
y su NODO escrito dentro. Sirve de entrada de prueba para el flujo completo.
"""
import os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")
import geopandas as gpd
from shapely import affinity

ENTREGA = r"C:/Dani/Carto_Malambo/BASE_CATASTRAL_MALAMBO/PRIMERA ENTREGA_2025/01.SHAPEFILE/LEVANTAMIENTO_01.shp"
CORRIMIENTO_MANUAL = (0.02, -3.03)


def escribir_dxf(ruta, poligonos, etiquetas):
    L = ["0", "SECTION", "2", "ENTITIES"]
    for p, n in zip(poligonos, etiquetas):
        L += ["0", "POLYLINE", "8", "PREDIOS", "66", "1", "70", "1"]
        for x, y in list(p.exterior.coords)[:-1]:
            L += ["0", "VERTEX", "8", "PREDIOS", "10", f"{x:.4f}", "20", f"{y:.4f}", "30", "0.0"]
        L += ["0", "SEQEND"]
        c = p.representative_point()
        L += ["0", "TEXT", "8", "NODOS", "10", f"{c.x:.4f}", "20", f"{c.y:.4f}", "30", "0.0", "40", "1.0", "1", str(n)]
    L += ["0", "ENDSEC", "0", "EOF"]
    with open(ruta, "w", encoding="ascii") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    lev = gpd.read_file(ENTREGA).drop_duplicates("NODO")
    lev = lev[lev.NODO.str.startswith("T")]
    lev["geometry"] = lev.geometry.force_2d()
    crudo = gpd.GeoSeries([affinity.translate(g, -CORRIMIENTO_MANUAL[0], -CORRIMIENTO_MANUAL[1]) for g in lev.geometry],
                          crs=lev.crs).to_crs("EPSG:3116")
    destino = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", "TESORO_reconstruido.dxf")
    escribir_dxf(destino, list(crudo.values), list(lev.NODO))
    print(destino, len(lev), "predios")
