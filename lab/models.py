from django.db import models
from django.conf import settings

class Laboratorio(models.Model):
    nombre = models.CharField(max_length=255)
    clave = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class user_laboratorio(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='laboratorios')
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.CASCADE, related_name='usuarios')

    def __str__(self):
        return f"{self.user} - {self.laboratorio}"

class Programa(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.nombre
    
class MetodoAnalitico(models.Model):
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return self.nombre


class Instrumento(models.Model):
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return self.nombre


class Reactivo(models.Model):
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return self.nombre


class UnidadDeMedida(models.Model):
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return self.nombre


class Prueba(models.Model):
    nombre = models.CharField(max_length=255)
    metodo_analitico = models.ForeignKey(MetodoAnalitico, on_delete=models.CASCADE, related_name='pruebas')
    instrumento = models.ForeignKey(Instrumento, on_delete=models.CASCADE, related_name='pruebas')
    reactivo = models.ForeignKey(Reactivo, on_delete=models.CASCADE, related_name='pruebas')
    unidad_de_medida = models.ForeignKey(UnidadDeMedida, on_delete=models.CASCADE, related_name='pruebas')
    programa = models.ForeignKey("Programa", on_delete=models.CASCADE, related_name='pruebas')
    
    def __str__(self):
        return self.nombre