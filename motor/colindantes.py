# -*- coding: utf-8 -*-
"""
Motor de colindantes.

Para cada lado de un lote levantado decide con quién colinda mirando
HACIA AFUERA del lado, no lo que toca el lado. Desde varios puntos del
lado se lanza un rayo perpendicular exterior y se anota lo primero
significativo que atraviesa:

  LOTE     otro lote del mismo levantamiento
  TERRENO  un predio catastral distinto al del lote
  MISMO    el mismo predio catastral (lote que es parte de un predio mayor)
  VIA      espacio sin predio: vía o espacio público

El lado se asigna a lo que gana la mayor parte de su longitud. Un vecino
que solo toca la esquina del lado no gana nada.

Solo depende de shapely y numpy, así que corre igual dentro de QGIS
(plugin) que fuera (motor por lotes / web).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon
from shapely.strtree import STRtree

LOTE, TERRENO, MISMO, VIA, SIN_DATO = "LOTE", "TERRENO", "MISMO", "VIA", "SIN_DATO"
VIA_SIN_NOMBRE = "VIA PUBLICA"
AREA_SIN_CATASTRO = "AREA SIN INFORMACION CATASTRAL"

CARDINALES = ["NORTE", "NORESTE", "ESTE", "SURESTE", "SUR", "SUROESTE", "OESTE", "NOROESTE"]


@dataclass
class Parametros:
    paso_muestra: float = 0.40    # m entre rayos a lo largo del lado
    min_muestras: int = 7
    margen_esquina: float = 0.25  # m descartados en cada extremo del lado
    alcance: float = 8.0          # m hacia afuera donde se buscan predios
    alcance_via: float = 45.0     # m hacia afuera donde se busca el eje vial
    hueco_max: float = 1.0        # vacío más angosto que esto entre predios se ignora
    astilla_max: float = 0.30     # franja de otro predio más angosta que esto se ignora
    propio_max: float = 1.5       # en subdivisión: franja del mismo predio más angosta se ignora
    propio_max_via: float = 4.0   # ídem cuando detrás de la franja ya está la vía (antejardín, desajuste)
    razon_subdivision: float = 0.6  # lote/predio por debajo de esto => el lote es parte de un predio mayor
    secundario_min: float = 0.25  # fracción del lado para reportar un segundo colindante
    secundario_min_m: float = 1.5


@dataclass
class Lote:
    nodo: str
    codigo: str
    geom: Polygon
    nombre: str = ""
    direccion: str = ""


@dataclass
class Lado:
    indice: int                 # 1..n, lado que va del vértice i al i+1
    p1: tuple
    p2: tuple
    longitud: float
    cardinal: str               # hacia dónde mira el lado (normal exterior)
    tipo: str = SIN_DATO
    colindante: str = ""
    etiqueta: str = ""          # nodo del lote vecino o código del predio
    fraccion: float = 0.0       # parte del lado que respalda al ganador
    separacion: float = 0.0     # m entre el lado y el colindante
    secundarios: list = field(default_factory=list)   # [(texto, fraccion)]
    reparto: dict = field(default_factory=dict)       # {(tipo, etiqueta): fraccion}
    confianza: str = "BAJA"
    lindero: str = ""
    descripcion: str = ""
    normal: tuple = (0.0, 0.0)

    @property
    def es_via(self):
        return self.tipo == VIA


class Contexto:
    """Capas de referencia indexadas: predios catastrales, vías, manzanas y lotes."""

    def __init__(self, terrenos: Iterable[tuple], vias: Iterable[tuple] = (),
                 manzanas: Iterable = (), lotes: Sequence[Lote] = ()):
        terrenos = [(str(c), g) for c, g in terrenos if g is not None and not g.is_empty]
        self.terr_cod = [c for c, _ in terrenos]
        self.terr_geom = np.array([g for _, g in terrenos], dtype=object)
        self.terr_tree = STRtree(self.terr_geom) if len(terrenos) else None
        vias = [(limpiar_via(n), g) for n, g in vias if g is not None and not g.is_empty]
        self.via_nom = [n for n, _ in vias]
        self.via_geom = np.array([g for _, g in vias], dtype=object)
        self.via_tree = STRtree(self.via_geom) if len(vias) else None
        manz = [g for g in manzanas if g is not None and not g.is_empty]
        self.manz_geom = np.array(manz, dtype=object)
        self.manz_tree = STRtree(self.manz_geom) if len(manz) else None
        self.set_lotes(lotes)

    def set_lotes(self, lotes: Sequence[Lote]):
        self.lotes = list(lotes)
        self.lote_geom = np.array([l.geom for l in self.lotes], dtype=object)
        self.lote_tree = STRtree(self.lote_geom) if self.lotes else None
        self._por_codigo = defaultdict(list)
        for l in self.lotes:
            self._por_codigo[l.codigo].append(l)

    def predio(self, codigo):
        """Geometría del predio catastral con ese código (unión si viene partido)."""
        idx = [i for i, c in enumerate(self.terr_cod) if c == codigo]
        if not idx:
            return None
        return shapely.union_all(self.terr_geom[idx]) if len(idx) > 1 else self.terr_geom[idx[0]]

    def es_subdivision(self, lote: Lote, p: Parametros) -> bool:
        if len(self._por_codigo.get(lote.codigo, [])) > 1:
            return True
        pred = self.predio(lote.codigo)
        if pred is None or pred.area <= 0:
            return False
        return lote.geom.area / pred.area < p.razon_subdivision


def limpiar_via(texto) -> str:
    t = re.sub(r"\s+", " ", str(texto or "").upper().strip())
    for pat, rep in ((r"^(CL|CLL|C)\b\.?", "CALLE"), (r"^(KR|KRA|CR|CRA|K)\b\.?", "CARRERA"),
                     (r"^(DG|DIAG)\b\.?", "DIAGONAL"), (r"^(TV|TRANS)\b\.?", "TRANSVERSAL"),
                     (r"^(AV)\b\.?", "AVENIDA")):
        t = re.sub(pat, rep, t)
    return t


def via_de_direccion(direccion) -> str:
    """'K 1C SUR 4 94 CASA 1' -> 'CARRERA 1C SUR' (la vía sobre la que está el predio)."""
    t = re.sub(r"\s+", " ", str(direccion or "").upper().strip())
    t = re.sub(r"[#\-,.]", " ", t)
    t = re.sub(r"^(CALLE|CLL|CL|C)(?=\s|\d)", "CALLE ", t)
    t = re.sub(r"^(CARRERA|CRA|KRA|KR|CR|K)(?=\s|\d)", "CARRERA ", t)
    t = re.sub(r"^(DIAGONAL|DIAG|DG)(?=\s|\d)", "DIAGONAL ", t)
    t = re.sub(r"^(TRANSVERSAL|TRANS|TV)(?=\s|\d)", "TRANSVERSAL ", t)
    m = re.match(r"^(CALLE|CARRERA|DIAGONAL|TRANSVERSAL)\s+(\d+\s?[A-Z]?\d?)(\s+(SUR|NORTE|ESTE|OESTE))?", re.sub(r"\s+", " ", t))
    if not m:
        return ""
    return re.sub(r"\s+", " ", f"{m.group(1)} {m.group(2).replace(' ', '')}{m.group(3) or ''}").strip()


def cardinal_de(nx, ny) -> str:
    az = math.degrees(math.atan2(nx, ny)) % 360.0
    return CARDINALES[int((az + 22.5) // 45) % 8]


def anillo_limpio(geom: Polygon, tol=0.02):
    """Vértices del anillo exterior sin el cierre ni duplicados consecutivos."""
    xy = [tuple(c[:2]) for c in geom.exterior.coords]
    if len(xy) > 1 and math.dist(xy[0], xy[-1]) <= tol:
        xy = xy[:-1]
    out = []
    for c in xy:
        if not out or math.dist(out[-1], c) > tol:
            out.append(c)
    while len(out) > 1 and math.dist(out[0], out[-1]) <= tol:
        out.pop()
    return out


def _normal_exterior(p1, p2, poly: Polygon):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    l = math.hypot(dx, dy)
    if l == 0:
        return (0.0, 0.0)
    nx, ny = dy / l, -dx / l
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    for d in (0.03, 0.10, 0.30):
        dentro_pos = shapely.contains_xy(poly, mx + nx * d, my + ny * d)
        dentro_neg = shapely.contains_xy(poly, mx - nx * d, my - ny * d)
        if dentro_pos != dentro_neg:
            return (-nx, -ny) if dentro_pos else (nx, ny)
    # sin decisión local: por el sentido de giro del anillo
    return (nx, ny) if not poly.exterior.is_ccw else (-nx, -ny)


def _tramos(inter, ox, oy, nx, ny):
    """Intervalos [s0, s1] a lo largo del rayo que cubre una intersección rayo-polígono."""
    out = []
    if inter is None or inter.is_empty:
        return out
    for g in (inter.geoms if hasattr(inter, "geoms") else [inter]):
        if g.geom_type != "LineString":
            continue
        c = np.asarray(g.coords)[:, :2]
        s = (c[:, 0] - ox) * nx + (c[:, 1] - oy) * ny
        out.append((float(s.min()), float(s.max())))
    return out


def _secuencia(tramos, alcance):
    """
    tramos: [(s0, s1, prioridad, clave)] posiblemente solapados.
    Devuelve la secuencia contigua [(s0, s1, clave)] de 0 a alcance; lo no cubierto es None.
    """
    cortes = {0.0, alcance}
    for s0, s1, _, _ in tramos:
        cortes.add(min(max(s0, 0.0), alcance))
        cortes.add(min(max(s1, 0.0), alcance))
    cortes = sorted(cortes)
    seq = []
    for a, b in zip(cortes[:-1], cortes[1:]):
        if b - a < 1e-6:
            continue
        m = (a + b) / 2
        mejor = None
        for s0, s1, pri, clave in tramos:
            if s0 <= m <= s1 and (mejor is None or pri < mejor[0] or (pri == mejor[0] and (s1 - s0) > mejor[2])):
                mejor = (pri, clave, s1 - s0)
        clave = mejor[1] if mejor else None
        if seq and seq[-1][2] == clave:
            seq[-1] = (seq[-1][0], b, clave)
        else:
            seq.append((a, b, clave))
    return seq


def _veredicto(seq, codigo_propio, subdivision, p: Parametros):
    """Primera región significativa del rayo -> (tipo, etiqueta, separación)."""
    alcance = p.alcance
    for i, (s0, s1, clave) in enumerate(seq):
        ancho = s1 - s0
        final = s1 >= alcance - 1e-6
        if clave is None:
            if ancho < p.hueco_max and not final:
                continue
            return (VIA, "", s0)
        tipo, etq = clave
        if tipo == "PROPIO":       # el rayo vuelve a entrar al mismo lote (entrante)
            return (MISMO, codigo_propio, s0)
        if tipo == LOTE:
            if ancho < p.astilla_max and not final:
                continue
            return (LOTE, etq, s0)
        if etq == codigo_propio:
            if not subdivision:
                continue
            sig = seq[i + 1] if i + 1 < len(seq) else None
            hacia_via = sig is not None and sig[2] is None and (sig[1] - sig[0] >= p.hueco_max or sig[1] >= alcance - 1e-6)
            if ancho < (p.propio_max_via if hacia_via else p.propio_max) and not final:
                continue
            return (MISMO, etq, s0)
        if ancho < p.astilla_max and not final:
            continue
        return (TERRENO, etq, s0)
    return (SIN_DATO, "", alcance)


def _nombre_via(ctx: Contexto, origenes, normal, p1, p2, p: Parametros):
    """Nombre de la vía que enfrenta el lado: primer eje vial que cortan los rayos."""
    if ctx.via_tree is None:
        return VIA_SIN_NOMBRE, 0.0
    nx, ny = normal
    votos = defaultdict(float)
    dist = defaultdict(list)
    rayos = [LineString([(x, y), (x + nx * p.alcance_via, y + ny * p.alcance_via)]) for x, y in origenes]
    if rayos:
        ri, gi = ctx.via_tree.query(rayos, predicate="intersects")
        primero = {}
        for r, g in zip(ri, gi):
            inter = rayos[r].intersection(ctx.via_geom[g])
            if inter.is_empty:
                continue
            ox, oy = origenes[r]
            c = shapely.get_coordinates(inter)
            s = float(((c[:, 0] - ox) * nx + (c[:, 1] - oy) * ny).min())
            if r not in primero or s < primero[r][0]:
                primero[r] = (s, ctx.via_nom[g])
        for s, nom in primero.values():
            votos[nom] += 1
            dist[nom].append(s)
    if votos:
        nom = max(votos, key=lambda k: (votos[k], -np.median(dist[k])))
        return nom, votos[nom] / max(1, len(origenes))
    # sin corte: el eje más cercano que corra paralelo al lado
    lado = LineString([p1, p2])
    ang_lado = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    mejor = None
    for g in ctx.via_tree.query(lado.buffer(p.alcance_via * 0.6)):
        eje = ctx.via_geom[g]
        d = lado.distance(eje)
        a = eje.interpolate(max(0.0, eje.project(lado.centroid) - 2))
        b = eje.interpolate(eje.project(lado.centroid) + 2)
        ang = math.atan2(b.y - a.y, b.x - a.x)
        dif = abs((ang - ang_lado + math.pi / 2) % math.pi - math.pi / 2)
        if dif <= math.radians(35) and (mejor is None or d < mejor[0]):
            mejor = (d, ctx.via_nom[g])
    return (mejor[1], 0.0) if mejor else (VIA_SIN_NOMBRE, 0.0)


def analizar_lote(lote: Lote, ctx: Contexto, p: Parametros | None = None,
                  vertices: Sequence[tuple] | None = None) -> list[Lado]:
    """
    Colindante de cada lado del lote. `vertices` fija el orden y el vértice inicial
    (p. ej. el de la capa COORDENADAS); si no se da, se usa el anillo del polígono.
    """
    p = p or Parametros()
    poly = lote.geom
    verts = list(vertices) if vertices else anillo_limpio(poly)
    n = len(verts)
    subdiv = ctx.es_subdivision(lote, p)
    lados: list[Lado] = []
    for i in range(n):
        p1, p2 = verts[i], verts[(i + 1) % n]
        L = math.dist(p1, p2)
        normal = _normal_exterior(p1, p2, poly)
        lado = Lado(indice=i + 1, p1=p1, p2=p2, longitud=L, normal=normal,
                    cardinal=cardinal_de(*normal) if L > 0 else "")
        lados.append(lado)
        if L < 0.02:
            continue
        nx, ny = normal
        margen = min(p.margen_esquina, L * 0.15)
        k = max(p.min_muestras, int(math.ceil((L - 2 * margen) / p.paso_muestra)) + 1)
        ts = np.linspace(margen / L, 1 - margen / L, k)
        eps = 0.01
        origenes = [(p1[0] + (p2[0] - p1[0]) * t + nx * eps, p1[1] + (p2[1] - p1[1]) * t + ny * eps) for t in ts]
        rayos = [LineString([(x, y), (x + nx * p.alcance, y + ny * p.alcance)]) for x, y in origenes]
        tramos = [[] for _ in rayos]

        def acumular(tree, geoms, clave_de, prioridad):
            if tree is None:
                return
            ri, gi = tree.query(rayos, predicate="intersects")
            for r, g in zip(ri, gi):
                clave = clave_de(g)
                if clave is None:
                    continue
                ox, oy = origenes[r]
                for s0, s1 in _tramos(rayos[r].intersection(geoms[g]), ox, oy, nx, ny):
                    if s1 - s0 > 1e-4:
                        tramos[r].append((s0, s1, prioridad, clave))

        acumular(ctx.lote_tree, ctx.lote_geom,
                 lambda g: ("PROPIO", "") if ctx.lotes[g].nodo == lote.nodo else (LOTE, ctx.lotes[g].nodo), 0)
        acumular(ctx.terr_tree, ctx.terr_geom, lambda g: (TERRENO, ctx.terr_cod[g]), 1)
        # el propio polígono (por si el lote no está en ctx.lotes)
        for r, ray in enumerate(rayos):
            ox, oy = origenes[r]
            for s0, s1 in _tramos(ray.intersection(poly), ox, oy, nx, ny):
                if s1 - s0 > 0.05:
                    tramos[r].append((s0, s1, 0, ("PROPIO", "")))

        votos = defaultdict(float)
        seps = defaultdict(list)
        vias_idx = []
        for r in range(len(rayos)):
            tipo, etq, sep = _veredicto(_secuencia(tramos[r], p.alcance), lote.codigo, subdiv, p)
            votos[(tipo, etq)] += 1.0 / len(rayos)
            seps[(tipo, etq)].append(sep)
            if tipo == VIA:
                vias_idx.append(r)

        # el espacio sin predio es vía solo si está fuera de manzana o hay un eje vial enfrente
        if vias_idx:
            nombre, apoyo = _nombre_via(ctx, [origenes[r] for r in vias_idx], normal, p1, p2, p)
            en_manzana = False
            if ctx.manz_tree is not None and nombre == VIA_SIN_NOMBRE:
                pts = shapely.points([(origenes[r][0] + nx * (np.median(seps[(VIA, "")]) + p.hueco_max / 2),
                                       origenes[r][1] + ny * (np.median(seps[(VIA, "")]) + p.hueco_max / 2)) for r in vias_idx])
                hit = ctx.manz_tree.query(pts, predicate="within")
                en_manzana = len(set(hit[0])) > len(vias_idx) / 2
            v = votos.pop((VIA, ""))
            s = seps.pop((VIA, ""))
            clave = (SIN_DATO, AREA_SIN_CATASTRO) if en_manzana else (VIA, nombre)
            votos[clave] += v
            seps[clave] += s

        lado.reparto = dict(votos)
        _resolver(lado, votos, seps, ctx, p)
    _orientar(lados, lote, ctx)
    for l in lados:
        l.descripcion = describir(l)
    return lados


def texto_colindante(tipo, etq, ctx: Contexto) -> str:
    if tipo == LOTE:
        for l in ctx.lotes:
            if l.nodo == etq:
                return l.codigo or etq
        return etq
    if tipo in (TERRENO, MISMO):
        return etq
    if tipo == VIA:
        return etq or VIA_SIN_NOMBRE
    return etq or "NO_ENCONTRADO"


def _resolver(lado: Lado, votos, seps, ctx: Contexto, p: Parametros):
    # se agrupa por el texto final: el lote T2 y el resto del predio 0053 dicen lo mismo
    por_texto = defaultdict(lambda: [0.0, [], None])
    for (tipo, etq), frac in votos.items():
        if tipo == SIN_DATO and not etq:
            continue
        txt = texto_colindante(tipo, etq, ctx)
        reg = por_texto[txt]
        reg[0] += frac
        reg[1] += seps[(tipo, etq)]
        if reg[2] is None or frac > reg[2][2]:
            reg[2] = (tipo, etq, frac)
    if not por_texto:
        lado.tipo, lado.colindante, lado.confianza = SIN_DATO, "NO_ENCONTRADO", "BAJA"
        return
    orden = sorted(por_texto.items(), key=lambda kv: -kv[1][0])
    txt, (frac, sep, (tipo, etq, _)) = orden[0]
    lado.tipo, lado.etiqueta, lado.colindante = tipo, etq, txt
    lado.fraccion = round(frac, 3)
    lado.separacion = round(float(np.median(sep)), 2) if sep else 0.0
    lado.secundarios = [(t, round(v[0], 3)) for t, v in orden[1:]
                        if v[0] >= p.secundario_min and v[0] * lado.longitud >= p.secundario_min_m]
    if tipo == SIN_DATO or frac < 0.5 or (tipo == VIA and txt == VIA_SIN_NOMBRE):
        lado.confianza = "BAJA"
    elif frac >= 0.8 and (tipo == VIA or lado.separacion <= 0.6):
        lado.confianza = "ALTA"
    else:
        lado.confianza = "MEDIA"


def _orientar(lados: list[Lado], lote: Lote, ctx: Contexto):
    """FRENTE / FONDO / DERECHA / IZQUIERDA entrando al predio por el frente."""
    validos = [l for l in lados if l.longitud >= 0.02]
    if not validos:
        return
    via_dir = via_de_direccion(lote.direccion)
    de_via = [l for l in validos if l.tipo == VIA]
    frente = None
    if de_via:
        en_dir = [l for l in de_via if via_dir and l.colindante == via_dir]
        frente = max(en_dir or de_via, key=lambda l: l.longitud)
        nfx, nfy = frente.normal
    else:
        # lote interior: el frente mira hacia la vía de su dirección (o la más cercana)
        nfx = nfy = None
        if ctx.via_tree is not None:
            c = lote.geom.centroid
            cand = [i for i, nom in enumerate(ctx.via_nom) if via_dir and nom == via_dir]
            if cand:
                d = [c.distance(ctx.via_geom[i]) for i in cand]
                eje = ctx.via_geom[cand[int(np.argmin(d))]]
            else:
                eje = ctx.via_geom[ctx.via_tree.nearest(c)]
            q = eje.interpolate(eje.project(c))
            v = (q.x - c.x, q.y - c.y)
            m = math.hypot(*v)
            if m > 0:
                nfx, nfy = v[0] / m, v[1] / m
        if nfx is None:
            f = max(validos, key=lambda l: l.longitud)
            nfx, nfy = f.normal
        frente = max(validos, key=lambda l: (l.normal[0] * nfx + l.normal[1] * nfy) * min(l.longitud, 5.0))
        nfx, nfy = frente.normal
    for l in validos:
        nx, ny = l.normal
        cos = nx * nfx + ny * nfy
        # el observador entra al predio mirando hacia -n_frente
        cruz = (-nfx) * ny - (-nfy) * nx
        if l is frente or cos >= math.cos(math.radians(45)):
            l.lindero = "FRENTE"
        elif cos <= -math.cos(math.radians(45)):
            l.lindero = "FONDO"
        elif cruz < 0:
            l.lindero = "DERECHA"
        else:
            l.lindero = "IZQUIERDA"


def describir(l: Lado) -> str:
    if l.longitud < 0.02:
        return ""
    dist = f"{l.longitud:.2f}".replace(".", ",")
    con = l.colindante
    if l.tipo in (TERRENO, MISMO, LOTE) and re.fullmatch(r"\d{20,30}", con or ""):
        con = f"el predio {con}"
    elif l.tipo == VIA:
        con = f"la {con}"
    txt = f"Por el costado {l.lindero} ({l.cardinal}), en una extensión de {dist} metros, colinda con {con}"
    if l.secundarios:
        txt += " y en parte con " + ", ".join(t for t, _ in l.secundarios)
    return txt + "."


def nivel_conf(l: Lado) -> str:
    return f"{l.confianza} ({int(round(l.fraccion * 100))}%)" if l.fraccion else l.confianza
