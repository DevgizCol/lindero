# -*- coding: utf-8 -*-
"""
Dirección -> código predial (referencia catastral), sin Google Earth.

Métodos, del más fiable al menos:

  PLACA          la placa domiciliaria del catastro (cruce-número) sobre la vía de la dirección
  R1             la dirección coincide con la registrada en el R1 del IGAC
  INTERPOLACION  se ubica el número sobre el eje de la vía (entre las placas vecinas del mismo
                 cruce, o en metros desde el cruce) y se toma el predio que da frente a ese punto

Cada resultado trae confianza (ALTA / MEDIA / BAJA) y los candidatos, para que solo se
revisen a mano los dudosos.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import Point
from shapely.ops import linemerge, nearest_points
from shapely.strtree import STRtree

PALABRAS_COMPLEMENTO = {"APTO", "APT", "AP", "APARTAMENTO", "CASA", "CS", "LOCAL", "LC", "PISO", "INT", "INTERIOR",
                        "LOTE", "LT", "MZ", "MANZANA", "BLOQUE", "BL", "TORRE", "ET", "ETAPA", "BODEGA", "OF", "OFICINA"}
TIPOS = [("C", r"CALLE|CLL|CLLE|CL|C"), ("K", r"CARRERA|CARRETERA|CRA|KRA|KR|CR|K"),
         ("D", r"DIAGONAL|DIAG|DG|D"), ("T", r"TRANSVERSAL|TRANSV|TRANS|TV|T"), ("A", r"AVENIDA|AV")]
TIPO_VIA = {"CALLE": "C", "CARRERA": "K", "DIAGONAL": "D", "TRANSVERSAL": "T", "AVENIDA": "A"}


def norm_num(txt) -> str:
    """'1C SUR' -> '1CSUR', '4S' -> '4SUR', '11A 1' -> '11A1'."""
    t = re.sub(r"[^0-9A-Z]", "", str(txt or "").upper())
    t = re.sub(r"^0+(?=\d)", "", t)
    if re.fullmatch(r"\d+[A-Z]?\d?S", t):
        t += "UR"
    return t


@dataclass
class Direccion:
    tipo: str
    via: str
    cruce: str
    numero: int
    complemento: str = ""

    @property
    def clave_via(self):
        return f"{self.tipo}:{self.via}"

    def texto(self):
        return f"{self.tipo} {self.via} {self.cruce} {self.numero}"


def parsear(txt) -> Direccion | None:
    t = str(txt or "").upper()
    t = re.sub(r"\bN[O°º]\.?(?=\s|\d)|#|,|;|\.", " ", t).replace("-", " ")
    t = re.sub(r"\s+", " ", t).strip()
    tipo = None
    for letra, pat in TIPOS:
        m = re.match(rf"^({pat})(?=\s|\d)\s*", t)
        if m:
            tipo, t = letra, t[m.end():]
            break
    if not tipo:
        return None
    toks = t.split()
    i = 0

    def tomar_numero_via():
        nonlocal i
        if i >= len(toks) or not toks[i][0].isdigit():
            return None
        partes = [toks[i]]
        i += 1
        while i < len(toks) and toks[i].isalpha() and toks[i] not in PALABRAS_COMPLEMENTO:
            partes.append(toks[i])
            i += 1
        return norm_num("".join(partes))

    via = tomar_numero_via()
    cruce = tomar_numero_via()
    if not via or not cruce or i >= len(toks) or not re.fullmatch(r"\d+", toks[i]):
        return None
    numero = int(toks[i])
    return Direccion(tipo, via, cruce, numero, " ".join(toks[i + 1:]))


def parsear_placa(txt):
    """'8ASUR-58' -> (None, '8ASUR', 58);  '4B-16-04' -> ('4B', '16', 4)."""
    partes = [p.strip() for p in str(txt or "").upper().split("-") if p.strip()]
    if len(partes) == 2 and partes[1].isdigit() and partes[0][:1].isdigit():
        return None, norm_num(partes[0]), int(partes[1])
    if len(partes) == 3 and partes[2].isdigit() and partes[0][:1].isdigit() and partes[1][:1].isdigit():
        return norm_num(partes[0]), norm_num(partes[1]), int(partes[2])
    return None


def norm_dir_r1(txt) -> str:
    d = parsear(txt)
    return d.texto() if d else ""


@dataclass
class Resultado:
    direccion: str
    codigo: str = ""
    metodo: str = ""
    confianza: str = "SIN_RESULTADO"
    candidatos: list = field(default_factory=list)   # [(codigo, motivo)]
    punto: tuple | None = None
    nota: str = ""


def _num_base(v: str) -> float:
    m = re.match(r"(\d+)([A-Z]?)(\d?)", v)
    if not m:
        return float("nan")
    n = int(m.group(1)) + ((ord(m.group(2)) - 64) / 30 if m.group(2) else 0)
    return n + (int(m.group(3)) / 300 if m.group(3) else 0)


class Geocodificador:
    DIST_PLACA_VIA = 14.0   # una placa pertenece a una vía si está a menos de esto de su eje

    def __init__(self, base, r1_ruta=None):
        self.base = base
        self.terr_cod = list(base.terrenos["codigo"])
        self.terr_geom = np.array(list(base.terrenos.geometry), dtype=object)
        self.terr_tree = STRtree(self.terr_geom)
        self.con_geom = set(self.terr_cod)
        # ejes viales por clave 'K:14'
        ejes = defaultdict(list)
        via_geoms, via_claves = [], []
        for tipo, num, g in zip(base.vias["tipo_via"], base.vias["numero_via"], base.vias.geometry):
            letra = TIPO_VIA.get(str(tipo).upper())
            if letra:
                k = f"{letra}:{norm_num(num)}"
                ejes[k].append(g)
                via_geoms.append(g)
                via_claves.append(k)
        self.ejes = {k: shapely.union_all(v) for k, v in ejes.items()}
        via_tree = STRtree(via_geoms)
        # placas: cada una se asigna a la vía cercana cuyo cruce queda a la distancia que dice su número
        self._cruces = {}
        self.placas = defaultdict(list)      # (clave_via, cruce, numero) -> [(punto, codigo)]
        self.placas_via = defaultdict(list)  # (clave_via, cruce) -> [(numero, punto, codigo)]
        for txt, cod, g in zip(base.placas["texto"], base.placas["terreno_codigo"], base.placas.geometry):
            pp = parsear_placa(txt)
            if not pp or not cod:
                continue
            via_txt, cruce, num = pp
            c = g.centroid
            cerca = {}
            for i in via_tree.query(c.buffer(self.DIST_PLACA_VIA)):
                dd = c.distance(via_geoms[i])
                if dd <= self.DIST_PLACA_VIA and dd < cerca.get(via_claves[i], 1e9):
                    cerca[via_claves[i]] = dd
            if via_txt:
                cerca = {k: v for k, v in cerca.items() if k.split(":")[1] == via_txt}
            if not cerca:
                continue
            mejor = None
            for k, dd in cerca.items():
                x = self.punto_cruce(k, cruce, c)
                if x is None:
                    continue
                desajuste = abs(c.distance(x) - num)
                if desajuste <= max(30.0, 0.6 * num) and (mejor is None or desajuste < mejor[0]):
                    mejor = (desajuste, k)
            k = mejor[1] if mejor else (min(cerca, key=cerca.get) if len(cerca) == 1 else None)
            if k is None:
                continue
            self.placas[(k, cruce, num)].append((c, str(cod)))
            self.placas_via[(k, cruce)].append((num, c, str(cod)))
        # R1: dirección normalizada -> códigos. Con la base empacada ya viene resuelto y sin datos
        # personales; con el R1 original se puede además cruzar por cédula.
        self.r1 = defaultdict(set)
        self.r1_doc = defaultdict(set)
        empacado = base.direcciones_r1() if hasattr(base, "direcciones_r1") else None
        ruta = r1_ruta or base.cfg.get("r1")
        if empacado is not None and not r1_ruta:
            for k, cods in empacado.items():
                self.r1[k].update(cods)
        elif ruta:
            try:
                with open(ruta, encoding="latin-1") as f:
                    for linea in f:
                        k = norm_dir_r1(linea[151:251])
                        if k:
                            self.r1[k].add(linea[:30])
                        doc = linea[139:151].strip().lstrip("0")
                        if doc:
                            self.r1_doc[doc].add(linea[:30])
            except OSError:
                pass

    def punto_cruce(self, clave_via, cruce, cerca_de=None):
        """Punto donde la vía se encuentra con su cruce (la vía del otro tipo con ese número)."""
        otros = {"C": ["K", "T", "D"], "K": ["C", "D", "T"]}.get(clave_via[0], ["C", "K"])
        eje = self.ejes.get(clave_via)
        if eje is None:
            return None
        for o in otros:
            kc = f"{o}:{cruce}"
            if kc not in self.ejes:
                continue
            if (clave_via, kc) not in self._cruces:
                otro = self.ejes[kc]
                if eje.distance(otro) > 35:
                    self._cruces[(clave_via, kc)] = []
                else:
                    inter = eje.intersection(otro.buffer(1.0))
                    pts = [g.centroid for g in (inter.geoms if hasattr(inter, "geoms") else [inter]) if not g.is_empty]
                    self._cruces[(clave_via, kc)] = pts or [nearest_points(eje, otro)[0]]
            pts = self._cruces[(clave_via, kc)]
            if pts:
                return min(pts, key=lambda q: q.distance(cerca_de)) if cerca_de is not None else pts[0]
        return None

    def terreno_de(self, codigo: str) -> str:
        """Código del terreno (con geometría) al que pertenece un código del R1 (p. ej. una mejora)."""
        if codigo in self.con_geom:
            return codigo
        base = codigo[:21] + "0" * 9
        return base if base in self.con_geom else ""

    # ---------- métodos ----------
    def _por_placa(self, d: Direccion, excluir=None):
        return [(p, c) for p, c in self.placas.get((d.clave_via, d.cruce, d.numero), []) if c != excluir]

    def _sentido(self, d: Direccion, eje, s0):
        """+1 / -1: hacia dónde crece la numeración sobre el eje a partir del cruce."""
        otro = {"C": ["K", "T", "D"], "K": ["C", "D", "T"]}.get(d.tipo, ["C", "K"])
        base_n = _num_base(d.cruce)
        sur = d.cruce.endswith("SUR")
        mejor = None
        for k, g in self.ejes.items():
            v = k.split(":")[1]
            if k[0] not in otro or v == d.cruce or v.endswith("SUR") != sur:
                continue
            n = _num_base(v)
            if math.isnan(n) or n == base_n or abs(n - base_n) > 3 or eje.distance(g) > 3:
                continue
            s = eje.project(nearest_points(eje, g)[0])
            if abs(s - s0) < 5:
                continue
            signo = 1 if (s > s0) == (n > base_n) else -1
            peso = 1 / abs(s - s0)
            if mejor is None or peso > mejor[0]:
                mejor = (peso, signo)
        return mejor[1] if mejor else 0

    def _eje_lineal(self, d: Direccion, cerca_de=None):
        eje = self.ejes.get(d.clave_via)
        if eje is None:
            return None
        if eje.geom_type == "MultiLineString":
            m = linemerge(eje)
            if m.geom_type == "MultiLineString":
                partes = list(m.geoms)
                if cerca_de is not None:
                    return min(partes, key=lambda g: g.distance(cerca_de))
                return max(partes, key=lambda g: g.length)
            return m
        return eje

    @staticmethod
    def _tangente(eje, s):
        a, b = eje.interpolate(max(s - 1, 0)), eje.interpolate(min(s + 1, eje.length))
        return b.x - a.x, b.y - a.y

    def _costado(self, eje, p):
        s = eje.project(p)
        tx, ty = self._tangente(eje, s)
        q = eje.interpolate(s)
        return 1 if tx * (p.y - q.y) - ty * (p.x - q.x) > 0 else -1

    def _por_interpolacion(self, d: Direccion, excluir=None):
        """Punto estimado sobre el eje y predios que le dan frente, del más al menos probable."""
        otro = {"C": ["K", "T", "D"], "K": ["C", "D", "T"]}.get(d.tipo, ["C", "K"])
        eje_cruce = next((self.ejes[f"{o}:{d.cruce}"] for o in otro if f"{o}:{d.cruce}" in self.ejes), None)
        eje_todo = self.ejes.get(d.clave_via)
        if eje_todo is None:
            return None, [], "no existe el eje de la vía en la base"
        vecinos = [(n, p, c) for n, p, c in self.placas_via.get((d.clave_via, d.cruce), [])
                   if not (c == excluir and n == d.numero)]
        ancla = vecinos[0][1] if vecinos else (nearest_points(eje_todo, eje_cruce)[0] if eje_cruce is not None else None)
        eje = self._eje_lineal(d, cerca_de=ancla)
        nota, s_est, costado_ok = "", [], 0
        # 1) con las placas del mismo cruce sobre esta misma vía (de preferencia las de igual paridad,
        #    que quedan en el mismo costado)
        if vecinos:
            igual = [v for v in vecinos if v[0] % 2 == d.numero % 2]
            usar = igual if len({n for n, _, _ in igual}) >= 2 else vecinos
            ns = np.array([n for n, _, _ in usar], float)
            ss = np.array([eje.project(p) for _, p, _ in usar])
            if len(set(ns)) >= 2 and ns.max() - ns.min() >= 6:
                b, a = np.polyfit(ns, ss, 1)
                if 0.25 <= abs(b) <= 4.0:
                    orden = np.argsort(ns)
                    if ns.min() <= d.numero <= ns.max():
                        s = float(np.interp(d.numero, ns[orden], ss[orden]))
                    else:
                        s = float(a + b * d.numero)
                    s_est.append(s)
                    nota = f"ajustado con {len(usar)} placas del cruce {d.cruce} sobre la vía"
            if not s_est:
                k = int(np.argmin(np.abs(ns - d.numero)))
                s0 = eje.project(nearest_points(eje, eje_cruce)[0]) if eje_cruce is not None else None
                signo = (1 if ss[k] > s0 else -1) if s0 is not None and abs(ss[k] - s0) > 3 else 0
                for sg in ([signo] if signo else [1, -1]):
                    s_est.append(float(ss[k] + sg * (d.numero - ns[k])))
                nota = f"a partir de la placa {d.cruce}-{int(ns[k])}"
            # costado: solo se fija si en esta cuadra pares e impares están bien separados
            pares = [self._costado(eje, p) * (1 if n % 2 == 0 else -1) for n, p, _ in vecinos]
            if len(pares) >= 4 and abs(sum(pares)) >= 0.75 * len(pares):
                costado_ok = (1 if sum(pares) > 0 else -1) * (1 if d.numero % 2 == 0 else -1)
        # 2) metros desde el cruce de ejes
        if not s_est and eje_cruce is not None and eje.distance(eje_cruce) <= 30:
            s0 = eje.project(nearest_points(eje, eje_cruce)[0])
            signo = self._sentido(d, eje, s0)
            s_est = [s0 + sg * d.numero for sg in ([signo] if signo else [1, -1])]
            nota = "metros desde el cruce de ejes" + ("" if signo else " (sentido sin confirmar)")
        # 3) el cruce no está en la base: se estima entre las vías vecinas que sí cruzan
        if not s_est:
            base_n, sur = _num_base(d.cruce), d.cruce.endswith("SUR")
            ref = []
            for k, g in self.ejes.items():
                v = k.split(":")[1]
                if k[0] not in otro or v.endswith("SUR") != sur or eje.distance(g) > 3:
                    continue
                n = _num_base(v)
                if not math.isnan(n) and abs(n - base_n) <= 4:
                    ref.append((n, eje.project(nearest_points(eje, g)[0])))
            ref = sorted(set(ref))
            if len({n for n, _ in ref}) >= 2 and not math.isnan(base_n):
                rn, rs = np.array([n for n, _ in ref]), np.array([x for _, x in ref])
                b, a = np.polyfit(rn, rs, 1)
                if abs(b) > 5:
                    s0 = float(np.interp(base_n, rn, rs)) if rn.min() <= base_n <= rn.max() else float(a + b * base_n)
                    s_est = [s0 + (1 if b > 0 else -1) * d.numero]
                    nota = f"cruce {d.cruce} estimado entre vías vecinas (no está en la base)"
        s_est = [min(max(s, 0), eje.length) for s in s_est if -8 <= s <= eje.length + 8]
        if not s_est:
            return None, [], "no se pudo ubicar el cruce sobre la vía"
        cands = {}
        for sq in s_est:
            q = eje.interpolate(sq)
            tx, ty = self._tangente(eje, sq)
            for g in self.terr_tree.query(q.buffer(30)):
                geom = self.terr_geom[g]
                lateral = geom.distance(eje)
                if lateral > 14:
                    continue
                # frente del predio: la parte de su borde que mira a la vía
                frente = geom.boundary.intersection(eje.buffer(lateral + 2.5))
                if frente.is_empty:
                    continue
                xs = [eje.project(Point(xy)) for xy in shapely.get_coordinates(frente)]
                lo, hi = min(xs), max(xs)
                fuera = max(0.0, lo - sq, sq - hi)
                if fuera > 8:
                    continue
                c = frente.centroid
                costado = 1 if tx * (c.y - q.y) - ty * (c.x - q.x) > 0 else -1
                costo = fuera + 0.15 * abs(sq - (lo + hi) / 2) + (12.0 if costado_ok and costado != costado_ok else 0.0)
                cod = self.terr_cod[g]
                if cod not in cands or costo < cands[cod][0]:
                    cands[cod] = (costo, cod, q)
        orden = sorted(cands.values(), key=lambda x: x[0])
        return eje.interpolate(s_est[0]), orden, nota + ("" if costado_ok else "; costado par/impar sin confirmar")

    def _lado_paridad(self, d: Direccion, eje):
        """+1 si los pares quedan a la izquierda del eje, según todas las placas de esa vía."""
        votos = n = 0
        for (k, _cruce), lst in self.placas_via.items():
            if k != d.clave_via:
                continue
            for num, p, _ in lst:
                if p.distance(eje) > self.DIST_PLACA_VIA + 2:
                    continue
                votos += self._costado(eje, p) * (1 if num % 2 == 0 else -1)
                n += 1
        return (1 if votos > 0 else -1) if n >= 4 and abs(votos) >= 0.6 * n else 0

    # ---------- resolución ----------
    def buscar(self, direccion, cedula=None, _excluir=None) -> Resultado:
        r = Resultado(str(direccion or "").strip())
        d = parsear(direccion)
        if d is None:
            r.nota = "dirección no interpretable (se espera vía, cruce y número de placa)"
            return r
        placa = self._por_placa(d, _excluir)
        cod_placa = list(dict.fromkeys(c for _, c in placa))
        r1 = sorted(self.r1.get(d.texto(), ()))
        r1_terr = {c: self.terreno_de(c) for c in r1}
        r1 = [c for c in r1 if r1_terr[c]]
        ced = sorted(c for c in self.r1_doc.get(str(cedula or "").strip().lstrip("0"), ())
                     if self.terreno_de(c)) if cedula else []

        def agregar(cod, motivo):
            if cod and cod not in [x[0] for x in r.candidatos]:
                r.candidatos.append((cod, motivo))

        for c in cod_placa:
            agregar(c, "PLACA")
        for c in r1:
            agregar(c, "R1")
        if cod_placa:
            r.punto = (placa[0][0].x, placa[0][0].y)
            en_r1 = [c for c in r1 if r1_terr[c] in cod_placa]
            if len(cod_placa) == 1:
                # si el R1 tiene esa dirección en una mejora del mismo terreno, esa es la referencia más precisa
                r.codigo = en_r1[0] if len(en_r1) == 1 else cod_placa[0]
                r.metodo, r.confianza = ("PLACA+R1" if en_r1 else "PLACA"), "ALTA"
                r.nota = "placa exacta sobre la vía" + ("; coincide con el R1" if en_r1 else "")
                return r
            if len({r1_terr[c] for c in en_r1}) == 1:
                r.codigo, r.metodo, r.confianza = en_r1[0], "PLACA+R1", "ALTA"
                r.nota = "placa repetida sobre la vía; el R1 desempata"
                return r
            r.codigo, r.metodo, r.confianza = cod_placa[0], "PLACA", "MEDIA"
            r.nota = f"{len(cod_placa)} predios con esa placa sobre la vía"
            return r
        punto, inter, nota = self._por_interpolacion(d, _excluir)
        if punto is not None:
            r.punto = (punto.x, punto.y)
        cerca = [c for _, c, _ in inter[:3]]
        if r1 and len({r1_terr[c] for c in r1}) == 1:
            r.codigo, r.metodo = r1[0], "R1"
            ok = r1_terr[r1[0]] in cerca
            r.confianza = "ALTA" if ok else "MEDIA"
            r.nota = "dirección igual en el R1" + ("; confirmada sobre el eje de la vía" if ok else "")
            for _, c, _ in inter[:3]:
                agregar(c, "INTERPOLACION")
            return r
        for _, c, _ in inter[:6]:
            agregar(c, "INTERPOLACION")
        for c in ced:
            agregar(c, "CEDULA_R1")
        if inter:
            comun = [c for c in r1 if r1_terr[c] in cerca]
            if comun:
                r.codigo, r.metodo, r.confianza = comun[0], "R1+INTERPOLACION", "MEDIA"
                r.nota = "varios predios con esa dirección en el R1; se toma el que da frente al punto"
                return r
            comun = [c for c in ced if self.terreno_de(c) in [x for _, x, _ in inter[:6]]]
            if comun:
                r.codigo, r.metodo, r.confianza = comun[0], "CEDULA_R1+INTERPOLACION", "MEDIA"
                r.nota = "el beneficiario figura en el R1 en un predio que da frente al punto"
                return r
            r.codigo, r.metodo = inter[0][1], "INTERPOLACION"
            claro = len(inter) == 1 or inter[1][0] - inter[0][0] >= 4.0
            r.confianza = "MEDIA" if (claro and nota.startswith("ajustado") and "sin confirmar" not in nota) else "BAJA"
            r.nota = nota
            return r
        if r1:
            r.codigo, r.metodo, r.confianza = r1[0], "R1", "BAJA"
            r.nota = f"{len(r1)} predios con esa dirección en el R1"
            return r
        r.nota = nota or "sin coincidencias"
        return r
