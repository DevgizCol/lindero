# -*- coding: utf-8 -*-
"""
Certificado de plano predial en PDF sin QGIS.

Reproduce la composición SALIDA_CARTOGRAFICA (misma hoja de 703 x 497 mm, mismas cajas y el mismo
contenido) dibujándola con matplotlib, que es Python puro: corre igual en Windows, Linux o un
contenedor. Las medidas de cada caja están tomadas de la plantilla .qpt, en milímetros.
"""
from __future__ import annotations

import math
import os
import re
from functools import lru_cache

import numpy as np
import shapely
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, Polygon as Parche, Rectangle
from matplotlib.textpath import TextPath

ANCHO, ALTO = 703.5, 496.7                    # hoja, mm
MAPA = (16.217, 133.775, 662.072, 253.914)    # x, y, ancho, alto del mapa
ESCALAS = [100, 125, 150, 200, 250, 300, 400, 500, 750, 1000, 1500, 2000, 2500, 5000, 10000]
SANS, SERIF = "DejaVu Sans", "DejaVu Serif"   # vienen con matplotlib: iguales en cualquier equipo
MM_PT = 25.4 / 72.0
SISTEMA_REF = ["PROYECCIÓN: TRANSVERSE_MERCATOR", "ORIGEN: MAGNA SIRGAS / ORIGEN", "NACIONAL CTM12",
               "Coordenadas Planas Gauss-Krüger", "5.000.000 Metros Este", "2.000.000 Metros Norte",
               "Coordenadas Geográficas", "Meridiano Central: -73 grados decimales", "Latitud: 4 grados decimales"]
GRIS, ROSA, ROJO, MENTA = "#7d7d7d", "#e9507f", "#e31a1c", "#a9f5d5"


@lru_cache(maxsize=4096)
def _ancho_100(texto, familia, negrita):
    """Ancho del texto a 100 pt (por los puntos de control de las letras: rápido y suficiente)."""
    fp = FontProperties(family=familia, weight="bold" if negrita else "normal")
    v = TextPath((0, 0), texto, size=100, prop=fp).vertices
    return float(v[:, 0].max() - v[:, 0].min()) if len(v) else 0.0


def _ancho_mm(texto, pt, familia=SANS, negrita=False):
    texto = str(texto or "")
    return _ancho_100(texto, familia, negrita) * pt / 100 * MM_PT if texto.strip() else 0.0


@lru_cache(maxsize=8)
def _imagen_firma(ruta, _mtime):
    from PIL import Image
    img = Image.open(ruta).convert("RGBA")
    img.thumbnail((900, 500))      # la caja de la firma mide 65 x 36 mm: más resolución no se ve
    return img


class _Hoja:
    """Lienzo en milímetros con el origen arriba a la izquierda, como el diseñador de QGIS."""

    def __init__(self):
        self.fig = Figure(figsize=(ANCHO / 25.4, ALTO / 25.4))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, ANCHO)
        self.ax.set_ylim(ALTO, 0)
        self.ax.axis("off")

    def caja(self, x, y, w, h, lw=0.9, relleno="none", borde="black", z=2):
        self.ax.add_patch(Rectangle((x, y), w, h, fill=relleno != "none", facecolor=relleno, edgecolor=borde, linewidth=lw, zorder=z))

    def linea(self, x1, y1, x2, y2, lw=0.9, color="black", z=2):
        self.ax.plot([x1, x2], [y1, y2], color=color, linewidth=lw, zorder=z, solid_capstyle="butt")

    def texto(self, x, y, s, pt, familia=SANS, negrita=False, ha="center", va="center", color="black", rot=0, cursiva=False, z=5):
        return self.ax.text(x, y, s, fontsize=pt, family=familia, weight="bold" if negrita else "normal", ha=ha, va=va,
                            color=color, rotation=rot, style="italic" if cursiva else "normal", zorder=z, linespacing=1.25)

    def celda(self, x, y, w, h, s, pt, familia=SANS, negrita=False, ha="center", encoger=True):
        """Caja con texto centrado; si no cabe, se reduce la letra."""
        self.caja(x, y, w, h)
        s = "" if s is None else str(s)
        if encoger and s:
            largo = max(_ancho_mm(l, pt, familia, negrita) for l in s.split("\n"))
            if largo > w - 4:
                pt *= (w - 4) / largo
        self.texto(x + (w / 2 if ha == "center" else 3), y + h / 2, s, pt, familia, negrita, ha=ha)

    def ejes_mapa(self, x, y, w, h):
        return self.fig.add_axes([x / ANCHO, 1 - (y + h) / ALTO, w / ANCHO, h / ALTO])

    def encima(self):
        """Capa transparente sobre el mapa: lo que se dibuje desde aquí queda por encima de él."""
        self.ax = self.fig.add_axes([0, 0, 1, 1], facecolor="none")
        self.ax.set_xlim(0, ANCHO)
        self.ax.set_ylim(ALTO, 0)
        self.ax.axis("off")


