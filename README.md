# SIGSAT — Prototipo de escritorio (Python + PySide6)

Sistema de Gestión de Solicitudes y Seguimiento de Atención de Tickets (TechSolve México). Prototipo de
interfaz con capa de datos en memoria (`datos.py`) que se **guarda sola en disco** (`datos_sigsat/`) con
respaldo diario; sirve para validar flujos y reglas de negocio antes de conectar el back-end.

## Instalación y ejecución

```bash
pip install -r requirements.txt     # PySide6, openpyxl (Excel), reportlab (PDF)
python main.py                      # guarda los datos en disco
python main.py --reiniciar          # vuelve a los datos de ejemplo (antes hace un respaldo)
python main.py --sin-guardar        # no escribe nada en disco
python -m unittest discover -s pruebas -t .      # pruebas (≈3 min; usan datos en memoria, nunca datos_sigsat/)
```

> Si abres datos guardados por una versión anterior (modelo de 4 roles), la aplicación los respalda en
> `antes_de_actualizar` y arranca con los datos de ejemplo del modelo actual (`VERSION_ESTADO = 3`).

## Los 3 roles

| Rol | Qué hace | Menú |
|---|---|---|
| **Representante de Área** | Pertenece a un **área** y una **sucursal**. Envía solicitudes, ve el estatus que va marcando el técnico y **califica el servicio (1–5)** una vez *Finalizado*. | Nueva solicitud · Mis solicitudes · Mesa de Servicio |
| **Técnico** | Atiende las solicitudes que el Administrador le asigna. Al abrir un reporte «Sin visualizar» pasa solo a **Visualizado**; luego **En proceso** y **Finalizado** (con comentario obligatorio). Solo avanza, no retrocede. | Mis reportes (con su historial de atención) · Mesa de Servicio |
| **Administrador** | Mantenimiento del sistema, **distribución** (asignar/reasignar) de solicitudes, verificación de reportes y avance. | Panel de indicadores · Solicitudes · Reportes (con el historial de atención) · Administración · Mesa de Servicio |

**Login:** usuario y contraseña, «¿Olvidaste tu contraseña?» y «Creación de cuenta».

- **Creación de cuenta (autorregistro):** la persona escribe nombre, correo, usuario, contraseña (dos veces), área y
  sucursal, y su cuenta queda **creada y activa al instante**; ya no la crea un administrador. Siempre entra como
  *Representante de Área*. Si alguien debe ser *Técnico*, el Administrador le cambia el rol en Administración →
  Usuarios y roles (también puede desactivar o eliminar cuentas). Usuario y correo no se repiten, la contraseña
  se guarda como hash y nunca se envía por correo, y hay un límite de 20 cuentas nuevas por hora.
- **Recuperar contraseña (3 pantallas):** 1) usuario o correo → se envía un código; 2) código recibido (se comprueba
  antes de seguir); 3) contraseña nueva y su confirmación.

## Reglas principales

- **Estatus:** Sin visualizar → Visualizado → En proceso → Finalizado. «Sin visualizar» lo pone el sistema al asignar.
- **Prioridad:** sale del **tiempo estimado de solución del tipo** (a menor tiempo, mayor prioridad):
  Alta ≤ 24 h · Media ≤ 72 h · Baja > 72 h. La fecha límite es creación + ese tiempo. Una solicitud vencida se sigue
  atendiendo y cuenta como «fuera de tiempo» en los indicadores.
- **Sin asignación automática:** toda solicitud nueva queda «Sin asignar» y se avisa por correo a los administradores.
- **Catálogos** (áreas, sucursales, tipos con su tiempo estimado): solo se **agregan**; no se editan ni eliminan.
- **Adjuntos:** solo al registrar la solicitud (hasta 5 archivos de 5 MB, contenido verificado).
- **Calificación:** una vez, solo el representante dueño, solo si está *Finalizado*; no cambia el estatus.
- **Historial de atención (antes «Bitácora»):** ya no es una sección aparte: se consulta desde **Reportes**, al elegir un
  reporte. Es inmutable y está encadenado con hashes (el Administrador ve la verificación de integridad). El
  Administrador ve todos los reportes; el Técnico, los suyos.
