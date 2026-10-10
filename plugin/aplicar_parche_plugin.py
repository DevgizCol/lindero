# -*- coding: utf-8 -*-
"""
Lleva el motor nuevo de colindantes al plugin Colindante Elite.

  python aplicar_parche_plugin.py "C:\\Dani\\Dev\\Colindante_Elite_Plugin\\Colindante_Elite_Plugin"

- copia motor/colindantes.py dentro del plugin como motor_colindantes.py
- cambia AICore.run() para que cada lado se resuelva con el motor nuevo
- quita el análisis anterior (contacto a 3 cm + franja de 6 m), que ya no se usa
Deja una copia ai_core.py.bak del archivo original.
"""
import os
import shutil
import sys

LF, CRLF = chr(10), chr(13) + chr(10)
AQUI = os.path.dirname(os.path.abspath(__file__))
MOTOR = os.path.join(os.path.dirname(AQUI), "motor", "colindantes.py")

IMPORTS = '''
from qgis.core import QgsRectangle

try:
    import shapely
    from .motor_colindantes import (Contexto, Lote, Parametros, analizar_lote, nivel_conf, VIA)
    MOTOR_OK = True
except Exception as _e:      # shapely viene con QGIS; si faltara, se avisa al ejecutar
    MOTOR_OK = False
    MOTOR_ERROR = str(_e)
'''

BLOQUE_PREVIO = '''            # Contexto del motor de colindantes: predios y vías alrededor de la selección, y TODOS los
            # lotes del levantamiento (el vecino de un lote suele ser otro lote levantado)
            if not MOTOR_OK:
                raise Exception("No se pudo cargar el motor de colindantes: " + MOTOR_ERROR)
            ctx = self._contexto_motor(layers, selection)

'''

