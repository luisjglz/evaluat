from django.contrib import admin, messages
from django.apps import apps
from django.db import transaction
from .models import PropiedadARevisar
from .utils.propuestas import materializar_propuesta
from lab.models import Laboratorio
from django.utils import timezone
from lab.utils.estados import filled_all_month

# Import only what we need for the custom logic
from .models import Laboratorio, ProgramaLaboratorio, Prueba, LaboratorioPruebaConfig, Reporte

# ------------ 1) Auto-register all models EXCEPT the ones we want custom ------------
lab_app = apps.get_app_config('lab')

excluded_models = {
    'LogEntry', 'Permission', 'Groups', 'Session', 'ContentType',
    'ProgramaLaboratorio', 'Laboratorio', 'LaboratorioPruebaConfig', 'ProgramaLaboratorio',
    'PropiedadARevisar', 'Reporte' # <-- handled manually below
}

for model in apps.get_models():
    name = model.__name__
    if name in excluded_models:
        continue
    if model in admin.site._registry:
        continue  # por si el modelo a registrar ya está registrado por otra parte
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass


# ------------ 2) Custom admin for ProgramaLaboratorio with post-save creation ------------
@admin.register(ProgramaLaboratorio)
class ProgramaLaboratorioAdmin(admin.ModelAdmin):
    list_display = ("id", "laboratorio_id", "programa_id")
    list_filter  = ("laboratorio_id", "programa_id")
    search_fields = ("laboratorio_id__nombre", "programa_id__nombre")

    def save_model(self, request, obj, form, change):
        """
        After saving ProgramaLaboratorio, create a LaboratorioPruebaConfig row
        for each Prueba in the selected Programa, tied to the selected Laboratorio.
        Copies defaults from Prueba.*_seleccionado_id into the config row.
        """
        # Save the ProgramaLaboratorio record first
        super().save_model(request, obj, form, change)

        # laboratorio = obj.laboratorio_id   # FK to Laboratorio
        # programa    = obj.programa_id      # FK to Programa

        # # Fetch all Pruebas for this Programa, including selected default relations
        # pruebas_qs = Prueba.objects.filter(programa_id=programa).select_related(
        #     "instrumento_seleccionado_id",
        #     "metodo_analitico_seleccionado_id",
        #     "reactivo_seleccionado_id",
        #     "unidad_de_medida_seleccionado_id",
        # )

        # # Avoid duplicates: find existing configs for (laboratorio, prueba)
        # existing_prueba_ids = set(
        #     LaboratorioPruebaConfig.objects
        #     .filter(laboratorio_id=laboratorio, prueba_id__in=pruebas_qs)
        #     .values_list("prueba_id_id", flat=True)
        # )

        # to_create = []
        # for p in pruebas_qs:
        #     if p.id in existing_prueba_ids:
        #         continue

        #     to_create.append(
        #         LaboratorioPruebaConfig(
        #             laboratorio_id=laboratorio,
        #             prueba_id=p,
        #             instrumento_id=getattr(p, "instrumento_seleccionado_id", None),
        #             metodo_analitico_id=getattr(p, "metodo_analitico_seleccionado_id", None),
        #             reactivo_id=getattr(p, "reactivo_seleccionado_id", None),
        #             unidad_de_medida_id=getattr(p, "unidad_de_medida_seleccionado_id", None),
        #         )
        #     )

        # created_count = 0
        # if to_create:
        #     # UniqueConstraint on (laboratorio_id, prueba_id) prevents dupes
        #     with transaction.atomic():
        #         LaboratorioPruebaConfig.objects.bulk_create(
        #             to_create, ignore_conflicts=True
        #         )
        #     created_count = len(to_create)

        # if created_count:
        #     messages.success(
        #         request,
        #         f"Se crearon {created_count} configuraciones en LaboratorioPruebaConfig "
        #         f"para {laboratorio} (programa: {programa})."
        #     )
        # else:
        #     messages.info(
        #         request,
        #         "No se crearon nuevas configuraciones; ya existían para este laboratorio y programa."
        #     )

