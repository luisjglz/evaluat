from django.contrib import admin
from django.urls import path, include

admin.site.site_header = "EvaluaT"
admin.site.site_title = "EvaluaT" 
admin.site.index_title = "Bienvenido a EvaluaT"

urlpatterns = [
    path("", include(("lab.urls", "lab"), namespace="lab")),  # namespace activo
    path("admin/", admin.site.urls),
]
