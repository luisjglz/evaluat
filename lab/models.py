from django.db import models

class Laboratorio(models.Model):
    nombre = models.CharField(max_length=200)
    clave = models.CharField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    contacto = models.CharField(blank=True)
    correo = models.EmailField(blank=True)

    def __str__(self):
        return self.nombre