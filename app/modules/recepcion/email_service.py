import os
import smtplib
import ssl
import re
import unicodedata
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from email.utils import formataddr
from typing import List, Optional
from sqlalchemy.orm import Session
import logging

from .excel import ExcelLogic
from .models import RecepcionMuestra
from app.audit import emit_audit_log

logger = logging.getLogger(__name__)

# Configuración SMTP por defecto para cPanel Geofal
DEFAULT_SMTP_HOST = os.getenv("SMTP_HOST", "geofal.com.pe")
DEFAULT_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
DEFAULT_SMTP_USER = os.getenv("SMTP_USER", "oficinatecnica1@geofal.com.pe")
DEFAULT_SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "Geo_Fal2025*-/")
DEFAULT_SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Oficina Técnica - GEOFAL")


class RecepcionEmailService:
    def __init__(self):
        self.excel_logic = ExcelLogic()

    def enviar_correo_recepcion(
        self,
        db: Session,
        recepcion: RecepcionMuestra,
        to_email: str,
        cc_emails: Optional[List[str]] = None,
        subject: Optional[str] = None,
        body_text: Optional[str] = None,
        actor_name: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ) -> dict:
        """
        Envía un correo directamente desde el servidor SMTP de cPanel (oficinatecnica1@geofal.com.pe)
        con el archivo Excel oficial adjunto en memoria y firma corporativa HTML.
        """
        # 1. Generar Excel oficial al vuelo
        excel_content = self.excel_logic.generar_excel_recepcion(recepcion)

        # Sanitizar nombre del archivo
        cliente_raw = recepcion.cliente or "Sin Cliente"
        cliente_safe = unicodedata.normalize('NFKD', cliente_raw).encode('ascii', 'ignore').decode('ascii')
        cliente_safe = re.sub(r'[^\w\s\-]', '', cliente_safe).strip()
        excel_filename = f"REC N-{recepcion.numero_recepcion} {cliente_safe}.xlsx"

        # 2. Normalizar destinatarios
        to_tokens = [t.strip() for t in re.split(r'[\r\n;,]+', str(to_email or "")) if t.strip()]
        if not to_tokens:
            raise ValueError("No se proporcionó ninguna dirección de correo de destinatario válida.")

        default_cc = ["oficinatecnica3@geofal.com.pe", "asesorcomercial1@geofal.com.pe"]
        raw_ccs = cc_emails if cc_emails is not None else default_cc
        cc_tokens = []
        for c in raw_ccs:
            for sub_c in re.split(r'[\r\n;,]+', str(c)):
                if sub_c.strip() and sub_c.strip() not in cc_tokens:
                    cc_tokens.append(sub_c.strip())

        # 3. Asunto dinámico según tipo de muestra
        tipo_map = {
            "CONCRETO": "Concreto",
            "SUELO_AGREGADO": "Suelo/Agregado",
            "ALBANILERIA": "Albañilería",
            "ROCA": "Roca",
            "AGUA": "Agua",
        }
        tipo_label = tipo_map.get(str(recepcion.tipo_recepcion or "").upper(), "Concreto")
        num_recepcion = recepcion.numero_recepcion or "-"
        default_subject = f"Recepción (N° {num_recepcion} muestra {tipo_label})"
        mail_subject = (subject if subject and subject.strip() else default_subject).strip()

        # 4. Cuerpo de texto y HTML con saludo dinámico según hora peruana (UTC-5)
        from datetime import datetime, timezone, timedelta
        peru_tz = timezone(timedelta(hours=-5))
        peru_hour = datetime.now(peru_tz).hour
        saludo = "Buenos días," if peru_hour < 12 else "Buenas tardes,"
        persona = (recepcion.persona_contacto or recepcion.cliente or "Cliente").strip()

        default_body = (
            f"{saludo}\n"
            f"Estimado(a) {persona}\n\n"
            f"De acuerdo con la muestra recepcionada en laboratorio, le hacemos llegar el Formato de Recepción (N° {num_recepcion}) con el fin de completar y/o verifique que los datos consignados sean correctos y tenga conocimiento de la fecha de entrega de los informes de ensayo.\n\n"
            f"Cualquier modificación solicitada una vez emitidos los informes de ensayo, deberá justificar el motivo del cambio por correo, el área comercial se pondrá en contacto.\n\n"
            f"Agradeceremos nos brinde su conformidad por este medio para emitir el informe de ensayo.\n\n"
            f"Atentamente,"
        )
        final_body_text = (body_text if body_text and body_text.strip() else default_body).strip()

        # Generar versión HTML estilizada con la firma corporativa
        paragraphs_html = "".join([f"<p style='margin: 6px 0;'>{p.strip()}</p>" for p in final_body_text.split("\n\n") if p.strip()])
        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Arial, Helvetica, sans-serif; font-size: 13px; color: #1e293b; line-height: 1.6; }}
