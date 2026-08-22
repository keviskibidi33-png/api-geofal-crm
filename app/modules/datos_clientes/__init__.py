"""
Módulo Datos Clientes e Informes.
"""
from app.modules.datos_clientes.models import DatosCliente
from app.modules.datos_clientes.router import router

__all__ = ["DatosCliente", "router"]
