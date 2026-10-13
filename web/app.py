# -*- coding: utf-8 -*-
"""
Plataforma de autoservicio con pago anticipado.

Flujo del cliente:
  1. sube Excel + plano (DXF) y los datos de quien firma
  2. el motor valida los archivos y arma una vista previa gratis con marca de agua
  3. paga (Wompi, o pago manual que confirma el administrador)
  4. se genera la entrega; si el motor marcó algo dudoso pasa a revisión antes de liberarse
  5. descarga el ZIP

Arranque local:  web\\iniciar_web.bat   (http://127.0.0.1:5080)
Variables de entorno:
  PLANOS_ADMIN_CLAVE   clave del panel /admin (sin ella el panel queda deshabilitado)
  PLANOS_SECRETO       secreto de las sesiones (si falta se genera y se guarda en datos/)
  PLANOS_DATOS         carpeta de pedidos (por defecto web/datos)
  WOMPI_LLAVE_PUBLICA, WOMPI_SECRETO_INTEGRIDAD, WOMPI_SECRETO_EVENTOS
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse

from flask import Flask, abort, redirect, render_template, request, send_file, session, url_for

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DATOS = os.environ.get("PLANOS_DATOS") or os.path.join(AQUI, "datos")
PEDIDOS = os.path.join(DATOS, "pedidos")
os.makedirs(PEDIDOS, exist_ok=True)

with open(os.path.join(AQUI, "config.json"), encoding="utf-8") as _f:
    CFG = json.load(_f)

# web/.env.local (CLAVE=valor por línea) completa las variables de entorno en el equipo de desarrollo
_env_local = os.path.join(AQUI, ".env.local")
if os.path.isfile(_env_local):
    with open(_env_local, encoding="utf-8") as _f:
        for _linea in _f:
            if "=" in _linea and not _linea.lstrip().startswith("#"):
                _k, _v = _linea.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

EXT = {"excel": {".xlsx", ".xlsm"}, "dxf": {".dxf"}, "puntos": {".txt", ".csv"}, "firma": {".png", ".jpg", ".jpeg"}}
RE_ID = re.compile(r"^[A-Za-z0-9_-]{16,40}$")
ESTADOS = {
    "RECIBIDO": "Archivos recibidos", "PROCESANDO_PREVIA": "Validando archivos y armando la vista previa",
    "ERROR_ENTRADA": "Hay que corregir los archivos", "PREVIA_LISTA": "Vista previa lista",
    "PAGADO": "Pago confirmado", "GENERANDO": "Generando los planos", "EN_REVISION": "En revisión técnica",
    "LISTO": "Entrega lista", "ERROR": "Error interno",
}


def _secreto():
    s = os.environ.get("PLANOS_SECRETO")
    if s:
        return s
    ruta = os.path.join(DATOS, "secreto.key")
    if not os.path.isfile(ruta):
        with open(ruta, "w") as f:
            f.write(secrets.token_hex(32))
    with open(ruta) as f:
        return f.read().strip()


from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = _secreto()
app.config.update(
    MAX_CONTENT_LENGTH=int(CFG.get("max_mb_pedido", CFG["max_mb_por_archivo"] * 5)) * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("PLANOS_HTTPS") == "1" or bool(os.environ.get("SPACE_ID")),
)


@app.after_request
def _cabeceras(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-XSS-Protection", "1; mode=block")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(self 'https://checkout.wompi.co')")
    
    if os.environ.get("PLANOS_HTTPS") == "1" or not os.environ.get("FLASK_DEBUG"):
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    
    # CSP: Permite Google Fonts, Leaflet (unpkg), teselas satelitales de Esri y checkout Wompi
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com https://checkout.wompi.co; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' https:; "
        "form-action 'self' https://checkout.wompi.co; "
    )
    
    if os.environ.get("SPACE_ID") or os.environ.get("PERMITIR_IFRAME") == "1":
        csp += "frame-ancestors 'self' https://huggingface.co https://*.hf.space;"
    else:
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        csp += "frame-ancestors 'self';"
        
    resp.headers["Content-Security-Policy"] = csp
    
    if request.path.startswith(("/pedidos/", "/admin")):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


# ------------------------------------------------------------------ telemetría y salud para Render y Cloud
@app.get("/salud")
@app.get("/healthz")
def salud():
    return {
        "status": "ok",
        "servicio": CFG.get("nombre_servicio", "Lindero PRO"),
        "version": "2.4.0",
        "motor": "Spatial Engine MAGNA-SIRGAS CTM12",
        "municipios_activos": list(CFG.get("municipios", {}).keys()),
        "cola": _cola.qsize(),
        "en_proceso": len(_en_proceso),
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds")
    }, 200


# ------------------------------------------------------------------ pedidos en disco
_candado = threading.RLock()


def _dir(pid):
    if not RE_ID.match(pid or ""):
        abort(404)
    d = os.path.join(PEDIDOS, pid)
    if not os.path.isdir(d):
        abort(404)
    return d


def leer(pid):
    with _candado, open(os.path.join(_dir(pid), "pedido.json"), encoding="utf-8") as f:
        return json.load(f)


def guardar(p):
    with _candado:
        ruta = os.path.join(PEDIDOS, p["id"], "pedido.json")
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=1)
        os.replace(tmp, ruta)


def actualizar(pid, **cambios):
    with _candado:
        p = leer(pid)
        p.update(cambios)
        p.setdefault("historial", []).append(
            {"cuando": datetime.datetime.now().isoformat(timespec="seconds"), "estado": p["estado"]})
        guardar(p)
        return p


def precio(n_predios):
    return max(int(CFG["precio_minimo"]), int(CFG["precio_por_predio"]) * int(n_predios))


# ------------------------------------------------------------------ ejecución del motor
# PLANOS_MODO=cola      un hilo en segundo plano procesa los pedidos (servidor propio, siempre encendido)
# PLANOS_MODO=peticion  el pedido se procesa dentro de una petición que lanza la página del pedido; es lo que
#                       necesitan Cloud Run y similares, que solo dan procesador mientras atienden una petición
MODO = os.environ.get("PLANOS_MODO", "cola")
_cola: queue.Queue = queue.Queue()
_en_proceso: set = set()
VENCE_PROCESO_S = 15 * 60


def encolar(pid, tipo):
    """Deja anotado qué le falta al pedido ('previa' o 'final') y, en modo cola, lo pasa al hilo."""
    actualizar(pid, pendiente=tipo, estado="RECIBIDO" if tipo == "previa" else "PAGADO", mensaje="")
    if MODO == "cola":
        _cola.put(pid)


def procesar_pendiente(pid):
    """Ejecuta lo que el pedido tenga pendiente. No hace nada si ya lo está procesando otra petición."""
    import time
    with _candado:
        p = leer(pid)
        tipo = p.get("pendiente")
        desde = p.get("proceso_desde", 0)
        if not tipo or pid in _en_proceso or (p.get("procesando") and time.time() - desde < VENCE_PROCESO_S):
            return False
        _en_proceso.add(pid)
        p.update(procesando=True, proceso_desde=time.time())
        guardar(p)
    try:
        _procesar(pid, tipo)
    except Exception as e:
        actualizar(pid, estado="ERROR", mensaje="Error interno al procesar el pedido.", error=str(e)[:500], pendiente=None)
    finally:
        with _candado:
            _en_proceso.discard(pid)
            p = leer(pid)
            p["procesando"] = False
            guardar(p)
    if leer(pid).get("pendiente"):          # p. ej. el pago llegó mientras se armaba la vista previa
        return procesar_pendiente(pid)
    return True


def _trabajo_json(p, previa):
    d = os.path.join(PEDIDOS, p["id"])
    ent = os.path.join(d, "entrada")
    arch = p["archivos"]
    return {
        "carpeta": os.path.join(d, "previa" if previa else "final"),
        "excel": [os.path.join(ent, a) for a in arch["excel"]],
        "dxf": os.path.join(ent, arch["dxf"]) if arch.get("dxf") else None,
        "puntos": os.path.join(ent, arch["puntos"]) if arch.get("puntos") else None,
        "municipio": p["municipio"],
        "firma": os.path.join(ent, arch["firma"]) if arch.get("firma") else "",
        "firmante": p.get("firmante") or "",
        "nombre": "PLANOS_" + p["id"][:8],
        "vista_previa": previa, "nodos_previa": 2, "hacer_atlas": True,
    }


def _correr_motor(pid, previa):
    p = leer(pid)
    d = os.path.join(PEDIDOS, pid)
    ruta_job = os.path.join(d, "trabajo_previa.json" if previa else "trabajo_final.json")
    job = _trabajo_json(p, previa)
    # el motor trabaja en una carpeta temporal local y al final se copia el resultado al almacén de pedidos
    # (que puede ser un disco o un bucket montado, donde escribir muchos archivos pequeños es lento)
    destino = job["carpeta"]
    temporal = tempfile.mkdtemp(prefix="lindero_")
    job["carpeta"] = os.path.join(temporal, os.path.basename(destino))
    with open(ruta_job, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=1)
    # solo viajan rutas generadas por el servidor: nada de lo que escribió el cliente llega a la línea de comandos
    proc = subprocess.run([sys.executable, "-m", "motor.cli", "trabajo", ruta_job],
                          capture_output=True, text=True, timeout=3600, cwd=RAIZ)
    try:
        ruta_inf = os.path.join(job["carpeta"], "informe.json")
        if not os.path.isfile(ruta_inf):
            with open(os.path.join(d, "error_motor.log"), "w", encoding="utf-8") as f:
                f.write((proc.stdout or "") + (proc.stderr or ""))
            return None
        with open(ruta_inf, encoding="utf-8") as f:
            inf = json.load(f)
        shutil.rmtree(destino, ignore_errors=True)
        shutil.copytree(job["carpeta"], destino)
        return inf
    finally:
        shutil.rmtree(temporal, ignore_errors=True)


def _resumen(inf):
    et = inf.get("etapas", {})
    return {
        "predios": len(inf.get("lotes", [])),
        "filas_excel": et.get("excel", {}).get("filas", 0),
        "poligonos": et.get("poligonos", {}).get("en_plano", 0),
        "sin_poligono": et.get("poligonos", {}).get("sin_poligono", []),
        "ubicacion": et.get("ubicacion", {}),
        "avisos": inf.get("avisos", []),
        "por_revisar": inf.get("por_revisar", []),
        "requiere_revision": bool(inf.get("requiere_revision")),
        "atlas_ok": bool(et.get("atlas", {}).get("ok")),
    }


def _procesar(pid, tipo):
    previa = tipo == "previa"
    actualizar(pid, estado="PROCESANDO_PREVIA" if previa else "GENERANDO", pendiente=None)
    inf = _correr_motor(pid, previa)
    if inf is None:
        actualizar(pid, estado="ERROR", mensaje="El motor no terminó. El equipo técnico ya fue avisado.")
        return
    r = _resumen(inf)
    if previa:
        if r["predios"] == 0 or not r["atlas_ok"]:
            actualizar(pid, estado="ERROR_ENTRADA", resumen=r,
                       mensaje="No fue posible armar los planos con estos archivos. Revisa los avisos y vuelve a subirlos.")
            return
        imgs = [os.path.basename(a) for a in inf.get("archivos", {}).get("vista_previa", [])]
        actualizar(pid, estado="PREVIA_LISTA", resumen=r, previas=imgs, precio=precio(r["predios"]))
        if leer(pid).get("pagado"):
            actualizar(pid, pendiente="final", estado="PAGADO")
    else:
        if not r["atlas_ok"]:
            actualizar(pid, estado="EN_REVISION", resumen=r, mensaje="La salida cartográfica necesita revisión manual.")
        elif r["requiere_revision"]:
            actualizar(pid, estado="EN_REVISION", resumen=r,
                       mensaje="Un profesional está verificando los predios marcados antes de liberar la descarga.")
        else:
            actualizar(pid, estado="LISTO", resumen=r, mensaje="")


def _obrero():
    while True:
        pid = _cola.get()
        try:
            procesar_pendiente(pid)
        except Exception:      # un pedido que falla no detiene la cola
            pass
        finally:
            _cola.task_done()


if MODO == "cola":
    threading.Thread(target=_obrero, daemon=True).start()


# ------------------------------------------------------------------ límites de uso (en memoria)
_usos: dict = {}


def _excede(clave, maximo, ventana_s):
    """True si `clave` ya gastó `maximo` usos en la ventana; si no, anota uno más."""
    import time
    ahora = time.time()
    with _candado:
        marcas = [t for t in _usos.get(clave, []) if ahora - t < ventana_s]
        if len(marcas) >= maximo:
            _usos[clave] = marcas
            return True
        marcas.append(ahora)
        _usos[clave] = marcas
        return False


def _ip():
    return request.remote_addr or "?"


# ------------------------------------------------------------------ utilidades web
def _csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def _exigir_csrf():
    enviado = request.form.get("csrf", "")
    if not enviado or not hmac.compare_digest(enviado, session.get("csrf", "")):
        abort(400, "Formulario vencido: recarga la página.")


def _version_estaticos():
    """Cambia cuando cambian el CSS o el JS, para que el navegador no use una copia vieja."""
    marcas = [os.path.getmtime(os.path.join(AQUI, "static", f)) for f in ("estilo.css", "app.js")]
    return str(int(max(marcas)))


app.jinja_env.globals.update(csrf=_csrf, CFG=CFG, ESTADOS=ESTADOS, VERSION=_version_estaticos())


@app.context_processor
def _contexto():
    return {"wompi": _wompi_activo(), "wompi_ambiente": _wompi_ambiente()}


# en qué tramo de la ruta (Archivos, Vista previa, Pago, Generación, Entrega) está cada estado
PASO = {"ERROR_ENTRADA": 0, "ERROR": 0, "RECIBIDO": 1, "PROCESANDO_PREVIA": 1, "PREVIA_LISTA": 2, "PAGADO": 3,
        "GENERANDO": 3, "EN_REVISION": 3, "LISTO": 5}
EN_CURSO = ("RECIBIDO", "PROCESANDO_PREVIA", "GENERANDO", "PAGADO")


@app.template_filter("pesos")
def _pesos(v):
    return "$ " + f"{int(v or 0):,}".replace(",", ".")


def _guardar_subida(archivo, tipo, carpeta, nombre):
    nombre_orig = archivo.filename or ""
    ext = os.path.splitext(nombre_orig)[1].lower()
    if ext not in EXT[tipo]:
        return None, f"El archivo de {tipo} ('{nombre_orig}') debe ser {', '.join(sorted(EXT[tipo]))}."
    destino = os.path.join(carpeta, nombre + ext)       # el nombre lo pone el servidor, no el cliente
    archivo.save(destino)
    tam = os.path.getsize(destino)
    if tam > int(CFG["max_mb_por_archivo"]) * 1024 * 1024:
        os.remove(destino)
        return None, f"El archivo de {tipo} supera {CFG['max_mb_por_archivo']} MB."
    if tam == 0:
        os.remove(destino)
        return None, f"El archivo de {tipo} ('{nombre_orig}') está vacío."

    # Validación de integridad de bytes mágicos
    try:
        with open(destino, "rb") as f_chk:
            cabecera = f_chk.read(2048)
        if tipo == "excel":
            # xlsx/xlsm son zips (PK\x03\x04); xls es OLE2 (\xd0\xcf\x11\xe0)
            if not (cabecera.startswith(b"PK\x03\x04") or cabecera.startswith(b"\xd0\xcf\x11\xe0")):
                os.remove(destino)
                return None, f"El archivo '{nombre_orig}' no parece un Excel válido o está protegido contra lectura."
        elif tipo == "dxf":
            cab_txt = cabecera.decode("latin-1", errors="ignore").upper()
            if not any(token in cab_txt for token in ("SECTION", "HEADER", "ENTITIES", "BLOCKS", "0\n", "0\r\n")):
                os.remove(destino)
                return None, f"El archivo '{nombre_orig}' no parece un plano DXF válido de AutoCAD."
        elif tipo == "firma":
            if not (cabecera.startswith(b"\x89PNG") or cabecera.startswith(b"\xff\xd8\xff")):
                os.remove(destino)
                return None, f"La imagen de la firma ('{nombre_orig}') debe ser una imagen PNG o JPG válida."
    except Exception as err:
        os.remove(destino)
        return None, f"No se pudo validar el archivo '{nombre_orig}': {err}"

    return nombre + ext, None


def _limpiar_firmante(txt):
    lineas = [re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ .,°º#/-]", "", l).strip()[:60] for l in (txt or "").splitlines()]
    return "\n".join([l for l in lineas if l][:3])


# ------------------------------------------------------------------ cliente
@app.get("/")
def inicio():
    return render_template("inicio.html", errores=[], datos={})


@app.post("/pedidos")
def crear_pedido():
    _exigir_csrf()
    lim = CFG.get("limites", {})
    if _cola.qsize() + len(_en_proceso) >= int(lim.get("cola_maxima", 25)):
        return render_template("inicio.html", errores=["Hay muchos pedidos en proceso. Intenta de nuevo en unos minutos."], datos=request.form), 503
    if _excede(("pedido", _ip()), int(lim.get("pedidos_por_hora", 6)), 3600):
        return render_template("inicio.html", errores=["Llegaste al límite de pedidos por hora. Intenta más tarde."], datos=request.form), 429
    errores = []
    municipio = request.form.get("municipio", "")
    if municipio not in CFG["municipios"]:
        errores.append("Elige un municipio disponible.")
    correo = request.form.get("correo", "").strip()[:120]
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        errores.append("Escribe un correo válido: ahí queda el enlace de tu pedido.")
    firmante = _limpiar_firmante(request.form.get("firmante", ""))
    if not firmante:
        errores.append("Indica el nombre y la matrícula profesional de quien firma los planos.")
    if not request.form.get("declaracion"):
        errores.append("Debes confirmar que tienes autorización del profesional que firma.")
    excels = [a for a in request.files.getlist("excel") if a and a.filename]
    dxf = request.files.get("dxf")
    if not excels:
        errores.append("Falta el Excel con los predios.")
    if not dxf or not dxf.filename:
        errores.append("Falta el plano en formato DXF.")
    if errores:
        return render_template("inicio.html", errores=errores, datos=request.form), 400

    pid = secrets.token_urlsafe(18)
    carpeta = os.path.join(PEDIDOS, pid, "entrada")
    os.makedirs(carpeta)
    arch = {"excel": []}
    for i, a in enumerate(excels[:6], start=1):
        n, e = _guardar_subida(a, "excel", carpeta, f"excel_{i}")
        errores += [e] if e else []
        arch["excel"] += [n] if n else []
    arch["dxf"], e = _guardar_subida(dxf, "dxf", carpeta, "plano")
    errores += [e] if e else []
    for campo, nombre in (("puntos", "cartera"), ("firma", "firma")):
        a = request.files.get(campo)
        if a and a.filename:
            arch[campo], e = _guardar_subida(a, campo, carpeta, nombre)
            errores += [e] if e else []
    if errores:
        import shutil
        shutil.rmtree(os.path.join(PEDIDOS, pid), ignore_errors=True)
        return render_template("inicio.html", errores=errores, datos=request.form), 400
    p = {"id": pid, "creado": datetime.datetime.now().isoformat(timespec="seconds"), "estado": "RECIBIDO",
         "municipio": municipio, "correo": correo, "firmante": firmante, "archivos": arch, "pagado": False,
         "historial": [], "mensaje": ""}
    p["referencia"] = obtener_referencia(p)
    guardar(p)
    encolar(pid, "previa")
    return redirect(url_for("ver_pedido", pid=pid), code=303)


@app.get("/pedidos/<pid>")
def ver_pedido(pid):
    p = leer(pid)
    # Soporte para retorno de Wompi ?id=<tx_id>&env=<test|prod>
    tx_id = request.args.get("id")
    if tx_id and not p.get("pagado") and _wompi_activo():
        env_arg = request.args.get("env") or _wompi_ambiente()
        tx_info = _verificar_transaccion_wompi(tx_id, env_arg)
        if tx_info and tx_info.get("status") == "APPROVED":
            ref_com = tx_info.get("reference", "")
            if ref_com in (obtener_referencia(p), pid):
                marcar_pagado(
                    pid=pid,
                    origen="wompi",
                    referencia_tx=str(tx_info.get("id", tx_id)),
                    referencia_comercial=ref_com,
                    ambiente=env_arg,
                    metodo=tx_info.get("payment_method_type", "WOMPI"),
                    monto_cop=int(tx_info.get("amount_in_cents", 0)) // 100
                )
                p = leer(pid)
    p["referencia"] = obtener_referencia(p)
    return render_template("pedido.html", p=p, en_curso=p["estado"] in EN_CURSO, paso=PASO.get(p["estado"], 0))


@app.post("/pedidos/<pid>/procesar")
def procesar_pedido(pid):
    """La página del pedido llama aquí mientras hay trabajo pendiente; la petición dura lo que tarde el motor."""
    _exigir_csrf()
    leer(pid)
    hizo = procesar_pendiente(pid)
    return {"procesado": bool(hizo), "estado": leer(pid)["estado"]}


@app.get("/pedidos/<pid>/estado.json")
def estado_pedido(pid):
    p = leer(pid)
    r = p.get("resumen", {})
    return {"estado": p["estado"], "titulo": ESTADOS.get(p["estado"], p["estado"]), "en_curso": p["estado"] in EN_CURSO,
            "pagado": bool(p.get("pagado")), "predios": r.get("predios", 0), "precio": p.get("precio", 0),
            "previas": p.get("previas", []), "por_revisar": len(r.get("por_revisar", []))}


@app.get("/pedidos/<pid>/previa/<nombre>")
def ver_previa(pid, nombre):
    p = leer(pid)
    if nombre == "vista_general.png":
        ruta = os.path.join(_dir(pid), "previa", "vista_general.png")
    elif nombre in p.get("previas", []):
        ruta = os.path.join(_dir(pid), "previa", "00.VISTA_PREVIA", nombre)
    else:
        abort(404)
    if not os.path.isfile(ruta):
        abort(404)
    return send_file(ruta)


@app.get("/pedidos/<pid>/descargar")
def descargar(pid):
    p = leer(pid)
    if not (p.get("pagado") and p["estado"] == "LISTO"):
        abort(403)
    ruta = os.path.join(_dir(pid), "final", "PLANOS_" + pid[:8] + ".zip")
    if not os.path.isfile(ruta):
        encolar(pid, "final")
        return redirect(url_for("ver_pedido", pid=pid), code=303)
    return send_file(ruta, as_attachment=True, download_name=f"planos_{pid[:8]}.zip")


# ------------------------------------------------------------------ pagos
def _wompi_activo():
    w = CFG.get("wompi", {})
    return bool(w.get("activo") and os.environ.get(w.get("llave_publica_env", "")) and os.environ.get(w.get("secreto_integridad_env", ""))
                and os.environ.get(w.get("secreto_eventos_env", "")))


def _wompi_ambiente():
    """Retorna 'test' o 'prod' según la llave pública configurada o variable de entorno."""
    w = CFG.get("wompi", {})
    llave = os.environ.get(w.get("llave_publica_env", ""), "").strip()
    if llave.startswith("pub_test_"):
        return "test"
    if llave.startswith("pub_prod_"):
        return "prod"
    return os.environ.get("WOMPI_AMBIENTE", w.get("ambiente_defecto", "prod")).lower()


def obtener_referencia(p):
    """Devuelve la referencia comercial oficial y parametrizada: LND-YYYYMMDD-XXXXXX."""
    if p.get("referencia"):
        return p["referencia"]
    prefijo = CFG.get("wompi", {}).get("prefijo_referencia", "LND")
    creado = p.get("creado", "")
    try:
        fecha_str = datetime.datetime.fromisoformat(creado).strftime("%Y%m%d") if creado else datetime.datetime.now().strftime("%Y%m%d")
    except Exception:
        fecha_str = datetime.datetime.now().strftime("%Y%m%d")
    clean_id = re.sub(r"[^A-Za-z0-9]", "", p.get("id", ""))[:8].upper()
    ref = f"{prefijo}-{fecha_str}-{clean_id}"
    p["referencia"] = ref
    return ref


def buscar_por_referencia(ref_o_id):
    """Busca el pid de un pedido por su referencia comercial (ej. LND-20261013-1PQH6L) o id directo."""
    if not ref_o_id:
        return None
    val = str(ref_o_id).strip()
    if RE_ID.match(val) and os.path.isdir(os.path.join(PEDIDOS, val)):
        return val
    val_upper = val.upper()
    try:
        for pid in os.listdir(PEDIDOS):
            if not RE_ID.match(pid):
                continue
            ruta_p = os.path.join(PEDIDOS, pid, "pedido.json")
            if os.path.isfile(ruta_p):
                try:
                    with open(ruta_p, "r", encoding="utf-8") as f:
                        p_data = json.load(f)
                    ref_p = p_data.get("referencia") or obtener_referencia(p_data)
                    if ref_p.upper() == val_upper:
                        return pid
                    if "-" in val_upper and val_upper.rsplit("-", 1)[-1] == re.sub(r"[^A-Za-z0-9]", "", pid)[:8].upper():
                        return pid
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _registrar_venta(pid, p, pago):
    """Registra la venta en web/datos/ventas.jsonl para auditoría y contabilidad."""
    try:
        ruta_ventas = os.path.join(DATOS, "ventas.jsonl")
        registro = {
            "fecha": pago.get("cuando"),
            "referencia_comercial": pago.get("referencia_comercial"),
            "id_pedido": pid,
            "id_transaccion": pago.get("referencia"),
            "origen": pago.get("origen"),
            "ambiente": pago.get("ambiente"),
            "metodo": pago.get("metodo"),
            "monto_cop": pago.get("monto_cop"),
            "predios": p.get("resumen", {}).get("predios", 1),
            "municipio": p.get("municipio", ""),
            "correo": p.get("correo", ""),
            "firmante": p.get("firmante", "")
        }
        with _candado, open(ruta_ventas, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[VENTAS] Error registrando venta: {e}")


def _verificar_transaccion_wompi(tx_id, ambiente="prod"):
    """Consulta la API de Wompi para verificar el estado de una transacción."""
    base_url = "https://sandbox.wompi.co/v1" if ambiente == "test" else "https://production.wompi.co/v1"
    url = f"{base_url}/transactions/{tx_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Lindero-Backend/2.4"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                datos = json.loads(resp.read().decode())
                return datos.get("data")
    except Exception:
        pass
    return None


def marcar_pagado(pid, origen, referencia_tx="", referencia_comercial="", ambiente=None, metodo="MANUAL", monto_cop=None):
    p = leer(pid)
    if p.get("pagado"):
        return p
    ref_com = referencia_comercial or obtener_referencia(p)
    amb = ambiente or _wompi_ambiente()
    monto = monto_cop if monto_cop is not None else int(p.get("precio", 0))
    ahora = datetime.datetime.now().isoformat(timespec="seconds")

    registro_pago = {
        "origen": origen,
        "referencia": referencia_tx,
        "referencia_comercial": ref_com,
        "ambiente": amb,
        "metodo": metodo,
        "monto_cop": monto,
        "cuando": ahora,
    }
    p = actualizar(pid, pagado=True, pago=registro_pago, referencia=ref_com, estado=p["estado"])
    _registrar_venta(pid, p, registro_pago)
    if p["estado"] == "PREVIA_LISTA":
        encolar(pid, "final")
    return leer(pid)


@app.post("/pedidos/<pid>/pagar")
def pagar(pid):
    _exigir_csrf()
    p = leer(pid)
    if p["estado"] != "PREVIA_LISTA" or p.get("pagado") or not _wompi_activo():
        return redirect(url_for("ver_pedido", pid=pid), code=303)
    w = CFG["wompi"]
    centavos = int(p["precio"]) * 100
    ref_comercial = obtener_referencia(p)
    integridad = hashlib.sha256(f"{ref_comercial}{centavos}COP{os.environ[w['secreto_integridad_env']]}".encode()).hexdigest()
    q = urllib.parse.urlencode({
        "public-key": os.environ[w["llave_publica_env"]], "currency": "COP", "amount-in-cents": centavos,
        "reference": ref_comercial, "signature:integrity": integridad, "redirect-url": url_for("ver_pedido", pid=pid, _external=True),
    })
    return redirect(w["checkout"] + "?" + q, code=303)


def _valor(d, ruta):
    for k in ruta.split("."):
        d = d[k]
    return d


@app.post("/pagos/wompi")
def evento_wompi():
    """Aviso de Wompi (servidor a servidor). Solo se acepta si la suma de comprobación coincide."""
    if not _wompi_activo():
        abort(404)
    ev = request.get_json(silent=True) or {}
    try:
        firma = ev["signature"]
        base = "".join(str(_valor(ev["data"], prop)) for prop in firma["properties"])
        base += str(ev["timestamp"]) + os.environ[CFG["wompi"]["secreto_eventos_env"]]
        if not hmac.compare_digest(hashlib.sha256(base.encode()).hexdigest().lower(), str(firma["checksum"]).lower()):
            abort(400)
        tx = ev["data"]["transaction"]
        ref_recibida = str(tx["reference"])
    except (KeyError, TypeError):
        abort(400)
    pid = buscar_por_referencia(ref_recibida)
    if not pid or not os.path.isdir(os.path.join(PEDIDOS, pid)):
        return {"ok": True}
    p = leer(pid)
    if tx.get("status") == "APPROVED" and tx.get("currency") == "COP" and int(tx.get("amount_in_cents", 0)) == int(p.get("precio", -1)) * 100:
        ambiente_tx = ev.get("environment") or tx.get("environment") or _wompi_ambiente()
        metodo = tx.get("payment_method_type", "WOMPI")
        marcar_pagado(
            pid=pid,
            origen="wompi",
            referencia_tx=str(tx.get("id", "")),
            referencia_comercial=ref_recibida,
            ambiente=ambiente_tx,
            metodo=metodo,
            monto_cop=int(tx.get("amount_in_cents", 0)) // 100
        )
    return {"ok": True}


# ------------------------------------------------------------------ administración
def _es_admin():
    return bool(session.get("admin"))


@app.route("/admin/entrar", methods=["GET", "POST"])
def admin_entrar():
    clave = os.environ.get("PLANOS_ADMIN_CLAVE", "")
    error = ""
    if request.method == "POST":
        _exigir_csrf()
        if _excede(("admin", _ip()), 6, 900):
            abort(429, "Demasiados intentos. Espera 15 minutos.")
        if clave and hmac.compare_digest(request.form.get("clave", "").encode(), clave.encode()):
            session.clear()
            session["admin"] = True
            return redirect(url_for("admin"), code=303)
        error = "Clave incorrecta."
    return render_template("admin_entrar.html", error=error, deshabilitado=not clave)


@app.post("/admin/salir")
def admin_salir():
    _exigir_csrf()
    session.clear()
    return redirect(url_for("inicio"), code=303)


@app.get("/admin")
def admin():
    if not _es_admin():
        return redirect(url_for("admin_entrar"))
    pedidos = []
    for pid in os.listdir(PEDIDOS):
        try:
            p_item = leer(pid)
            p_item["referencia"] = obtener_referencia(p_item)
            pedidos.append(p_item)
        except Exception:
            continue
    pedidos.sort(key=lambda p: p.get("creado", ""), reverse=True)
    recaudado_prod = sum(int(p.get("precio", 0)) for p in pedidos if p.get("pagado") and p.get("pago", {}).get("ambiente") != "test")
    recaudado_test = sum(int(p.get("precio", 0)) for p in pedidos if p.get("pagado") and p.get("pago", {}).get("ambiente") == "test")
    stats = {
        "total": len(pedidos),
        "recaudado": recaudado_prod,
        "recaudado_test": recaudado_test,
        "en_revision": sum(1 for p in pedidos if p.get("estado") == "EN_REVISION"),
        "esperando_pago": sum(1 for p in pedidos if p.get("estado") == "PREVIA_LISTA" and not p.get("pagado")),
        "listos": sum(1 for p in pedidos if p.get("estado") == "LISTO"),
    }
    return render_template("admin.html", pedidos=pedidos, stats=stats)


@app.post("/admin/pedidos/<pid>/<accion>")
def admin_accion(pid, accion):
    if not _es_admin():
        abort(403)
    _exigir_csrf()
    p = leer(pid)
    if accion == "pagado":
        ref_man = request.form.get("referencia", "")[:80]
        marcar_pagado(pid, "manual", referencia_tx=ref_man, metodo="MANUAL")
    elif accion == "aprobar" and p["estado"] == "EN_REVISION" and p.get("pagado"):
        ruta_zip = os.path.join(_dir(pid), "final", "PLANOS_" + pid[:8] + ".zip")
        if not os.path.isfile(ruta_zip):
            encolar(pid, "final")
        else:
            actualizar(pid, estado="LISTO", mensaje="")
    elif accion == "regenerar" and p.get("pagado"):
        encolar(pid, "final")
    elif accion == "previa":
        encolar(pid, "previa")
    else:
        abort(400)
    return redirect(url_for("admin"), code=303)


@app.get("/admin/pedidos/<pid>/archivo/<nombre>")
def admin_archivo(pid, nombre):
    if not _es_admin():
        return redirect(url_for("admin_entrar"))
    permitidos = {
        "informe_previa.xlsx": ("previa", "INFORME_REVISION.xlsx"), "informe_final.xlsx": ("final", "INFORME_REVISION.xlsx"),
        "vista_previa.png": ("previa", "vista_general.png"), "vista_final.png": ("final", "vista_general.png"),
        "entrega.zip": ("final", "PLANOS_" + pid[:8] + ".zip"),
    }
    if nombre not in permitidos:
        abort(404)
    ruta = os.path.join(_dir(pid), *permitidos[nombre])
    if not os.path.isfile(ruta):
        abort(404)
    return send_file(ruta, as_attachment=nombre.endswith((".xlsx", ".zip")), download_name=nombre)


@app.errorhandler(413)
def _muy_grande(_e):
    return render_template("inicio.html", errores=["Los archivos superan el tamaño permitido."], datos={}), 413


def _pagina_aviso(codigo, titulo, detalle):
    if request.path.endswith(".json") or request.path.startswith("/pagos/"):
        return {"error": titulo}, codigo
    return render_template("aviso.html", codigo=codigo, titulo=titulo, detalle=detalle), codigo


@app.errorhandler(404)
def _no_existe(_e):
    return _pagina_aviso(404, "Esta página no existe", "Revisa la dirección. Si es el enlace de un pedido, debe estar completo.")


@app.errorhandler(403)
def _sin_permiso(_e):
    return _pagina_aviso(403, "Todavía no está disponible", "La descarga se libera cuando el pedido está pagado y listo.")


@app.errorhandler(400)
def _mal_pedido(e):
    return _pagina_aviso(400, "No pudimos procesar el formulario", getattr(e, "description", "") or "Recarga la página e inténtalo de nuevo.")


@app.errorhandler(429)
def _demasiado(e):
    return _pagina_aviso(429, "Demasiados intentos", getattr(e, "description", "") or "Espera unos minutos y vuelve a intentarlo.")


if __name__ == "__main__":
    app.run(host=os.environ.get("PLANOS_HOST", "127.0.0.1"), port=int(os.environ.get("PLANOS_PUERTO", "5080")),
            debug=False, threaded=True)
