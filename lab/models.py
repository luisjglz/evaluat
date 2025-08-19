from django.db import models

class Laboratorio(models.Model):
    nombre = models.CharField(max_length=200)
    clave = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name