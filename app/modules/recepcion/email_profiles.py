import os
from typing import Dict, Any, List

# Catálogo Modular de Perfiles de Correo Geofal
EMAIL_PROFILES: Dict[str, Dict[str, Any]] = {
    "OFICINA_TECNICA": {
        "id": "OFICINA_TECNICA",
        "codigo": "OFICINA_TECNICA",
        "nombre": "Oficina Técnica",
        "cargo": "Oficina Técnica - Control de Calidad",
        "from_name": os.getenv("SMTP_FROM_NAME_OT", "Oficina Técnica - GEOFAL"),
        "from_email": os.getenv("SMTP_USER_OT", "oficinatecnica1@geofal.com.pe"),
        "smtp_host": os.getenv("SMTP_HOST", "geofal.com.pe"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "imap_host": os.getenv("IMAP_HOST", "geofal.com.pe"),
        "imap_port": int(os.getenv("IMAP_PORT", "993")),
        "smtp_user": os.getenv("SMTP_USER_OT", "oficinatecnica1@geofal.com.pe"),
        "smtp_password": os.getenv("SMTP_PASSWORD_OT", "Geo_Fal2025*-/"),
        "default_cc": ["oficinatecnica3@geofal.com.pe", "asesorcomercial1@geofal.com.pe"],
        "signature_type": "HTML",
        "signature_image_filename": None,
        "telefono": "+51 1 9051911",
        "web": "www.geofal.com.pe",
        "is_default": True,
    },
    "COORDINADOR_LAB": {
        "id": "COORDINADOR_LAB",
        "codigo": "COORDINADOR_LAB",
        "nombre": "Coordinación de Laboratorio",
        "cargo": "Coordinadora de Laboratorio",
        "from_name": os.getenv("SMTP_FROM_NAME_COORD", "Coordinación de Laboratorio - GEOFAL"),
        "from_email": os.getenv("SMTP_USER_COORD", "coordinadorlab@geofal.com.pe"),
        "smtp_host": os.getenv("SMTP_HOST", "geofal.com.pe"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "imap_host": os.getenv("IMAP_HOST", "geofal.com.pe"),
        "imap_port": int(os.getenv("IMAP_PORT", "993")),
        "smtp_user": os.getenv("SMTP_USER_COORD", "coordinadorlab@geofal.com.pe"),
        "smtp_password": os.getenv("SMTP_PASSWORD_COORD", "SM*fyYI&=VOA"),
        "default_cc": ["oficinatecnica1@geofal.com.pe", "oficinatecnica3@geofal.com.pe", "asesorcomercial1@geofal.com.pe"],
        "signature_type": "IMAGE_AND_HTML",
        "signature_image_filename": "FirmaCoordinadoraLabBetzabethSaravia.png",
        "telefono": "+51 1 9051911",
        "web": "www.geofal.com.pe",
        "is_default": False,
    }
}


def get_email_profile(profile_id: str = None) -> Dict[str, Any]:
    """Obtiene la configuración del perfil de correo solicitado o el predeterminado"""
    if profile_id and profile_id.upper() in EMAIL_PROFILES:
        return EMAIL_PROFILES[profile_id.upper()]
    return EMAIL_PROFILES["OFICINA_TECNICA"]


def list_email_profiles() -> List[Dict[str, Any]]:
    """Devuelve la lista pública de perfiles de correo disponibles para el frontend (sin passwords)"""
    profiles = []
    for key, p in EMAIL_PROFILES.items():
        sig_file = p.get("signature_image_filename")
        profiles.append({
            "id": p["id"],
            "codigo": p["codigo"],
            "nombre": p["nombre"],
            "cargo": p["cargo"],
            "from_name": p["from_name"],
            "from_email": p["from_email"],
            "default_cc": p["default_cc"],
            "signature_type": p["signature_type"],
            "signature_image_url": f"/{sig_file}" if sig_file else None,
            "telefono": p["telefono"],
            "web": p["web"],
            "is_default": p.get("is_default", False),
        })
    return profiles
