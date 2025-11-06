# lab/utils/estados.py
from django.utils import timezone
from django.db.models import Count
from lab.models import LaboratorioPruebaConfig, Dato  # ajusta import según tu estructura

def filled_all_month(lab, mes):
    """
    True si TODAS las pruebas configuradas del laboratorio `lab`
    tienen al menos un Dato en el mes `mes` (date con day=1).
    """
    # Pruebas configuradas (ids únicos)
    pruebas_cfg = list(
        LaboratorioPruebaConfig.objects
        .filter(laboratorio_id=lab.id)
        .values_list('prueba_id', flat=True)
        .distinct()
    )
    if not pruebas_cfg:
        return False  # sin configuración no se considera completo

    # Datos presentes en el mes por prueba
    datos_por_prueba = (
        Dato.objects
        .filter(laboratorio_id=lab.id, mes=mes, prueba_id__in=pruebas_cfg)
        .values('prueba_id')
        .annotate(n=Count('id'))
    )
    pruebas_con_dato = {row['prueba_id'] for row in datos_por_prueba if row['n'] > 0}
    return set(pruebas_cfg).issubset(pruebas_con_dato)

def es_mes_completo(lab):
    """Azúcar sintáctico usando el mes vigente (día 1 del mes actual)."""
    hoy = timezone.localdate()
    mes_vigente = hoy.replace(day=1)
    return filled_all_month(lab, mes_vigente)


def mes_vigente():
    # Mes en curso normalizado al día 1, consistente con uso en vistas
    today = timezone.localdate()
    return today.replace(day=1)

def avanzar_estado_si_corresponde(lab, persistir=True):
    """
    Si el lab está en estado 2 (Registro), override de captura NO está activo y el mes está completo,
    avanza a estado 3 (Consulta). Devuelve True si cambió el estado.
    """
    # Campos esperados en el modelo Laboratorio: estado y overridecapturaactiva
    if getattr(lab, 'estado', None) != 2:
        return False
    if getattr(lab, 'overridecapturaactiva', False):
        return False
    if not es_mes_completo(lab):
        return False
    lab.estado = 3
    if persistir:
        lab.save(update_fields=['estado'])
    return True

def puede_capturar_datos(lab):
    """
    True si la ventana de captura está ABIERTA para el laboratorio.
    Criterio: override_captura_activa (vigente) OR hoy.day <= corte_captura_dia.
    """
    hoy = timezone.localdate()
    corte = getattr(lab, 'corte_captura_dia', 25) or 25
    cap_override_vigente = (
        getattr(lab, 'override_captura_activa', False)
        and (lab.override_captura_hasta is None or hoy <= lab.override_captura_hasta)
    )
    return cap_override_vigente or (hoy.day <= corte)
