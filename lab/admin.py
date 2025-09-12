from django.contrib import admin, messages
from django.apps import apps
from django.db import transaction

# Import only what we need for the custom logic
from .models import Laboratorio, ProgramaLaboratorio, Prueba, LaboratorioPruebaConfig

# ------------ 1) Auto-register all models EXCEPT the ones we want custom ------------
lab_app = apps.get_app_config('lab')

# Add ProgramaLaboratorio to the excluded list so we can register it with a custom admin below.
excluded_models = {
    'LogEntry', 'Permission', 'Groups', 'Session', 'ContentType',
    'ProgramaLaboratorio', 'Laboratorio', 'LaboratorioPruebaConfig', 'ProgramaLaboratorio'  # <-- handled manually below
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
    list_display = ("nombre", "edicion_hasta_dia", "override_edicion_activa", "override_edicion_hasta")
    fields = ("nombre", "clave", "edicion_hasta_dia", "override_edicion_activa", "override_edicion_hasta")
    # Admin estándar para alternar bandera y fecha límite de override.  # [9]

@admin.register(LaboratorioPruebaConfig)
class LaboratorioPruebaConfigAdmin(admin.ModelAdmin):
    list_display = ("laboratorio_id", "prueba_id", "instrumento_id", "metodo_analitico_id", "reactivo_id", "unidad_de_medida_id", "bloqueada")
    list_editable = ("bloqueada",)  # editable en la lista para rapidez  # [9][19]