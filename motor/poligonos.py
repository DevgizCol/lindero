# -*- coding: utf-8 -*-
"""
Plano del cliente (DXF) -> polígonos de los predios levantados con su NODO.

El DXF se lee con GDAL (no hace falta AutoCAD). Se toman las líneas de las capas de dibujo,
se arman los polígonos y cada uno recibe su NODO por:
  1. el texto que tiene dentro (p. ej. "T1"), o
  2. el código de los puntos de la cartera que caen en sus vértices (p. ej. "C402", "C1y2").
"""
from __future__ import annotations

import os
import re
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import Point, Polygon
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

CAPAS_NO_DIBUJO = re.compile(r"GRILLA|MARQUILLA|RETICULA|ROTULO|FORMATO|CAJETIN|V-NODE|COTA|DIM|DEFPOINTS", re.I)


@dataclass
class Dibujo:
    poligonos: list = field(default_factory=list)      # shapely Polygon
    nodos: list = field(default_factory=list)          # NODO de cada polígono ("" si no se pudo)
    origen: list = field(default_factory=list)         # cómo se etiquetó cada uno
    textos: list = field(default_factory=list)         # [(texto, x, y)]
    avisos: list = field(default_factory=list)
    sueltas: float = 0.0                               # metros de línea que no cerraron polígono


def norm_nodo(t) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(t or "").upper())


def leer_dxf(ruta) -> gpd.GeoDataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = gpd.read_file(ruta, engine="pyogrio")
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    g["geometry"] = g.geometry.force_2d()
    return g


def leer_puntos(ruta) -> list[tuple]:
    """Cartera de campo 'id, norte, este, cota, código' (txt/csv) -> [(x, y, código)]."""
    pts = []
    with open(ruta, encoding="latin-1") as f:
        for linea in f:
            p = [c.strip() for c in re.split(r"[,;\t]", linea.strip())]
            if len(p) < 4:
                continue
            try:
                a, b = float(p[1]), float(p[2])
            except ValueError:
                continue
            cod = p[4] if len(p) > 4 else ""
            # la cartera trae norte, este; en CTM12 el este (~4.8 M) es mayor que el norte (~2.7 M)
            pts.append((b, a, cod))
    return pts


def nodos_de_codigo(cod) -> list[str]:
    """'C402' -> ['402'];  'C10y11' -> ['10', '11'];  'C3y4F' -> ['3', '4'];  'T5' -> ['T5', '5']."""
    t = str(cod or "").strip().upper()
    nums = re.findall(r"\d+", t)
    out = [norm_nodo(t)] if t else []
    return out + [n for n in nums if n not in out]