BLOQUE_LOTE = '''                    # PUNTOS DEL PREDIO, en el orden de su índice de vértice
                    req = QgsFeatureRequest().setFilterExpression(f"\\"{self.config['FIELDS']['NODO']}\\" = '{nodo_val}'")
                    idx_v = l_pts.fields().indexOf(self.config['FIELDS']['VERTEX_INDEX'])
                    puntos_predio = [p for p in l_pts.getFeatures(req) if p.hasGeometry()]

                    def _orden(p):
                        try:
                            return int(float(p.attributes()[idx_v]))
                        except Exception:
                            return 0
                    puntos_predio.sort(key=_orden)

                    lote = next((l for l in ctx.lotes if l.nodo == nodo_val), None)
                    if lote is None:
                        self.log_error(geom.centroid().asPoint(), "LOTE_SIN_GEOMETRIA", 0, "Revisar el polígono del levantamiento")
                        failures += 1
                        continue
                    verts = [(p.geometry().asPoint().x(), p.geometry().asPoint().y()) for p in puntos_predio]
                    lejos = [v for v in verts if lote.geom.exterior.distance(shapely.Point(v)) > 0.20]
                    if len(verts) < 3 or lejos:
                        self.log_error(geom.centroid().asPoint(), "PUNTOS_NO_COINCIDEN", len(lejos),
                                       "La capa de coordenadas no tiene los vértices de este predio; vuelva a extraerlos")
                        failures += 1
                        continue

                    # MOTOR: mira hacia afuera de cada lado y decide con quién colinda
                    lados = analizar_lote(lote, ctx, vertices=verts)

                    poly_report = {
                        'id': code_main,
                        'nodo': nodo_val,
                        'area': geom.area(),
                        'perimeter': geom.length(),
                        'segments': [],
                        'segments_detailed': []
                    }
                    n_lados = len(lados)
                    for lado, pt_feat in zip(lados, puntos_predio):
                        if self.stop_requested: break
                        segments_count += 1
                        seg_geom = QgsGeometry.fromPolylineXY([QgsPointXY(*lado.p1), QgsPointXY(*lado.p2)])
                        self.visual_feedback.emit(seg_geom)
                        tramo_tag = f"V{lado.indice} - V{lado.indice % n_lados + 1}"
                        conf = nivel_conf(lado)
                        if lado.longitud < 0.02:
                            continue
                        if lado.colindante == "NO_ENCONTRADO" or lado.confianza == "BAJA":
                            mid = seg_geom.interpolate(lado.longitud / 2).asPoint()
                            self.log_error(mid, "REVISAR_COLINDANTE", lado.separacion,
                                           f"{lado.colindante} ({int(round(lado.fraccion * 100))}% del lado)")
                            failures += 1

                        attrs = {
                            'COLINDANTE': lado.colindante,
                            'LINDERO': lado.lindero,
                            'PUNTO_CARD': lado.cardinal,
                            'DESCRIPCIO': lado.descripcion[:254],
                            'NIVEL_CONF': conf
                        }
                        for f, v in attrs.items():
                            idx = l_pts.fields().indexOf(f)
                            if idx != -1: l_pts.changeAttributeValue(pt_feat.id(), idx, v)

                        poly_report['segments'].append(f"{lado.lindero}: {lado.descripcion}")
                        poly_report['segments_detailed'].append({
                            'idx': lado.indice,
                            'tramo': tramo_tag,
                            'orientacion': lado.lindero,
                            'cardinal': lado.cardinal,
                            'length': round(lado.longitud, 2),
                            'colindante': lado.colindante,
                            'confianza': conf,
                            'score': int(round(lado.fraccion * 100)),
                            'narracion': lado.descripcion
                        })

                        now_t = time.time()
                        elapsed_sec = now_t - start_time
                        speed_val = segments_count / max(0.2, elapsed_sec)
                        rem_segs = max(0, total_segments_expected - segments_count)
                        eta_sec = rem_segs / max(0.1, speed_val)
                        elapsed_str = f"{int(elapsed_sec//60):02d}:{int(elapsed_sec%60):02d}"
                        eta_str = f"{int(eta_sec//60):02d}:{int(eta_sec%60):02d}"
                        metodo = {"LOTE": "LOTE VECINO DEL LEVANTAMIENTO", "TERRENO": "PREDIO CATASTRAL VECINO",
                                  "MISMO": "RESTO DEL MISMO PREDIO", "VIA": "VÍA / ESPACIO PÚBLICO"}.get(lado.tipo, "SIN DATO")
                        step_data = {
                            'predio_id': code_main, 'nodo': nodo_val,
                            'step': lado.indice, 'total_steps': n_lados,
                            'predio_idx': i + 1, 'total_predios': total,
                            'tramo_label': f"V{lado.indice} ➔ V{lado.indice % n_lados + 1}",
                            'distancia': round(lado.longitud, 2), 'cardinal': lado.cardinal,
                            'colindante': lado.colindante, 'score': int(round(lado.fraccion * 100)),
                            'confianza': conf, 'metodo': metodo,
                            'geom': seg_geom, 'bbox': seg_geom.boundingBox(),
                            'elapsed_str': elapsed_str, 'eta_str': eta_str, 'speed': round(speed_val, 1)
                        }
                        self.step_inspected.emit(step_data)
                        self.stats_updated.emit({
                            'elapsed_seconds': int(elapsed_sec), 'elapsed_str': elapsed_str,
                            'eta_seconds': int(eta_sec), 'eta_str': eta_str, 'speed': round(speed_val, 1),
                            'predios_done': i + 1, 'total_predios': total,
                            'segments_done': segments_count, 'total_segments': total_segments_expected
                        })
                        if status_manager:
                            status_manager.update_step(step_data)
                            status_manager.update_status(
                                predios=i+1, total_predios=total, segments=segments_count, errors=failures,
                                progress=int((segments_count / max(1, total_segments_expected)) * 100),
                                task=f"V{lado.indice}➔V{lado.indice % n_lados + 1}: {lado.colindante}",
                                elapsed=int(elapsed_sec), eta=int(eta_sec), speed=round(speed_val, 1)
                            )
                        QApplication.processEvents()
                        if self.is_paused:
                            while self.is_paused and not self.stop_requested:
                                if self.step_trigger:
                                    self.step_trigger = False
                                    break
                                QApplication.processEvents()
                                time.sleep(0.04)
                        elif self.delay_ms > 0:
                            time.sleep(self.delay_ms / 1000.0)
                            QApplication.processEvents()

                    self.reports.append(poly_report)
'''

