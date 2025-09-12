from django.db import transaction
from ..models import Instrumento, MetodoAnalitico, Reactivo, UnidadDeMedida

TIPO_TO_MODEL = {
    "instrumento": Instrumento,
    "metodo": MetodoAnalitico,
    "reactivo": Reactivo,
    "unidad": UnidadDeMedida,
}

@transaction.atomic
def materializar_propuesta(propuesta):
    """
    Crea (o reusa) un registro en la tabla maestra correspondiente al tipo de la propuesta.
    Debe llamarse cuando propuesta.status == 1 (Aprobado).
    """
    modelo = TIPO_TO_MODEL.get(propuesta.tipoElemento)
    if not modelo:
        return None

    # Evitar duplicados por nombre (case-insensitive)
    existente = modelo.objects.filter(nombre__iexact=propuesta.valor).first()
    if existente:
        return existente

    # Algunos modelos tienen 'descripcion'; si no aplica, ignora el kwarg
    campos = {"nombre": propuesta.valor}
    if hasattr(modelo, "descripcion"):
        campos["descripcion"] = propuesta.descripcion or ""

    creado = modelo.objects.create(**campos)
    return creado
