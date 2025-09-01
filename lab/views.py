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
    
def accept_configurations(request):
    # Obtener el laboratorio asociado al usuario autenticado usando UserLaboratorio
    laboratorio = None
    if request.user.is_authenticated:
        user_lab = UserLaboratorio.objects.filter(user_id=request.user).first()
        if user_lab:
            laboratorio = user_lab.laboratorio

    print("Laboratorio obtenido:", laboratorio)  # Esto aparecerá en la terminal del servidor

    if not laboratorio:
        messages.error(request, "No hay laboratorio asociado a tu usuario.")
        return redirect('labmainview')

    # 1. Obtener los programas del laboratorio
    programas_ids = ProgramaLaboratorio.objects.filter(
        laboratorio_id=laboratorio.id
    ).values_list('programa_id', flat=True)

    # 2. Obtener todas las pruebas de esos programas
    pruebas_laboratorio = Prueba.objects.filter(programa_id__in=programas_ids)

    # 3. Obtener pruebas ya aceptadas (en LaboratorioPruebaConfig)
    accepted_configs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=laboratorio)
    accepted_prueba_ids = accepted_configs.values_list('prueba_id', flat=True)

    # 4. Pruebas pendientes por aceptar
    pending_pruebas = pruebas_laboratorio.exclude(id__in=accepted_prueba_ids)

    instrumentos = Instrumento.objects.all()
    metodos = MetodoAnalitico.objects.all()
    reactivos = Reactivo.objects.all()
    unidades = UnidadDeMedida.objects.all()

    if request.method == 'POST':
        prueba_id = request.POST.get('prueba_id')
        instrumento_id = request.POST.get('instrumento')
        metodo_id = request.POST.get('metodo')
        reactivo_id = request.POST.get('reactivo')
        unidad_id = request.POST.get('unidad')
        accion = request.POST.get('accion', 'aceptar')  # 'aceptar' o 'proponer'

        prueba = Prueba.objects.get(id=prueba_id)

        if accion == 'aceptar':
            LaboratorioPruebaConfig.objects.create(
                laboratorio_id=laboratorio,
                prueba_id=prueba,
                instrumento_id=Instrumento.objects.get(id=instrumento_id) if instrumento_id else None,
                metodo_analitico_id=MetodoAnalitico.objects.get(id=metodo_id) if metodo_id else None,
                reactivo_id=Reactivo.objects.get(id=reactivo_id) if reactivo_id else None,
                unidad_de_medida_id=UnidadDeMedida.objects.get(id=unidad_id) if unidad_id else None,
            )
        else:
            if instrumento_id:
                instrumento = Instrumento.objects.get(id=instrumento_id)
                PropiedadARevisar.objects.create(
                    tipoElemento='Instrumento',
                    valor=instrumento.nombre,
                    descripcion=f'Instrumento propuesto para {prueba.nombre}',
                    status=0
                )
            if metodo_id:
                metodo = MetodoAnalitico.objects.get(id=metodo_id)
                PropiedadARevisar.objects.create(
                    tipoElemento='MetodoAnalitico',
                    valor=metodo.nombre,
                    descripcion=f'Método analítico propuesto para {prueba.nombre}',
                    status=0
                )
            if reactivo_id:
                reactivo = Reactivo.objects.get(id=reactivo_id)
                PropiedadARevisar.objects.create(
                    tipoElemento='Reactivo',
                    valor=reactivo.nombre,
                    descripcion=f'Reactivo propuesto para {prueba.nombre}',
                    status=0
                )
            if unidad_id:
                unidad = UnidadDeMedida.objects.get(id=unidad_id)
                PropiedadARevisar.objects.create(
                    tipoElemento='UnidadDeMedida',
                    valor=unidad.nombre,
                    descripcion=f'Unidad de medida propuesta para {prueba.nombre}',
                    status=0
                )
        return redirect('accept_configurations')

    return render(request, 'accept_configurations.html', {
        'pending_pruebas': pending_pruebas,
        'accepted_configs': accepted_configs,
        'instrumentos': instrumentos,
        'metodos': metodos,
        'reactivos': reactivos,
        'unidades': unidades,
        'laboratorio': laboratorio,
    })