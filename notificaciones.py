"""
Textos de los correos de SIGSAT. Recibe diccionarios simples (nunca toca el estado
interno de `datos`) y delega el envío en `correo`.

RF-11  correo de asignación  → al técnico asignado, al representante y (si lo hay) al técnico anterior.
RF-12  correo de cambio de estatus → al representante que levantó la solicitud.
Recuperación de contraseña → código de un solo uso para quien lo pidió.
"""

import correo

LIM_DESCRIPCION_CORREO = 400


def _recortar(texto: str, maximo: int = LIM_DESCRIPCION_CORREO) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= maximo else texto[: maximo - 1].rstrip() + "…"


def _pie() -> str:
    return "\n—\nSIGSAT · TechSolve México\nEste es un mensaje automático; no respondas a este correo.\n"


def _ficha(s: dict) -> str:
    return (f"  Folio: {s['folio']}\n  Tipo: {s['tipo']}\n  Área: {s['area']}\n"
            f"  Sucursal: {s.get('sucursal') or '—'}\n"
            f"  Prioridad: {s['prioridad']}\n  Fecha límite de atención: {s.get('vence') or '—'}\n"
            f"  Solicitante: {s['solicitante']}\n  Descripción: {_recortar(s['descripcion'])}\n")


def solicitud_asignada(s: dict, agente: dict, solicitante: dict, anterior: dict = None,
                       por: str = None, motivo: str = "") -> None:
    """Asignación o reasignación. `s` es la vista de lectura de la solicitud; los demás son cuentas."""
    reasignada = anterior is not None
    verbo = "reasignada" if reasignada else "asignada"
    quien = f" por {por}" if por else ""
    razon = f"\nMotivo: {_recortar(motivo, 300)}\n" if motivo else ""

    correo.enviar(agente["correo"], f"[SIGSAT] Se te {'reasignó' if reasignada else 'asignó'} la solicitud {s['folio']}",
                  f"Hola {agente['nombre']},\n\nSe te {'reasignó' if reasignada else 'asignó'} una solicitud{quien}:\n\n"
                  f"{_ficha(s)}{razon}\nRevísala en SIGSAT → Mis reportes.\n{_pie()}",
                  tipo="asignacion")

    if solicitante and solicitante["correo"] != agente["correo"]:
        correo.enviar(solicitante["correo"], f"[SIGSAT] Tu solicitud {s['folio']} fue {verbo}",
                      f"Hola {solicitante['nombre']},\n\nTu solicitud {s['folio']} fue {verbo} a "
                      f"{agente['nombre']}, quien dará seguimiento a tu caso.\n"
                      f"Fecha límite de atención: {s.get('vence') or '—'}.\n\n"
                      f"Puedes consultar el avance en SIGSAT → Mis solicitudes.\n{_pie()}",
                      tipo="asignacion")

    if reasignada and anterior["correo"] not in (agente["correo"], (solicitante or {}).get("correo")):
        correo.enviar(anterior["correo"], f"[SIGSAT] La solicitud {s['folio']} ya no está a tu cargo",
                      f"Hola {anterior['nombre']},\n\nLa solicitud {s['folio']} fue reasignada a "
                      f"{agente['nombre']}{quien}.{razon}{_pie()}",
                      tipo="asignacion")


def estatus_cambiado(s: dict, estado_anterior: str, comentario: str, solicitante: dict) -> None:
    """RF-12: avisa al representante que cambió el estatus de su solicitud."""
    if not solicitante:
        return
    nota = f"\nComentario del técnico: {_recortar(comentario, 500)}\n" if comentario else ""
    cierre = ("\nTu solicitud quedó finalizada. Entra a SIGSAT → Mis solicitudes para calificar el servicio "
              "recibido (de 1 a 5).\n") if s["estado"] == "Finalizado" else ""
    correo.enviar(solicitante["correo"], f"[SIGSAT] Tu solicitud {s['folio']} ahora está «{s['estado']}»",
                  f"Hola {solicitante['nombre']},\n\nEl estatus de tu solicitud {s['folio']} cambió de "
                  f"«{estado_anterior}» a «{s['estado']}».\n{nota}{cierre}\n"
                  f"Atiende: {s.get('agente_asignado') or 'sin técnico asignado'}.\n{_pie()}",
                  tipo="estatus")


