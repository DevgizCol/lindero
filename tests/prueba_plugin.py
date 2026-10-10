# -*- coding: utf-8 -*-
"""
Prueba del plugin Colindante Elite ya parchado, sin abrir QGIS.

    python-qgis-ltr.bat tests\\prueba_plugin.py <carpeta_del_plugin> <carpeta_01.SHAPEFILE> <carpeta_temporal>

Copia las capas a la carpeta temporal, borra los colindantes de COORDENADAS, ejecuta AICore.run()
con todos los predios seleccionados y compara lo que escribió el plugin con lo que calculó el motor.
"""
import os
import shutil
import sys
import webbrowser

from qgis.core import QgsApplication, QgsProject, QgsVectorLayer

GDB = r"C:/Dani/Carto_Malambo/BASE_CATASTRAL_MALAMBO/ANEXOS_MALAMBO_2025013571/2. Información cartográfica/08433_MALAMBO.gdb/08433_MALAMBO.gdb"
CAMPOS = ["COLINDANTE", "LINDERO", "PUNTO_CARD", "DESCRIPCIO", "NIVEL_CONF"]


def main(carpeta_plugin, carpeta_shp, tmp):
    app = QgsApplication([], False)
    app.initQgis()
    os.makedirs(tmp, exist_ok=True)
    for f in os.listdir(carpeta_shp):
        shutil.copyfile(os.path.join(carpeta_shp, f), os.path.join(tmp, f))
    proj = QgsProject.instance()
    proj.setFileName(os.path.join(tmp, "prueba.qgz"))      # el reporte del plugin queda en la carpeta temporal
    capas = {
        "LEVANTAMIENTO_01": QgsVectorLayer(os.path.join(tmp, "LEVANTAMIENTO_01.shp"), "LEVANTAMIENTO_01", "ogr"),
        "COORDENADAS": QgsVectorLayer(os.path.join(tmp, "COORDENADAS.shp"), "COORDENADAS", "ogr"),
        "lc_terreno": QgsVectorLayer(GDB + "|layername=lc_terreno", "lc_terreno", "ogr"),
        "vias": QgsVectorLayer(GDB + "|layername=cc_nomeclatura_vial", "vias", "ogr"),
    }
    for n, c in capas.items():
        assert c.isValid(), n
        proj.addMapLayer(c)
    proj.setCrs(capas["lc_terreno"].crs())
    pts = capas["COORDENADAS"]
    esperado = {(f["NODO"], f["vertex_ind"]): tuple(str(f[c]) for c in CAMPOS) for f in pts.getFeatures()}
    pts.startEditing()
    for f in pts.getFeatures():
        for c in CAMPOS:
            pts.changeAttributeValue(f.id(), pts.fields().indexOf(c), None)
    pts.commitChanges()

    sys.path.insert(0, os.path.dirname(os.path.abspath(carpeta_plugin)))
    paquete = os.path.basename(os.path.abspath(carpeta_plugin))
    ai_core = __import__(paquete + ".ai_core", fromlist=["AICore"])
    webbrowser.open = lambda *a, **k: None                  # el plugin abre el reporte al terminar
    config = {"LAYERS": {"LEVANTAMIENTO": "LEVANTAMIENTO_01", "TERRENO": "lc_terreno", "VIAS": "vias", "SPECIAL": "",
                         "PUNTOS": "COORDENADAS"},
              "FIELDS": {"PROTAGONISTA": "CODIGO", "VECINO": "codigo", "NODO": "NODO", "VERTEX_INDEX": "vertex_ind"}}
    capas["LEVANTAMIENTO_01"].selectAll()
    fin = {}
    core = ai_core.AICore(config)
    core.finished.connect(lambda ok, msg: fin.update(ok=ok, msg=msg))
    core.run()
    print("plugin terminó:", fin.get("ok"), "|", (fin.get("msg") or "").replace("\n", " ")[:160])

    pts2 = QgsVectorLayer(os.path.join(tmp, "COORDENADAS.shp"), "c2", "ogr")
    obtenido = {(f["NODO"], f["vertex_ind"]): tuple(str(f[c]) for c in CAMPOS) for f in pts2.getFeatures()}
    iguales = sum(1 for k in esperado if obtenido.get(k) == esperado[k])
    col = sum(1 for k in esperado if obtenido.get(k, ("",))[0] == esperado[k][0])
    print(f"vértices: {len(esperado)} | mismo COLINDANTE que el motor: {col} | los 5 campos iguales: {iguales}")
    for k in sorted(esperado, key=str):
        if obtenido.get(k) != esperado[k]:
            print("  distinto", k, "plugin:", obtenido.get(k, ("?",))[:2], "motor:", esperado[k][:2])
            break
    sys.stdout.flush()
    os._exit(0)      # QGIS falla al cerrar si quedan capas vivas; la prueba ya terminó


if __name__ == "__main__":
    main(*sys.argv[1:4])
