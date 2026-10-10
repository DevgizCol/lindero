# -*- coding: utf-8 -*-
"""
Prueba de la ubicación automática con El Tesoro: se devuelven los lotes entregados a las
coordenadas en que llegó el plano del topógrafo (origen Bogotá, sin el corrimiento que se hizo
a ojo) y se comprueba que el motor los vuelve a dejar donde quedaron en la entrega.
"""
import os, sys, time, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")
import geopandas as gpd
import numpy as np
from shapely import affinity
from motor.base import cargar_base
from motor.ubicacion import ubicar

ENTREGA = r"C:/Dani/Carto_Malambo/BASE_CATASTRAL_MALAMBO/PRIMERA ENTREGA_2025/01.SHAPEFILE/LEVANTAMIENTO_01.shp"
CORRIMIENTO_MANUAL = (0.02, -3.03)   # medido entre la cartera reproyectada y la entrega


def main():
    base = cargar_base("malambo")
    lev = gpd.read_file(ENTREGA).drop_duplicates("NODO")
    lev = lev[lev.NODO.str.startswith("T")]
    lev["geometry"] = lev.geometry.force_2d()
    crudo = gpd.GeoSeries([affinity.translate(g, -CORRIMIENTO_MANUAL[0], -CORRIMIENTO_MANUAL[1]) for g in lev.geometry],
                          crs=base.crs).to_crs("EPSG:3116")
    for nombre, cods in (("sin códigos", None), ("con códigos del Excel", list(lev.CODIGO))):
        t = time.time()
        u = ubicar(list(crudo.values), base, cods)
        d = [a.centroid.distance(b.centroid) for a, b in zip(u.poligonos, lev.geometry)]
        iguales = sum(1 for a, b in zip(u.codigo_debajo, lev.CODIGO) if a == b)
        print(f"[{nombre}] CRS detectado: {u.crs_origen} | ajuste dx={u.dx:.2f} dy={u.dy:.2f} giro={u.giro:.2f}° "
              f"(manual: {CORRIMIENTO_MANUAL}) | fuera de predio {100*u.fuera_antes:.1f}% -> {100*u.fuera_despues:.1f}% "
              f"| diferencia con la entrega: mediana {np.median(d):.2f} m, máx {max(d):.2f} m "
              f"| código por traslape igual al del Excel: {iguales}/{len(lev)} | {time.time()-t:.1f}s")
        for a in u.avisos:
            print("   aviso:", a)
        print("   distintos:", [(n, e[13:21], c[13:21], round(k, 2)) for n, e, c, k in zip(lev.NODO, lev.CODIGO, u.codigo_debajo, u.calce) if e != c])


if __name__ == "__main__":
    main()
