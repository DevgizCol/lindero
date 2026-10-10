# -*- coding: utf-8 -*-
"""
Salida cartográfica: atlas de QGIS sin abrir QGIS (un PDF por NODO).

Se ejecuta con el Python de QGIS:
    python-qgis-ltr.bat atlas_qgis.py trabajo.json

trabajo.json:
{
  "proyecto": ".../BASE_CATASTRAL_MALAMBO.qgz",
  "plantilla": ".../SALIDA_CARTOGRAFICA.qpt",        (opcional; si falta se usa "layout" del proyecto)
  "layout": "SALIDAS_GRAFICAS",
  "capas": {"LEVANTAMIENTO_01": "...shp", "COTAS": "...shp", "COORDENADAS": "...shp"},
  "capas_mapa": ["COORDENADAS", "COTAS", "LEVANTAMIENTO_01", ...],   (opcional: capas del mapa, de arriba a abajo)
  "salida": "carpeta de los PDF",
  "fecha": "10/10/2026",
  "firma": "firma.png" | "" | null,     (null = dejar la de la plantilla; "" = sin firma)
  "firmante": "Top. Nombre\\nT.P. 00-0000" | null,
  "nodos": ["T1", "T2"] | null,          (null = todos)
  "vista_previa": false,                 (true = imagen de baja resolución con marca de agua)
  "resultado": "resultado.json"
}
"""
import json
import os
import re
import sys
import traceback

from qgis.core import (Qgis, QgsApplication, QgsLayoutExporter, QgsLayoutItemAttributeTable, QgsLayoutItemHtml,
                       QgsLayoutItemLabel, QgsLayoutItemMap, QgsLayoutItemPicture, QgsLayoutPoint, QgsLayoutSize,
                       QgsPrintLayout, QgsProject, QgsReadWriteContext, QgsUnitTypes)
from qgis.PyQt.QtCore import QLocale, Qt
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtXml import QDomDocument


ESCALAS = [100, 125, 150, 200, 250, 300, 400, 500, 750, 1000, 1500, 2000, 2500, 5000, 10000]


def _layout(proyecto, trabajo):
    plantilla = trabajo.get("plantilla")
    if plantilla and os.path.isfile(plantilla):
        doc = QDomDocument()
        with open(plantilla, encoding="utf-8") as f:
            doc.setContent(f.read())
        lay = QgsPrintLayout(proyecto)
        lay.initializeDefaults()
        ctx = QgsReadWriteContext()
        ctx.setPathResolver(proyecto.pathResolver())   # rutas relativas de la plantilla (./firma.png)
        _, ok = lay.loadFromTemplate(doc, ctx)
        if not ok:
            raise RuntimeError("No se pudo cargar la plantilla " + plantilla)
        return lay
    lay = proyecto.layoutManager().layoutByName(trabajo.get("layout", "SALIDAS_GRAFICAS"))
    if lay is None:
        raise RuntimeError("El proyecto no tiene la composición " + str(trabajo.get("layout")))
    return lay


def _personalizar(lay, trabajo, proyecto):
    firma, firmante, fecha = trabajo.get("firma"), trabajo.get("firmante"), trabajo.get("fecha")
    visibles = []
    for nombre in trabajo.get("capas_mapa") or []:
        visibles += proyecto.mapLayersByName(nombre)
    for item in lay.items():
        if isinstance(item, QgsLayoutItemMap):
            if visibles:
                item.setLayers(visibles)          # de arriba hacia abajo
                item.setKeepLayerSet(True)
            if item.atlasDriven():
                # la plantilla trae escala fija: se conserva para los predios que caben y los grandes
                # pasan a la siguiente escala redonda (antes se cambiaba a mano hoja por hoja)
                base = item.scale()
                escalas = [base] + [e for e in trabajo.get("escalas", ESCALAS) if e > base * 1.05]
                lay.renderContext().setPredefinedScales(escalas)
                item.setAtlasScalingMode(QgsLayoutItemMap.Predefined)
            continue
        if isinstance(item, QgsLayoutItemPicture) and firma is not None:
            ruta = item.picturePath() or ""
            if "firma" in os.path.basename(ruta).lower():
                item.setPicturePath(firma)
                item.setVisibility(bool(firma))
        elif isinstance(item, QgsLayoutItemLabel) and firmante is not None:
            if re.match(r"\s*(Top\.|Ing\.|Arq\.|T\.P\.)", item.text()) or "T.P." in item.text():
                item.setText(firmante)
                fmt = item.textFormat()               # el nombre y la matrícula salen tal como se escribieron
                fmt.setCapitalization(Qgis.Capitalization.MixedCase)
                item.setTextFormat(fmt)
    for mf in lay.multiFrames():
        if isinstance(mf, QgsLayoutItemHtml) and fecha and re.fullmatch(r"\s*\d{1,2}/\d{1,2}/\d{4}\s*", mf.html() or ""):
            mf.setHtml(fecha)
            mf.loadHtml()
        elif isinstance(mf, QgsLayoutItemAttributeTable):
            # el cuadro venía ordenado por el texto del tramo ("1 AL 2", "10 AL 1", "2 AL 3"...)
            mf.setDisplayOnlyVisibleFeatures(False)   # ningún vértice se omite por quedar fuera del mapa
            columnas = mf.columns()
            for c in columnas:                        # "16 m" -> "16.00 m"
                if re.fullmatch(r'\s*"DISTANCIA"\s*\|\|\s*\' m\'\s*', c.attribute() or ""):
                    c.setAttribute('format_number("DISTANCIA", 2) || \' m\'')
            mf.setColumns(columnas)
            cols = mf.sortColumns()
            if cols:
                for c in cols:
                    c.setAttribute('"vertex_ind"')
                mf.setSortColumns(cols)
                mf.refreshAttributes()


