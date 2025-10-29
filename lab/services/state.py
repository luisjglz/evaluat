# lab/services/state.py
from datetime import date
from django.utils import timezone
from django.db import transaction
from lab.models import Laboratorio, Prueba, Dato

def today_local():
    return timezone.localdate()

def first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)

def filled_all_month(lab: Laboratorio, mes: date) -> bool:
    total_pruebas = Prueba.objects.count()
    capturadas = Dato.objects.filter(laboratorio=lab, mes=mes).count()
    return total_pruebas > 0 and capturadas >= total_pruebas

@transaction.atomic
def avanzar_estado_si_corresponde(lab: Laboratorio, mes: date, today: date | None = None) -> Laboratorio:
    if today is None:
        today = today_local()

    # 1 -> 2 al llegar al día 16 si no hay override de edición
    ed_override = lab.override_edicion_activa and (lab.override_edicion_hasta is None or today <= lab.override_edicion_hasta)
    if lab.estado == 1 and not ed_override and today.day >= 16:
        lab.estado = 2
        lab.save(update_fields=['estado', 'actualizado_en'])

    # 2 -> 3 por completitud sin override de captura
    cap_override = lab.override_captura_activa and (lab.override_captura_hasta is None or today <= lab.override_captura_hasta)
    if lab.estado == 2 and not cap_override and filled_all_month(lab, mes):
        lab.estado = 3
        lab.save(update_fields=['estado', 'actualizado_en'])

    return lab
