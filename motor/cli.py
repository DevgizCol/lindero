# -*- coding: utf-8 -*-
"""
Línea de comandos del motor.

  planos   Excel + plano -> capas, colindantes, PDF por predio y ZIP
  refcat   Excel -> referencia catastral de cada dirección (+ KML de los dudosos)

Ejemplos (con planos.bat, que usa el Python de QGIS):
  planos.bat planos --excel "LEVANTAMIENTO.xlsx" --dxf "PLANO.dxf" --salida "C:\\trabajos\\tesoro" --nombre BR_TESORO
  planos.bat refcat --excel "TODO MB PARA REFERENCIA CATASTRAL.xlsx" --salida "C:\\trabajos\\ref"
"""
import argparse
import json
import sys
import warnings

warnings.filterwarnings("ignore")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="motor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("planos", help="flujo completo")
    p.add_argument("--excel", nargs="+", required=True)
    p.add_argument("--dxf")
    p.add_argument("--puntos", help="cartera de campo (txt/csv: id, norte, este, cota, código)")
    p.add_argument("--poligonos", help="capa de polígonos con campo NODO (en vez del DXF)")
    p.add_argument("--crs", help="CRS de la capa de polígonos si no lo trae (p. ej. EPSG:3116)")
    p.add_argument("--salida", required=True)
    p.add_argument("--nombre", default="ENTREGA")
    p.add_argument("--municipio", default="malambo")
    p.add_argument("--firma", help="imagen de la firma (png/jpg) que reemplaza la de la plantilla")
    p.add_argument("--sin-firma", action="store_true", help="deja en blanco el espacio de la firma")
    p.add_argument("--firmante", help='texto bajo "Firma Autorizada", p. ej. "Top. Nombre\\nT.P. 00-0000"')
    p.add_argument("--fecha", help="dd/mm/aaaa (por defecto hoy)")
    p.add_argument("--previa", action="store_true", help="solo imágenes de baja resolución con marca de agua")
    p.add_argument("--sin-atlas", action="store_true")
    j = sub.add_parser("trabajo", help="flujo completo descrito en un archivo JSON (lo usa la plataforma web)")
    j.add_argument("json")
    r = sub.add_parser("refcat", help="referencia catastral masiva")
    r.add_argument("--excel", nargs="+", required=True)
    r.add_argument("--salida")
    r.add_argument("--municipio", default="malambo")
    a = ap.parse_args(argv)
    if a.cmd == "refcat":
        from .refcat_lote import procesar
        for x in a.excel:
            res = procesar(x, a.salida, a.municipio)
            print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    from .pipeline import Trabajo, ejecutar
    if a.cmd == "trabajo":
        # los textos del cliente (firmante, nombres de archivo) viajan en el JSON, nunca por la línea de comandos
        with open(a.json, encoding="utf-8") as f:
            ejecutar(Trabajo(**json.load(f)))
        return 0
    t = Trabajo(carpeta=a.salida, excel=a.excel, dxf=a.dxf, puntos=a.puntos, capa_poligonos=a.poligonos,
                crs_poligonos=a.crs, municipio=a.municipio, firma="" if a.sin_firma else a.firma,
                firmante=a.firmante.replace("\\n", "\n") if a.firmante else None, fecha=a.fecha, nombre=a.nombre,
                vista_previa=a.previa, hacer_atlas=not a.sin_atlas)
    inf = ejecutar(t)
    for av in inf["avisos"]:
        print("AVISO:", av)
    print("Requiere revisión:" if inf["requiere_revision"] else "Sin pendientes.", ", ".join(map(str, inf.get("por_revisar", []))))
    print("Archivos:", json.dumps({k: v for k, v in inf["archivos"].items() if k not in ("pdf", "vista_previa")},
                                  ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
