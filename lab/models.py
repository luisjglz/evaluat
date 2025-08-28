from django.db import models
from django.conf import settings

class Laboratorio(models.Model):
    nombre = models.CharField(max_length=255)
    clave = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class user_laboratorio(models.Model):
    user_id = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='laboratorios')
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='usuarios')

    def __str__(self):
        return f"{self.user_id} - {self.laboratorio}"
    
# New model to link Laboratorio and Programa
class programa_laboratorio(models.Model):
    laboratorio_id = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='programas')
    programa_id = models.ForeignKey("Programa", on_delete=models.PROTECT, related_name='laboratorios')

    def __str__(self):
        return f"{self.laboratorio_id} - {self.programa_id}"

class Programa(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.nombre
    
class Prueba(models.Model):
    programa_id = models.ForeignKey("Programa", on_delete=models.PROTECT, related_name='pruebas')
    nombre = models.CharField(max_length=255)
    # metodo_analitico = models.ForeignKey(MetodoAnalitico, on_delete=models.PROTECT, related_name='pruebas')
    # instrumento = models.ForeignKey(Instrumento, on_delete=models.PROTECT, related_name='pruebas')
    # reactivo = models.ForeignKey(Reactivo, on_delete=models.PROTECT, related_name='pruebas')
    instrumento_seleccionado_id = models.ForeignKey('Instrumento', on_delete=models.PROTECT, related_name='pruebas_instrumento_seleccionado', null=True, blank=True)
    metodo_analitico_seleccionado_id = models.ForeignKey('MetodoAnalitico', on_delete=models.PROTECT, related_name='pruebas_metodo_analitico_seleccionado', null=True, blank=True)
    reactivo_seleccionado_id = models.ForeignKey('Reactivo', on_delete=models.PROTECT, related_name='pruebas_reactivo_seleccionado', null=True, blank=True)
    unidad_de_medida_seleccionado_id = models.ForeignKey('UnidadDeMedida', on_delete=models.PROTECT, related_name='pruebas_unidad_de_medida_seleccionado', null=True, blank=True)

    def __str__(self):
        return self.nombre
    
class Instrumento(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre
    
class MetodoAnalitico(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre

class Reactivo(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre

class UnidadDeMedida(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre

class PropiedadARevisar(models.Model):
    tipoElemento = models.CharField(max_length=255)
    valor = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    status = models.IntegerField()  # 0: pendiente, 1: aprobado, 2: rechazado

    def __str__(self):
        return f"{self.tipoElemento} - {self.valor}"
    
class Dato(models.Model):
    laboratorio_id = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='datos')
    prueba_id = models.ForeignKey(Prueba, on_delete=models.PROTECT, related_name='datos')
    valor = models.FloatField()
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.prueba_id} - {self.valor} - {self.fecha}"

class KitDeReactivos(models.Model):
    laboratorio_id = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='kits_de_reactivos')
    fechaDeRecepcion = models.DateTimeField(auto_now_add=True)
    estadoDelProducto = models.IntegerField()  # del 1 al 10
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Kit de Reactivos en {self.laboratorio_id.nombre} recibido el {self.fechaDeRecepcion.strftime('%Y-%m-%d %H:%M:%S')}"