def elegir_escala(geom, base=167.0, escalas=ESCALAS):
    """La escala de la plantilla si el predio cabe con 10 % de margen; si no, la siguiente redonda."""
    minx, miny, maxx, maxy = geom.bounds
    necesaria = max((maxx - minx) * 1.1 / (MAPA[2] / 1000), (maxy - miny) * 1.1 / (MAPA[3] / 1000))
    for e in [base] + [e for e in escalas if e > base * 1.05]:
        if e >= necesaria:
            return e
    return math.ceil(necesaria / 1000) * 1000


def _intervalo_grilla(ancho_m):
    for i in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if ancho_m / i <= 5.5:
            return i
    return 10000


def _lineas(geoms):
    segs = []
    for g in geoms:
        b = g.boundary if g.geom_type in ("Polygon", "MultiPolygon") else g
        for parte in (b.geoms if hasattr(b, "geoms") else [b]):
            if parte.geom_type in ("LineString", "LinearRing") and len(parte.coords) > 1:
                segs.append(np.asarray(parte.coords)[:, :2])
    return segs


def _mapa(hoja: _Hoja, lote, puntos, base, escala):
    x, y, w, h = MAPA
    cx, cy = (lote.bounds[0] + lote.bounds[2]) / 2, (lote.bounds[1] + lote.bounds[3]) / 2
    am, hm = w / 1000 * escala, h / 1000 * escala
    x0, x1, y0, y1 = cx - am / 2, cx + am / 2, cy - hm / 2, cy + hm / 2
    marco = shapely.box(x0, y0, x1, y1)
    mm = escala / 1000.0                        # metros de terreno por milímetro de papel
    ax = hoja.ejes_mapa(x, y, w, h)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(0.9)
    # predios catastrales
    terr = base.terrenos.cx[x0:x1, y0:y1]
    ax.add_collection(LineCollection(_lineas(terr.geometry), colors=GRIS, linewidths=0.85, zorder=2))
    for cod, g in zip(terr["codigo"], terr.geometry):
        v = g.intersection(marco)
        if v.is_empty or v.area < (9 * mm) ** 2:
            continue
        p = v.representative_point()
        ax.text(p.x, p.y, str(cod)[17:21], fontsize=9, family=SANS, color="#4d4d4d", ha="center", va="center", zorder=3, clip_on=True)
    # ejes viales con su nombre a lo largo del tramo visible más largo
    vias = base.vias.cx[x0:x1, y0:y1]
    ax.add_collection(LineCollection(_lineas(vias.geometry), colors=ROSA, linewidths=1.0, zorder=3))
    mejor = {}
    for nombre, g in zip(vias["texto"], vias.geometry):
        v = g.intersection(marco)
        for parte in (v.geoms if hasattr(v, "geoms") else [v]):
            if parte.geom_type == "LineString" and parte.length > mejor.get(nombre, (0, None))[0]:
                mejor[nombre] = (parte.length, parte)
    for nombre, (largo, parte) in mejor.items():
        if largo < 22 * mm or not nombre:
            continue
        a, b = parte.interpolate(0.42, normalized=True), parte.interpolate(0.58, normalized=True)
        ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
        if ang > 90 or ang < -90:
            ang += 180
        m = parte.interpolate(0.5, normalized=True)
        nx, ny = -math.sin(math.radians(ang)), math.cos(math.radians(ang))
        ax.text(m.x + nx * 3.2 * mm, m.y + ny * 3.2 * mm, str(nombre), fontsize=19, family=SANS, color="#3c3c3c", rotation=ang,
                rotation_mode="anchor", ha="center", va="center", zorder=4, clip_on=True)
    # el predio, sus cotas y sus vértices
    ax.add_patch(Parche(np.asarray(lote.exterior.coords)[:, :2], closed=True, fill=False, edgecolor="#1a1a1a", linewidth=2.3, zorder=6, joinstyle="miter"))
    n = len(puntos)

    def hacia_afuera(i):
        """Normal exterior del lado que sale del vértice i."""
        px, py = puntos[i][0], puntos[i][1]
        qx, qy = puntos[(i + 1) % n][0], puntos[(i + 1) % n][1]
        largo = math.hypot(qx - px, qy - py)
        if largo == 0:
            return 0.0, 0.0, 0.0
        ux, uy = (qy - py) / largo, -(qx - px) / largo
        if shapely.contains_xy(lote, (px + qx) / 2 + ux * 0.05, (py + qy) / 2 + uy * 0.05):
            ux, uy = -ux, -uy
        return ux, uy, largo

    normales = [hacia_afuera(i) for i in range(n)]
    for i, (px, py, _num, dist) in enumerate(puntos):
        ux, uy, largo = normales[i]
        if largo >= 11 * mm:            # la cota va por dentro del predio; el número del vértice, por fuera
            qx, qy = puntos[(i + 1) % n][0], puntos[(i + 1) % n][1]
            ang = math.degrees(math.atan2(qy - py, qx - px))
            if ang > 90 or ang < -90:
                ang += 180
            ax.text((px + qx) / 2 - ux * 2.9 * mm, (py + qy) / 2 - uy * 2.9 * mm, f"{dist:.2f}", fontsize=13, family=SANS, style="italic",
                    color="#222", rotation=ang, rotation_mode="anchor", ha="center", va="center", zorder=7, clip_on=True)
    ax.plot([p[0] for p in puntos], [p[1] for p in puntos], linestyle="none", marker="x", color=ROJO, markersize=11, markeredgewidth=1.7, zorder=8)
    for i, (px, py, num, _) in enumerate(puntos):
        ax_, ay_ = normales[i][0] + normales[i - 1][0], normales[i][1] + normales[i - 1][1]   # bisectriz exterior
        d = math.hypot(ax_, ay_)
        if d < 1e-6:
            ax_, ay_, d = normales[i][0], normales[i][1], 1.0
        ax.text(px + ax_ / d * 4.4 * mm, py + ay_ / d * 4.4 * mm, str(num), fontsize=17, family=SANS, color="#222", ha="center", va="center", zorder=8, clip_on=True)
    # grilla de coordenadas con sus rótulos fuera del marco
    paso = _intervalo_grilla(am)
    for gx in np.arange(math.ceil(x0 / paso) * paso, x1, paso):
        ax.axvline(gx, color="#4a4a4a", linewidth=0.45, zorder=5)
        for yy, va in ((y - 1.3, "bottom"), (y + h + 1.3, "top")):
            hoja.texto(x + (gx - x0) / mm, yy, f"{gx:.0f}", 6.5, SERIF, va=va)
    for gy in np.arange(math.ceil(y0 / paso) * paso, y1, paso):
        ax.axhline(gy, color="#4a4a4a", linewidth=0.45, zorder=5)
        for xx, ha in ((x - 1.3, "right"), (x + w + 1.3, "left")):
            hoja.texto(xx, y + (y1 - gy) / mm, f"{gy:.0f}", 6.5, SERIF, ha=ha, rot=90)
    return ax


def _norte(hoja: _Hoja, cx=639.0, cy=172.6, r=17.5):
    a = hoja.ax
    a.add_patch(Circle((cx, cy), r, facecolor="white", edgecolor="black", linewidth=3.2, zorder=9))
    a.add_patch(Circle((cx, cy), r * 0.74, fill=False, edgecolor="black", linewidth=0.9, zorder=9))
    a.add_patch(Parche([(cx, cy - r * 1.55), (cx + r * 0.95, cy + r * 1.05), (cx, cy + r * 0.45), (cx - r * 0.95, cy + r * 1.05)],
                       closed=True, facecolor="white", edgecolor="black", linewidth=2.6, zorder=10, joinstyle="miter"))
    a.add_patch(Parche([(cx, cy - r * 1.55), (cx, cy + r * 0.45), (cx - r * 0.95, cy + r * 1.05)], closed=True, facecolor="black", edgecolor="black", linewidth=0.5, zorder=11))


def _cuadro(hoja: _Hoja, filas):
    """Cuadro de coordenadas y linderos; la letra se reduce lo justo para que quepan todas las filas."""
    enc = ["NODO", "ID", "TRAMO", "NORTE", "ESTE", "DISTANCIA", "COLINDANTE"]
    x0, y0, ancho_max, alto_max = 14.07, 412.72, 282.0, 72.0
    f = 1.0
    for _ in range(6):
        pt, pt_e = 18.0 * f, 21.0 * f
        anchos = [max(_ancho_mm(enc[k], pt_e, SANS, True), max(_ancho_mm(r[k], pt) for r in filas)) + 3.2 * f for k in range(7)]
        alto_f, alto_e = pt * MM_PT * 1.2, pt_e * MM_PT * 1.2
        ajuste = min(1.0, ancho_max / sum(anchos), alto_max / (alto_e + alto_f * len(filas)))
        if ajuste >= 0.999:
            break
        f *= ajuste * 0.995
    x = x0
    xs = []
    for a in anchos:
        xs.append(x)
        x += a
    hoja.caja(x0, y0, sum(anchos), alto_e, lw=0.7, relleno=MENTA, z=3)
    for k, t in enumerate(enc):
        hoja.texto(xs[k] + anchos[k] / 2, y0 + alto_e / 2, t, pt_e, SANS, True, color="#1d3b2f")
    for i, r in enumerate(filas):
        y = y0 + alto_e + i * alto_f
        hoja.caja(x0, y, sum(anchos), alto_f, lw=0.7, relleno="#dedede" if i % 2 else "white", z=3)
        for k, t in enumerate(r):
            izq = k == 6
            hoja.texto(xs[k] + (1.4 * f if izq else anchos[k] / 2), y + alto_f / 2, t, pt, SANS, ha="left" if izq else "center")
    for k in range(1, 7):
        hoja.linea(xs[k], y0, xs[k], y0 + alto_e + alto_f * len(filas), lw=0.7, z=4)


def _convenciones(hoja: _Hoja):
    a, pt = hoja.ax, 8.5
    a.plot([324], [422.5], marker="x", color=ROJO, markersize=10, markeredgewidth=1.6, linestyle="none", zorder=5)
    hoja.texto(332, 422.5, "COORDENADAS", pt, ha="left")
    a.annotate("", xy=(329, 434.5), xytext=(319, 434.5), arrowprops=dict(arrowstyle="<->", color="#222", linewidth=0.9), zorder=5)
    hoja.texto(332, 434.5, "COTAS", pt, ha="left")
    hoja.caja(384, 420, 7.5, 5, lw=2.0)
    hoja.texto(395, 422.5, "PREDIO LEVANTAMIENTO", pt, ha="left")
    hoja.linea(384, 434.5, 391.5, 434.5, lw=1.0, color=ROSA)
    hoja.texto(395, 434.5, "NOMENCLATURA VIAL", pt, ha="left")
    hoja.caja(455, 420, 7.5, 5, lw=0.9, borde=GRIS)
    hoja.texto(466, 422.5, "PREDIO CATASTRAL", pt, ha="left")


def dibujar(attrs, lote, puntos_tabla, base, cfg, fecha, firma=None, firmante=None, marca_agua=False):
    """
    attrs: atributos del predio (LEVANTAMIENTO_01).  lote: su polígono.
    puntos_tabla: filas de COORDENADAS del predio en orden de vértice.
    """
    h = _Hoja()
    cod = str(attrs.get("CODIGO") or "")
    # marco y título
    h.caja(4.71, 5.10, 694.15, 486.48, lw=1.3)
    h.linea(4.71, 21.84, 698.86, 21.84)
    h.texto(351.8, 13.6, "CERTIFICADO PLANO PREDIAL CATASTRAL", 34, SERIF, True)
    # encabezado
    y = [28.77, 46.20, 63.60, 81.04, 98.46, 114.75]
    alto = [y[i + 1] - y[i] for i in range(5)]
    for i, rot in enumerate(["Departamento:", "N° Predial:", "Dirección:", "Ocupante:", "Fecha:"]):
        h.celda(8.81, y[i], 58.75, alto[i], rot, 19.5)
    h.celda(67.56, y[0], 112.12, alto[0], cfg.get("departamento", ""), 19.5)
    h.celda(179.68, y[0], 61.96, alto[0], "Municipio:", 19.5)
    h.celda(241.64, y[0], 162.36, alto[0], cfg.get("municipio", ""), 19.5)
    h.celda(67.56, y[1], 219.53, alto[1], cod, 19.5, SERIF)
    h.celda(287.09, y[1], 46.54, alto[1], "Area del\nPredio:", 17.5)
    h.celda(333.63, y[1], 70.37, alto[1], f"{float(attrs.get('AREA') or 0):.2f} m²", 19.5, SERIF)
    h.celda(67.56, y[2], 219.53, alto[2], attrs.get("NOMENCLATU") or "", 19.5, SERIF)
    h.celda(287.09, y[2], 46.54, alto[2], "Barrio:", 19.5)
    h.celda(333.63, y[2], 70.37, alto[2], attrs.get("BARRIO_URB") or "", 19.5, SERIF)
    h.celda(67.56, y[3], 219.53, alto[3], attrs.get("NOMBRE_BEN") or "", 19.5, SERIF)
    h.celda(67.56, y[4], 219.53, alto[4], fecha, 19.5, SERIF)
    h.celda(287.09, y[3], 46.54, y[5] - y[3], "Zona:", 19.5)
    zona = attrs.get("TIPO_DE_PR")
    h.celda(333.63, y[3], 70.37, y[5] - y[3], f"01-{zona}" if zona else "", 19.5, SERIF)
    h.celda(416.12, 28.77, 272.12, 15.42, "Sistema De Referencia:", 19.5)
    h.caja(416.12, 44.19, 272.12, 70.56)
    h.texto(552.18, 79.5, "\n".join(cfg.get("sistema_referencia", SISTEMA_REF)), 13.2)
    # mapa
    escala = elegir_escala(lote, float(cfg.get("escala_base", 167)), cfg.get("escalas", ESCALAS))
    h.caja(8.76, 126.53, 679.52, 268.40)
    pts = [(p.x, p.y, a["vertex_ind"], float(a["DISTANCIA"] or 0)) for p, a in puntos_tabla]
    _mapa(h, lote, pts, base, escala)
    h.encima()
    area = float(attrs.get("AREA") or 0)
    c = lote.representative_point() if not lote.contains(lote.centroid) else lote.centroid
    mm = escala / 1000.0
    cx, cy = (lote.bounds[0] + lote.bounds[2]) / 2, (lote.bounds[1] + lote.bounds[3]) / 2
    h.texto(MAPA[0] + MAPA[2] / 2 + (c.x - cx) / mm, MAPA[1] + MAPA[3] / 2 - (c.y - cy) / mm, f"A: {area:.2f} m²", 21, SANS, True, color=ROJO, z=12)
    _norte(h)
    h.caja(21.36, 350.92, 63.70, 12.75, relleno="white", z=12)
    h.texto(53.2, 357.3, "Escala:", 16, z=13)
    h.caja(21.36, 363.67, 63.70, 19.6, relleno="white", z=12)
    h.texto(53.2, 373.5, f"1:{escala:.0f}", 24, z=13)
    # cuadro de coordenadas
    h.celda(9.96, 400.19, 290.41, 8.75, "Cuadro De Cordenadas Y Linderos", 19.5)
    h.caja(9.96, 408.94, 290.41, 79.44)
    filas = [[str(a["NODO"]), str(a["vertex_ind"]), str(a["TRAMO"]), f"{float(a['NORTE']):.2f}", f"{float(a['ESTE']):.2f}",
              f"{float(a['DISTANCIA'] or 0):.2f} m", str(a["COLINDANTE"] or "")] for _, a in puntos_tabla]
    if filas:
        _cuadro(h, filas)
    # convenciones, manzana y número de plano
    h.celda(312.31, 400.19, 201.02, 12.38, "Convenciones", 19.5)
    h.caja(312.31, 412.57, 201.02, 32.72)
    _convenciones(h)
    h.celda(312.31, 447.86, 96.80, 11.84, "Localizacion De Manzana", 16)
    h.celda(312.31, 459.70, 96.80, 28.62, cod[13:17], 26, SERIF)
    h.celda(416.53, 447.86, 96.80, 11.84, "Plano N°", 19.5)
    h.celda(416.53, 459.70, 96.80, 28.62, str(attrs.get("NODO") or ""), 26, SERIF)
    # firma
    h.celda(524.16, 399.43, 164.13, 8.75, "Firma Autorizada", 19.5)
    h.caja(524.16, 408.18, 164.13, 79.44)
    if firmante:
        h.texto(606.2, 426.5, firmante, 17)
    if firma and os.path.isfile(firma):
        try:
            img = _imagen_firma(firma, os.path.getmtime(firma))
            bw, bh = 65.02, 36.16
            r = min(bw / img.width, bh / img.height)
            w, hh = img.width * r, img.height * r
            eje = h.ejes_mapa(582.31 + (bw - w) / 2, 441.47 + (bh - hh) / 2, w, hh)
            eje.imshow(img, interpolation="lanczos")
            eje.axis("off")
        except Exception:
            pass
    h.linea(583, 477.6, 631, 477.6, lw=0.7)
    h.texto(607, 481.3, "FIRMA AUTORIZADA:", 7)
    if marca_agua:
        for fy in (0.67, 0.30):
            h.fig.text(0.5, fy, "VISTA PREVIA - SIN VALIDEZ", fontsize=118, family=SANS, weight="bold", color=(0.8, 0, 0, 0.30),
                       ha="center", va="center", rotation=18, zorder=100)
    return h.fig


