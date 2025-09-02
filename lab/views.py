import json, os
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy, reverse
#from .forms import *
from .models import *
from django.views.decorators.csrf import csrf_exempt
from django.core import serializers
from django.db.models import Q, Count, F, OuterRef, Subquery, DateTimeField, Exists
from datetime import datetime
from django.core.paginator import Paginator
from django.template.loader import get_template
#from xhtml2pdf import pisa
from io import BytesIO
from django.contrib.auth.hashers import make_password
from django.shortcuts import get_object_or_404
from collections import defaultdict
from pathlib import Path
from django.db import transaction
# Para creación de pruebas de manera segura y robusta
from django.db import transaction, IntegrityError
from django.contrib import messages
from django.views.decorators.http import require_http_methods

# Para la vista de aceptar las configuraciones
from .models import (
    LaboratorioPruebaConfig, PropiedadARevisar,
    Instrumento, MetodoAnalitico, Reactivo, UnidadDeMedida
)



def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")
# Create your views here.


def homepage(request):
    if (request.method == "POST"):
        username = request.POST["usuario"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.POST.get('next') or 'labmainview'
            return redirect(next_url)
        else:
            messages.error(request, ("Login o password incorrecto"))
            return redirect('homepage')
    return render(request, 'homepage.html', {'next': request.GET.get('next', '')})

def logout_user(request):
    logout(request)
    messages.success(request, ("Logged out"))
    return redirect('homepage')

class LabMainView(LoginRequiredMixin, View):
    template_name = 'labmain.html'
    login_url = 'homepage'

    def get(self, request):
        laboratorio = None
        if request.user.is_authenticated:
            user_lab = UserLaboratorio.objects.filter(user_id=request.user).first()
            if user_lab:
                laboratorio = user_lab.laboratorio

        if not laboratorio:
            messages.error(request, "No hay laboratorio asociado a tu usuario.")
            return redirect('homepage')

        programas_ids = ProgramaLaboratorio.objects.filter(
            laboratorio_id=laboratorio.id
        ).values_list('programa_id', flat=True)

        pruebas_laboratorio = Prueba.objects.filter(programa_id__in=programas_ids)
        accepted_configs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=laboratorio)
        accepted_prueba_ids = accepted_configs.values_list('prueba_id', flat=True)
        pending_pruebas = pruebas_laboratorio.exclude(id__in=accepted_prueba_ids)

        instrumentos = Instrumento.objects.all()
        metodos = MetodoAnalitico.objects.all()
        reactivos = Reactivo.objects.all()
        unidades = UnidadDeMedida.objects.all()

        context = {
            'pending_pruebas': pending_pruebas,
            'accepted_configs': accepted_configs,
            'instrumentos': instrumentos,
            'metodos': metodos,
            'reactivos': reactivos,
            'unidades': unidades,
            'laboratorio': laboratorio,
        }
        return render(request, self.template_name, context)
    

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction, IntegrityError
from .models import (
    UserLaboratorio, ProgramaLaboratorio, Prueba, LaboratorioPruebaConfig,
    Instrumento, MetodoAnalitico, Reactivo, UnidadDeMedida, PropiedadARevisar
)

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction, IntegrityError
from .models import (
    UserLaboratorio, ProgramaLaboratorio, Prueba, LaboratorioPruebaConfig,
    Instrumento, MetodoAnalitico, Reactivo, UnidadDeMedida, PropiedadARevisar
)

