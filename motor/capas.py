# -*- coding: utf-8 -*-
"""
Capas de la entrega con su estructura exacta: LEVANTAMIENTO_01 (polígonos), COTAS (un lado
por línea) y COORDENADAS (un vértice por punto, con tramo, distancia y colindante).
"""
from __future__ import annotations

import math
import os
import re

from shapely.geometry import LineString, Point, Polygon

from .colindantes import Contexto, Lote, Parametros, analizar_lote, anillo_limpio, describir, nivel_conf

# (nombre, tipo, longitud, precisión)   tipo: I64 entero largo, I entero, S texto, R real
CAMPOS_LEVANTAMIENTO = [
    ("OBJECTID_1", "I64", 10, 0), ("NODO", "S", 254, 0), ("NOMBRE_BEN", "S", 254, 0), ("NO_DE_IDEN", "I64", 10, 0),
    ("NOMENCLATU", "S", 254, 0), ("MUNICIPIO", "S", 254, 0), ("BARRIO_URB", "S", 254, 0), ("TIEMPO_DE_", "S", 254, 0),
    ("TIPO_DE_PR", "S", 254, 0), ("DESTINACIO", "S", 254, 0), ("_CELULAR", "S", 254, 0), ("_RANGO_DE_", "S", 254, 0),
    ("GENERO", "S", 254, 0), ("ESTADO_CIV", "S", 254, 0), ("NOMBRE_B_1", "S", 254, 0), ("NO_DE_ID_1", "S", 254, 0),
    ("CORRECTA", "S", 10, 0), ("CODIGO", "S", 30, 0), ("MANZANA_CO", "S", 17, 0), ("CODIGO_ANT", "S", 20, 0),
    ("codigo_mun", "S", 5, 0), ("Shape_Leng", "R", 18, 11), ("Shape_Area", "R", 18, 11), ("AREA", "R", 10, 2),
    ("id_row_nr", "I", 9, 0),
]
CAMPOS_COTAS = [("OBJECTID", "I64", 10, 0), ("NODO", "S", 254, 0), ("Shape_Leng", "R", 18, 11)]
CAMPOS_COORDENADAS = [
    ("OBJECTID_1", "I64", 10, 0), ("NODO", "S", 254, 0), ("vertex_ind", "I64", 10, 0), ("TRAMO", "S", 20, 0),
    ("NORTE", "R", 10, 2), ("ESTE", "R", 10, 2), ("COLINDANTE", "S", 50, 0), ("DISTANCIA", "R", 10, 2),
    ("LINDERO", "S", 254, 0), ("PUNTO_CARD", "S", 254, 0), ("DESCRIPCIO", "S", 254, 0), ("NIVEL_CONF", "S", 254, 0),
]


def ordenar_vertices(poly: Polygon) -> list[tuple]:
    """Vértices en sentido horario empezando por el más al norte (el más al oeste si empatan)."""
    v = anillo_limpio(poly)
    area2 = sum(v[i][0] * v[(i + 1) % len(v)][1] - v[(i + 1) % len(v)][0] * v[i][1] for i in range(len(v)))
    if area2 > 0:
        v = v[::-1]
    ymax = max(y for _, y in v)
    k = min((i for i in range(len(v)) if ymax - v[i][1] <= 0.01), key=lambda i: v[i][0])
    return v[k:] + v[:k]


def poligono_numerado(verts) -> Polygon:
    """
    Polígono cuyo anillo empieza en el último vértice: así 'Extraer vértices' de QGIS, quitando
    el índice 0 como se hace a mano, da la misma numeración 1..n que la capa COORDENADAS.
    """
    return Polygon([verts[-1]] + list(verts))


def _entero(v):
    t = re.sub(r"\D", "", str(v or ""))
    return int(t) if t and len(t) <= 18 else None


class Medidor:
    """
    Áreas y longitudes. 'elipsoidal' da lo mismo que $area / $length de la calculadora de campos de
    QGIS (sobre el elipsoide GRS80), que es como están calculadas las entregas; 'plana' mide sobre
    la proyección.
    """

    def __init__(self, crs, modo="elipsoidal"):
        self.plana = modo != "elipsoidal"
        if not self.plana:
            import pyproj
            self._geod = pyproj.Geod(ellps="GRS80")
            self._a_geo = pyproj.Transformer.from_crs(crs, "EPSG:4686", always_xy=True).transform

    def _ll(self, coords):
        xs, ys = zip(*coords)
        return self._a_geo(xs, ys)

    def area_perimetro(self, poly: Polygon):
        if self.plana:
            return poly.area, poly.length
        lon, lat = self._ll(poly.exterior.coords)
        a, p = self._geod.polygon_area_perimeter(lon, lat)
        return abs(a), p

    def longitud(self, p1, p2):
        if self.plana:
            return math.dist(p1, p2)
        lon, lat = self._ll([p1, p2])
        return self._geod.line_length(lon, lat)


def construir(lotes_info, ctx: Contexto, municipio, params: Parametros | None = None, medidor: Medidor | None = None):
    """
    lotes_info: [{'NODO', 'geom' (Polygon ya ubicado), 'CODIGO', y los campos del Excel}]
    Devuelve (levantamiento, cotas, coordenadas, detalle) como listas de (geometría, atributos).
    """
    medidor = medidor or Medidor(None, "plana")
    numerados = []
    for info in lotes_info:
        verts = ordenar_vertices(info["geom"])
        numerados.append((info, verts, poligono_numerado(verts)))
    lotes = [Lote(str(i["NODO"]), str(i.get("CODIGO") or ""), g, str(i.get("NOMBRE_BEN") or ""), str(i.get("NOMENCLATU") or ""))
             for i, _, g in numerados]
    ctx.set_lotes(lotes)
    lev, cotas, coord, detalle = [], [], [], []
    oid_cota = oid_pt = 0
    for k, ((info, verts, geom), lote) in enumerate(zip(numerados, lotes)):
        cod = lote.codigo
        area, perimetro = medidor.area_perimetro(geom)
        lev.append((geom, {
            "OBJECTID_1": k, "NODO": lote.nodo, "NOMBRE_BEN": info.get("NOMBRE_BEN") or None,
            "NO_DE_IDEN": _entero(info.get("NO_DE_IDEN")), "NOMENCLATU": info.get("NOMENCLATU") or None,
            "MUNICIPIO": municipio, "BARRIO_URB": info.get("BARRIO_URB") or None,
            "TIEMPO_DE_": None, "TIPO_DE_PR": info.get("TIPO_DE_PR") or tipo_predio(cod), "DESTINACIO": None,
            "_CELULAR": None, "_RANGO_DE_": None, "GENERO": None, "ESTADO_CIV": None,
            "NOMBRE_B_1": None, "NO_DE_ID_1": None, "CORRECTA": None,
            "CODIGO": cod or None, "MANZANA_CO": cod[:17] or None, "CODIGO_ANT": None, "codigo_mun": cod[:5] or None,
            "Shape_Leng": perimetro, "Shape_Area": area, "AREA": round(area, 2), "id_row_nr": None,
        }))
        lados = analizar_lote(lote, ctx, params, vertices=verts)
        n = len(verts)
        for lado in lados:
            sig = lado.indice % n + 1
            lado.longitud = medidor.longitud(lado.p1, lado.p2)
            lado.descripcion = describir(lado)
            cotas.append((LineString([lado.p1, lado.p2]), {"OBJECTID": oid_cota, "NODO": lote.nodo, "Shape_Leng": lado.longitud}))
            oid_cota += 1
            coord.append((Point(lado.p1), {
                "OBJECTID_1": oid_pt, "NODO": lote.nodo, "vertex_ind": lado.indice, "TRAMO": f"{lado.indice} AL {sig}",
                "NORTE": round(lado.p1[1], 2), "ESTE": round(lado.p1[0], 2),
                "COLINDANTE": lado.colindante[:50], "DISTANCIA": round(lado.longitud, 2),
                "LINDERO": lado.lindero, "PUNTO_CARD": lado.cardinal, "DESCRIPCIO": lado.descripcion[:254],
                "NIVEL_CONF": nivel_conf(lado),
            }))
            oid_pt += 1
        detalle.append((lote, lados))
    return lev, cotas, coord, detalle


def tipo_predio(codigo) -> str | None:
    """Zona según el código predial: posiciones 6-7 '00' rural, lo demás urbano."""
    if not codigo or len(codigo) < 7:
        return None
    return "RURAL" if codigo[5:7] == "00" else "URBANO"


def escribir_shp(ruta, filas, campos, tipo_geom, crs_wkt):
    """Shapefile con el tipo, ancho y precisión exactos de cada campo, sin depender de GDAL."""
    from . import shp
    return shp.escribir(ruta, filas, campos, tipo_geom, crs_wkt)


def escribir_capas(carpeta, lev, cotas, coord, crs_wkt):
    return {
        "LEVANTAMIENTO_01": escribir_shp(os.path.join(carpeta, "LEVANTAMIENTO_01.shp"), lev, CAMPOS_LEVANTAMIENTO, "Polygon", crs_wkt),
        "COTAS": escribir_shp(os.path.join(carpeta, "COTAS.shp"), cotas, CAMPOS_COTAS, "LineString", crs_wkt),
        "COORDENADAS": escribir_shp(os.path.join(carpeta, "COORDENADAS.shp"), coord, CAMPOS_COORDENADAS, "Point", crs_wkt),
    }
