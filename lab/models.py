from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import date
from django.db.models import Q
import secrets
# ----------- Helpers -----------
# Helper para fecha por defecto
def first_day_of_current_month():
    # usa zona horaria de Django y normaliza al día 1
    return timezone.now().date().replace(day=1)

# ----------- Models -----------

class Laboratorio(models.Model):
    nombre = models.CharField(max_length=255)
    clave = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    edicion_hasta_dia = models.PositiveSmallIntegerField(default=15) # Con esto un admin puede cambiar el día límite (p.ej. 15),
    override_edicion_activa = models.BooleanField(default=False) # activar una excepción y opcionalmente fijar una fecha hasta cuándo aplica.
    override_edicion_hasta = models.DateField(null=True, blank=True)
    corte_captura_dia = models.PositiveSmallIntegerField(default=25)
    override_captura_activa = models.BooleanField(default=False)
    override_captura_hasta = models.DateField(null=True, blank=True)
    estado = models.PositiveSmallIntegerField(
        choices=[(1, "Configuración"), (2, "Registro"), (3, "Consulta")],
        default=1
    )
    
    def __str__(self):
        return self.nombre

class UserLaboratorio(models.Model):
    user_id = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='laboratorios')
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='usuarios')

    def __str__(self):
        return f"{self.user_id} - {self.laboratorio}"
    
    class Meta:
        verbose_name_plural = "UserLaboratorio"
    
class Programa(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.nombre

class ProgramaLaboratorio(models.Model):
    laboratorio_id = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='programas')
    programa_id = models.ForeignKey(Programa, on_delete=models.PROTECT, related_name='laboratorios')

    def __str__(self):
        return f"{self.laboratorio_id} - {self.programa_id}"
    
    class Meta:
        verbose_name_plural = "ProgramaLaboratorio"
    
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
    class Meta:
        verbose_name_plural = "MetodoAnalitico"

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
    
    class Meta:
        verbose_name_plural = "UnidadDeMedida"


class PropiedadARevisar(models.Model):
    TIPO_ELEMENTO_CHOICES = (
        ("instrumento", "Instrumento"),
        ("metodo", "Método Analítico"),
        ("reactivo", "Reactivo"),
        ("unidad", "Unidad"),
    )
    STATUS_CHOICES = (
        (0, "Pendiente"),
        (1, "Aprobado"),
        (2, "Rechazado"),
    )

    tipoElemento = models.CharField(max_length=50, choices=TIPO_ELEMENTO_CHOICES)
    valor = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    status = models.IntegerField(choices=STATUS_CHOICES, default=0)
    propuesto_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='propuestas',
        null=True,
        blank=True,
    )
    moderation_nonce = models.CharField(max_length=64, blank=True, null=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='propuestas_resueltas')
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def ensure_nonce(self, force=False):
        if force or not self.moderation_nonce:
            self.moderation_nonce = secrets.token_urlsafe(24)

    class Meta:
        verbose_name_plural = "Propiedades a Revisar"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['propuesto_por']),
        ]

    def __str__(self):
        return f"{self.get_tipoElemento_display()} - {self.valor} ({self.get_status_display()})"

class Prueba(models.Model):
    programa_id = models.ForeignKey(Programa, on_delete=models.PROTECT, related_name='pruebas')
    nombre = models.CharField(max_length=255)
    instrumento_seleccionado_id = models.ForeignKey(Instrumento, on_delete=models.PROTECT, related_name='pruebas_instrumento_seleccionado_id', null=True, blank=True)
    metodo_analitico_seleccionado_id = models.ForeignKey(MetodoAnalitico, on_delete=models.PROTECT, related_name='pruebas_metodo_analitico_seleccionado_id', null=True, blank=True)
    reactivo_seleccionado_id = models.ForeignKey(Reactivo, on_delete=models.PROTECT, related_name='pruebas_reactivo_seleccionado_id', null=True, blank=True)
    unidad_de_medida_seleccionado_id = models.ForeignKey(UnidadDeMedida, on_delete=models.PROTECT, related_name='pruebas_unidad_de_medida_seleccionado_id', null=True, blank=True)

    def __str__(self):
        return self.nombre
    
