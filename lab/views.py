import json, os
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse, reverse_lazy
from django.db import transaction, IntegrityError
from django.utils import timezone
from .utils.puede_editar_config import puede_editar_config


from .models import (
    UserLaboratorio, ProgramaLaboratorio, Prueba, LaboratorioPruebaConfig,
    Instrumento, MetodoAnalitico, Reactivo, UnidadDeMedida, PropiedadARevisar,
    Laboratorio
)

# --------------------------
# Vistas para manejo de autenticación con homepage y login system de Django
# --------------------------
def homepage(request):
    # Si ya está autenticado, llevar al flujo normal de selección de laboratorio
    if request.user.is_authenticated:
        return redirect('lab:select_lab')
    if request.method == 'POST':
        username = request.POST.get('usuario')      # name="usuario" en tu template
        password = request.POST.get('password')     # name="password" en tu template
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next') or reverse('lab:select_lab')
            return redirect(next_url)
        messages.error(request, 'Usuario o contraseña inválidos.')
    return render(request, 'homepage.html')


# --------------------------
# Vistas para manejo de laboratorios
# --------------------------
@login_required
def select_lab(request):
    """
    Vista inicial donde el usuario selecciona uno de los laboratorios
    a los que tiene acceso. Estos laboratorios vienen de UserLaboratorio.
    """
    laboratorios_usuario = Laboratorio.objects.filter(usuarios__user_id=request.user)

    if request.method == "POST":
        laboratorio_id = request.POST.get("laboratorio_id")
        if laboratorio_id:
            request.session["laboratorio_seleccionado"] = laboratorio_id
            return redirect("lab:labmainview")

    return render(request, "select_lab.html", {"laboratorios": laboratorios_usuario})


# --------------------------
# Vista para cerrar sesión
# --------------------------
@login_required
def logout_user(request):
    logout(request)
    return redirect("lab:homepage")



# --------------------------
# Vista principal de /lab
# --------------------------
class LabMainView(LoginRequiredMixin, View):
    template_name = 'labmain.html'
    login_url = reverse_lazy('lab:homepage')

    def get(self, request):
        laboratorio_id = request.session.get("laboratorio_seleccionado")
        laboratorio = Laboratorio.objects.filter(id=laboratorio_id).first() if laboratorio_id else None

        if not laboratorio:
            messages.error(request, "No hay laboratorio asociado a tu usuario.")
            return redirect('lab:homepage')

        programas_ids = ProgramaLaboratorio.objects.filter(
            laboratorio_id=laboratorio.id
        ).values_list('programa_id', flat=True)

        pruebas_laboratorio = Prueba.objects.filter(programa_id__in=programas_ids)
        accepted_configs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=laboratorio)
        accepted_prueba_ids = accepted_configs.values_list('prueba_id', flat=True)
        pending_pruebas = pruebas_laboratorio.exclude(id__in=accepted_prueba_ids)

        # Construir el wrapper con el flag can_edit por fila
        accepted_configs_wrapped = [
            {"obj": c, "can_edit": puede_editar_config(laboratorio, c)}
            for c in accepted_configs
        ]

        context = {
            'pending_pruebas': pending_pruebas,
            'accepted_configs': accepted_configs,               # si lo usas en otras partes
            'accepted_configs_wrapped': accepted_configs_wrapped,  # para Acciones/Editar
            'instrumentos': Instrumento.objects.all(),
            'metodos': MetodoAnalitico.objects.all(),
            'reactivos': Reactivo.objects.all(),
            'unidades': UnidadDeMedida.objects.all(),
            'laboratorio': laboratorio,
            'propuestas': PropiedadARevisar.objects.all(),
            'today': timezone.localdate(),  # opcional, solo para display
        }
        return render(request, self.template_name, context)

