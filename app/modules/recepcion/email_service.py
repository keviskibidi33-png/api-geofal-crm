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
from .email_profiles import get_email_profile
from app.audit import emit_audit_log
from email.mime.image import MIMEImage
from pathlib import Path

logger = logging.getLogger(__name__)


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
        profile_id: Optional[str] = None,
        actor_name: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ) -> dict:
        """
        Envía un correo directamente desde el servidor SMTP de cPanel usando el perfil de correo seleccionado
        (Oficina Técnica, Coordinador de Lab, etc.) con el archivo Excel oficial adjunto y firma con imagen corporativa.
        """
        # 1. Obtener perfil de correo seleccionado
        profile = get_email_profile(profile_id)
        from_name = profile["from_name"]
        from_email = profile["from_email"]
        smtp_host = profile["smtp_host"]
        smtp_port = profile["smtp_port"]
        smtp_user = profile["smtp_user"]
        smtp_password = profile["smtp_password"]
        cargo_title = profile.get("cargo", "Oficina Técnica")

        # 2. Generar Excel oficial al vuelo
        excel_content = self.excel_logic.generar_excel_recepcion(recepcion)

        # Sanitizar nombre del archivo
        cliente_raw = recepcion.cliente or "Sin Cliente"
        cliente_safe = unicodedata.normalize('NFKD', cliente_raw).encode('ascii', 'ignore').decode('ascii')
        cliente_safe = re.sub(r'[^\w\s\-]', '', cliente_safe).strip()
        excel_filename = f"REC N-{recepcion.numero_recepcion} {cliente_safe}.xlsx"

        # 3. Normalizar destinatarios
        to_tokens = [t.strip() for t in re.split(r'[\r\n;,]+', str(to_email or "")) if t.strip()]
        if not to_tokens:
            raise ValueError("No se proporcionó ninguna dirección de correo de destinatario válida.")

        default_cc = profile.get("default_cc", ["oficinatecnica3@geofal.com.pe", "asesorcomercial1@geofal.com.pe"])
        raw_ccs = cc_emails if cc_emails is not None else default_cc
        cc_tokens = []
        for c in raw_ccs:
            for sub_c in re.split(r'[\r\n;,]+', str(c)):
                if sub_c.strip() and sub_c.strip() not in cc_tokens:
                    cc_tokens.append(sub_c.strip())

        # 4. Asunto dinámico según tipo de muestra
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

        # 5. Cuerpo de texto y HTML con saludo dinámico según hora peruana (UTC-5)
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

        # 6. Intentar cargar imagen de firma oficial del perfil (si tiene asignada)
        sig_filename = profile.get("signature_image_filename")
        has_signature_img = False
        sig_img_bytes = None
        if sig_filename:
            img_path = Path(__file__).resolve().parents[2] / "src" / "Firmas_Correo" / sig_filename
            if img_path.exists():
                try:
                    sig_img_bytes = img_path.read_bytes()
                    has_signature_img = True
                except Exception as e:
                    logger.warning(f"No se pudo leer la imagen de firma: {e}")
                    has_signature_img = False

        # Generar versión HTML con soporte de negritas markdown (**)
        formatted_paragraphs = []
        for p in final_body_text.split("\n\n"):
            clean_p = p.strip()
            if not clean_p:
                continue
            p_html = clean_p.replace("\n", "<br/>")
            # Convertir **texto** a <strong>texto</strong>
            p_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', p_html)
            formatted_paragraphs.append(f"<p style='margin: 6px 0;'>{p_html}</p>")

        paragraphs_html = "".join(formatted_paragraphs)
        
        if has_signature_img:
            # Firma gráfica oficial (banner corporativo completo con datos y firma)
            signature_visual_html = f"""
<div style="margin-top: 20px;">
  <img src="cid:geofal_signature_img" alt="{cargo_title} - GEOFAL S.A.C." style="width: 100%; max-width: 550px; height: auto; display: block; border: none;" />
</div>"""
        else:
            # Sin imagen de firma: no se crea ninguna firma ficticia
            signature_visual_html = ""

        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Arial, Helvetica, sans-serif; font-size: 13px; line-height: 1.6; }}
</style>
</head>
<body>
{paragraphs_html}
{signature_visual_html}
</body>
</html>"""

        # Versión de texto plano limpia (sin asteriscos)
        plain_body_text = re.sub(r'\*\*(.+?)\*\*', r'\1', final_body_text)

        # 7. Construcción del mensaje MIME multipart/related y multipart/mixed
        msg = MIMEMultipart("mixed")
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = ", ".join(to_tokens)
        if cc_tokens:
            msg["Cc"] = ", ".join(cc_tokens)
        msg["Subject"] = Header(mail_subject, "utf-8")

        # Subparte multipart/related para permitir imágenes inline (CID)
        related_part = MIMEMultipart("related")
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(plain_body_text, "plain", "utf-8"))
        alt_part.attach(MIMEText(html_content, "html", "utf-8"))
        related_part.attach(alt_part)

        # Si tenemos la imagen de firma, incrustarla como CID inline
        if has_signature_img and sig_img_bytes:
            img_mime = MIMEImage(sig_img_bytes, _subtype="png")
            img_mime.add_header("Content-ID", "<geofal_signature_img>")
            img_mime.add_header("Content-Disposition", "inline", filename=sig_filename or "FirmaCoordinadoraLabBetzabethSaravia.png")
            img_mime.add_header("X-Attachment-Id", "geofal_signature_img")
            related_part.attach(img_mime)

        msg.attach(related_part)

        # 8. Adjuntar Excel oficial en memoria
        part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.set_payload(excel_content)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{excel_filename}"'
        )
        msg.attach(part)

        # 9. Envío mediante servidor SMTP de cPanel con TLS
        all_recipients = to_tokens + cc_tokens
        host = smtp_host
        port = smtp_port
        user = smtp_user
        password = smtp_password

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=25) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
                server.sendmail(user, all_recipients, msg.as_bytes())
                logger.info(f"Correo de recepción {recepcion.numero_recepcion} enviado exitosamente desde {from_email} a {all_recipients}")
        except Exception as e:
            logger.exception("Error al enviar correo por SMTP cPanel")
            raise RuntimeError(f"Error al enviar correo mediante el servidor SMTP ({host}:{port}) con la cuenta {from_email}: {str(e)}")

        # 10. Registro de auditoría
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
                    "perfil_utilizado": profile["id"],
                    "remitente": from_email,
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
            "message": f"Correo enviado exitosamente desde {from_name} a {', '.join(to_tokens)}",
            "profile": profile["id"],
            "from": from_email,
            "to": to_tokens,
            "cc": cc_tokens,
            "filename": excel_filename,
        }