# ------------ 3) Custom admin for Laboratorio to manage override flags for editing the configurations ------------
@admin.register(Laboratorio)
class LaboratorioAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "clave", "estado", "edicion_hasta_dia", "corte_captura_dia",
                    "override_edicion_activa", "override_edicion_hasta",
                    "override_captura_activa", "override_captura_hasta")
    list_editable = ("estado",)
    list_filter = ("estado", "override_edicion_activa", "override_captura_activa")
    search_fields = ("nombre", "clave")
    fields = ("nombre", "clave", "estado", "edicion_hasta_dia", "corte_captura_dia",
              "override_edicion_activa", "override_edicion_hasta",
              "override_captura_activa", "override_captura_hasta")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Si se desactiva override de captura, NO promover antes del corte
        if change and form and ('override_captura_activa' in form.changed_data) and obj.estado == 2:
            hoy = timezone.localdate()
            corte = getattr(obj, 'corte_captura_dia', 25) or 25
            cap_override_vigente = (
                getattr(obj, 'override_captura_activa', False)
                and (obj.override_captura_hasta is None or hoy <= obj.override_captura_hasta)
            )
            cap_window_open = cap_override_vigente or (hoy.day <= corte)
            if not cap_window_open:
                mes_vigente = hoy.replace(day=1)
                if filled_all_month(obj, mes_vigente):
                    obj.estado = 3
                    obj.save(update_fields=['estado'])


@admin.register(LaboratorioPruebaConfig)
class LaboratorioPruebaConfigAdmin(admin.ModelAdmin):
    list_display = ("laboratorio_id", "prueba_id", "instrumento_id", "metodo_analitico_id", "reactivo_id", "unidad_de_medida_id", "bloqueada")
    list_editable = ("bloqueada",)  # editable en la lista para rapidez  # [9][19]

# ------------ 4) Custom admin for PropiedadARevisar with action to approve and materialize ------------
@admin.register(PropiedadARevisar)
class PropiedadARevisarAdmin(admin.ModelAdmin):
    list_display  = ("tipoElemento", "valor", "status", "created_at")
    list_filter   = ("status", "tipoElemento", "created_at")
    search_fields = ("valor", "descripcion")
    actions       = ["aprobar_y_materializar"]

    @admin.action(description="Approve and materialize selected proposals")
    @transaction.atomic
    def aprobar_y_materializar(self, request, queryset):
        aprobadas = 0
        creadas   = 0
        for prop in queryset.select_for_update():
            # Aprobar si no lo está
            if prop.status != 1:
                prop.status = 1  # Aprobado
                prop.save(update_fields=["status"])
                aprobadas += 1
            # Crear en tabla maestra (idempotente)
            creado = materializar_propuesta(prop)
            if creado:
                creadas += 1
        self.message_user(
            request,
            f"Propuestas aprobadas: {aprobadas}. Registros creados/confirmados en tablas maestras: {creadas}.",
            level=messages.SUCCESS
        )
    # Cubrir el caso de edición individual en el admin
    @transaction.atomic
    def save_model(self, request, obj, form, change):
        previo = None
        if change:
            try:
                previo = PropiedadARevisar.objects.get(pk=obj.pk)
            except PropiedadARevisar.DoesNotExist:
                previo = None

        super().save_model(request, obj, form, change)

        # Si cambió a Aprobado (1), materializar
        if obj.status == 1 and (not previo or previo.status != 1):
            materializar_propuesta(obj)

# admin.py
@admin.register(Reporte)
class ReporteAdmin(admin.ModelAdmin):
    list_display = ('laboratorio', 'tipo', 'estado', 'mes', 'fecha', 'nombre')
    list_filter = ('laboratorio', 'tipo', 'estado', 'mes')
    search_fields = ('nombre',)
    filter_horizontal = ('programas', 'pruebas')

# Branding del panel de administración
admin.site.site_header = "EvaluaT"
admin.site.site_title = "EvaluaT"
admin.site.index_title = "Panel de administración"