def _marca_agua(lay):
    pagina = lay.pageCollection().page(0)
    w, h = pagina.pageSize().width(), pagina.pageSize().height()
    for fx, fy in ((0.5, 0.33), (0.5, 0.72)):
        et = QgsLayoutItemLabel(lay)
        et.setText("VISTA PREVIA - SIN VALIDEZ")
        f = QFont("Arial")
        f.setPointSizeF(max(40.0, w * 0.2))
        f.setBold(True)
        et.setFont(f)
        et.setFontColor(QColor(200, 0, 0, 70))
        et.setHAlign(Qt.AlignHCenter)
        et.setVAlign(Qt.AlignVCenter)
        ancho, alto = w * 0.95, h * 0.2
        et.attemptResize(QgsLayoutSize(ancho, alto, QgsUnitTypes.LayoutMillimeters))
        et.attemptMove(QgsLayoutPoint(w * fx - ancho / 2, h * fy - alto / 2, QgsUnitTypes.LayoutMillimeters))
        et.setItemRotation(-18)
        et.setZValue(10000)
        lay.addLayoutItem(et)


def exportar(trabajo):
    proyecto = QgsProject.instance()
    if not proyecto.read(trabajo["proyecto"]):
        raise RuntimeError("No se pudo abrir el proyecto " + trabajo["proyecto"])
    for nombre, ruta in trabajo["capas"].items():
        capas = proyecto.mapLayersByName(nombre)
        if not capas:
            raise RuntimeError(f"El proyecto no tiene la capa {nombre}")
        capas[0].setDataSource(ruta, nombre, "ogr")
        if not capas[0].isValid():
            raise RuntimeError(f"No se pudo leer {ruta}")
    cobertura = proyecto.mapLayersByName("LEVANTAMIENTO_01")[0]
    lay = _layout(proyecto, trabajo)
    _personalizar(lay, trabajo, proyecto)
    previa = bool(trabajo.get("vista_previa"))
    if previa:
        _marca_agua(lay)
    atlas = lay.atlas()
    atlas.setCoverageLayer(cobertura)
    atlas.setEnabled(True)
    atlas.setHideCoverage(False)
    atlas.setFilenameExpression('"NODO"')
    nodos = trabajo.get("nodos")
    if nodos:
        lista = ",".join("'" + str(n).replace("'", "''") + "'" for n in nodos)
        atlas.setFilterFeatures(True)
        atlas.setFilterExpression(f'"NODO" IN ({lista})')
    else:
        atlas.setFilterFeatures(False)
    salida = trabajo["salida"]
    os.makedirs(salida, exist_ok=True)
    tablas = [(mf, mf.contentTextFormat().size(), mf.headerTextFormat().size())
              for mf in lay.multiFrames() if isinstance(mf, QgsLayoutItemAttributeTable)]
    exp = QgsLayoutExporter(lay)
    if previa:
        conf = QgsLayoutExporter.ImageExportSettings()
        conf.dpi = float(trabajo.get("dpi_previa", 45))
    else:
        conf = QgsLayoutExporter.PdfExportSettings()
        if trabajo.get("dpi"):
            conf.dpi = float(trabajo["dpi"])
    hechos = []
    atlas.beginRender()
    ok = atlas.first()
    while ok:
        nodo = str(lay.reportContext().feature()["NODO"])
        for mf, t_cont, t_enc in tablas:
            _ajustar_tabla(mf, t_cont, t_enc)
        destino = os.path.join(salida, re.sub(r'[\/:*?"<>|]', "_", nodo) + (".jpg" if previa else ".pdf"))
        r = exp.exportToImage(destino, conf) if previa else exp.exportToPdf(destino, conf)
        if r != QgsLayoutExporter.Success:
            raise RuntimeError(f"Fallo al exportar {nodo} (código {r})")
        hechos.append(destino)
        ok = atlas.next()
    atlas.endRender()
    return hechos


def _ajustar_tabla(mf, t_cont, t_enc):
    """Reduce la letra del cuadro de coordenadas lo justo para que quepan todos los vértices del predio."""
    alto_marco = sum(f.rect().height() for f in mf.frames())
    for escala in (1.0, 0.94, 0.88, 0.82, 0.76, 0.7, 0.64, 0.58, 0.52, 0.46, 0.4):
        for obtener, fijar, base in ((mf.contentTextFormat, mf.setContentTextFormat, t_cont),
                                     (mf.headerTextFormat, mf.setHeaderTextFormat, t_enc)):
            fmt = obtener()
            fmt.setSize(base * escala)
            fijar(fmt)
        mf.refreshAttributes()
        mf.recalculateFrameSizes()
        # totalSize() crece por marcos completos: si supera el alto del marco, hay filas que no caben
        if mf.totalSize().height() <= alto_marco + 0.01:
            break


def main(ruta_trabajo):
    with open(ruta_trabajo, encoding="utf-8") as f:
        trabajo = json.load(f)
    app = QgsApplication([], False)
    app.initQgis()
    loc = QLocale(QLocale.English, QLocale.UnitedStates)   # punto decimal, como en las entregas
    loc.setNumberOptions(QLocale.OmitGroupSeparator)   # coordenadas sin separador de miles
    QLocale.setDefault(loc)
    res = {"ok": False}
    try:
        res = {"ok": True, "archivos": exportar(trabajo)}
    except Exception as e:
        res = {"ok": False, "error": str(e), "traza": traceback.format_exc()}
    with open(trabajo.get("resultado") or (os.path.splitext(ruta_trabajo)[0] + "_resultado.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    QgsProject.instance().clear()
    app.exitQgis()
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
