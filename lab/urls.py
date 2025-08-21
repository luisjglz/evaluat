from django.conf import settings
from django.urls import path
from . import views
from django.conf.urls.static import static

from . import views

urlpatterns = [
    path("", views.homepage, name='homepage'),
    path('logout', views.logout_user, name='logout'),
    path('lab', views.LabMainView.as_view(), name='labmainview'),
]