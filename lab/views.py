import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse

from .models import (
    UserLaboratorio, ProgramaLaboratorio, Prueba, LaboratorioPruebaConfig,
    Instrumento, MetodoAnalitico, Reactivo, UnidadDeMedida, PropiedadARevisar
)

# ---------- Páginas básicas ----------
def homepage(request):
    if request.method == "POST":
        username = request.POST["usuario"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.POST.get('next') or 'labmainview'
            return redirect(next_url)
        else:
            messages.error(request, "Login o password incorrecto")
            return redirect('homepage')
    return render(request, 'homepage.html', {'next': request.GET.get('next', '')})


def logout_user(request):
    logout(request)
    messages.success(request, "Logged out")
    return redirect('homepage')


# ---------- Vista principal del laboratorio ----------
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

        # Añadir nombre_prueba a cada config aceptada
        pruebas_dict = {prueba.id: prueba.nombre for prueba in Prueba.objects.filter(id__in=accepted_prueba_ids)}
        for config in accepted_configs:
            config.nombre_prueba = pruebas_dict.get(config.prueba_id.id, "-")

        # Propuestas pendientes
        propuestas = PropiedadARevisar.objects.all()

        context = {
            'pending_pruebas': pending_pruebas,
            'accepted_configs': accepted_configs,
            'instrumentos': instrumentos,
            'metodos': metodos,
            'reactivos': reactivos,
            'unidades': unidades,
            'propuestas': propuestas,
            'laboratorio': laboratorio,
        }
        return render(request, self.template_name, context)


# ---------- Vista para aceptar / proponer configuraciones ----------
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

    # Añadir atributo nombre_prueba a cada config aceptada
    pruebas_dict = {prueba.id: prueba.nombre for prueba in Prueba.objects.filter(id__in=accepted_prueba_ids)}
    for config in accepted_configs:
        config.nombre_prueba = pruebas_dict.get(config.prueba_id.id, "-")

    # 4. Pruebas pendientes de aceptar
    pending_pruebas = pruebas_laboratorio.exclude(id__in=accepted_prueba_ids)

    # 5. Opciones de configuración
    instrumentos = Instrumento.objects.all()
    metodos = MetodoAnalitico.objects.all()
    reactivos = Reactivo.objects.all()
    unidades = UnidadDeMedida.objects.all()

    # 6. Propuestas pendientes
    propuestas = PropiedadARevisar.objects.all()

    # Detectar si es AJAX
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    # POST: aceptar o proponer configuración
    if request.method == 'POST':
        prueba_id = request.POST.get('prueba_id')
        instrumento_id = request.POST.get('instrumento')
        metodo_id = request.POST.get('metodo')
        reactivo_id = request.POST.get('reactivo')
        unidad_id = request.POST.get('unidad')
        accion = request.POST.get('accion', 'aceptar')  # aceptar | proponer

        if not prueba_id:
            message = "No se indicó la prueba a procesar."
            if is_ajax:
                return JsonResponse({'success': False, 'message': message})
            messages.error(request, message)
            return redirect('labmainview')

        try:
            prueba = Prueba.objects.get(id=prueba_id, programa_id__in=programas_ids)
        except Prueba.DoesNotExist:
            message = "Prueba inválida o no pertenece a tu laboratorio."
            if is_ajax:
                return JsonResponse({'success': False, 'message': message})
            messages.error(request, message)
            return redirect('labmainview')

        # ---------- ACEPTAR CONFIGURACIÓN ----------
        if accion == 'aceptar':
            # Validar que todos los campos estén llenos
            if not (instrumento_id and metodo_id and reactivo_id and unidad_id):
                message = "Todos los campos deben estar completos para aceptar la configuración."
                if is_ajax:
                    return JsonResponse({'success': False, 'message': message})
                messages.error(request, message)
                return redirect('labmainview')

            try:
                with transaction.atomic():
                    config, created = LaboratorioPruebaConfig.objects.get_or_create(
                        laboratorio_id=laboratorio,
                        prueba_id=prueba,
                        defaults={
                            'instrumento_id': Instrumento.objects.get(id=instrumento_id),
                            'metodo_analitico_id': MetodoAnalitico.objects.get(id=metodo_id),
                            'reactivo_id': Reactivo.objects.get(id=reactivo_id),
                            'unidad_de_medida_id': UnidadDeMedida.objects.get(id=unidad_id),
                        }
                    )
                    if not created:
                        config.instrumento_id = get_object_or_404(Instrumento, id=instrumento_id)
                        config.metodo_analitico_id = get_object_or_404(MetodoAnalitico, id=metodo_id)
                        config.reactivo_id = get_object_or_404(Reactivo, id=reactivo_id)
                        config.unidad_de_medida_id = get_object_or_404(UnidadDeMedida, id=unidad_id)
                        config.save()
                message = f"Configuración para '{prueba.nombre}' aceptada correctamente."
                if is_ajax:
                    return JsonResponse({'success': True, 'message': message})
                messages.success(request, message)
                return redirect('labmainview')
            except IntegrityError:
                message = "Ya existe una configuración para esta prueba."
                if is_ajax:
                    return JsonResponse({'success': False, 'message': message})
                messages.error(request, message)
                return redirect('labmainview')
            except Exception as e:
                message = "Ocurrió un error al aceptar la configuración."
                print("Error:", e)
                if is_ajax:
                    return JsonResponse({'success': False, 'message': message})
                messages.error(request, message)
                return redirect('labmainview')

        # ---------- PROPONER CONFIGURACIÓN ----------
        else:
            try:
                with transaction.atomic():
                    if instrumento_id:
                        instrumento = get_object_or_404(Instrumento, id=instrumento_id)
                        PropiedadARevisar.objects.create(
                            tipoElemento='instrumento',
                            valor=instrumento.nombre,
                            descripcion=f'Instrumento propuesto para {prueba.nombre}',
                            status=0
                        )
                    if metodo_id:
                        metodo = get_object_or_404(MetodoAnalitico, id=metodo_id)
                        PropiedadARevisar.objects.create(
                            tipoElemento='metodo',
                            valor=metodo.nombre,
                            descripcion=f'Método analítico propuesto para {prueba.nombre}',
                            status=0
                        )
                    if reactivo_id:
                        reactivo = get_object_or_404(Reactivo, id=reactivo_id)
                        PropiedadARevisar.objects.create(
                            tipoElemento='reactivo',
                            valor=reactivo.nombre,
                            descripcion=f'Reactivo propuesto para {prueba.nombre}',
                            status=0
                        )
                    if unidad_id:
                        unidad = get_object_or_404(UnidadDeMedida, id=unidad_id)
                        PropiedadARevisar.objects.create(
                            tipoElemento='unidad',
                            valor=unidad.nombre,
                            descripcion=f'Unidad de medida propuesta para {prueba.nombre}',
                            status=0
                        )
                message = f"Propuesta registrada para '{prueba.nombre}'."
                if is_ajax:
                    return JsonResponse({'success': True, 'message': message})
                messages.success(request, message)
                return redirect('labmainview')
            except Exception as e:
                print("Error creando propuesta:", e)
                message = "Ocurrió un error al proponer la configuración."
                if is_ajax:
                    return JsonResponse({'success': False, 'message': message})
                messages.error(request, message)
                return redirect('labmainview')

    # GET: renderizar la página normalmente
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
