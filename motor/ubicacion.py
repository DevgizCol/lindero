# -*- coding: utf-8 -*-
"""
Ubicación del levantamiento sobre la base catastral (lo que antes se hacía a ojo).

1. Sistema de coordenadas del plano: se prueban los orígenes usuales (CTM12, Bogotá, Oeste...)
   y se toma el que deja los lotes sobre los predios. Si ninguno sirve, el plano es local.
2. Ajuste fino: el menor desplazamiento (y giro, si hace falta) que deja cada lote dentro de
   UN solo predio catastral, sin invadir al vecino ni la vía. Si el lote trae código predial
   confiable, ese es el predio que debe contenerlo.
3. Plano local (sin coordenadas reales): se arma la posición con los códigos prediales de los
   lotes (centroide del grupo de lotes -> centroide de su predio) y luego se hace el ajuste fino.

Devuelve los polígonos ubicados, el código predial que queda debajo de cada lote y qué tan
bien calzó cada uno, para revisar solo los que no calzan.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import shapely
from shapely import affinity
from shapely.strtree import STRtree


@dataclass
class Ubicacion:
    poligonos: list
    crs_origen: str = ""
    dx: float = 0.0
    dy: float = 0.0
    giro: float = 0.0                 # grados, antihorario
    fuera_antes: float = 0.0          # fracción del área de los lotes fuera de su predio
    fuera_despues: float = 0.0
    codigo_debajo: list = field(default_factory=list)   # predio con mayor traslape por lote
    calce: list = field(default_factory=list)           # fracción de cada lote dentro de ese predio
    metodo: str = ""
    avisos: list = field(default_factory=list)

    @property
    def desplazamiento(self):
        return math.hypot(self.dx, self.dy)


def _bloques(lotes, holgura=0.5):
    """Grupos de lotes contiguos (se tocan o casi)."""
    n = len(lotes)
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    tree = STRtree(lotes)
    a, b = tree.query(shapely.buffer(lotes, holgura), predicate="intersects")
    for i, j in zip(a, b):
        padre[raiz(int(i))] = raiz(int(j))
    grupos = {}
    for i in range(n):
        grupos.setdefault(raiz(i), []).append(i)
    return list(grupos.values())


class _Calce:
    """
    Área de los lotes que queda fuera de donde deben estar, para una posición dada.

    Con código predial: cada lote debe quedar dentro de los predios de su bloque (los códigos de
    los lotes contiguos a él), así un lindero interno entre predios de la misma familia no cuenta.
    Sin código: dentro de un solo predio, el que más lo cubra.
    """

    def __init__(self, base, zona, lotes, codigos=None):
        sub = base.terrenos[base.terrenos.intersects(zona)]
        self.cod = list(sub["codigo"])
        self.geom = np.array(list(sub.geometry), dtype=object)
        self.tree = STRtree(self.geom) if len(self.geom) else None
        self.idx = {c: i for i, c in enumerate(self.cod)}
        n = len(lotes)
        permitido = [None] * n
        if codigos:
            for bloque in _bloques(lotes):
                cods = {codigos[i] for i in bloque if codigos[i] in self.idx}
                if not cods:
                    continue
                geom = shapely.union_all(self.geom[[self.idx[c] for c in cods]])
                for i in bloque:
                    if codigos[i] in self.idx:
                        permitido[i] = geom
        self.con = np.array([p is not None for p in permitido], dtype=bool)
        self.permitido = np.array([p for p in permitido if p is not None], dtype=object)

    def traslapes(self, lotes):
        """(mayor área dentro de un solo predio, índice de ese predio) por lote."""
        n = len(lotes)
        mejor = np.zeros(n)
        cual = np.full(n, -1)
        if self.tree is None or n == 0:
            return mejor, cual
        li, ti = self.tree.query(lotes, predicate="intersects")
        if len(li):
            ar = shapely.area(shapely.intersection(lotes[li], self.geom[ti]))
            orden = np.argsort(ar)
            mejor[li[orden]] = ar[orden]
            cual[li[orden]] = ti[orden]
        return mejor, cual

    def fuera(self, lotes, areas):
        tot = 0.0
        if self.con.any():
            tot += float(np.sum(areas[self.con] - shapely.area(shapely.intersection(lotes[self.con], self.permitido))))
        if (~self.con).any():
            mejor, _ = self.traslapes(lotes[~self.con])
            tot += float(np.sum(areas[~self.con] - mejor))
        return tot


def _mover(lotes, dx, dy, giro=0.0, centro=(0.0, 0.0)):
    if giro:
        a = math.radians(giro)
        c, s = math.cos(a), math.sin(a)
        cx, cy = centro
        return shapely.transform(lotes, lambda xy: np.column_stack((
            cx + (xy[:, 0] - cx) * c - (xy[:, 1] - cy) * s + dx,
            cy + (xy[:, 0] - cx) * s + (xy[:, 1] - cy) * c + dy)))
    return shapely.transform(lotes, lambda xy: xy + (dx, dy))


def _buscar(calce, lotes, areas, centro, radio, pasos, giros=(0.0,), costo_mov=1.0, x0=(0.0, 0.0, 0.0)):
    """Búsqueda en malla de gruesa a fina de (dx, dy, giro) que minimiza área fuera + costo de moverse."""
    n = len(lotes)
    mejor = None
    paso_prev = None

    def evaluar(dx, dy, g):
        # cada metro que se mueve (en norte o en este) debe justificarse por separado
        return calce.fuera(_mover(lotes, dx, dy, g, centro), areas) + costo_mov * n * (abs(dx) + abs(dy))

    for paso in pasos:
        r = radio if paso_prev is None else paso_prev * 1.5
        rejilla = np.arange(-r, r + 1e-9, paso)
        cx0, cy0 = (x0[0], x0[1]) if mejor is None else (mejor[1], mejor[2])
        for g in (giros if mejor is None else (mejor[3],)):
            for ddx in rejilla:
                for ddy in rejilla:
                    j = evaluar(cx0 + ddx, cy0 + ddy, g)
                    if mejor is None or j < mejor[0] - 1e-9:
                        mejor = (j, cx0 + ddx, cy0 + ddy, g)
        paso_prev = paso
    return mejor


def detectar_crs(poligonos, base, candidatos, codigos=None):
    """CRS del plano: el que deja los lotes más cerca de los predios (de su código, si lo hay)."""
    tree = STRtree(np.array(list(base.terrenos.geometry), dtype=object))
    terr = base.terrenos.set_index("codigo").geometry
    minx, miny, maxx, maxy = base.terrenos.total_bounds
    mejor = None
    for crs in candidatos:
        try:
            gs = gpd.GeoSeries(poligonos, crs=crs).to_crs(base.crs)
        except Exception:
            continue
        cen = gs.centroid
        if not ((cen.x > minx - 2000) & (cen.x < maxx + 2000) & (cen.y > miny - 2000) & (cen.y < maxy + 2000)).all():
            continue
        d = []
        for i, c in enumerate(cen):
            cod = codigos[i] if codigos else ""
            if cod and cod in terr.index:
                d.append(c.distance(terr[cod]))
            else:
                d.append(c.distance(tree.geometries[tree.nearest(c)]))
        med = float(np.median(d))
        if mejor is None or med < mejor[0]:
            mejor = (med, crs, list(gs.values))
    return mejor


def _inicio_local(poligonos, base, codigos):
    """Posición inicial de un plano sin coordenadas reales, a partir de los códigos prediales."""
    terr = base.terrenos.set_index("codigo").geometry
    grupos = {}
    for p, c in zip(poligonos, codigos or []):
        if c and c in terr.index:
            grupos.setdefault(c, []).append(p)
    if not grupos:
        return None
    src = np.array([shapely.union_all(v).centroid.coords[0] for v in grupos.values()])
    dst = np.array([terr[c].centroid.coords[0] for c in grupos])
    todo = shapely.union_all(poligonos)
    c0 = np.array(todo.centroid.coords[0])
    if len(grupos) >= 2 and np.ptp(dst, axis=0).max() > 15:
        ms, md = src.mean(0), dst.mean(0)
        a, b = src - ms, dst - md
        ang = math.atan2((a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum(), (a * b).sum())
        giros = [math.degrees(ang)]
    else:
        ms, md = src.mean(0), dst.mean(0)
        giros = list(np.arange(0, 360, 4.0))
    objetivo = shapely.union_all([terr[c] for c in grupos])
    mejor = None
    for g in giros:
        rot = [affinity.rotate(p, g, origin=tuple(ms)) for p in poligonos]
        mov = [affinity.translate(p, md[0] - ms[0], md[1] - ms[1]) for p in rot]
        u = shapely.union_all(mov)
        puntaje = u.intersection(objetivo).area / max(u.area, 1e-9)
        if mejor is None or puntaje > mejor[0]:
            mejor = (puntaje, mov, g)
    return mejor


def ubicar(poligonos, base, codigos=None, crs_candidatos=None, radio=10.0, permitir_giro=True) -> Ubicacion:
    """
    poligonos: lotes en las coordenadas del plano.  codigos: código predial por lote (o None / '').

    Sin códigos se hace en dos pasadas: la primera encuentra sobre qué predio cae cada lote y la
    segunda repite el ajuste usando esos predios como si fueran los códigos.
    """
    if not codigos or not any(codigos):
        primera = _ubicar(poligonos, base, None, crs_candidatos, radio, permitir_giro)
        if primera.metodo != "COORDENADAS_DEL_PLANO" or not any(primera.codigo_debajo):
            return primera
        segunda = _ubicar(poligonos, base, primera.codigo_debajo, crs_candidatos, radio, permitir_giro)
        segunda.avisos = [a for a in segunda.avisos if "distinto al código" not in a]
        return segunda
    return _ubicar(poligonos, base, codigos, crs_candidatos, radio, permitir_giro)


def _ubicar(poligonos, base, codigos, crs_candidatos, radio, permitir_giro) -> Ubicacion:
    poligonos = [shapely.force_2d(p) for p in poligonos]
    codigos = [str(c or "") for c in codigos] if codigos else None
    candidatos = [str(base.crs)] + [c for c in (crs_candidatos or base.cfg.get("crs_origen_candidatos", []))]
    res = Ubicacion(poligonos=poligonos)
    det = detectar_crs(poligonos, base, candidatos, codigos)
    giros = (0.0,)
    if det and det[0] <= 60:
        res.crs_origen = "CTM12" if det[1] == str(base.crs) else det[1]
        trabajo = det[2]
        res.metodo = "COORDENADAS_DEL_PLANO"
    else:
        ini = _inicio_local(poligonos, base, codigos)
        if ini is None:
            res.avisos.append("El plano no tiene coordenadas reales y los lotes no traen código predial: no se puede ubicar.")
            res.metodo = "SIN_UBICAR"
            return res
        res.crs_origen, trabajo, res.giro = "LOCAL", ini[1], ini[2]
        res.metodo = "CODIGOS_PREDIALES"
        res.avisos.append("El plano no tiene coordenadas reales: se ubicó con los códigos prediales. Conviene revisar la vista previa.")
        giros = tuple(np.arange(-12, 12.1, 1.5))
        radio = max(radio, 15.0)
    lotes = np.array(trabajo, dtype=object)
    areas = shapely.area(lotes)
    zona = shapely.union_all(lotes).buffer(radio + 25)
    calce = _Calce(base, zona, lotes, codigos)
    centro = shapely.union_all(lotes).centroid.coords[0]
    res.fuera_antes = calce.fuera(lotes, areas) / max(areas.sum(), 1e-9)
    # mover 1 m solo se justifica si saca de donde no debe estar más de 1 m² por lote
    costo = 1.0 if res.metodo == "COORDENADAS_DEL_PLANO" else 0.02
    mejor = _buscar(calce, lotes, areas, centro, radio, (1.0, 0.25, 0.05), giros, costo)
    if permitir_giro and res.metodo == "COORDENADAS_DEL_PLANO":
        # un giro pequeño solo se acepta si mejora claro el calce
        base_j = mejor[0]
        for g in (-1.5, -1.0, -0.5, 0.5, 1.0, 1.5):
            alt = _buscar(calce, lotes, areas, centro, 1.5, (0.25, 0.05), (g,), costo, x0=(mejor[1], mejor[2], g))
            if alt[0] < base_j * 0.85 - 0.5 and alt[0] < mejor[0]:
                mejor = alt
    _, dx, dy, g = mejor
    final = _mover(lotes, dx, dy, g, centro)
    res.poligonos = list(final)
    res.dx, res.dy = float(dx), float(dy)
    res.giro = float(res.giro + g)
    res.fuera_despues = calce.fuera(final, areas) / max(areas.sum(), 1e-9)
    m, cual = calce.traslapes(final)
    res.codigo_debajo = [calce.cod[i] if i >= 0 else "" for i in cual]
    res.calce = [float(a / ar) if ar else 0.0 for a, ar in zip(m, areas)]
    flojos = sum(1 for c in res.calce if c < 0.85)
    if flojos:
        res.avisos.append(f"{flojos} lote(s) quedan con menos del 85 % dentro de un solo predio catastral.")
    if codigos:
        dist = [i for i, (c, d) in enumerate(zip(codigos, res.codigo_debajo)) if c and d and c != d]
        if dist:
            res.avisos.append(f"{len(dist)} lote(s) caen sobre un predio distinto al código que traen.")
    return res