def extraer(ruta_dxf, nodos_esperados=(), ruta_puntos=None, area_min=8.0, area_max=50000.0,
            rejilla=0.01) -> Dibujo:
    ent = leer_dxf(ruta_dxf)
    d = Dibujo()
    capa = ent["Layer"].astype(str)
    sub = ent["SubClasses"].astype(str) if "SubClasses" in ent else ""
    util = ~capa.str.contains(CAPAS_NO_DIBUJO)
    lineas = ent[util & ent.geom_type.isin(["LineString", "MultiLineString"])
                 & ~sub.str.contains("BlockReference|Dimension|Hatch", na=False)]
    if lineas.empty:
        d.avisos.append("El DXF no tiene líneas de dibujo fuera de la grilla y el rótulo.")
        return d
    # se cierra con la rejilla más fina que sirva: 1 mm conserva el área al centímetro cuadrado;
    # solo si quedan líneas sin cerrar se prueba a juntar extremos separados hasta 1 cm y 5 cm
    mejor = None
    for rej in sorted({0.001, rejilla, 0.05}):
        geoms = shapely.set_precision(lineas.geometry.values, rej)
        red_r = unary_union([g for g in geoms if g is not None and not g.is_empty])
        polys_r = [p for p in polygonize(red_r) if area_min <= p.area <= area_max]
        if mejor is None or len(polys_r) > len(mejor[1]):
            mejor = (rej, polys_r, red_r)
    rejilla, polys, red = mejor
    if rejilla > 0.001:
        d.avisos.append(f"Para cerrar los polígonos hubo que juntar extremos separados hasta {rejilla * 100:.0f} cm.")
    # una figura que encierra a varias otras es un marco o el contorno de la manzana, no un predio
    if len(polys) > 3:
        arbol = STRtree(polys)
        fuera = set()
        for i, p in enumerate(polys):
            dentro = [j for j in arbol.query(p, predicate="contains") if j != i]
            if len(dentro) >= 3:
                fuera.add(i)
        polys = [p for i, p in enumerate(polys) if i not in fuera]
    d.poligonos = list(polys)
    usados = unary_union([p.exterior for p in polys]) if polys else None
    if usados is not None:
        d.sueltas = float(red.difference(usados.buffer(rejilla * 2)).length)
        if d.sueltas > 1:
            d.avisos.append(f"{d.sueltas:.0f} m de línea no cierran ningún polígono (predios abiertos o líneas sueltas).")
    # textos
    tx = ent[util & ent.geom_type.eq("Point") & ent["Text"].notna()] if "Text" in ent else ent.iloc[0:0]
    d.textos = [(str(t).strip(), g.x, g.y) for t, g in zip(tx["Text"], tx.geometry)]
    esperados = {norm_nodo(n): str(n) for n in nodos_esperados if norm_nodo(n)}
    d.nodos = [""] * len(d.poligonos)
    d.origen = [""] * len(d.poligonos)
    if d.poligonos:
        arbol = STRtree(d.poligonos)
        # 1) texto dentro del polígono
        votos = defaultdict(list)
        for t, x, y in d.textos:
            k = norm_nodo(t)
            if esperados and k not in esperados:
                continue
            if not esperados and not re.fullmatch(r"[A-Z]{0,3}\d{1,5}[A-Z]?", k):
                continue
            for i in arbol.query(Point(x, y), predicate="within"):
                votos[int(i)].append(esperados.get(k, t))
        for i, v in votos.items():
            if len(set(v)) == 1:
                d.nodos[i], d.origen[i] = v[0], "TEXTO"
        # 2) códigos de la cartera en los vértices
        if ruta_puntos and os.path.isfile(ruta_puntos):
            pts = leer_puntos(ruta_puntos)
            if pts:
                _etiquetar_por_puntos(d, pts, esperados)
    sin = sum(1 for n in d.nodos if not n)
    if sin:
        d.avisos.append(f"{sin} de {len(d.poligonos)} polígonos quedaron sin NODO (falta el texto dentro o el código en la cartera).")
    rep = [n for n, c in Counter(n for n in d.nodos if n).items() if c > 1]
    if rep:
        d.avisos.append(f"NODO repetido en más de un polígono: {', '.join(rep[:10])}.")
    return d


def _etiquetar_por_puntos(d: Dibujo, pts, esperados, tol=0.15):
    xy = np.array([(x, y) for x, y, _ in pts])
    arbol = STRtree(shapely.points(xy))
    for i, pol in enumerate(d.poligonos):
        if d.nodos[i]:
            continue
        cuenta = Counter()
        verts = list(pol.exterior.coords)[:-1]
        for vx, vy in verts:
            for j in arbol.query(Point(vx, vy).buffer(tol)):
                for n in nodos_de_codigo(pts[j][2]):
                    if not esperados or n in esperados:
                        cuenta[n] += 1
        if not cuenta:
            continue
        (n1, c1), *resto = cuenta.most_common(2)
        if c1 >= max(2, 0.5 * len(verts)) and (not resto or c1 > resto[0][1]):
            d.nodos[i], d.origen[i] = esperados.get(n1, n1), "CARTERA"


def desde_poligonos(geoms, nodos) -> Dibujo:
    """Dibujo ya resuelto (p. ej. una capa de polígonos con NODO)."""
    d = Dibujo()
    for g, n in zip(geoms, nodos):
        g = shapely.force_2d(g)
        if g.geom_type == "MultiPolygon":
            g = max(g.geoms, key=lambda p: p.area)
        if isinstance(g, Polygon) and not g.is_empty:
            d.poligonos.append(g)
            d.nodos.append(str(n))
            d.origen.append("CAPA")
    return d
