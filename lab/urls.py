# lab/urls.py
from django.urls import path
from . import views

# Opcional pero recomendado: declarar un namespace para la app
app_name = "lab"  # si activas esto, deberás llamar {% url 'lab:save_config' %} en el template

urlpatterns = [
    path("", views.homepage, name='homepage'),                # si vas a usar homepage en raíz
    path("select-lab/", views.select_lab, name='select_lab'), # protegida con login_required
    path("logout/", views.logout_user, name='logout'),
    path("lab/", views.LabMainView.as_view(), name='labmainview'),
    path("accept-configurations/", views.accept_configurations, name='accept_configurations'),
    path("config/save/", views.crear_o_actualizar_configuracion, name="save_config"),
    path("config/update/<int:config_id>/", views.actualizar_configuracion, name="update_config"),
]
