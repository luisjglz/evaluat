from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("", include(("lab.urls", "lab"), namespace="lab")),  # namespace activo
    path("admin/", admin.site.urls),
]