# --------------------------
# Crear o actualizar configuración (incluye propuestas)
# --------------------------
@login_required
@transaction.atomic
def crear_o_actualizar_configuracion(request):
    """
    Maneja propuestas individuales y la aceptación de configuraciones con validaciones
    de pertenencia, existencia y estado de propuestas, todo bajo transacción atómica.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido"}, status=405)  # [docs]

    laboratorio_id = request.session.get("laboratorio_seleccionado")
    if not laboratorio_id:
        return JsonResponse({"success": False, "error": "Debes seleccionar un laboratorio primero."}, status=400)  # [docs]

    # Seguridad: validar que el usuario tenga acceso al laboratorio
    pertenece = UserLaboratorio.objects.filter(user_id=request.user, laboratorio_id=laboratorio_id).exists()
    if not pertenece:
        return JsonResponse({"success": False, "error": "Acceso denegado al laboratorio seleccionado."}, status=403)  # [docs]

    laboratorio = get_object_or_404(Laboratorio, id=laboratorio_id)
    prueba_id = request.POST.get("prueba_id")
    accion = request.POST.get("accion", "").strip()

    if not prueba_id:
        return JsonResponse({"success": False, "error": "ID de prueba es requerido."}, status=400)  # [docs]

    # Validar que la prueba pertenezca a algún programa asignado al laboratorio
    programas_ids = ProgramaLaboratorio.objects.filter(laboratorio_id=laboratorio.id).values_list('programa_id', flat=True)
    if not Prueba.objects.filter(id=prueba_id, programa_id__in=programas_ids).exists():
        return JsonResponse({"success": False, "error": "La prueba no pertenece al laboratorio seleccionado."}, status=400)  # [docs]

    prueba = get_object_or_404(Prueba, id=prueba_id)

    # --------- Propuestas ---------
    if accion.startswith("proponer_"):
        tipo = accion.replace("proponer_", "")
        valor = (request.POST.get(f"{tipo}_valor") or "").strip()
        descripcion = (request.POST.get(f"{tipo}_descripcion") or "").strip()

        tipos_validos = ["instrumento", "metodo", "reactivo", "unidad"]
        if tipo not in tipos_validos:
            return JsonResponse({"success": False, "error": f"Tipo '{tipo}' no válido."}, status=400)  # [docs]

        if not valor:
            return JsonResponse({"success": False, "error": f"El valor para {tipo} es requerido."}, status=400)  # [docs]

        modelos_map = {
            "instrumento": Instrumento,
            "metodo": MetodoAnalitico,
            "reactivo": Reactivo,
            "unidad": UnidadDeMedida
        }
        modelo = modelos_map[tipo]

        # No duplicar un valor que ya exista en la tabla maestra
        if modelo.objects.filter(nombre__iexact=valor).exists():
            return JsonResponse({"success": False, "error": f"Ya existe un {tipo} con el nombre '{valor}'"}, status=400)  # [docs]

        # No duplicar propuestas pendientes o aprobadas con el mismo valor/tipo
        if PropiedadARevisar.objects.filter(tipoElemento=tipo, valor__iexact=valor, status__in=[0, 1]).exists():
            return JsonResponse({"success": False, "error": f"Ya existe una propuesta para {tipo} '{valor}'"}, status=400)  # [docs]

        propuesta = PropiedadARevisar.objects.create(
            tipoElemento=tipo, valor=valor, descripcion=descripcion, status=0
        )
        return JsonResponse({
            "success": True,
            "message": f"{tipo.capitalize()} '{valor}' propuesto exitosamente",
            "propuesta": {
                "id": propuesta.id,
                "tipoElemento": propuesta.tipoElemento,              # "instrumento" | "metodo" | "reactivo" | "unidad"
                "valor": propuesta.valor,
                "descripcion": propuesta.descripcion or "",
                "status": propuesta.status,                          # 0/1/2
                "status_text": "Pendiente" if propuesta.status == 0 else ("Aprobado" if propuesta.status == 1 else "Rechazado")
            }
        }, status=201)  # [docs]

    # --------- Aceptar configuración ---------
    if accion == "aceptar":
        campos_config = {
            "instrumento_id": (request.POST.get("instrumento_id"), Instrumento),
            "metodo_analitico_id": (request.POST.get("metodo_analitico_id"), MetodoAnalitico),
            "reactivo_id": (request.POST.get("reactivo_id"), Reactivo),
            "unidad_de_medida_id": (request.POST.get("unidad_de_medida_id"), UnidadDeMedida),
        }

        # 1) Todos los campos presentes
        faltantes = []
        for campo, (valor, _) in campos_config.items():
            if not valor:
                faltantes.append(campo.replace("_id", "").replace("_", " ").title())
        if faltantes:
            return JsonResponse({"success": False, "error": "Campos faltantes: " + ", ".join(faltantes)}, status=400)  # [docs]

        # 2) IDs válidos que existan
        instancias = {}
        for campo, (valor_id, modelo) in campos_config.items():
            try:
                instancias[campo] = modelo.objects.get(id=valor_id)
            except modelo.DoesNotExist:
                return JsonResponse({"success": False, "error": f"{campo.replace('_id','').replace('_',' ').title()} seleccionado no existe"}, status=400)  # [docs]

        # 3) No aceptar si hay una propuesta pendiente con el mismo nombre/tipo
        for campo, instancia in instancias.items():
            tipo_norm = campo.replace("_id", "").replace("metodo_analitico", "metodo").replace("unidad_de_medida", "unidad")
            propuesta_pendiente = PropiedadARevisar.objects.filter(
                tipoElemento=tipo_norm, valor__iexact=instancia.nombre, status=0
            ).first()
            if propuesta_pendiente:
                return JsonResponse({"success": False, "error": f"El {tipo_norm} '{instancia.nombre}' tiene una propuesta pendiente de aprobación"}, status=400)  # [docs]

        try:
            config, created = LaboratorioPruebaConfig.objects.update_or_create(
                laboratorio_id=laboratorio,
                prueba_id=prueba,
                defaults={
                    "instrumento_id": instancias["instrumento_id"],
                    "metodo_analitico_id": instancias["metodo_analitico_id"],
                    "reactivo_id": instancias["reactivo_id"],
                    "unidad_de_medida_id": instancias["unidad_de_medida_id"],
                }
            )
        except IntegrityError:
            # Por si se quisiera crear en vez de actualizar y ya existe por unique constraint
            return JsonResponse({"success": False, "error": "Ya existe una configuración para esta prueba en este laboratorio"}, status=409)  # [docs]

        return JsonResponse({"success": True, "message": "Configuración aceptada exitosamente", "config_id": config.id, "created": created}, status=201 if created else 200)  # [docs]

    # Acción desconocida
    return JsonResponse({"success": False, "error": "Acción no válida"}, status=400)  # [docs]



# --------------------------
# Validar y aceptar configuraciones
# --------------------------
@transaction.atomic
def aceptar_configuracion(request, config_id):
    """
    Valida y acepta una configuración pendiente.
    """
    config = get_object_or_404(LaboratorioPruebaConfig, id=config_id)

    campos_obligatorios = [
        ("instrumento_id", "Instrumento"),
        ("metodo_analitico_id", "Método Analítico"),
        ("reactivo_id", "Reactivo"),
        ("unidad_de_medida_id", "Unidad de Medida"),
    ]

    # 1. Validar campos obligatorios
    for campo, nombre in campos_obligatorios:
        valor = getattr(config, campo)
        if not valor:
            return JsonResponse({
                "error": f"El campo {nombre} es obligatorio para aceptar la configuración."
            }, status=400)

    # 2. Validar que los valores estén aprobados
    for tipo, modelo in [
        ("instrumento", Instrumento),
        ("metodo", MetodoAnalitico),
        ("reactivo", Reactivo),
        ("unidad", UnidadDeMedida),
    ]:
        valor = getattr(config, f"{tipo}_id")
        if valor:
            propuesta = PropiedadARevisar.objects.filter(valor=valor.nombre, tipoElemento=tipo).first()
            if propuesta and propuesta.status != 1:
                return JsonResponse({
                    "error": f"El {tipo} '{valor.nombre}' no está aprobado (estado: {propuesta.get_status_display()})."
                }, status=400)

    return JsonResponse({
        "message": "Configuración aceptada y guardada correctamente."
    }, status=200)


# --------------------------
# Vista central para aceptación de configuraciones
# --------------------------
def accept_configurations(request):
    """
    Muestra configuraciones pendientes, aceptadas y propuestas.
    """
    laboratorio_id = request.session.get("laboratorio_seleccionado")
    laboratorio = None
    if laboratorio_id:
        laboratorio = Laboratorio.objects.filter(id=laboratorio_id).first()

    if not laboratorio:
        messages.error(request, "No hay laboratorio asociado a tu usuario.")
        return redirect('lab:labmainview')

    programas_ids = ProgramaLaboratorio.objects.filter(
        laboratorio_id=laboratorio.id
    ).values_list('programa_id', flat=True)

    pruebas_laboratorio = Prueba.objects.filter(programa_id__in=programas_ids)

    accepted_configs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=laboratorio)
    accepted_prueba_ids = accepted_configs.values_list('prueba_id', flat=True)
    pending_pruebas = pruebas_laboratorio.exclude(id__in=accepted_prueba_ids)

    propuestas = PropiedadARevisar.objects.all()

    context = {
        "pending_pruebas": pending_pruebas,
        "accepted_configs": accepted_configs,
        "instrumentos": Instrumento.objects.all(),
        "metodos": MetodoAnalitico.objects.all(),
        "reactivos": Reactivo.objects.all(),
        "unidades": UnidadDeMedida.objects.all(),
        "propuestas": propuestas,
    }
    return render(request, "accept_configurations.html", context)

# --------------------------
# Vista para actualizar configuración existente
# --------------------------
@login_required
@transaction.atomic
def actualizar_configuracion(request, config_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido"}, status=405)  # [22]

    config = get_object_or_404(LaboratorioPruebaConfig, id=config_id)
    laboratorio = config.laboratorio_id

    # Seguridad: pertenencia usuario-lab
    if not UserLaboratorio.objects.filter(user_id=request.user, laboratorio_id=laboratorio.id).exists():
        return JsonResponse({"success": False, "error": "Acceso denegado"}, status=403)  # [22]

    # Ventana de edición y bloqueos
    if not puede_editar_config(laboratorio, config):
        return JsonResponse({"success": False, "error": "La edición está bloqueada por ventana de tiempo o bandera de bloqueo"}, status=403)  # [1][9]

    # Validar que la prueba pertenece a los programas del laboratorio (consistencia)
    programas_ids = ProgramaLaboratorio.objects.filter(laboratorio_id=laboratorio.id).values_list("programa_id", flat=True)
    if not Prueba.objects.filter(id=config.prueba_id.id, programa_id__in=programas_ids).exists():
        return JsonResponse({"success": False, "error": "Prueba no pertenece al laboratorio"}, status=400)  # [22]

    # Validar y setear campos
    campos = {
        "instrumento_id": (request.POST.get("instrumento_id"), Instrumento),
        "metodo_analitico_id": (request.POST.get("metodo_analitico_id"), MetodoAnalitico),
        "reactivo_id": (request.POST.get("reactivo_id"), Reactivo),
        "unidad_de_medida_id": (request.POST.get("unidad_de_medida_id"), UnidadDeMedida),
    }
    faltantes = [k.replace("_id","").replace("_"," ").title() for k,(v,_) in campos.items() if not v]
    if faltantes:
        return JsonResponse({"success": False, "error": "Campos faltantes: " + ", ".join(faltantes)}, status=400)  # [22]

    instancias = {}
    for campo, (valor_id, Modelo) in campos.items():
        try:
            instancias[campo] = Modelo.objects.get(id=valor_id)
        except Modelo.DoesNotExist:
            return JsonResponse({"success": False, "error": f"{campo.replace('_id','').replace('_',' ').title()} no existe"}, status=400)  # [22]

    # Aplicar cambios
    config.instrumento_id = instancias["instrumento_id"]
    config.metodo_analitico_id = instancias["metodo_analitico_id"]
    config.reactivo_id = instancias["reactivo_id"]
    config.unidad_de_medida_id = instancias["unidad_de_medida_id"]
    config.save()

    return JsonResponse({"success": True, "message": "Configuración actualizada"}, status=200)  # [22]
