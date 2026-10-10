# -*- coding: utf-8 -*-
"""Mide el geocodificador contra las referencias catastrales que ya se entregaron resueltas a mano."""
import os, sys, warnings, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")
import openpyxl
from motor.base import cargar_base
from motor.refcat import Geocodificador, parsear

CASOS = [(r"C:/Dani/Carto_Malambo/REF_CATASTRAL/ENTREGA/PARA SOL. REF CAT ARLEY.xlsx", 4, 6),
         (r"C:/Dani/Carto_Malambo/REF_CATASTRAL/ENTREGA/BARRIO LA POPA.xlsx", 2, 5)]


def main(detalle=True):
    geo = Geocodificador(cargar_base("malambo"))
    tot = collections.Counter(); filas = []
    for ruta, ca, cr in CASOS:
        ws = openpyxl.load_workbook(ruta, read_only=True, data_only=True).worksheets[0]
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0 or not row[ca]:
                continue
            ref = str(row[cr] or "").strip()
            if not ref.startswith("08433"):
                continue
            r = geo.buscar(row[ca])
            en_base = ref in geo.con_geom
            if not r.codigo:
                est = "SIN_RESULTADO"
            elif r.codigo == ref:
                est = "OK"
            elif ref in [c for c, _ in r.candidatos]:
                est = "EN_CANDIDATOS"
            else:
                est = "DISTINTO"
            tot[(r.confianza, est)] += 1
            filas.append((est, r.confianza, r.metodo, str(row[ca]).strip(), ref[13:21], r.codigo[13:21], en_base, r.nota))
    n = len(filas)
    print(f"{n} direcciones con referencia conocida")
    for conf in ("ALTA", "MEDIA", "BAJA", "SIN_RESULTADO"):
        sub = {e: c for (cf, e), c in tot.items() if cf == conf}
        if sub:
            print(f"  {conf:14} {sum(sub.values()):3}  ->  {sub}")
    ok = sum(c for (cf, e), c in tot.items() if e == "OK")
    print(f"  aciertos totales: {ok}/{n} ({100*ok/n:.0f}%)")
    if detalle:
        for f in sorted(filas):
            if f[0] != "OK":
                print("   ", f)
    return filas


if __name__ == "__main__":
    main()