def exportar(lev, coord, base, cfg, salida, fecha, firma=None, firmante=None, nodos=None, vista_previa=False):
    """Un archivo por NODO (PDF, o JPG de baja resolución con marca de agua). Devuelve las rutas."""
    os.makedirs(salida, exist_ok=True)
    por_nodo = {}
    for p, a in coord:
        por_nodo.setdefault(str(a["NODO"]), []).append((p, a))
    hechos = []
    for geom, attrs in lev:
        nodo = str(attrs["NODO"])
        if nodos and nodo not in nodos:
            continue
        filas = sorted(por_nodo.get(nodo, []), key=lambda t: t[1]["vertex_ind"])
        fig = dibujar(attrs, geom, filas, base, cfg, fecha, firma, firmante, marca_agua=vista_previa)
        nombre = re.sub(r'[\\/:*?"<>|]', "_", nodo)
        destino = os.path.join(salida, nombre + (".jpg" if vista_previa else ".pdf"))
        if vista_previa:
            fig.savefig(destino, format="jpg", dpi=45, pil_kwargs={"quality": 72})
        else:
            fig.savefig(destino, format="pdf", metadata={"Title": f"Certificado plano predial {nodo}", "Creator": "Lindero"})
        fig.clear()
        hechos.append(destino)
    return hechos
