# -*- coding: utf-8 -*-
"""
Prueba independiente de la ubicación: grupos de predios catastrales contiguos se corren y giran
una cantidad conocida (como llega un levantamiento con el GPS desfasado) y se mide con cuánto
error los devuelve el motor a su sitio.

Uso: python tests/sintetico_ubicacion.py [n_grupos] [corrimiento_max_m]
"""
import math, os, random, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")
import numpy as np
import shapely
from shapely import affinity
from shapely.strtree import STRtree
from motor.base import cargar_base
from motor.ubicacion import ubicar


def main(n=40, dmax=4.0, semilla=5):
    random.seed(semilla)
    base = cargar_base("malambo")
    t = base.terrenos
    geoms = list(t.geometry); cods = list(t.codigo)
    tree = STRtree(geoms)
    urb = [i for i, (c, g) in enumerate(zip(cods, geoms)) if c[5:7] == "01" and 60 < g.area < 500]
    err = {"con códigos": [], "sin códigos": []}
    for _ in range(n):
        i = random.choice(urb)
        # el predio y hasta 5 vecinos de la misma manzana
        vec = [j for j in tree.query(geoms[i].buffer(0.3), predicate="intersects") if cods[j][:17] == cods[i][:17] and 60 < geoms[j].area < 500]
        grupo = list(dict.fromkeys([i] + list(vec)))[:random.randint(1, 6)]
        dx, dy = random.uniform(-dmax, dmax), random.uniform(-dmax, dmax)
        orig = [geoms[j] for j in grupo]
        mov = [affinity.translate(g, dx, dy) for g in orig]
        for nombre, c in (("con códigos", [cods[j] for j in grupo]), ("sin códigos", None)):
            u = ubicar(mov, base, c, permitir_giro=False)
            e = max(a.centroid.distance(b.centroid) for a, b in zip(u.poligonos, orig))
            err[nombre].append(e)
    print(f"{n} grupos de 1 a 6 predios, corridos hasta {dmax} m en cada eje")
    for k, v in err.items():
        v = np.array(v)
        print(f"  {k}: error mediano {np.median(v):.2f} m | p90 {np.percentile(v, 90):.2f} m | máx {v.max():.2f} m | "
              f"dentro de 0,5 m: {100 * np.mean(v <= 0.5):.0f}%")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40, float(sys.argv[2]) if len(sys.argv) > 2 else 4.0)
