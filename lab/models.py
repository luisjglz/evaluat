from django.db import models
from django.conf import settings

class Laboratorio(models.Model):
    nombre = models.CharField(max_length=255)
    clave = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class user_laboratorio(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='laboratorios')
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='usuarios')

    def __str__(self):
        return f"{self.user} - {self.laboratorio}"
    
# New model to link Laboratorio and Programa
class programa_laboratorio(models.Model):
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='programas')
    programa = models.ForeignKey("Programa", on_delete=models.PROTECT, related_name='laboratorios')

    def __str__(self):
        return f"{self.laboratorio} - {self.programa}"

class Programa(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.nombre
    
class Prueba(models.Model):
    programa = models.ForeignKey("Programa", on_delete=models.PROTECT, related_name='pruebas')
    nombre = models.CharField(max_length=255)
    # metodo_analitico = models.ForeignKey(MetodoAnalitico, on_delete=models.PROTECT, related_name='pruebas')
    # instrumento = models.ForeignKey(Instrumento, on_delete=models.PROTECT, related_name='pruebas')
    # reactivo = models.ForeignKey(Reactivo, on_delete=models.PROTECT, related_name='pruebas')
    instrumento_default = models.ForeignKey('Instrumentos', on_delete=models.PROTECT, related_name='pruebas_default', null=True, blank=True)
    metodo_analitico_default = models.ForeignKey('MetodosAnaliticos', on_delete=models.PROTECT, related_name='pruebas_default', null=True, blank=True)
    reactivo_default = models.ForeignKey('Reactivos', on_delete=models.PROTECT, related_name='pruebas_default', null=True, blank=True)
    unidad_de_medida_default = models.ForeignKey('UnidadesDeMedida', on_delete=models.PROTECT, related_name='pruebas', null=True, blank=True)

    def __str__(self):
        return self.nombre
    
class Instrumentos(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    default = models.BooleanField(default=False)
    # defaultEnPruebas = models.ManyToManyField('Prueba', related_name='instrumentos', blank=True)

    def __str__(self):
        return self.nombre
    
class MetodosAnaliticos(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    default = models.BooleanField(default=False)
    # defaultEnPruebas = models.ManyToManyField('Prueba', related_name='modelos_analíticos', blank=True)

    def __str__(self):
        return self.nombre

class Reactivos(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    default = models.BooleanField(default=False)
    # defaultEnPruebas = models.ManyToManyField('Prueba', related_name='reactivos', blank=True)

    def __str__(self):
        return self.nombre

class UnidadesDeMedida(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    # defaultEnPruebas = models.ManyToManyField('Prueba', related_name='unidades', blank=True)

    def __str__(self):
        return self.nombre

class PropiedadesARevisar(models.Model):
    tipoElemento = models.CharField(max_length=255)
    valor = models.CharField(max_length=255)
    status = models.IntegerField()  # 0: pendiente, 1: aprobado, 2: rechazado

    def __str__(self):
        return self.nombre
    
class Dato(models.Model):
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='datos')
    prueba = models.ForeignKey(Prueba, on_delete=models.PROTECT, related_name='datos')
    valor = models.FloatField()
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.prueba} - {self.valor} - {self.fecha}"

class KitDeReactivos(models.Model):
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='kits_de_reactivos')
    fechaDeRecepcion = models.DateTimeField(auto_now_add=True)
    estadoDelProducto = models.IntegerField()  # del 1 al 10
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre