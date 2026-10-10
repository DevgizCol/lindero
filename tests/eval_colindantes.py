# -*- coding: utf-8 -*-
"""
Compara el motor de colindantes contra una entrega ya corregida a mano
(columna COLINDANTE de la capa COORDENADAS entregada).

Uso:  python tests/eval_colindantes.py [carpeta_shapefiles] [--plot carpeta]
"""
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import geopandas as gpd

from motor.base import cargar_base
from motor.colindantes import Lote, Parametros, analizar_lote

ENTREGA = r"C:/Dani/Carto_Malambo/BASE_CATASTRAL_MALAMBO/PRIMERA ENTREGA_2025/01.SHAPEFILE"


def cargar_entrega(carpeta):
    lev = gpd.read_file(os.path.join(carpeta, "LEVANTAMIENTO_01.shp"))
    lev["geometry"] = lev.geometry.force_2d()
    lev = lev.drop_duplicates("NODO")
    coo = gpd.read_file(os.path.join(carpeta, "COORDENADAS.shp"))
    coo["geometry"] = coo.geometry.force_2d()
    return lev, coo


def evaluar(carpeta=ENTREGA, params=None, verbose=True):
    base = cargar_base("malambo")
    lev, coo = cargar_entrega(carpeta)
    lotes = [Lote(str(r.NODO), str(r.CODIGO), r.geometry, str(r.NOMBRE_BEN or ""), str(r.NOMENCLATU or ""))
             for r in lev.itertuples()]
    ctx = base.contexto(lotes)
    filas = []
    for lote in lotes:
        pts = coo[coo.NODO == lote.nodo].sort_values("vertex_ind")
        verts = [(g.x, g.y) for g in pts.geometry]
        lados = analizar_lote(lote, ctx, params, vertices=verts)
        for lado, r in zip(lados, pts.itertuples()):
            if lado.longitud < 0.02:
                continue
            filas.append(dict(nodo=lote.nodo, tramo=r.TRAMO, dist=round(lado.longitud, 2),
                              esperado=str(r.COLINDANTE).strip(), motor=lado.colindante,
                              tipo=lado.tipo, frac=lado.fraccion, sep=lado.separacion,
                              conf=lado.confianza, sec=lado.secundarios, lindero=lado.lindero,
                              lind_plugin=r.LINDERO, card=lado.cardinal, reparto=lado.reparto, lado=lado))
    ok = [f for f in filas if f["esperado"] == f["motor"]]
    if verbose:
        print(f"Lados: {len(filas)}  coinciden: {len(ok)}  ({100 * len(ok) / len(filas):.1f}%)")
        for f in filas:
            if f["esperado"] != f["motor"]:
                print(f"  {f['nodo']:4} {f['tramo']:9} {f['dist']:6.2f} m  esperado={f['esperado'][-12:]:14} "
                      f"motor={f['motor'][-14:]:14} {f['tipo']:8} frac={f['frac']:.2f} sep={f['sep']:.2f} "
                      f"{f['conf']:5} sec={[(t[-6:], v) for t, v in f['sec']]}")
    return filas, lotes, ctx, base


def dibujar(filas, lotes, ctx, base, carpeta_png, solo=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(carpeta_png, exist_ok=True)
    por_nodo = {}
    for f in filas:
        por_nodo.setdefault(f["nodo"], []).append(f)
    for lote in lotes:
        if solo and lote.nodo not in solo:
            continue
        fs = por_nodo.get(lote.nodo, [])
        if not solo and all(f["esperado"] == f["motor"] for f in fs):
            continue
        minx, miny, maxx, maxy = lote.geom.buffer(18).bounds
        fig, ax = plt.subplots(figsize=(11, 11))
        t = base.terrenos.cx[minx:maxx, miny:maxy]
        t.boundary.plot(ax=ax, color="#888", linewidth=0.8)
        for r in t.itertuples():
            c = r.geometry.representative_point()
            if minx < c.x < maxx and miny < c.y < maxy:
                ax.text(c.x, c.y, r.codigo[17:21], fontsize=8, color="#555", ha="center")
        base.vias.cx[minx:maxx, miny:maxy].plot(ax=ax, color="#e58", linewidth=1)
        for o in lotes:
            if o.nodo != lote.nodo and o.geom.intersects(lote.geom.buffer(18)):
                ax.plot(*o.geom.exterior.xy, color="#2a7", linewidth=1)
                c = o.geom.representative_point()
                ax.text(c.x, c.y, o.nodo, fontsize=8, color="#2a7", ha="center")
        ax.plot(*lote.geom.exterior.xy, color="k", linewidth=2)
        for f in fs:
            l = f["lado"]
            mx, my = (l.p1[0] + l.p2[0]) / 2, (l.p1[1] + l.p2[1]) / 2
            bien = f["esperado"] == f["motor"]
            ax.annotate(f"{f['tramo']}\nE:{f['esperado'][-13:-9] if f['esperado'].isdigit() else f['esperado']}\n"
                        f"M:{f['motor'][-13:-9] if f['motor'].isdigit() else f['motor']} {f['frac']:.2f}",
                        (mx, my), (mx + l.normal[0] * 4, my + l.normal[1] * 4), fontsize=7,
                        color="#060" if bien else "#c00", ha="center",
                        arrowprops=dict(arrowstyle="-", color="#060" if bien else "#c00", lw=0.5))
            ax.plot(l.p1[0], l.p1[1], "kx")
            ax.text(l.p1[0], l.p1[1], str(l.indice), fontsize=9, color="b")
        ax.set_xlim(minx, maxx); ax.set_ylim(miny, maxy); ax.set_aspect("equal"); ax.set_title(lote.nodo)
        fig.savefig(os.path.join(carpeta_png, f"{lote.nodo}.png"), dpi=80, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    argv = sys.argv[1:]
    png = None
    if "--plot" in argv:
        i = argv.index("--plot")
        png = argv[i + 1]
        del argv[i:i + 2]
    filas, lotes, ctx, base = evaluar(argv[0] if argv else ENTREGA)
    if png:
        dibujar(filas, lotes, ctx, base, png)
