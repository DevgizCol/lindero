# -*- coding: utf-8 -*-
"""
Recorrido completo de la plataforma contra el servidor local (http://127.0.0.1:5080):
subir archivos -> vista previa -> intento de descarga sin pagar -> confirmar pago en /admin ->
generar -> aprobar la revisión -> descargar el ZIP.

    python tests/prueba_web.py
"""
import io
import os
import re
import sys
import threading
import time
import zipfile

import requests

BASE = os.environ.get("PLANOS_URL", "http://127.0.0.1:5080")
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEL = r"C:/Dani/Carto_Malambo/REC_Tesoro/LEVANTAMIENTO EL TESORO MB OK OK.xlsx"
DXF = os.path.join(RAIZ, "tests", "datos", "TESORO_reconstruido.dxf")


def clave_admin():
    with open(os.path.join(RAIZ, "web", ".env.local"), encoding="utf-8") as f:
        for l in f:
            if l.startswith("PLANOS_ADMIN_CLAVE="):
                return l.split("=", 1)[1].strip()


def csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def esperar(s, url, estados, tope=600):
    # como hace la página del pedido: pide procesar lo pendiente (en modo cola no hace nada) y consulta el estado
    def lanzar():
        try:
            s.post(url + "/procesar", data={"csrf": csrf(s.get(BASE + "/").text)}, timeout=tope)
        except Exception:
            pass
    threading.Thread(target=lanzar, daemon=True).start()
    t0 = time.time()
    while time.time() - t0 < tope:
        j = s.get(url + "/estado.json").json()
        if j["titulo"] in estados:
            return j["titulo"], j
        time.sleep(4)
    raise TimeoutError(j["titulo"])


def main():
    ok = lambda cond, txt: print(("  OK   " if cond else "  FALLA ") + txt) or (cond or sys.exit(1))
    c = requests.Session()
    h = c.get(BASE + "/").text
    ok("vista previa gratis" in h and 'name="csrf"' in h, "portada")
    ok(all(c.get(BASE + u).status_code == 200 for u in re.findall(r'(?:href|src)="(/static/[^"]+)"', h)), "hojas de estilo y scripts")
    r = c.post(BASE + "/pedidos", data={"csrf": "malo", "municipio": "malambo"}, allow_redirects=False)
    ok(r.status_code == 400, "se rechaza un formulario sin el token correcto")
    with open(EXCEL, "rb") as fe, open(DXF, "rb") as fd:
        r = c.post(BASE + "/pedidos", allow_redirects=False,
                   data={"csrf": csrf(h), "municipio": "malambo", "correo": "prueba@example.com",
                         "firmante": "Top. Persona De Prueba\nT.P. 00-0000 CPNT", "declaracion": "1"},
                   files={"excel": ("clientes & cosas.xlsx", fe), "dxf": ("../../plano raro.dxf", fd)})
    ok(r.status_code == 303, "pedido creado")
    url = BASE + r.headers["Location"] if r.headers["Location"].startswith("/") else r.headers["Location"]
    pid = url.rsplit("/", 1)[1]
    estado, j = esperar(c, url, {"Vista previa lista", "Hay que corregir los archivos", "Error interno"})
    ok(estado == "Vista previa lista", f"vista previa ({estado})")
    ok(j["predios"] == 22 and j["precio"] > 0, "22 predios reconocidos y precio calculado")
    imgs = re.findall(r'<img src="([^"]+)"', c.get(url).text)
    ok(len(imgs) == 3 and all(c.get(BASE + i).headers["Content-Type"].startswith("image/") for i in imgs), "3 imágenes de vista previa")
    ok(c.get(BASE + "/no-existe").status_code == 404 and "no existe" in c.get(BASE + "/no-existe").text, "página 404 propia")
    ok(c.get(url + "/descargar").status_code == 403, "sin pagar no hay descarga")
    ok(c.get(url + "/previa/..%2F..%2Fpedido.json").status_code == 404, "no se pueden pedir otros archivos del pedido")
    ok(requests.get(BASE + "/admin/pedidos/" + pid + "/archivo/entrega.zip").status_code == 403, "archivos de administración protegidos")
    ok(requests.post(BASE + "/admin/pedidos/" + pid + "/pagado").status_code == 403, "nadie externo puede marcar un pago")

    a = requests.Session()
    h2 = a.get(BASE + "/admin/entrar").text
    r = a.post(BASE + "/admin/entrar", data={"csrf": csrf(h2), "clave": "incorrecta"})
    ok("Clave incorrecta" in r.text, "clave de administración incorrecta rechazada")
    r = a.post(BASE + "/admin/entrar", data={"csrf": csrf(r.text), "clave": clave_admin()})
    ok("Pedidos" in r.text and pid[:8] in r.text, "panel de administración")
    r = a.post(f"{BASE}/admin/pedidos/{pid}/pagado", data={"csrf": csrf(r.text), "referencia": "PRUEBA-1"})
    ok(r.status_code == 200, "pago confirmado a mano")
    estado, h = esperar(c, url, {"Entrega lista", "En revisión técnica", "Error interno"})
    ok(estado in ("Entrega lista", "En revisión técnica"), f"entrega generada ({estado})")
    if estado == "En revisión técnica":
        ok(c.get(url + "/descargar").status_code == 403, "en revisión todavía no se descarga")
        r = a.get(BASE + "/admin")
        r = a.post(f"{BASE}/admin/pedidos/{pid}/aprobar", data={"csrf": csrf(r.text)})
        estado, h = esperar(c, url, {"Entrega lista"})
    z = c.get(url + "/descargar")
    ok(z.status_code == 200, "descarga del ZIP")
    nombres = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    ok(len(nombres) == 22 and "T1.pdf" in nombres, f"ZIP con {len(nombres)} PDF")
    print("Pedido de prueba:", url)


if __name__ == "__main__":
    main()
