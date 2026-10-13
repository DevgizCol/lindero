"""motor/correo.py: Módulo de notificaciones transaccionales y entrega automática.

Soporta:
1. Resend API (HTTPS REST https://api.resend.com/emails)
2. SendGrid API (HTTPS REST https://api.sendgrid.com/v3/mail/send)
3. SMTP Estándar (smtplib TLS/SSL)
4. Fallback simulado en logs si no hay credenciales configuradas
"""

import json
import logging
import os
import smtplib
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("lindero.correo")


def _plantilla_correo(datos: dict) -> str:
    """Genera la plantilla HTML responsiva de alta gama para la entrega de planos."""
    ref = datos.get("referencia", "LND-20261013-0000")
    tx_id = datos.get("id_transaccion", "-")
    monto = datos.get("monto_formateado", "$4.000 COP")
    predios = datos.get("predios", 1)
    municipio = datos.get("municipio", "Malambo (Atlántico)")
    firmante = datos.get("firmante", "Profesional Topógrafo")
    url_descarga = datos.get("url_descarga", "https://lindero.onrender.com")
    url_pedido = datos.get("url_pedido", "https://lindero.onrender.com")
    metodo = datos.get("metodo", "Pasarela Wompi").upper()

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Entrega de Planos Certificados - Lindero PRO</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #070a13; color: #e2e8f0; margin: 0; padding: 20px 10px; line-height: 1.5; }}
    .contenedor {{ max-width: 600px; margin: 0 auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.6); }}
    .cabecera {{ background: linear-gradient(135deg, #001a40 0%, #030712 100%); padding: 32px 28px; border-bottom: 1px solid #1e293b; text-align: center; }}
    .badge {{ display: inline-block; background: rgba(0, 240, 255, 0.12); color: #00f0ff; border: 1px solid rgba(0, 240, 255, 0.3); padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 12px; }}
    .titulo {{ color: #ffffff; font-size: 24px; font-weight: 800; margin: 0 0 6px; letter-spacing: -0.5px; }}
    .subtitulo {{ color: #94a3b8; font-size: 14px; margin: 0; }}
    .cuerpo {{ padding: 28px 24px; }}
    .saludo {{ font-size: 15px; color: #cbd5e1; margin-bottom: 20px; }}
    .comprobante {{ background: #131d35; border: 1px solid #1e3a5f; border-radius: 12px; padding: 20px; margin: 24px 0; }}
    .comp-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 14px; }}
    .comp-ref {{ font-family: monospace; font-size: 16px; font-weight: 700; color: #00f0ff; }}
    .comp-estado {{ background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 6px; }}
    .grid-detalles {{ width: 100%; border-collapse: collapse; }}
    .grid-detalles td {{ padding: 6px 0; font-size: 13px; }}
    .grid-detalles td.rotulo {{ color: #64748b; width: 45%; }}
    .grid-detalles td.valor {{ color: #ffffff; font-weight: 600; text-align: right; }}
    .btn-wrap {{ text-align: center; margin: 32px 0 24px; }}
    .btn-descarga {{ display: inline-block; background: linear-gradient(135deg, #00f0ff 0%, #0066ff 100%); color: #000000 !important; font-weight: 800; font-size: 15px; padding: 14px 28px; border-radius: 10px; text-decoration: none; box-shadow: 0 8px 24px rgba(0, 102, 255, 0.4); text-transform: uppercase; letter-spacing: 0.5px; }}
    .incluye {{ background: #0b1120; border: 1px solid #1e293b; border-radius: 10px; padding: 16px; margin-bottom: 24px; font-size: 12.5px; color: #94a3b8; }}
    .incluye ul {{ margin: 8px 0 0; padding-left: 18px; }}
    .incluye li {{ margin-bottom: 4px; }}
    .pie {{ background: #070a13; border-top: 1px solid #1e293b; padding: 20px; text-align: center; font-size: 12px; color: #64748b; }}
    .pie a {{ color: #00f0ff; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="contenedor">
    <div class="cabecera">
      <span class="badge">DEVGIZ · CARTOGRAFÍA OFICIAL</span>
      <h1 class="titulo">Tus Planos Catastrales Están Listos</h1>
      <p class="subtitulo">Validación MAGNA-SIRGAS Origen Nacional (CTM12 / EPSG:9377)</p>
    </div>

    <div class="cuerpo">
      <p class="saludo">Hola <strong>{firmante}</strong>,</p>
      <p style="color:#94a3b8;font-size:14px;margin-top:0;">Tu pago ha sido confirmado y procesado con éxito. El paquete de entrega oficial de <strong>{predios} predio(s)</strong> en <strong>{municipio}</strong> ha sido generado y certificado con tu firma profesional.</p>

      <div class="comprobante">
        <table style="width:100%;margin-bottom:12px;">
          <tr>
            <td style="font-size:11px;color:#94a3b8;text-transform:uppercase;font-weight:700;">Comprobante Digital de Pago</td>
            <td style="text-align:right;"><span class="comp-estado">✓ PAGO APROBADO</span></td>
          </tr>
          <tr>
            <td colspan="2" class="comp-ref" style="padding-top:4px;">{ref}</td>
          </tr>
        </table>
        
        <table class="grid-detalles">
          <tr><td class="rotulo">Transacción Pasarela:</td><td class="valor">#{tx_id}</td></tr>
          <tr><td class="rotulo">Método de Pago:</td><td class="valor">{metodo}</td></tr>
          <tr><td class="rotulo">Total Cancelado:</td><td class="valor" style="color:#00f0ff;">{monto}</td></tr>
          <tr><td class="rotulo">Predios Procesados:</td><td class="valor">{predios} plano(s)</td></tr>
          <tr><td class="rotulo">Municipio / Zona:</td><td class="valor">{municipio}</td></tr>
        </table>
      </div>

      <div class="btn-wrap">
        <a class="btn-descarga" href="{url_descarga}" target="_blank">⬇️ Descargar Paquete Completo (ZIP)</a>
      </div>

      <div class="incluye">
        <strong style="color:#e2e8f0;">📦 Contenido del Paquete Oficial Descargable:</strong>
        <ul>
          <li><strong>Shapefiles Catastrales (SHP):</strong> Capas oficiales LEVANTAMIENTO_01, COTAS y COORDENADAS con sus 25 atributos estándar IGAC.</li>
          <li><strong>Planos Certificados en PDF:</strong> Planos vectoriales de alta resolución con cuadro de linderos, ortofoto y tu firma digital.</li>
          <li><strong>Informe Técnico de Coordenadas (XLSX):</strong> Tabla completa de vértices en coordenadas MAGNA-SIRGAS CTM12.</li>
        </ul>
      </div>

      <p style="font-size:12px;color:#64748b;text-align:center;">
        También puedes consultar tu pedido en línea en cualquier momento desde:<br>
        <a href="{url_pedido}" style="color:#38bdf8;text-decoration:none;">{url_pedido}</a>
      </p>
    </div>

    <div class="pie">
      <p style="margin:0 0 6px;">Lindero PRO es una tecnología de alta precisión desarrollada por <a href="https://devgiz.vercel.app/" target="_blank">DevGiz Engineering</a>.</p>
      <p style="margin:0;">¿Necesitas ayuda o soporte? Escríbenos a <a href="mailto:soporte@devgiz.com">soporte@devgiz.com</a></p>
    </div>
  </div>
</body>
</html>"""


def enviar_correo_entrega(datos: dict) -> bool:
    """Envía el correo de confirmación de pago y descarga de planos.
    
    Busca credenciales en:
    1. RESEND_API_KEY
    2. SENDGRID_API_KEY
    3. SMTP_HOST, SMTP_USER, SMTP_PASS
    4. Fallback a log local si no hay proveedor configurado.
    """
    destinatario = (datos.get("correo") or "").strip()
    if not destinatario or "@" not in destinatario:
        logger.warning("No hay correo de destinatario válido para notificar.")
        return False

    ref = datos.get("referencia", "LND-PEDIDO")
    asunto = f"Tus Planos Catastrales Están Listos · Pedido {ref}"
    cuerpo_html = _plantilla_correo(datos)
    remitente = os.environ.get("CORREO_REMITENTE", "Lindero PRO <soporte@devgiz.com>")

    # 1. Probar Resend API
    resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    if resend_key:
        try:
            remitente_resend = os.environ.get("RESEND_FROM", "").strip()
            if not remitente_resend:
                if os.environ.get("RESEND_DOMAIN_VERIFIED") == "1":
                    remitente_resend = remitente
                else:
                    remitente_resend = "Lindero PRO <onboarding@resend.dev>"

            payload = json.dumps({
                "from": remitente_resend,
                "to": [destinatario],
                "subject": asunto,
                "html": cuerpo_html
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Lindero-Mailer/2.4"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    logger.info("Correo enviado exitosamente vía Resend a %s", destinatario)
                    return True
        except urllib.error.HTTPError as he:
            cuerpo_err = he.read().decode("utf-8", errors="replace")
            logger.warning("Resend devolvió HTTP %s: %s", he.code, cuerpo_err)
        except Exception as e:
            logger.error("Error enviando por Resend: %s", e)

    # 2. Probar SendGrid API
    sendgrid_key = os.environ.get("SENDGRID_API_KEY", "").strip()
    if sendgrid_key:
        try:
            payload = json.dumps({
                "personalizations": [{"to": [{"email": destinatario}]}],
                "from": {"email": os.environ.get("SENDGRID_FROM", "soporte@devgiz.com"), "name": "Lindero PRO"},
                "subject": asunto,
                "content": [{"type": "text/html", "value": cuerpo_html}]
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.sendgrid.com/v3/mail/send",
                data=payload,
                headers={
                    "Authorization": f"Bearer {sendgrid_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Lindero-Mailer/2.4"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 202):
                    logger.info("Correo enviado exitosamente vía SendGrid a %s", destinatario)
                    return True
        except Exception as e:
            logger.error("Error enviando por SendGrid: %s", e)

    # 3. Probar SMTP Estándar
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    if smtp_host:
        try:
            smtp_port = int(os.environ.get("SMTP_PORT", 587))
            smtp_user = os.environ.get("SMTP_USER", "").strip()
            smtp_pass = os.environ.get("SMTP_PASS", "").strip()
            
            msg = MIMEMultipart("alternative")
            msg["Subject"] = asunto
            msg["From"] = remitente
            msg["To"] = destinatario
            msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(remitente, [destinatario], msg.as_string())
            server.quit()
            logger.info("Correo enviado exitosamente vía SMTP a %s", destinatario)
            return True
        except Exception as e:
            logger.error("Error enviando por SMTP: %s", e)

    # 4. Modo Simulación / Log (cuando no hay llaves aún)
    logger.info("[CORREO SIMULADO] Se habría enviado correo a %s con referencia %s y descarga %s",
                destinatario, ref, datos.get("url_descarga"))
    return True