</style>
</head>
<body>
{paragraphs_html}
<br/>
<table style="border:none; border-collapse:collapse; font-family: Arial, Helvetica, sans-serif; margin-top: 15px;">
  <tr>
    <td style="vertical-align:middle; padding-right: 16px;">
      <div style="background-color: #ff5500; color: #ffffff; font-weight: bold; font-size: 20px; padding: 12px 16px; border-radius: 10px; text-align: center;">
        Geofal
      </div>
    </td>
    <td style="border-left: 2px solid #ea580c; padding-left: 16px; vertical-align:middle;">
      <div style="font-size: 14px; font-weight: bold; color: #ea580c; text-transform: uppercase;">
        OFICINA TÉCNICA
      </div>
      <div style="font-size: 12px; color: #0284c7; font-weight: bold; margin-top: 2px;">
        GEOFAL S.A.C. — Laboratorio de Ensayo de Materiales
      </div>
      <div style="font-size: 11px; color: #475569; margin-top: 4px;">
        <strong>T:</strong> +51 1 9051911 &nbsp;|&nbsp; <strong>E:</strong> oficinatecnica1@geofal.com.pe
      </div>
      <div style="font-size: 11px; color: #64748b; margin-top: 2px;">
        <strong>W:</strong> <a href="https://www.geofal.com.pe" style="color: #0284c7; text-decoration: none;">www.geofal.com.pe</a>
      </div>
    </td>
  </tr>
</table>
</body>
</html>"""

        # 5. Construcción del mensaje MIME multipart/mixed
        msg = MIMEMultipart("mixed")
        msg["From"] = formataddr((DEFAULT_SMTP_FROM_NAME, DEFAULT_SMTP_USER))
        msg["To"] = ", ".join(to_tokens)
        if cc_tokens:
            msg["Cc"] = ", ".join(cc_tokens)
        msg["Subject"] = Header(mail_subject, "utf-8")

        # Subparte multipart/alternative para texto plano + HTML
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(final_body_text, "plain", "utf-8"))
        alt_part.attach(MIMEText(html_content, "html", "utf-8"))
        msg.attach(alt_part)

        # 6. Adjuntar Excel oficial en memoria
        part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.set_payload(excel_content)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{excel_filename}"'
        )
        msg.attach(part)

        # 7. Envío mediante servidor SMTP de cPanel con TLS
        all_recipients = to_tokens + cc_tokens
        host = DEFAULT_SMTP_HOST
        port = DEFAULT_SMTP_PORT
        user = DEFAULT_SMTP_USER
        password = DEFAULT_SMTP_PASSWORD

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
                server.sendmail(user, all_recipients, msg.as_bytes())
                logger.info(f"Correo de recepción {recepcion.numero_recepcion} enviado exitosamente a {all_recipients}")
        except Exception as e:
            logger.exception("Error al enviar correo por SMTP cPanel")
            raise RuntimeError(f"Error al enviar correo mediante el servidor SMTP ({host}:{port}): {str(e)}")

        # 8. Registro de auditoría
        try:
            emit_audit_log(
                db=db,
                user_id=actor_user_id,
                user_name=actor_name or "Usuario CRM",
                action="ENVIAR_CORREO_RECEPCION",
                module="RECEPCION",
                details={
                    "recepcion_id": recepcion.id,
                    "numero_recepcion": recepcion.numero_recepcion,
                    "cliente": recepcion.cliente,
                    "destinatarios": to_tokens,
                    "cc": cc_tokens,
                    "asunto": mail_subject,
                    "adjunto": excel_filename,
                }
            )
        except Exception as audit_err:
            logger.warning(f"No se pudo registrar la auditoría de correo: {audit_err}")

        return {
            "success": True,
            "message": f"Correo enviado exitosamente a {', '.join(to_tokens)}",
            "to": to_tokens,
            "cc": cc_tokens,
            "filename": excel_filename,
        }