- **Finalizado:** aparece en Reportes (y en su filtro de estatus) y lo ven el Representante, el Técnico y el
  Administrador, también con un aviso en el detalle. Solo el Técnico asignado avanza el estatus.
- **Seguridad:** contraseñas con scrypt, bloqueo por intentos fallidos, cierre de sesión por inactividad.
- **Correos:** modo desarrollo (archivos `.eml`, visibles en Administración → Correos enviados) o SMTP real por variables `SIGSAT_SMTP_*`.

## Pantallas del Administrador

1. **Panel de indicadores** (se actualiza cada 30 s): totales, tiempo promedio, fuera de tiempo, efectividad, satisfacción,
   por asignar, vencidas; desglose por estatus, área y sucursal; carga por técnico. Pestaña *Análisis y exportación* (Excel/PDF).
2. **Solicitudes:** Folio, Tipo, Área, Solicitante, Prioridad, Estatus, Técnico asignado (o «Sin asignar»); doble clic para asignar.
3. **Reportes:** una sola vista con el estatus de cada técnico, **incluidos los Finalizados**; filtros por fecha, estatus,
   prioridad, área y técnico. Al elegir un reporte aparece abajo su **historial de atención** (qué pasó, cuándo y quién).
4. **Administración:** usuarios y roles, catálogos, correos enviados y respaldos.
5. **Mesa de Servicio:** conversaciones con Representantes y Técnicos.

## Cuentas de prueba

| Usuario | Contraseña | Rol |
|---|---|---|
| direccion | Dir_000 | Administrador |
| sestrada | Est_001 | Técnico |
| dlopez | Lop_002 | Técnico |
| zarriaga | Arr_003 | Técnico |
| gsantiago | San_004 | Técnico |
| jmontes | Mon_005 | Técnico |
| areyes | Rey_006 | Representante (Contabilidad · Matriz CDMX) |
| cpena | Pen_007 | Representante (Ventas · Monterrey) |
| lrios | Rio_008 | Representante (Recursos Humanos · Guadalajara) |

Datos de ejemplo: 7 solicitudes en todos los estatus (0003 y 0006 sin asignar, 0005 finalizada pendiente de calificar),
3 conversaciones de la Mesa de Servicio.

## Estructura

```
main.py · estilos.py · permisos.py · seguridad.py · persistencia.py · correo.py · notificaciones.py
datos.py          # reglas de negocio y datos (ValueError con mensajes en español, PermissionError)
reportes.py       # exportación a Excel y PDF
archivos.py       # validación de adjuntos
ventana_login.py · ventana_principal.py     # login y ventana con menú por rol
vistas/           # nueva_solicitud, mis_solicitudes, bandeja_reportes, solicitudes_admin, reportes_vista,
                  # dashboard_admin, administracion, admin_catalogos, mesa_ti, …
widgets/          # detalle_solicitud, dialogo_usuario, dialogo_registro, dialogos_catalogo, …
pruebas/          # unittest (Qt en modo offscreen)
```

La interfaz solo muestra; toda regla de negocio y permiso vive en `datos.py` / `permisos.py`.


## Generar el instalador de Windows (.exe)

Opción A, en tu PC con Windows: instala Python 3.10+ e [Inno Setup 6](https://jrsoftware.org/isinfo.php) y ejecuta
`build_windows.bat` dentro de esta carpeta. Genera `dist\SIGSAT\SIGSAT.exe` y `salida\SIGSAT_Instalador.exe`.

Opción B, desde GitHub: en la pestaña **Actions** ejecuta «Construir instalador de Windows»; al terminar, descarga el
artefacto `SIGSAT_Instalador`.

La versión instalada guarda sus datos en `%LOCALAPPDATA%\SIGSAT\datos_sigsat` (no se borran al desinstalar).
