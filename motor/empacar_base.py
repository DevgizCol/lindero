# -*- coding: utf-8 -*-
"""
Empaca la base catastral de un municipio en una carpeta portátil, para que el motor no dependa
de las rutas de un equipo ni de la geodatabase original:

    python -m motor.empacar_base malambo

Deja en base/<municipio>/:
  base.gpkg            predios (código), ejes viales, placas domiciliarias y manzanas
  r1_direcciones.json.gz   dirección normalizada -> códigos prediales

Del R1 solo se conserva la dirección y el código: nombres y cédulas NO salen del equipo.
"""
import gzip
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

from .base import RAIZ, _leer, leer_config
from .refcat import norm_dir_r1


def empacar(municipio="malambo"):
    cfg = leer_config(municipio)
    destino = os.path.join(RAIZ, "base", cfg["municipio"].lower())
    os.makedirs(destino, exist_ok=True)
    gpkg = os.path.join(destino, "base.gpkg")
    if os.path.exists(gpkg):
        os.remove(gpkg)
    capas = cfg["capas"]
    columnas = {"terreno": ["codigo"], "vias": ["texto", "tipo_via", "numero_via"],
                "placas": ["texto", "terreno_codigo"], "manzanas": ["codigo"]}
    resumen = {}
    for nombre, cols in columnas.items():
        g = _leer(cfg["gdb"], capas[nombre], cols)
        if nombre in ("terreno", "manzanas"):
            g["geometry"] = g.geometry.make_valid()
        g.to_file(gpkg, layer=nombre, driver="GPKG", engine="pyogrio")
        resumen[nombre] = len(g)
    dirs = {}
    if cfg.get("r1") and os.path.isfile(cfg["r1"]):
        with open(cfg["r1"], encoding="latin-1") as f:
            for linea in f:
                k = norm_dir_r1(linea[151:251])
                if k:
                    dirs.setdefault(k, set()).add(linea[:30])
    with gzip.open(os.path.join(destino, "r1_direcciones.json.gz"), "wt", encoding="utf-8") as f:
        json.dump({k: sorted(v) for k, v in dirs.items()}, f)
    resumen["direcciones_r1"] = len(dirs)
    resumen["carpeta"] = destino
    resumen["MB"] = round(sum(os.path.getsize(os.path.join(destino, a)) for a in os.listdir(destino)) / 1e6, 1)
    return resumen


if __name__ == "__main__":
    print(json.dumps(empacar(sys.argv[1] if len(sys.argv) > 1 else "malambo"), ensure_ascii=False, indent=1))
