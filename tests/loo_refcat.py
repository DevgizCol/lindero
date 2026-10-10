# -*- coding: utf-8 -*-
"""
Prueba objetiva de la interpolación de direcciones: a una muestra de placas del catastro
se les oculta la placa y se le pide al geocodificador que encuentre el predio solo con
la dirección. La respuesta correcta es el predio que el catastro asigna a esa placa.

Uso: python tests/loo_refcat.py [n]
"""
import collections
import os
import random
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from motor.base import cargar_base
from motor.refcat import Geocodificador


def main(n=600, semilla=11):
    random.seed(semilla)
    geo = Geocodificador(cargar_base("malambo"))
    geo.r1.clear()   # solo se mide la interpolación
    claves = [k for k, v in geo.placas.items() if len({c for _, c in v}) == 1]
    res = collections.Counter()
    porconf = collections.defaultdict(collections.Counter)
    for k in random.sample(claves, n):
        via, cruce, num = k
        cod = geo.placas[k][0][1]
        r = geo.buscar(f"{via[0]} {via[2:]} {cruce} {num}", _excluir=cod)
        cands = [c for c, _ in r.candidatos]
        if r.codigo == cod:
            est = "top1"
        elif cod in cands[:3]:
            est = "top3"
        elif cod in cands:
            est = "candidatos"
        else:
            est = "fallo" if r.codigo else "sin_resultado"
        res[est] += 1
        porconf[r.confianza][est] += 1
    print(f"{n} direcciones con la placa oculta")
    print(f"  acierta el predio: {res['top1']} ({100 * res['top1'] / n:.0f}%)   "
          f"entre los 3 primeros candidatos: {res['top1'] + res['top3']} ({100 * (res['top1'] + res['top3']) / n:.0f}%)")
    for c, v in porconf.items():
        t = sum(v.values())
        print(f"  {c:14} {t:4}  acierto {100 * v['top1'] / t:.0f}%   {dict(v)}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 600)
