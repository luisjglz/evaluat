from django.utils import timezone

# --------------------------
# Función para determinar si se puede editar una configuración según la fecha
# --------------------------
def puede_editar_config(laboratorio, config):
    hoy = timezone.localdate()  # fecha “aware” en la zona activa  # [1]
    dentro_de_ventana = hoy.day <= (laboratorio.edicion_hasta_dia or 15)
    override_activo = laboratorio.override_edicion_activa and (
        laboratorio.override_edicion_hasta is None or hoy <= laboratorio.override_edicion_hasta
    )
    bloqueo_por_config = getattr(config, "bloqueada", False)
    return (dentro_de_ventana or override_activo) and not bloqueo_por_config  # [1][9]