class LaboratorioPruebaConfig(models.Model):
    laboratorio_id = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='laboratorios')
    prueba_id = models.ForeignKey(Prueba, on_delete=models.PROTECT, related_name='pruebas')
    instrumento_id = models.ForeignKey(Instrumento, on_delete=models.PROTECT, related_name='laboratorio_prueba_config_instrumento_id', null=True, blank=True)
    metodo_analitico_id = models.ForeignKey(MetodoAnalitico, on_delete=models.PROTECT, related_name='laboratorio_prueba_config_metodo_analitico_id', null=True, blank=True)
    reactivo_id = models.ForeignKey(Reactivo, on_delete=models.PROTECT, related_name='laboratorio_prueba_config_pruebas_reactivo_id', null=True, blank=True)
    unidad_de_medida_id = models.ForeignKey(UnidadDeMedida, on_delete=models.PROTECT, related_name='laboratorio_prueba_config_pruebas_unidad_de_medida_id', null=True, blank=True)
    bloqueada = models.BooleanField(default=False)  # bloqueo puntual por configuración

    def __str__(self):
        return f"{self.laboratorio_id} - {self.prueba_id}"
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['laboratorio_id', 'prueba_id'], name='uq_laboratorio_prueba')
        ]
        verbose_name_plural = "LaboratorioPruebaConfig"

class Dato(models.Model):
    laboratorio_id = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='datos')
    prueba_id = models.ForeignKey(Prueba, on_delete=models.PROTECT, related_name='datos')
    valor = models.FloatField()
    fecha = models.DateTimeField(auto_now_add=True)
    mes = models.DateField(default=first_day_of_current_month)  # primer día del mes actual

    def __str__(self):
        return f"{self.laboratorio_id} - {self.prueba_id} - {self.valor} - {self.fecha}"
    
    class Meta:
        constraints = [
            # Restricción compuesta que evita duplicados por mes
            models.UniqueConstraint(
                fields=['laboratorio_id', 'prueba_id', 'mes'],
                name='uq_dato_lab_prueba_mes'
            )
        ]


class KitDeReactivos(models.Model):
    laboratorio_id = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='kits_de_reactivos')
    fechaDeRecepcion = models.DateTimeField(auto_now_add=True)
    estadoDelProducto = models.IntegerField()  # del 1 al 10
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Kit de Reactivos en {self.laboratorio_id.nombre} recibido el {self.fechaDeRecepcion.strftime('%Y-%m-%d %H:%M:%S')}"
    
    class Meta:
        verbose_name_plural = "KitDeReactivos"

class Reporte(models.Model):
    TIPO_CHOICES = (('mensual', 'Mensual'), ('anual', 'Anual'))
    ESTADO_CHOICES = (('trabajando', 'Trabajando'), ('completado', 'Completado'))

    laboratorio = models.ForeignKey('Laboratorio', on_delete=models.CASCADE, related_name='reportes')
    # mes se usa como referencia temporal para mensual o año (usando 01-01) para anual
    mes = models.DateField(help_text="Primer día del mes (YYYY-MM-01)")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='mensual')
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default='trabajando')
    # fecha que muestra la tabla: si trabajando => fecha de cierre de captura; si completado => fecha de subida
    fecha = models.DateField(help_text="Fecha de referencia mostrada en tabla")
    nombre = models.CharField(max_length=200)
    archivo = models.FileField(upload_to='reportes/%Y/%m/', blank=True, null=True)
    programas = models.ManyToManyField('Programa', related_name='reportes', blank=True)
    pruebas = models.ManyToManyField('Prueba', related_name='reportes', blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.nombre} ({self.mes:%Y-%m})'

    class Meta:
        constraints = [
            # Un reporte por laboratorio, tipo y periodo (mes: YYYY-MM-01)
            models.UniqueConstraint(fields=['laboratorio', 'tipo', 'mes'], name='uq_reporte_lab_tipo_mes'),
            # Si es anual, exigir que mes sea enero (primer día del año)
            models.CheckConstraint(name='ck_reporte_anual_mes_enero',
                                   check=Q(tipo='anual', mes__month=1, mes__day=1) | ~Q(tipo='anual')),
            # Si estado es completado, debe existir archivo
            models.CheckConstraint(name='ck_reporte_completado_con_archivo',
                                   check=Q(estado='completado', archivo__isnull=False) | ~Q(estado='completado')),
        ]

