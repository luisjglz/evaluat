from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect


admin.site.site_header = "EvaluaT"
admin.site.site_title = "EvaluaT" 
admin.site.index_title = "Bienvenido a EvaluaT"

urlpatterns = [
    path("", include(("lab.urls", "lab"), namespace="lab")),  # namespace activo
    path('admin/logout/', lambda request: redirect('/logout/', permanent=False)),
    path("admin/", admin.site.urls),
]
