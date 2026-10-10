# -*- coding: utf-8 -*-
"""
Base catastral del municipio: predios, ejes viales, placas domiciliarias y manzanas.

Se lee de la base empacada (base/<municipio>/base.gpkg, portátil) si existe; si no, de la
geodatabase original indicada en la configuración.
"""
from __future__ import annotations

import gzip
import json
import os
import warnings
from dataclasses import dataclass
from functools import lru_cache

import geopandas as gpd

from .colindantes import Contexto

warnings.filterwarnings("ignore", message=".*Measured.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyogrio")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTAS = ("gdb", "r1", "proyecto_qgis", "plantilla", "firma", "base_empacada")


def leer_config(municipio_o_ruta="malambo") -> dict:
    ruta = municipio_o_ruta
    if not os.path.isfile(ruta):
        ruta = os.path.join(RAIZ, "config", f"{municipio_o_ruta.lower()}.json")
    with open(ruta, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["_ruta"] = ruta
    for k in RUTAS:                       # las rutas relativas parten de la carpeta del proyecto
        if cfg.get(k) and not os.path.isabs(cfg[k]):
            cfg[k] = os.path.join(RAIZ, cfg[k])
    cfg.setdefault("base_empacada", os.path.join(RAIZ, "base", cfg["municipio"].lower()))
    return cfg


@dataclass
class Base:
    cfg: dict
    terrenos: gpd.GeoDataFrame   # codigo, geometry
    vias: gpd.GeoDataFrame       # texto, tipo_via, numero_via, geometry
    placas: gpd.GeoDataFrame     # texto, terreno_codigo, geometry
    manzanas: gpd.GeoDataFrame   # codigo, geometry
    origen: str = ""

    @property
    def crs(self):
        return self.terrenos.crs

    def contexto(self, lotes=()) -> Contexto:
        return Contexto(
            terrenos=zip(self.terrenos["codigo"], self.terrenos.geometry),
            vias=zip(self.vias["texto"], self.vias.geometry),
            manzanas=self.manzanas.geometry,
            lotes=lotes,
        )

    def direcciones_r1(self):
        """Dirección normalizada -> códigos, de la base empacada (None si no está empacada)."""
        ruta = os.path.join(self.cfg["base_empacada"], "r1_direcciones.json.gz")
        if self.origen == "empacada" and os.path.isfile(ruta):
            with gzip.open(ruta, "rt", encoding="utf-8") as f:
                return json.load(f)
        return None


def _leer(origen, capa, columnas):
    g = gpd.read_file(origen, layer=capa, columns=columnas, engine="pyogrio")
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    g["geometry"] = g.geometry.force_2d()
    return g.reset_index(drop=True)


@lru_cache(maxsize=4)
def _cargar(ruta_cfg) -> Base:
    cfg = leer_config(ruta_cfg)
    gpkg = os.path.join(cfg["base_empacada"], "base.gpkg")
    if os.path.isfile(gpkg):
        return Base(cfg, _leer(gpkg, "terreno", ["codigo"]), _leer(gpkg, "vias", ["texto", "tipo_via", "numero_via"]),
                    _leer(gpkg, "placas", ["texto", "terreno_codigo"]), _leer(gpkg, "manzanas", ["codigo"]), "empacada")
    gdb, capas = cfg["gdb"], cfg["capas"]
    terr = _leer(gdb, capas["terreno"], ["codigo"])
    terr["geometry"] = terr.geometry.make_valid()
    manz = _leer(gdb, capas["manzanas"], ["codigo"])
    manz["geometry"] = manz.geometry.make_valid()
    return Base(cfg, terr, _leer(gdb, capas["vias"], ["texto", "tipo_via", "numero_via"]),
                _leer(gdb, capas["placas"], ["texto", "terreno_codigo"]), manz, "geodatabase")


def cargar_base(municipio_o_ruta="malambo") -> Base:
    return _cargar(leer_config(municipio_o_ruta)["_ruta"])
