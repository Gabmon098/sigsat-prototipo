"""
Matriz de permisos por rol del prototipo SIGSAT.

Cada vista consulta `puede(usuario, permiso)` en lugar de comparar roles
directamente, de modo que cambiar qué puede hacer cada rol se hace en un
solo lugar.
"""

ROL_REPRESENTANTE = "Representante de Área"
ROL_TECNICO = "Técnico"
ROL_ADMINISTRADOR = "Administrador"

PERMISOS_POR_ROL = {
    ROL_REPRESENTANTE: {
        "solicitud.crear",             # levantar solicitudes de incidente
        "solicitud.ver_propias",       # consultar solo sus solicitudes
        "solicitud.calificar",         # calificar el servicio recibido (1 a 5) una vez finalizado
        "mesa.crear_conversacion",     # abrir conversaciones con la Administración (Mesa de Servicio)
    },
    ROL_TECNICO: {
        "solicitud.ver_asignadas",     # sus reportes (las solicitudes que el Administrador le asignó)
        "solicitud.atender",           # avanzar el estatus (Visualizado, En proceso, Finalizado) y comentar
        "reportes.ver_propios",        # bandeja de sus reportes con filtros e histórico
        "bitacora.ver_asignadas",      # historial de atención de sus reportes (se consulta desde «Mis reportes»)
        "mesa.crear_conversacion",     # abrir conversaciones con la Administración (Mesa de Servicio)
    },
    ROL_ADMINISTRADOR: {
        "dashboard.ver",               # panel de indicadores (KPIs)
        "administracion.ver",          # usuarios, catálogos, correos y respaldos
        "usuarios.gestionar",          # cambiar el rol, desactivar o eliminar cuentas (las cuentas las crea cada persona al registrarse)
        "catalogos.crear",             # RF-04: agregar áreas, sucursales y tipos de solicitud (con su tiempo estimado)
        "solicitud.ver_todas",         # supervisar todas las solicitudes
        "solicitud.asignar",           # RF-09: distribuir (asignar y reasignar) las solicitudes a los técnicos
        "reportes.ver",                # RF-24/25: reportes filtrables y exportación; bandeja de reportes
        "bitacora.ver_todas",          # RF-21: historial de atención de TODAS las solicitudes (desde «Reportes»)
        "respaldos.gestionar",         # RNF-09: respaldos, restauración y verificación de la bitácora
        "correos.ver",                 # bandeja de correos enviados
        # ---- Reglas del proyecto (deshabilitadas a propósito; ningún rol tiene estos permisos) ----
        # "catalogos.editar",          # los catálogos NO se editan: solo se agregan elementos nuevos
        # "catalogos.eliminar",        # los catálogos NO se eliminan
        "mesa.ver_todas",              # supervisar todas las conversaciones de la Mesa de Servicio
        "mesa.responder",
        "mesa.cerrar",
    },
}


# Permisos que NINGÚN rol tiene hoy, por regla del proyecto. Para volver a permitirlos, agrega el nombre al
# conjunto del rol que corresponda en PERMISOS_POR_ROL (y listo: la interfaz y la capa de datos lo respetan).
#
#   solicitud.adjuntar_despues  → agregar o quitar archivos de una solicitud YA creada. Los archivos
#                                 solo se adjuntan al registrar la solicitud (el representante).
#   catalogos.editar            → renombrar o desactivar áreas, sucursales y tipos de solicitud.
#   catalogos.eliminar          → eliminar áreas, sucursales y tipos de solicitud.
PERMISOS_DESHABILITADOS = ("solicitud.adjuntar_despues", "catalogos.editar", "catalogos.eliminar")


def puede(usuario: dict, permiso: str) -> bool:
    return permiso in PERMISOS_POR_ROL.get(usuario["rol"], set())
