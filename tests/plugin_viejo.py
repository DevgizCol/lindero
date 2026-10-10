# -*- coding: utf-8 -*-
"""Réplica en shapely de AICore.evaluate() del plugin Colindante Elite v3 (solo para medir el antes/después)."""
import math
from shapely.geometry import LineString, Polygon
import shapely


def evaluar_viejo(p1, p2, poly, codigo, ctx):
    seg = LineString([p1, p2])
    buf = seg.buffer(0.03, 2)
    cont = []
    for g in ctx.terr_tree.query(buf):
        c = ctx.terr_cod[g]
        if c == codigo:
            continue
        geom = ctx.terr_geom[g]
        d = seg.distance(geom)
        if d <= 0.03:
            cont.append((d, -buf.intersection(geom).area, c))
    if cont:
        cont.sort()
        return cont[0][2]
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    l = math.hypot(vx, vy)
    if l == 0:
        return "NO_ENCONTRADO"
    nx, ny = -vy / l, vx / l
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    if shapely.contains_xy(poly, mx + nx * 0.02, my + ny * 0.02):
        nx, ny = -nx, -ny
    box = Polygon([p1, p2, (p2[0] + nx * 6, p2[1] + ny * 6), (p1[0] + nx * 6, p1[1] + ny * 6)])
    cand = []
    for g in ctx.via_tree.query(box):
        geom = ctx.via_geom[g]
        if box.intersects(geom):
            d = seg.distance(geom)
            cand.append((-(box.intersection(geom).length / max(0.2, d)), d, ctx.via_nom[g]))
    for g in ctx.terr_tree.query(box):
        c = ctx.terr_cod[g]
        if c == codigo:
            continue
        geom = ctx.terr_geom[g]
        if box.intersects(geom):
            d = seg.distance(geom)
            cand.append((-(box.intersection(geom).area / max(0.5, d)), d, c))
    if not cand:
        return "NO_ENCONTRADO"
    cand.sort()
    return cand[0][2]


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tests.eval_colindantes import evaluar
    filas, lotes, ctx, base = evaluar(verbose=False)
    por = {l.nodo: l for l in lotes}
    # la referencia se corrige en los dos lados de T4 que quedaron intercambiados en la entrega
    def ref(f):
        if f["nodo"] == "T4" and f["tramo"] in ("5 AL 6", "6 AL 7"):
            return f["motor"]
        return f["esperado"]
    tes = [f for f in filas if f["nodo"] != "C1"]
    v = sum(evaluar_viejo(f["lado"].p1, f["lado"].p2, por[f["nodo"]].geom, por[f["nodo"]].codigo, ctx) == ref(f) for f in tes)
    n = sum(f["motor"] == ref(f) for f in tes)
    print(f"El Tesoro, {len(tes)} lados -> plugin anterior: {v} ({100*v/len(tes):.1f}%)   motor nuevo: {n} ({100*n/len(tes):.1f}%)")
