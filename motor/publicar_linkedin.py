# -*- coding: utf-8 -*-
"""
Módulo de automatización para LinkedIn · DevGiz Engineering.
Permite autenticarse vía OAuth 2.0 y publicar posts automáticos en LinkedIn.

Uso:
  1. Para conectar tu cuenta por primera vez:
     python motor/publicar_linkedin.py --conectar

  2. Para publicar el post oficial de lanzamiento:
     python motor/publicar_linkedin.py --lanzamiento

  3. Para publicar un texto personalizado:
     python motor/publicar_linkedin.py --post "Tu texto aquí" --link "https://lindero.onrender.com"
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import urllib.parse
import webbrowser
import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
ENV_PATH = os.path.join(RAIZ, "web", ".env.local")

# Cargar variables de entorno desde .env.local
def _cargar_env():
    if os.path.isfile(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k, v = linea.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_cargar_env()

CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("LINKEDIN_REDIRECT_URI", "http://localhost:5080/callback")
ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
PERSON_URN = os.environ.get("LINKEDIN_PERSON_URN", "")


ORG_ID = os.environ.get("LINKEDIN_ORG_ID", "")
ORG_URN = os.environ.get("LINKEDIN_ORG_URN", "")


def _guardar_en_env(clave: str, valor: str):
    """Guarda o actualiza una variable en web/.env.local sin borrar el resto."""
    lineas = []
    encontrado = False
    if os.path.isfile(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lineas = f.readlines()

    nuevas = []
    for l in lineas:
        if l.strip().startswith(f"{clave}="):
            nuevas.append(f"{clave}={valor}\n")
            encontrado = True
        else:
            nuevas.append(l)

    if not encontrado:
        nuevas.append(f"{clave}={valor}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(nuevas)
    os.environ[clave] = valor


def conectar():
    """Inicia un mini-servidor local en el puerto 5080 y abre la pantalla de autorización."""
    auth_code = None

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if "code" in qs:
                auth_code = qs["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = """
                <html>
                <body style="font-family:sans-serif;background:#0b0f19;color:#fff;text-align:center;padding:50px;">
                    <h1 style="color:#00f0ff;">&#10003; &iexcl;Autenticaci&oacute;n exitosa con DevGiz!</h1>
                    <p style="font-size:18px;color:#cbd5e1;">Tu cuenta de LinkedIn ha quedado conectada. Ya puedes cerrar esta ventana y regresar a la terminal.</p>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))
            else:
                error = qs.get("error_description", ["Error desconocido"])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>Error de autenticaci&oacute;n: {error}</h1>".encode("utf-8"))

        def log_message(self, format, *args):
            return  # silenciar logs de peticiones HTTP en consola

    # Scopes: w_member_social es el scope para publicar en perfil
    # Si la app tiene Community Management API se agrega w_organization_social
    scope = "w_member_social openid profile email"
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": "devgiz_oauth_state",
        "scope": scope,
    }
    auth_url = f"https://www.linkedin.com/oauth/v2/authorization?{urllib.parse.urlencode(params)}"

    port = 5080
    server_address = ("", port)
    try:
        httpd = http.server.HTTPServer(server_address, CallbackHandler)
    except OSError as e:
        print(f"Error al iniciar servidor en puerto {port}: {e}")
        print("Asegúrate de que no haya otra aplicación usando el puerto 5080.")
        return False

    print("\n" + "=" * 70)
    print("CONECTAR DEVGIz CON LINKEDIN")
    print("=" * 70)
    print("Abriendo tu navegador para autorizar la aplicacion DevGiz en LinkedIn...")
    print(f"\nSi no se abre automaticamente, haz clic en este enlace:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("Esperando autorizacion en http://localhost:5080/callback ...")
    while not auth_code:
        httpd.handle_request()

    httpd.server_close()
    print("\n[OK] Codigo de autorizacion recibido.")

    # Intercambiar código por Access Token
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    payload = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    resp = requests.post(token_url, data=payload, headers=headers)
    if resp.status_code != 200:
        print(f"[!] Error al solicitar token ({resp.status_code}): {resp.text}")
        return False

    token_data = resp.json()
    token = token_data.get("access_token")
    if not token:
        print(f"[!] No se recibio access_token: {token_data}")
        return False

    _guardar_en_env("LINKEDIN_ACCESS_TOKEN", token)
    print("[OK] Access Token obtenido y guardado en web/.env.local con exito.")

    # Obtener el URN de la persona
    person_urn = _obtener_person_urn(token)
    if person_urn:
        _guardar_en_env("LINKEDIN_PERSON_URN", person_urn)
        print(f"[OK] Identificador de autor personal guardado: {person_urn}")

    print("\n" + "=" * 70)
    print("✓ DEVGIz YA ESTA CONECTADO A LINKEDIN.")
    print("Ya puedes publicar automaticamente con:")
    print("  python motor/publicar_linkedin.py --lanzamiento --destino ambos")
    print("=" * 70 + "\n")
    return True


def _obtener_person_urn(token: str) -> str:
    """Obtiene el ID del usuario actual mediante userinfo o v2/me."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=10)
        if r.status_code == 200:
            sub = r.json().get("sub")
            if sub:
                return f"urn:li:person:{sub}"
    except Exception:
        pass

    try:
        r = requests.get("https://api.linkedin.com/v2/me", headers=headers, timeout=10)
        if r.status_code == 200:
            mid = r.json().get("id")
            if mid:
                return f"urn:li:person:{mid}"
    except Exception:
        pass

    return ""


def _enviar_ugc(author_urn: str, texto: str, url_enlace: str, titulo_enlace: str, token: str) -> tuple[bool, str]:
    """Envía un UGC Post a LinkedIn y retorna (exito, id_o_error)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    ugc_data = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": texto},
                "shareMediaCategory": "ARTICLE" if url_enlace else "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    if url_enlace:
        ugc_data["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
            {
                "status": "READY",
                "originalUrl": url_enlace,
                "title": {"text": titulo_enlace},
                "description": {
                    "text": "Plataforma SIG y Cloud de DevGiz. MAGNA-SIRGAS Origen Nacional CTM12 (EPSG:9377), Shapefiles IGAC y planos oficiales para Colombia."
                },
            }
        ]

    post_url = "https://api.linkedin.com/v2/ugcPosts"
    try:
        resp = requests.post(post_url, headers=headers, json=ugc_data, timeout=15)
        if resp.status_code in (200, 201):
            pid = resp.json().get("id", "OK")
            return True, pid
        else:
            return False, f"HTTP {resp.status_code}: {resp.text}"
    except Exception as exc:
        return False, str(exc)


def publicar_post(
    texto: str,
    url_enlace: str = "https://lindero.onrender.com",
    titulo_enlace: str = "Lindero PRO · Del levantamiento al plano certificado en 38 segundos",
    destino: str = "ambos",
    org_id: str | None = None,
) -> dict[str, bool]:
    """
    Publica en LinkedIn hacia el perfil personal, la página de empresa DevGiz, o ambos.
    
    destino: 'perfil', 'empresa', o 'ambos'.
    org_id: ID numérico de la organización (ej: '105234123').
    """
    _cargar_env()
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    person_urn = os.environ.get("LINKEDIN_PERSON_URN")
    empresa_id = org_id or os.environ.get("LINKEDIN_ORG_ID", "")
    empresa_urn = os.environ.get("LINKEDIN_ORG_URN", "")

    if not empresa_urn and empresa_id:
        if not str(empresa_id).startswith("urn:li:"):
            empresa_urn = f"urn:li:organization:{empresa_id.strip()}"
        else:
            empresa_urn = empresa_id.strip()

    if not token:
        print("[!] No hay LINKEDIN_ACCESS_TOKEN configurado.")
        print("Ejecuta primero: python motor/publicar_linkedin.py --conectar")
        return {"perfil": False, "empresa": False}

    if not person_urn:
        person_urn = _obtener_person_urn(token)
        if person_urn:
            _guardar_en_env("LINKEDIN_PERSON_URN", person_urn)

    resultados = {}

    # 1. PUBLICAR EN PERFIL PERSONAL
    if destino in ("perfil", "ambos"):
        if not person_urn:
            print("[!] No se encontró URN de perfil personal.")
            resultados["perfil"] = False
        else:
            print(f"Publicando en perfil personal ({person_urn})...")
            ok, res = _enviar_ugc(person_urn, texto, url_enlace, titulo_enlace, token)
            resultados["perfil"] = ok
            if ok:
                print(f"[✓ OK] Publicado con exito en tu perfil personal! ID: {res}")
            else:
                print(f"[!] Error al publicar en perfil personal: {res}")

    # 2. PUBLICAR EN PAGINA DE EMPRESA DEVGIz
    if destino in ("empresa", "ambos"):
        if not empresa_urn:
            print("\n" + "-" * 70)
            print("ℹ PAGINA DE EMPRESA DEVGIz:")
            print("Para publicar directamente en la Company Page de DevGiz vía API:")
            print("1. Agrega LINKEDIN_ORG_ID=<numero_de_tu_empresa> en web/.env.local")
            print("   (El número que aparece en la URL https://linkedin.com/company/<ID>/admin/)")
            print("2. En LinkedIn Developers -> Products -> Solicita 'Community Management API'")
            print("   para habilitar el permiso de publicación de organizaciones (w_organization_social).")
            print("-" * 70)
            print("Texto listo para copiar y publicar en DevGiz Company Page:")
            print(f"\n{texto}\nEnlace: {url_enlace}\n")
            print("-" * 70)
            resultados["empresa"] = False
        else:
            print(f"Publicando en la página de empresa DevGiz ({empresa_urn})...")
            ok, res = _enviar_ugc(empresa_urn, texto, url_enlace, titulo_enlace, token)
            resultados["empresa"] = ok
            if ok:
                print(f"[✓ OK] Publicado con exito en la página de DevGiz! ID: {res}")
            else:
                print(f"[!] La API de LinkedIn respondió: {res}")
                if "403" in res or "ACCESS_DENIED" in res or "Data Processing Exception" in res:
                    print("\n[NOTA DE PERMISO LINKEDIN]")
                    print("Para autorizar la publicación directa en la página de empresa:")
                    print("Tu app en developer.linkedin.com requiere solicitar el producto 'Community Management API'.")
                    print("Mientras se aprueba, tu publicación ya está activa en tu feed personal y puedes")
                    print("compartirla o pegarla directamente en la página de DevGiz con 1 clic.")

    return resultados


# CATÁLOGO DE CONTENIDO EDITORIAL DE ALTO IMPACTO PARA DEVGIz
TEMAS = {
    "lanzamiento": {
        "titulo": "Lanzamiento oficial de DevGiz & Lindero PRO",
        "texto": (
            "Building Digital Territories: En DevGiz fusionamos la ingeniería de software de alta gama "
            "con la inteligencia territorial y la automatización geoespacial.\n\n"
            "Sabemos que en Colombia la cartografía y el licenciamiento enfrentan un cuello de botella constante: "
            "horas de dibujo manual en AutoCAD, inconsistencias en el nuevo Origen Nacional CTM12 (EPSG:9377) "
            "y demoras de semanas en Curadurías y Notarías.\n\n"
            "Por eso creamos Lindero PRO: nuestra plataforma en la nube que transforma datos de campo en planos "
            "certificados, archivos DXF por capas y Shapefiles oficiales del IGAC (LEVANTAMIENTO_01) en solo 38 segundos.\n\n"
            "Construimos software a medida, arquitectura cloud y sistemas geoespaciales de alta precisión "
            "para modernizar la gestión de la tierra en Colombia.\n\n"
            "🔗 Conoce el ecosistema y prueba tu primer levantamiento sin costo:\n"
            "👉 https://lindero.onrender.com\n\n"
            "#DevGiz #IngenieriaGeoespacial #SoftwareColombia #CatastroMultiproposito #Topografia #CTM12 #DevOps #SmartTerritories"
        ),
        "link": "https://lindero.onrender.com",
    },
    "ctm12": {
        "titulo": "El fin del dibujo manual y el estándar CTM12 (EPSG:9377)",
        "texto": (
            "¿Por qué siguen rechazando planos topográficos en Curadurías y Oficinas de Registro?\n\n"
            "La respuesta técnica casi siempre es la misma: desplazamientos métricos al proyectar a "
            "MAGNA-SIRGAS Origen Nacional CTM12 (EPSG:9377) o errores topológicos en el cierre de polígonos.\n\n"
            "En Colombia, un topógrafo promedio tarda entre 4 y 8 horas configurando capas de AutoCAD, "
            "cuadros de rumbos y distancias, y corrigiendo vértices a mano.\n\n"
            "En DevGiz automatizamos este flujo al 100%:\n"
            "✔ Ingesta de coordenadas (CSV / TXT / Excel)\n"
            "✔ Validación geodésica en tiempo real\n"
            "✔ Cálculo instantáneo de acimutes, rumbos y áreas\n"
            "✔ Exportación en 38 segundos de DXF listo para imprimir + Shapefiles IGAC.\n\n"
            "Acelera tus proyectos y elimina reprocesos:\n"
            "👉 https://lindero.onrender.com\n\n"
            "#TopografiaColombia #IngenieriaCivil #CTM12 #MAGNASIRGAS #Catastro #AutoCAD #DevGiz"
        ),
        "link": "https://lindero.onrender.com",
    },
    "parcelacion": {
        "titulo": "Parcelaciones Campestres y División Material",
        "texto": (
            "Loteos campestres y desenglobes: De semanas de gabinete a minutos en la nube.\n\n"
            "Desarrollar un proyecto de parcelación en Antioquia, la Sabana de Bogotá o el Eje Cafetero "
            "suele convertirse en un dolor de cabeza cuando cada lote requiere su propio cuadro de linderos, "
            "colindancias verificadas y membretes para Notaría.\n\n"
            "Con Lindero PRO de DevGiz, puedes procesar decenas de lotes en un solo flujo:\n"
            "📌 Cierre angular y lineal garantizado\n"
            "📌 Colindancias y cuadro de coordenadas según norma IGAC\n"
            "📌 Membrete profesional personalizable con la marca de tu firma\n\n"
            "Haz que tu firma de ingeniería entregue proyectos 10x más rápido:\n"
            "👉 https://lindero.onrender.com/#soluciones\n\n"
            "#DesarrolloInmobiliario #Parcelaciones #Topografia #Ingenieria #Urbanismo #Colombia #DevGiz"
        ),
        "link": "https://lindero.onrender.com/#soluciones",
    },
    "curaduria": {
        "titulo": "Radicación expedita ante Curadurías Urbanas",
        "texto": (
            "Cero observaciones en Curadurías Urbanas: El estándar cartográfico que exige el IGAC.\n\n"
            "Para licencias de subdivisión, reloteo o propiedad horizontal, las Curadurías en Colombia "
            "exigen capas estrictas en DXF y atributos alfanuméricos detallados.\n\n"
            "Un error en el formato de un punto o una discrepancia de centímetros en el cálculo geodésico "
            "puede suspender una licencia por 30 días hábiles.\n\n"
            "Lindero PRO genera la estructura cartográfica exacta:\n"
            "🔹 Capas estandarizadas: PREDIOS, CONSTRUCCION, COTAS, VERTICES\n"
            "🔹 Cuadro de elementos técnicos conforme a Resoluciones 1040 y 1149 del IGAC\n"
            "🔹 Archivos interoperables para QGIS, ArcGIS y AutoCAD\n\n"
            "Prueba el validador oficial:\n"
            "👉 https://lindero.onrender.com\n\n"
            "#Curadurias #LicenciasUrbanisticas #DerechoInmobiliario #Catastro #Topografia #DevGiz"
        ),
        "link": "https://lindero.onrender.com",
    },
    "devops": {
        "titulo": "Dev Program + Geospatial Cloud: Building Digital Territories",
        "texto": (
            "El territorio ya no se gestiona con hojas de cálculo aisladas: se gestiona con software de misión crítica.\n\n"
            "En DevGiz no solo construimos herramientas para topógrafos; diseñamos arquitecturas completas:\n"
            "⚡ Microservicios geográficos en Python & Rust\n"
            "⚡ Pipelines espaciales en PostGIS / Cloud-native Geospatial\n"
            "⚡ Integración con el modelo LADM-COL para Catastro Multipropósito\n"
            "⚡ APIs REST para empresas inmobiliarias, fintechs de tierras y gobernanzas locales\n\n"
            "Si tu empresa necesita digitalizar su infraestructura territorial o crear software a la medida, "
            "conoce el Dev Program de DevGiz.\n\n"
            "🌐 https://devgiz.vercel.app\n"
            "🚀 https://lindero.onrender.com\n\n"
            "#SoftwareEngineering #DevOps #CloudGeospatial #PostGIS #LADMCOL #GovTech #Colombia"
        ),
        "link": "https://devgiz.vercel.app",
    },
}


def post_por_tema(tema: str, destino: str = "ambos", org_id: str | None = None) -> dict[str, bool]:
    """Publica un post predefinido según el tema elegido."""
    info = TEMAS.get(tema.lower())
    if not info:
        print(f"[!] Tema '{tema}' no reconocido. Temas disponibles: {', '.join(TEMAS.keys())}")
        return {"perfil": False, "empresa": False}

    print(f"\n--- Publicando tema: {info['titulo']} (Destino: {destino}) ---")
    return publicar_post(
        texto=info["texto"],
        url_enlace=info["link"],
        titulo_enlace=f"DevGiz · {info['titulo']}",
        destino=destino,
        org_id=org_id,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automatización de publicaciones en LinkedIn para DevGiz")
    parser.add_argument("--conectar", action="store_true", help="Inicia el flujo OAuth para conectar tu cuenta")
    parser.add_argument("--lanzamiento", action="store_true", help="Publica el post oficial de lanzamiento")
    parser.add_argument("--tema", type=str, choices=list(TEMAS.keys()), help="Publica un tema predefinido (ctm12, parcelacion, curaduria, devops, lanzamiento)")
    parser.add_argument("--post", type=str, help="Texto del post a publicar")
    parser.add_argument("--link", type=str, default="https://lindero.onrender.com", help="URL del enlace a incluir")
    parser.add_argument("--destino", type=str, choices=["perfil", "empresa", "ambos"], default="ambos", help="Destino: perfil personal, empresa DevGiz o ambos (default: ambos)")
    parser.add_argument("--org-id", type=str, help="ID numérico de la empresa DevGiz en LinkedIn")

    args = parser.parse_args()

    if args.conectar:
        conectar()
    elif args.lanzamiento:
        post_por_tema("lanzamiento", destino=args.destino, org_id=args.org_id)
    elif args.tema:
        post_por_tema(args.tema, destino=args.destino, org_id=args.org_id)
    elif args.post:
        publicar_post(args.post, url_enlace=args.link, destino=args.destino, org_id=args.org_id)
    else:
        if not os.environ.get("LINKEDIN_ACCESS_TOKEN"):
            print("No se encontró sesión activa de LinkedIn. Iniciando conexión...")
            conectar()
        else:
            print("Sesión de LinkedIn activa encontrada en .env.local.")
            print("\nOpciones de publicación:")
            print("  python motor/publicar_linkedin.py --lanzamiento --destino ambos")
            print("  python motor/publicar_linkedin.py --tema ctm12 --destino ambos")
            print("  python motor/publicar_linkedin.py --tema parcelacion --destino ambos")
            print("  python motor/publicar_linkedin.py --tema devops --destino ambos")
            print("  python motor/publicar_linkedin.py --post '...' --destino ambos")