METODO_CONTEXTO = '''    def _contexto_motor(self, layers, selection, margen=80.0):
        """Predios, vías y lotes como geometrías shapely para el motor de colindantes."""
        def a_shapely(g):
            s = shapely.force_2d(shapely.from_wkb(bytes(g.asWkb())))
            return shapely.make_valid(s) if not s.is_valid else s

        caja = QgsRectangle()
        for f in selection:
            caja.combineExtentWith(f.geometry().boundingBox())
        caja.grow(margen)
        req = QgsFeatureRequest().setFilterRect(caja)

        campo_vec = self.config['FIELDS']['VECINO']
        terrenos = [(str(f.attribute(campo_vec)), a_shapely(f.geometry()))
                    for f in layers['TERRENO'].getFeatures(req) if f.hasGeometry()]

        vias = []
        if 'VIAS' in layers:
            campos = [f.name() for f in layers['VIAS'].fields()]
            campo_via = next((c for c in ['texto', 'TEXTO', 'nombre', 'NOMBRE', 'name', 'NAME', 'etiqueta',
                                          'ETIQUETA', 'via', 'VIA'] if c in campos), None)
            for f in layers['VIAS'].getFeatures(req):
                if f.hasGeometry():
                    vias.append((str(f.attribute(campo_via) or "VIA PUBLICA") if campo_via else "VIA PUBLICA",
                                 a_shapely(f.geometry())))

        campo_nodo, campo_cod = self.config['FIELDS']['NODO'], self.config['FIELDS']['PROTAGONISTA']
        campos_lev = [f.name() for f in layers['LEVANTAMIENTO'].fields()]
        campo_dir = next((c for c in ('NOMENCLATU', 'DIRECCION', 'direccion') if c in campos_lev), None)
        lotes = []
        for f in layers['LEVANTAMIENTO'].getFeatures():
            if not f.hasGeometry():
                continue
            g = a_shapely(f.geometry())
            if g.geom_type == 'MultiPolygon':
                g = max(g.geoms, key=lambda p: p.area)
            if g.geom_type != 'Polygon' or g.is_empty:
                continue
            lotes.append(Lote(str(f.attribute(campo_nodo)), str(f.attribute(campo_cod) or ""), g, "",
                              str(f.attribute(campo_dir) or "") if campo_dir else ""))
        return Contexto(terrenos=terrenos, vias=vias, lotes=lotes)

'''


def main(carpeta):
    ruta = os.path.join(carpeta, "ai_core.py")
    with open(ruta, encoding="utf-8", newline="") as f:
        s = f.read()
    crlf = CRLF in s          # se respetan los saltos de línea que traiga el archivo
    s = s.replace(CRLF, LF)
    if "motor_colindantes" in s:
        print("El plugin ya tiene el motor nuevo; solo se actualiza motor_colindantes.py")
    else:
        shutil.copyfile(ruta, ruta + ".bak")
        # 1. imports
        ancla = "class NarrativeEngine:"
        assert ancla in s
        s = s.replace(ancla, IMPORTS.lstrip(LF) + LF + ancla, 1)
        # 2. contexto antes de empezar a editar la capa de puntos
        ancla = "            l_pts.startEditing()" + LF
        assert ancla in s
        s = s.replace(ancla, BLOQUE_PREVIO + ancla, 1)
        # 3. análisis por lote
        ini = s.index("                    # SELECCIÓN DE PUNTOS")
        fin_txt = "                    self.reports.append(poly_report)" + LF
        fin = s.index(fin_txt, ini) + len(fin_txt)
        s = s[:ini] + BLOQUE_LOTE + s[fin:]
        # 4. se retira el análisis anterior y se agrega el armado del contexto
        ini = s.index("    def create_probe(self, p1, p2, parent, depth=6.0):")
        fin = s.index("    def calculate_tramos(self, layer):")
        s = s[:ini] + METODO_CONTEXTO + s[fin:]
        with open(ruta, "w", encoding="utf-8", newline="") as f:
            f.write(s.replace(LF, CRLF) if crlf else s)
    shutil.copyfile(MOTOR, os.path.join(carpeta, "motor_colindantes.py"))
    meta = os.path.join(carpeta, "metadata.txt")
    with open(meta, encoding="utf-8", newline="") as f:
        m = f.read()
    if "version=3.0.0" in m:
        with open(meta, "w", encoding="utf-8", newline="") as f:
            f.write(m.replace("version=3.0.0", "version=3.1.0"))
    print("Plugin actualizado en", carpeta)


if __name__ == "__main__":
    main(sys.argv[1])
