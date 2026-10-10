# -*- coding: utf-8 -*-
"""
Prueba independiente del motor de colindantes sobre predios catastrales reales.

Se toma una muestra de predios urbanos y se usa cada uno como si fuera un lote
levantado, desplazado y girado al azar (como queda un levantamiento ubicado sobre
el catastro). La respuesta correcta de cada lado se conoce por topología: el predio
que comparte ese lindero en la base, o vía si ninguno lo comparte.

Uso: python tests/sintetico.py [n_predios] [desplazamiento_max_m]
"""
import math
import os
import random
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import shapely
from shapely import affinity
from shapely.geometry import LineString

from motor.base import cargar_base
from motor.colindantes import VIA, Lote, analizar_lote, anillo_limpio


def verdad_lado(p1, p2, idx, ctx):
    """Predio que comparte el lindero (por longitud de borde común) o None si es vía."""
    seg = LineString([p1, p2])
    franja = seg.buffer(0.05, cap_style="flat")
    mejor = (0.0, None)
    for g in ctx.terr_tree.query(franja):
        if g == idx:
            continue
        comun = ctx.terr_geom[g].boundary.intersection(franja).length
        if comun > mejor[0]:
            mejor = (comun, ctx.terr_cod[g])
    return mejor[1] if mejor[0] >= 0.5 * seg.length else (None if mejor[0] < 0.1 * seg.length else "AMBIGUO")


def main(n=400, dmax=0.7, semilla=7):
    random.seed(semilla)
    base = cargar_base("malambo")
    ctx = base.contexto()
    t = base.terrenos
    def simple(g):
        return g.geoms[0] if g.geom_type == "MultiPolygon" and len(g.geoms) == 1 else g
    urb = [i for i, (c, g) in enumerate(zip(t.codigo, t.geometry))
           if c[5:7] == "01" and simple(g).geom_type == "Polygon" and 60 < g.area < 600
           and len(simple(g).exterior.coords) <= 9]
    muestra = random.sample(urb, n)
    tot = ok = 0
    m_tot = m_ok = 0.0
    por_tipo = {"predio": [0, 0], "via": [0, 0]}
    fallos = []
    for i in muestra:
        g, cod = simple(ctx.terr_geom[i]), ctx.terr_cod[i]
        verts = anillo_limpio(g)
        ang, dx, dy = random.uniform(-1, 1), random.uniform(-dmax, dmax), random.uniform(-dmax, dmax)
        mov = affinity.translate(affinity.rotate(g, ang, origin="centroid"), dx, dy)
        lote = Lote("X", cod, mov)
        lados = analizar_lote(lote, ctx, vertices=anillo_limpio(mov))
        for k, lado in enumerate(lados):
            p1, p2 = verts[k], verts[(k + 1) % len(verts)]
            if math.dist(p1, p2) < 1.5:
                continue
            v = verdad_lado(p1, p2, i, ctx)
            if v == "AMBIGUO":
                continue
            bien = (lado.tipo == VIA) if v is None else (lado.colindante == v)
            clase = "via" if v is None else "predio"
            por_tipo[clase][0] += 1
            por_tipo[clase][1] += bien
            tot += 1
            ok += bien
            m_tot += lado.longitud
            m_ok += lado.longitud * bien
            if not bien:
                fallos.append((cod[-17:-9], k + 1, round(lado.longitud, 1), "VIA" if v is None else v[-17:-9],
                               lado.tipo, lado.colindante[-17:-9] if lado.colindante.isdigit() else lado.colindante,
                               lado.fraccion, lado.separacion))
    print(f"{n} predios, desplazamiento hasta {dmax} m y giro hasta 1°")
    print(f"lados: {tot}  correctos: {ok} ({100 * ok / tot:.1f}%)   por longitud: {100 * m_ok / m_tot:.1f}%")
    for c, (a, b) in por_tipo.items():
        print(f"  {c}: {b}/{a} ({100 * b / max(a, 1):.1f}%)")
    return fallos


if __name__ == "__main__":
    f = main(int(sys.argv[1]) if len(sys.argv) > 1 else 400, float(sys.argv[2]) if len(sys.argv) > 2 else 0.7)
    for x in f[:25]:
        print("  ", x)