def accept_configurations(request):
    # 1. Obtener laboratorio asociado al usuario
    laboratorio = None
    if request.user.is_authenticated:
        user_lab = UserLaboratorio.objects.filter(user_id=request.user).first()
        if user_lab:
            laboratorio = user_lab.laboratorio

    if not laboratorio:
        messages.error(request, "No hay laboratorio asociado a tu usuario.")
        return redirect('labmainview')

    # 2. Programas y pruebas del laboratorio
    programas_ids = ProgramaLaboratorio.objects.filter(
        laboratorio_id=laboratorio.id
    ).values_list('programa_id', flat=True)

    pruebas_laboratorio = Prueba.objects.filter(programa_id__in=programas_ids)

    # 3. Configuraciones ya aceptadas
    accepted_configs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=laboratorio)
    accepted_prueba_ids = accepted_configs.values_list('prueba_id', flat=True)

    # Diccionario para obtener nombre de prueba por ID
    pruebas_dict = {prueba.id: prueba.nombre for prueba in Prueba.objects.filter(id__in=accepted_prueba_ids)}

    # Añadir atributo nombre_prueba a cada config aceptada
    for config in accepted_configs:
        config.nombre_prueba = pruebas_dict.get(config.prueba_id, "-")

    # 4. Pruebas pendientes de aceptar
    pending_pruebas = pruebas_laboratorio.exclude(id__in=accepted_prueba_ids)

    # 5. Opciones de configuración
    instrumentos = Instrumento.objects.all()
    metodos = MetodoAnalitico.objects.all()
    reactivos = Reactivo.objects.all()
    unidades = UnidadDeMedida.objects.all()

    # 6. Propuestas pendientes
    propuestas = PropiedadARevisar.objects.all()

    # POST: aceptar o proponer configuración
    if request.method == 'POST':
        prueba_id = request.POST.get('prueba_id')
        instrumento_id = request.POST.get('instrumento')
        metodo_id = request.POST.get('metodo')
        reactivo_id = request.POST.get('reactivo')
        unidad_id = request.POST.get('unidad')
        accion = request.POST.get('accion', 'aceptar')  # aceptar | proponer

        if not prueba_id:
            messages.error(request, "No se indicó la prueba a procesar.")
            return redirect('accept_configurations')

        try:
            prueba = Prueba.objects.get(id=prueba_id, programa_id__in=programas_ids)
        except Prueba.DoesNotExist:
            messages.error(request, "Prueba inválida o no pertenece a tu laboratorio.")
            return redirect('accept_configurations')

        if accion == 'aceptar':
            try:
                with transaction.atomic():
                    config, created = LaboratorioPruebaConfig.objects.get_or_create(
                        laboratorio_id=laboratorio,
                        prueba_id=prueba,
                        defaults={
                            'instrumento_id': Instrumento.objects.get(id=instrumento_id) if instrumento_id else None,
                            'metodo_analitico_id': MetodoAnalitico.objects.get(id=metodo_id) if metodo_id else None,
                            'reactivo_id': Reactivo.objects.get(id=reactivo_id) if reactivo_id else None,
                            'unidad_de_medida_id': UnidadDeMedida.objects.get(id=unidad_id) if unidad_id else None,
                        }
                    )
                    if not created:
                        updated = False
                        if instrumento_id:
                            config.instrumento_id = get_object_or_404(Instrumento, id=instrumento_id)
                            updated = True
                        if metodo_id:
                            config.metodo_analitico_id = get_object_or_404(MetodoAnalitico, id=metodo_id)
                            updated = True
                        if reactivo_id:
                            config.reactivo_id = get_object_or_404(Reactivo, id=reactivo_id)
                            updated = True
                        if unidad_id:
                            config.unidad_de_medida_id = get_object_or_404(UnidadDeMedida, id=unidad_id)
                            updated = True
                        if updated:
                            config.save()

                messages.success(request, f"Configuración para '{prueba.nombre}' aceptada correctamente.")
            except IntegrityError:
                messages.error(request, "Ya existe una configuración para esta prueba.")
            except Exception as e:
                print("Error creando configuración:", e)
                messages.error(request, "Ocurrió un error al aceptar la configuración.")

        else:
            # Proponer nueva configuración
            try:
                with transaction.atomic():
                    if instrumento_id:
                        instrumento = get_object_or_404(Instrumento, id=instrumento_id)
                        PropiedadARevisar.objects.create(
                            tipoElemento='Instrumento',
                            valor=instrumento.nombre,
                            descripcion=f'Instrumento propuesto para {prueba.nombre}',
                            status=0
                        )
                    if metodo_id:
                        metodo = get_object_or_404(MetodoAnalitico, id=metodo_id)
                        PropiedadARevisar.objects.create(
                            tipoElemento='MetodoAnalitico',
                            valor=metodo.nombre,
                            descripcion=f'Método analítico propuesto para {prueba.nombre}',
                            status=0
                        )
                    if reactivo_id:
                        reactivo = get_object_or_404(Reactivo, id=reactivo_id)
                        PropiedadARevisar.objects.create(
                            tipoElemento='Reactivo',
                            valor=reactivo.nombre,
                            descripcion=f'Reactivo propuesto para {prueba.nombre}',
                            status=0
                        )
                    if unidad_id:
                        unidad = get_object_or_404(UnidadDeMedida, id=unidad_id)
                        PropiedadARevisar.objects.create(
                            tipoElemento='UnidadDeMedida',
                            valor=unidad.nombre,
                            descripcion=f'Unidad de medida propuesta para {prueba.nombre}',
                            status=0
                        )
                messages.success(request, f"Propuesta registrada para '{prueba.nombre}'.")
            except Exception as e:
                print("Error creando propuesta:", e)
                messages.error(request, "Ocurrió un error al proponer la configuración.")

        return redirect('accept_configurations')

    context = {
        "pending_pruebas": pending_pruebas,
        "accepted_configs": accepted_configs,
        "instrumentos": instrumentos,
        "metodos": metodos,
        "reactivos": reactivos,
        "unidades": unidades,
        "propuestas": propuestas,
    }

    return render(request, "accept_configurations.html", context)
