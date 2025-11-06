from django.utils import timezone

def get_allow_edit_now(lab, today=None):
    """
    Retorna True si el laboratorio puede editar configuraciones ahora:
    - Dentro de la ventana mensual (día actual <= edicion_hasta_dia o 15 por defecto)
    - O si hay override activo y vigente (override_edicion_activa y, si existe fecha fin, hoy <= override_edicion_hasta)
    """
    if not lab:
        return False
    if today is None:
        today = timezone.localdate()
    try:
        limite = getattr(lab, 'edicion_hasta_dia', None) or 15
    except Exception:
        limite = 15
    dentro_de_ventana = today.day <= limite
    override_activo = bool(
        getattr(lab, 'override_edicion_activa', False)
        and (
            getattr(lab, 'override_edicion_hasta', None) is None
            or today <= getattr(lab, 'override_edicion_hasta', None)
        )
    )
    return dentro_de_ventana or override_activo