def servicio_calificado(s: dict, tecnico: dict, solicitante: dict) -> None:
    """El representante calificó el servicio: se avisa al técnico que la atendió, con la calificación."""
    if not tecnico or (solicitante and tecnico["correo"] == solicitante["correo"]):
        return
    quien = solicitante["nombre"] if solicitante else "El representante"
    correo.enviar(tecnico["correo"], f"[SIGSAT] La solicitud {s['folio']} fue calificada con {s['calificacion']}/5",
                  f"Hola {tecnico['nombre']},\n\n{quien} calificó el servicio de la solicitud "
                  f"{s['folio']} ({s['tipo']}) con {s['calificacion']} de 5.\n{_pie()}",
                  tipo="estatus")


def solicitud_por_asignar(s: dict, administradores: list) -> None:
    """RF-09/RF-11: hay una solicitud nueva por distribuir; se avisa a los administradores."""
    for admin in administradores:
        correo.enviar(admin["correo"], f"[SIGSAT] Nueva solicitud {s['folio']} por asignar",
                      f"Hola {admin['nombre']},\n\nSe registró una solicitud que espera ser asignada a un técnico:\n\n"
                      f"{_ficha(s)}\nAsígnala en SIGSAT → Solicitudes.\n{_pie()}",
                      tipo="asignacion")


def codigo_recuperacion(cuenta: dict, codigo: str, minutos: int) -> None:
    correo.enviar(cuenta["correo"], "[SIGSAT] Código para restablecer tu contraseña",
                  f"Hola {cuenta['nombre']},\n\nRecibimos una solicitud para restablecer la contraseña de tu "
                  f"cuenta en SIGSAT. Tu código es:\n\n    {codigo}\n\n"
                  f"Escríbelo en la pantalla «¿Olvidaste tu contraseña?». Vale {minutos} minutos y solo se "
                  f"puede usar una vez.\n\nSi tú no lo pediste, ignora este mensaje: tu contraseña no cambiará.\n"
                  f"No compartas este código con nadie.\n{_pie()}",
                  tipo="recuperacion", sensible=True)


def cuenta_registrada(cuenta: dict, administradores: list) -> None:
    """Alguien creó su propia cuenta desde el login: se le da la bienvenida (sin contraseña: nunca se envía) y se
    avisa a los administradores, solo para que estén enterados."""
    area = f"  Área: {cuenta['area']}\n" if cuenta.get("area") else ""
    area += f"  Sucursal: {cuenta['sucursal']}\n" if cuenta.get("sucursal") else ""
    correo.enviar(cuenta["correo"], "[SIGSAT] Tu cuenta fue creada",
                  f"Hola {cuenta['nombre']},\n\nTu cuenta en SIGSAT ya está activa:\n\n"
                  f"  Usuario: {cuenta['usuario']}\n  Rol: {cuenta['rol']}\n{area}\n"
                  f"Inicia sesión con tu usuario y la contraseña que elegiste. Si la olvidas, usa "
                  f"«¿Olvidaste tu contraseña?» en la pantalla de acceso.\n\n"
                  f"Si tú no creaste esta cuenta, avisa al administrador del sistema.\n{_pie()}",
                  tipo="cuenta")
    for admin in administradores:
        correo.enviar(admin["correo"], f"[SIGSAT] Nueva cuenta registrada: {cuenta['nombre']}",
                      f"Hola {admin['nombre']},\n\nUna persona creó su cuenta desde el inicio de sesión:\n\n"
                      f"  Nombre: {cuenta['nombre']}\n  Usuario: {cuenta['usuario']}\n  Correo: {cuenta['correo']}\n{area}\n"
                      f"Entró como {cuenta['rol']}. Si debe ser Técnico, cámbiale el rol en "
                      f"SIGSAT → Administración → Usuarios y roles.\n{_pie()}",
                      tipo="cuenta")
