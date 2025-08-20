from django.db import models

class Laboratorio(models.Model):
    nombre = models.CharField(max_length=255)
    clave = models.CharField(max_length=255)
    contacto = models.CharField(max_length=255)
    correo = models.EmailField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre