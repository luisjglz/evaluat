from django.db import models

class Laboratorio(models.Model):
    nombre = models.CharField(max_length=255)
    clave = models.CharField(max_length=255)
    contacto = models.CharField(max_length=255)
    correo = models.EmailField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

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