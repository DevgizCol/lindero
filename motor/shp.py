# -*- coding: utf-8 -*-
"""
Escritor de shapefile en Python puro (sin GDAL), para fijar el tipo, el ancho y la precisión
de cada campo exactamente como en las entregas.

Tipos de campo:  I64 / I -> numérico sin decimales;  R -> numérico con decimales;  S -> texto.
Geometrías: Polygon (un anillo exterior), LineString y Point, todas en 2D.
"""
from __future__ import annotations

import datetime
import math
import os
import struct

TIPO_SHP = {"Point": 1, "LineString": 3, "Polygon": 5}


def _anillo_horario(coords):
    """El shapefile pide los anillos exteriores en sentido horario; se conserva el vértice inicial."""
    c = [(float(x), float(y)) for x, y, *_ in coords]
    area2 = sum(c[i][0] * c[i + 1][1] - c[i + 1][0] * c[i][1] for i in range(len(c) - 1))
    return c if area2 <= 0 else c[::-1]


def _registro(geom, tipo):
    if tipo == 1:
        return struct.pack("<idd", 1, geom.x, geom.y), (geom.x, geom.y, geom.x, geom.y)
    pts = _anillo_horario(geom.exterior.coords) if tipo == 5 else [(float(x), float(y)) for x, y, *_ in geom.coords]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    caja = (min(xs), min(ys), max(xs), max(ys))
    cuerpo = struct.pack("<i4dii i", tipo, *caja, 1, len(pts), 0)
    cuerpo += b"".join(struct.pack("<dd", x, y) for x, y in pts)
    return cuerpo, caja


def _cabecera(tipo, largo_bytes, caja):
    return (struct.pack(">i5ii", 9994, 0, 0, 0, 0, 0, largo_bytes // 2) + struct.pack("<ii", 1000, tipo)
            + struct.pack("<8d", *caja, 0.0, 0.0, 0.0, 0.0))


def _valor_dbf(v, tipo, largo, prec):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return b" " * largo
    if tipo == "S":
        b = str(v).encode("utf-8")[:largo]
        while b:                       # no cortar un carácter UTF-8 por la mitad
            try:
                b.decode("utf-8")
                break
            except UnicodeDecodeError:
                b = b[:-1]
        return b.ljust(largo, b" ")
    txt = f"{float(v):.{prec}f}" if tipo == "R" else str(int(v))
    if len(txt) > largo:
        raise ValueError(f"El valor {txt} no cabe en un campo numérico de {largo} posiciones")
    return txt.rjust(largo).encode("ascii")


def escribir(ruta, filas, campos, tipo_geom, wkt_prj):
    """
    filas: [(geometría shapely, {campo: valor})]   campos: [(nombre, tipo, largo, precisión)]
    """
    tipo = TIPO_SHP[tipo_geom]
    base = os.path.splitext(ruta)[0]
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    registros, indice, cajas, pos = [], [], [], 100
    for n, (geom, _) in enumerate(filas, start=1):
        cuerpo, caja = _registro(geom, tipo)
        registros.append(struct.pack(">ii", n, len(cuerpo) // 2) + cuerpo)
        indice.append(struct.pack(">ii", pos // 2, len(cuerpo) // 2))
        cajas.append(caja)
        pos += 8 + len(cuerpo)
    total = (min(c[0] for c in cajas), min(c[1] for c in cajas), max(c[2] for c in cajas), max(c[3] for c in cajas)) if cajas else (0, 0, 0, 0)
    with open(base + ".shp", "wb") as f:
        f.write(_cabecera(tipo, pos, total))
        f.write(b"".join(registros))
    with open(base + ".shx", "wb") as f:
        f.write(_cabecera(tipo, 100 + 8 * len(indice), total))
        f.write(b"".join(indice))
    # dBase III
    hoy = datetime.date.today()
    largo_reg = 1 + sum(c[2] for c in campos)
    largo_cab = 32 + 32 * len(campos) + 1
    with open(base + ".dbf", "wb") as f:
        f.write(struct.pack("<BBBBIHH20x", 3, hoy.year - 1900, hoy.month, hoy.day, len(filas), largo_cab, largo_reg))
        for nombre, t, largo, prec in campos:
            if len(nombre.encode("ascii")) > 10:
                raise ValueError(f"El nombre de campo {nombre} supera 10 caracteres")
            f.write(struct.pack("<11sc4xBB14x", nombre.encode("ascii"), b"C" if t == "S" else b"N", largo, prec if t == "R" else 0))
        f.write(b"\r")
        for _, attrs in filas:
            f.write(b" " + b"".join(_valor_dbf(attrs.get(n), t, l, p) for n, t, l, p in campos))
        f.write(b"\x1a")
    with open(base + ".prj", "w", encoding="ascii", errors="replace") as f:
        f.write(wkt_prj)
    with open(base + ".cpg", "w", encoding="ascii") as f:
        f.write("UTF-8")
    return base + ".shp"
