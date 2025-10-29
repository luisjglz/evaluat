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
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from datetime import date

from .models import (
    UserLaboratorio, ProgramaLaboratorio, Prueba, LaboratorioPruebaConfig,
    Instrumento, MetodoAnalitico, Reactivo, UnidadDeMedida, PropiedadARevisar,
    Laboratorio, Dato, Reporte
)

# ----------- Helpers -----------
def avanzar_estado_si_corresponde(lab, *, persistir: bool = True):
    """
    Reglas:
    - 1→2: desde el día 16 local si no hay override de edición.
    - 2→3: por completitud del mes (todas las pruebas requeridas) si no hay override de captura.
    - 3 se respeta; solo cambia por acción de admin u override de captura.
    """
    from django.utils import timezone
    hoy = timezone.localdate()
    if lab.estado == 3:
        return lab
    ed_override = lab.override_edicion_activa and (lab.override_edicion_hasta is None or hoy <= lab.override_edicion_hasta)
    if lab.estado == 1 and not ed_override and hoy.day >= 16:
        lab.estado = 2
        if persistir:
            lab.save(update_fields=['estado'])
        return lab
    cap_override = lab.override_captura_activa and (lab.override_captura_hasta is None or hoy <= lab.override_captura_hasta)
    # El cierre por completitud se evalúa después del guardado en la vista de data_entry
    return lab

# def avanzar_estado_si_corresponde(lab: Laboratorio, *, persistir: bool = True) -> Laboratorio:
#     """
#     Reglas:
#     - Si admin fija estado 1|2|3 manualmente, se respeta el valor salvo transición natural a 2 por fecha.
#     - Si override_edicion_activa y override_edicion_hasta:
#         - Mientras hoy <= override_edicion_hasta, no se fuerza a 2.
#         - Si hoy > override_edicion_hasta, estado => 2 (registro).
#     - Sin override:
#         - Si hoy.day > edicion_hasta_dia, estado => 2 (registro).
#     - Nunca sobreescribe manualmente a 3 (consulta); admin manda.
#     """
#     hoy = timezone.localdate()

#     # Caso 3 (Consulta) es totalmente manual: no forzar cambios automáticos
#     if lab.estado == 3:
#         return lab

#     # Override activo define la ventana de edición
#     if lab.override_edicion_activa and lab.override_edicion_hasta:
#         if hoy > lab.override_edicion_hasta and lab.estado != 2:
#             lab.estado = 2
#             if persistir:
#                 lab.save(update_fields=['estado'])
#         return lab

#     # Sin override: usar el día límite de edición (por defecto 15 si no definido)
#     dia_limite = lab.edicion_hasta_dia or 15
#     if hoy.day > dia_limite and lab.estado != 2:
#         lab.estado = 2
#         if persistir:
#             lab.save(update_fields=['estado'])

#     return lab


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
# @login_required
# def select_lab(request):
#     """
#     Vista inicial donde el usuario selecciona uno de los laboratorios
#     a los que tiene acceso. Estos laboratorios vienen de UserLaboratorio/Laboratorio. 
#     """
#     # Laboratorios a los que el usuario pertenece
#     laboratorios_usuario_qs = Laboratorio.objects.filter(
#         usuarios__user_id=request.user
#     ).distinct().order_by('nombre')
#     laboratorios_usuario = list(laboratorios_usuario_qs)

#     if request.method == 'GET':
#         # Si no tiene laboratorios, mostrar mensaje y página de selección vacía
#         if not laboratorios_usuario:
#             messages.error(request, "No tienes laboratorios asignados. Contacta al administrador.")
#             return render(request, 'select_lab.html', {'laboratorios': []})

#         # Si ya hay un laboratorio en sesión y sigue siendo válido, atajo (opcional)
#         lab_id_sesion = request.session.get('laboratorio_seleccionado')
#         if lab_id_sesion and laboratorios_usuario_qs.filter(id=lab_id_sesion).exists():
#             return redirect('lab:lab_route')

#         # Si solo tiene uno, saltar selección y mandar a ruteo por estado
#         if len(laboratorios_usuario) == 1:
#             request.session['laboratorio_seleccionado'] = laboratorios_usuario[0].id
#             return redirect('lab:lab_route')

#         # Caso normal: mostrar selector
#         return render(request, 'select_lab.html', {'laboratorios': laboratorios_usuario})

#     if request.method == 'POST':
#         laboratorio_id = request.POST.get("laboratorio_id")
#         try:
#             laboratorio_id = int(laboratorio_id)
#         except (TypeError, ValueError):
#             messages.error(request, "Selecciona un laboratorio válido.")
#             return redirect('lab:select_lab')

#         # Validar pertenencia
#         if not laboratorios_usuario_qs.filter(id=laboratorio_id).exists():
#             messages.error(request, "No tienes acceso a ese laboratorio.")
#             return redirect('lab:select_lab')

#         # Guardar selección en sesión y delegar a ruteo por estado
#         request.session["laboratorio_seleccionado"] = laboratorio_id
#         return redirect("lab:lab_route")

#     # Fallback (no debería llegar)
#     return render(request, "select_lab.html", {"laboratorios": laboratorios_usuario})


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
        lab_id = request.session.get("laboratorio_seleccionado")
        lab = Laboratorio.objects.filter(id=lab_id).first() if lab_id else None
        if not lab:
            messages.error(request, "No hay laboratorio asociado a tu usuario.")
            return redirect('lab:homepage')

        # Asegurar estado actualizado
        avanzar_estado_si_corresponde(lab, persistir=True)

        ctx = {'lab': lab, 'today': timezone.localdate()}

        if lab.estado == 1:
            # Contexto para configuraciones
            programas_ids = ProgramaLaboratorio.objects.filter(
                laboratorio_id=lab.id
            ).values_list('programa_id', flat=True)

            pruebas_laboratorio = Prueba.objects.filter(programa_id__in=programas_ids)

            accepted_configs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=lab)
            accepted_prueba_ids = accepted_configs.values_list('prueba_id', flat=True)

            pending_pruebas = pruebas_laboratorio.exclude(id__in=accepted_prueba_ids)

            accepted_configs_wrapped = [
                {"obj": c, "can_edit": puede_editar_config(lab, c)}
                for c in accepted_configs
            ]

            ctx.update({
                'pending_pruebas': pending_pruebas,
                'accepted_configs': accepted_configs,
                'accepted_configs_wrapped': accepted_configs_wrapped,
                'instrumentos': Instrumento.objects.all(),
                'metodos': MetodoAnalitico.objects.all(),
                'reactivos': Reactivo.objects.all(),
                'unidades': UnidadDeMedida.objects.all(),
                'propuestas': PropiedadARevisar.objects.all(),
            })
            return render(request, self.template_name, ctx)

        # Estado 2 o 3: registro/consulta - solo pruebas configuradas
        cfgs = (LaboratorioPruebaConfig.objects
                .filter(laboratorio_id=lab)
                .select_related("prueba_id", "unidad_de_medida_id"))
        unidades_por_prueba = {
            c.prueba_id_id: (c.unidad_de_medida_id.nombre if c.unidad_de_medida_id else "")
            for c in cfgs
        }
        pruebas_cfg_ids = list(unidades_por_prueba.keys())

        pls = ProgramaLaboratorio.objects.filter(laboratorio_id=lab).select_related("programa_id")
        programas = []
        for pl in pls:
            pruebas = (Prueba.objects
                       .filter(programa_id=pl.programa_id, id__in=pruebas_cfg_ids)
                       .order_by("nombre"))
            if pruebas.exists():
                filas = [{"prueba": p, "unidad": unidades_por_prueba.get(p.id, "")} for p in pruebas]
                programas.append({"programa": pl.programa_id, "filas": filas})

        ctx.update({"programas": programas})
        return render(request, self.template_name, ctx)

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
@login_required
def accept_configurations(request):
    lab_id = request.session.get('laboratorio_seleccionado')
    if not lab_id:
        messages.error(request, "No hay laboratorio asociado a tu usuario.")
        return redirect('lab:select_lab')

    laboratorio = get_object_or_404(Laboratorio, pk=lab_id)

    programas_ids = ProgramaLaboratorio.objects.filter(
        laboratorio_id=laboratorio.id
    ).values_list('programa_id', flat=True)

    pruebas_laboratorio = Prueba.objects.filter(programa_id__in=programas_ids)

    accepted_configs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=laboratorio)
    accepted_prueba_ids = accepted_configs.values_list('prueba_id', flat=True)

    pending_pruebas = pruebas_laboratorio.exclude(id__in=accepted_prueba_ids)

    # CONSTRUIR WRAPPER PARA EL TEMPLATE
    accepted_configs_wrapped = [
        {"obj": c, "can_edit": puede_editar_config(laboratorio, c)}
        for c in accepted_configs
    ]

    context = {
        "pending_pruebas": pending_pruebas,
        "accepted_configs": accepted_configs,  # si lo usas en otro lado
        "accepted_configs_wrapped": accepted_configs_wrapped,  # LO QUE USA EL PARCIAL
        "instrumentos": Instrumento.objects.all(),
        "metodos": MetodoAnalitico.objects.all(),
        "reactivos": Reactivo.objects.all(),
        "unidades": UnidadDeMedida.objects.all(),
        "propuestas": PropiedadARevisar.objects.all(),
        "laboratorio": laboratorio,
        "today": timezone.localdate(),
    }
    # Renderizar labmain para que traiga topbar/sidebar/footer y dentro incluya el parcial
    return render(request, "labmain.html", context)


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

# --------------------------
# Vistas para selección de laboratorio y routing basado en estado (se esta configurando, llenando datos o consultado reportes)
# --------------------------
# @login_required
# def select_lab(request):
#     qs = UserLaboratorio.objects.filter(user_id=request.user).select_related('laboratorio')
#     labs = [ul.laboratorio for ul in qs]
#     if request.method == 'GET':
#         if len(labs) == 1:
#             request.session['laboratorio_seleccionado'] = labs[0].id
#             return redirect('lab:lab_route')
#         return render(request, 'select_lab.html', {'laboratorios': labs})
#     # POST: el usuario eligió un lab
#     lab_id = request.POST.get('laboratorio_id') or request.POST.get('laboratorio')
#     lab = get_object_or_404(Laboratorio, pk=lab_id)
#     request.session['laboratorio_seleccionado'] = lab.id
#     return redirect('lab:lab_route')

@login_required
def select_lab(request):
    """
    Selector de laboratorio del usuario (UserLaboratorio/Laboratorio).
    Si el usuario solo tiene 1 laboratorio, se salta la selección.
    """
    laboratorios_usuario_qs = Laboratorio.objects.filter(
        usuarios__user_id=request.user
    ).distinct().order_by('nombre')
    laboratorios_usuario = list(laboratorios_usuario_qs)

    if request.method == 'GET':
        if not laboratorios_usuario:
            messages.error(request, "No tienes laboratorios asignados. Contacta al administrador.")
            return render(request, 'select_lab.html', {'laboratorios': []})

        lab_id_sesion = request.session.get('laboratorio_seleccionado')
        if lab_id_sesion and laboratorios_usuario_qs.filter(id=lab_id_sesion).exists():
            return redirect('lab:lab_route')

        if len(laboratorios_usuario) == 1:
            request.session['laboratorio_seleccionado'] = laboratorios_usuario[0].id
            return redirect('lab:lab_route')

        return render(request, 'select_lab.html', {'laboratorios': laboratorios_usuario})

    if request.method == 'POST':
        laboratorio_id = request.POST.get("laboratorio_id")
        try:
            laboratorio_id = int(laboratorio_id)
        except (TypeError, ValueError):
            messages.error(request, "Selecciona un laboratorio válido.")
            return redirect('lab:select_lab')

        if not laboratorios_usuario_qs.filter(id=laboratorio_id).exists():
            messages.error(request, "No tienes acceso a ese laboratorio.")
            return redirect('lab:select_lab')

        request.session["laboratorio_seleccionado"] = laboratorio_id
        return redirect('lab:lab_route')

    return render(request, 'select_lab.html', {'laboratorios': laboratorios_usuario})


# solo decide y envía a “/lab”
@login_required
def lab_route(request):
    lab_id = request.session.get('laboratorio_seleccionado')
    if not lab_id:
        return redirect('lab:select_lab')
    lab = get_object_or_404(Laboratorio, pk=lab_id)
    avanzar_estado_si_corresponde(lab, persistir=True)
    return redirect('lab:labmainview')


# @login_required
# def lab_route(request):
#     lab_id = request.session.get('laboratorio_seleccionado')
#     if not lab_id:
#         return redirect('lab:select_lab')
#     lab = get_object_or_404(Laboratorio, pk=lab_id)
#     lab = avanzar_estado_si_corresponde(lab)

#     ctx = {"lab": lab}

#     if lab.estado == 1:
#         # Contexto para configuraciones (aceptadas/pendientes), ya existente en tu app
#         # Rellena ctx con pending_pruebas, accepted_configs_wrapped, instrumentos, etc.
#         return render(request, "labmain.html", ctx)
#     else:
#         # Contexto para data entry: solo pruebas configuradas
#         cfgs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=lab).select_related(
#             "prueba_id", "unidad_de_medida_id"
#         )
#         pruebas_cfg_ids = [c.prueba_id_id for c in cfgs]
#         # Por programa
#         pls = ProgramaLaboratorio.objects.filter(laboratorio_id=lab).select_related("programa_id")
#         programas = []
#         # Mapa unidad por prueba para la UI
#         unidades_por_prueba = {c.prueba_id_id: (c.unidad_de_medida_id.nombre if c.unidad_de_medida_id else "") for c in cfgs}
#         for pl in pls:
#             pruebas = Prueba.objects.filter(programa_id=pl.programa_id, id__in=pruebas_cfg_ids).order_by("nombre")
#             if pruebas.exists():
#                 programas.append({"programa": pl.programa_id, "pruebas": list(pruebas)})
#         ctx.update({"programas": programas, "unidades_por_prueba": unidades_por_prueba})
#         return render(request, "labmain.html", ctx)

# @login_required
# def lab_route(request):

#     lab_id = request.session.get('laboratorio_seleccionado')
#     if not lab_id:
#         return redirect('lab:select_lab')

#     lab = get_object_or_404(Laboratorio, pk=lab_id)

#     # Forzar transición si corresponde (fecha de corte u override vencido)
#     lab = avanzar_estado_si_corresponde(lab)

#     # En lugar de saltar a otra URL, siempre usa la vista principal
#     return redirect('lab:labmainview')
#     # Ruteo por estado
#     # if lab.estado == 1:
#     #     return redirect('lab:accept_configurations')
#     # elif lab.estado == 2:
#     #     return redirect('lab:lab_data_entry')
#     # else:  # estado == 3 (Consulta)
#     #     # Puedes crear una vista de reportes/consulta y redirigir aquí
#     #     return redirect('lab:lab_data_entry')  # fallback: ver datos


# --------------------------
# Vista para propuestas de nuevas propiedades usando un modal (instrumentos, métodos, reactivos, unidades)
# --------------------------
@require_POST
@login_required
def propose_property(request):
    tipo = request.POST.get('tipo')            # 'instrumento'|'metodo'|'reactivo'|'unidad'
    valor = request.POST.get('valor', '').strip()
    desc  = request.POST.get('descripcion', '').strip()
    if tipo not in {'instrumento','metodo','reactivo','unidad'} or not valor:
        return JsonResponse({'error': 'Datos inválidos'}, status=400)
    prop = PropiedadARevisar.objects.create(
        tipoElemento=tipo,
        valor=valor,
        descripcion=desc,
        status=0
    )
    return JsonResponse({'ok': True, 'id': prop.id})

# --------------------------
# Vista para captura de datos
# --------------------------
# @login_required
# def lab_data_entry(request):
#     lab_id = request.session.get('laboratorio_seleccionado')
#     if not lab_id:
#         return redirect('lab:select_lab')
#     lab = get_object_or_404(Laboratorio, pk=lab_id)

#     # Asegurar estado actualizado
#     lab = avanzar_estado_si_corresponde(lab)
#     if lab.estado == 1:
#         return redirect('lab:accept_configurations')

#     if request.method == 'GET':
#         # Solo pruebas configuradas
#         cfgs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=lab)
#         pruebas_cfg_ids = set(cfgs.values_list('prueba_id', flat=True))

#         pls = ProgramaLaboratorio.objects.filter(laboratorio_id=lab).select_related('programa_id')
#         programas = []
#         for pl in pls:
#             pruebas = Prueba.objects.filter(
#                 programa_id=pl.programa_id,
#                 id__in=pruebas_cfg_ids
#             ).order_by('nombre')
#             if pruebas.exists():
#                 programas.append({'programa': pl.programa_id, 'pruebas': pruebas})

#         return render(request, 'data_entry.html', {'lab': lab, 'programas': programas})

#     # POST: guardado parcial
#     mes = date.today().replace(day=1)
#     if mes_str:
#         try:
#             yyyy, mm, dd = map(int, mes_str.split('-'))
#             mes = date(yyyy, mm, 1)
#         except Exception:
#             mes = date.today().replace(day=1)
#     else:
#         mes = date.today().replace(day=1)

#     saved, errors = 0, {}
#     with transaction.atomic():
#         for key, val in request.POST.items():
#             if not key.startswith('valor_'):
#                 continue
#             if val == '':
#                 continue
#             try:
#                 prueba_id = int(key.split('_', 1)[1])
#                 valor = float(val)
#             except Exception:
#                 errors[key] = 'Valor inválido'
#                 continue
#             prueba = get_object_or_404(Prueba, pk=prueba_id)
#             try:
#                 obj, created = Dato.objects.update_or_create(
#                     laboratorio_id_id=lab.id,
#                     prueba_id_id=prueba.id,
#                     mes=mes,
#                     defaults={'valor': valor}
#                 )
#                 saved += 1
#             except IntegrityError:
#                 errors[key] = 'Duplicado en el mes'
#     return JsonResponse({'saved': saved, 'errors': errors})

def filled_all_month(lab, mes):
    """True si todas las pruebas configuradas del laboratorio tienen Dato en ese mes."""
    req_ids = set(LaboratorioPruebaConfig.objects.filter(laboratorio_id=lab.id).values_list('prueba_id', flat=True))
    if not req_ids:
        return False
    capturadas = Dato.objects.filter(laboratorio_id=lab.id, mes=mes, prueba_id_id__in=req_ids).count()
    return capturadas >= len(req_ids)

# def avanzar_estado_si_corresponde(lab: Laboratorio, *, persistir: bool = True) -> Laboratorio:
#     """
#     - Admin manda en estado 3 (Consulta): no se sobreescribe automáticamente.
#     - Con override: mientras hoy <= override_edicion_hasta, no se fuerza; si hoy > override, estado => 2.
#     - Sin override: si hoy.day > edicion_hasta_dia (default 15), estado => 2.
#     """
#     hoy = timezone.localdate()
#     if lab.estado == 3:
#         return lab
#     if lab.override_edicion_activa and lab.override_edicion_hasta:
#         if hoy > lab.override_edicion_hasta and lab.estado != 2:
#             lab.estado = 2
#             if persistir:
#                 lab.save(update_fields=['estado'])
#         return lab
#     dia_limite = lab.edicion_hasta_dia or 15
#     if hoy.day > dia_limite and lab.estado != 2:
#         lab.estado = 2
#         if persistir:
#             lab.save(update_fields=['estado'])
#     return lab

@login_required
def lab_data_entry(request):
    lab_id = request.session.get('laboratorio_seleccionado')
    if not lab_id:
        return JsonResponse({'error': 'Laboratorio no seleccionado'}, status=400)

    lab = get_object_or_404(Laboratorio, pk=lab_id)
    lab = avanzar_estado_si_corresponde(lab)
    if lab.estado == 1:
        return JsonResponse({'error': 'Modo configuración activo; no se permite registro'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    # Mes siempre controlado por servidor
    mes = date.today().replace(day=1)

    saved, errors = 0, {}
    import re
    sci_re = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\d*\.\d+)(?:[eE][+-]?\d+)?$')

    with transaction.atomic():
        for key, val in request.POST.items():
            if not key.startswith('valor_'):
                continue

            # Refuerzo: ignorar vacíos/espacios
            if val is None or str(val).strip() == '':
                continue

            # Normalizar coma decimal a punto y validar formato
            raw = str(val).strip().replace(',', '.')
            if not sci_re.match(raw):
                errors[key] = 'Valor inválido'
                continue

            try:
                prueba_id = int(key.split('_', 1)[1])
                valor = float(raw)
            except Exception:
                errors[key] = 'Valor inválido'
                continue

            prueba = get_object_or_404(Prueba, pk=prueba_id)
            # try:
            #     Dato.objects.update_or_create(
            #         laboratorio_id_id=lab.id,
            #         prueba_id_id=prueba.id,
            #         mes=mes,
            #         defaults={'valor': valor}
            #     )
            #     saved += 1
            # except IntegrityError:
            #     errors[key] = 'Duplicado en el mes'
            obj, created = Dato.objects.get_or_create(
                laboratorio_id_id=lab.id,
                prueba_id_id=prueba.id,
                mes=mes,
                defaults={'valor': valor}
            )
            if created:
                saved += 1
            else:
                errors[key] = 'Dato ya registrado este mes'

    # return JsonResponse({'saved': saved, 'errors': errors}, status=200)
    hoy = timezone.localdate()
    cap_override_vigente = lab.override_captura_activa and (lab.override_captura_hasta is None or hoy <= lab.override_captura_hasta)
    if lab.estado == 2 and not cap_override_vigente and filled_all_month(lab, mes):
        lab.estado = 3
        lab.save(update_fields=['estado'])
    closed = (lab.estado == 3) and not cap_override_vigente
    return JsonResponse({'saved': saved, 'errors': errors, 'closed': closed}, status=200)


# ------- Vistas PDF al final del archivo --------

class ReportUploadView(View):
    def post(self, request, *args, **kwargs):
        lab_id = request.POST.get('laboratorio_id')
        mes_str = request.POST.get('mes')
        nombre = request.POST.get('nombre') or 'Reporte'
        archivo = request.FILES.get('archivo')
        if not lab_id or not mes_str or not archivo:
            return JsonResponse({'success': False, 'errors': {'non_field': ['Faltan campos requeridos']}}, status=400)
        if archivo.content_type != 'application/pdf':
            return JsonResponse({'success': False, 'errors': {'archivo': ['Solo PDF es permitido']}}, status=400)
        if len(mes_str) == 7:
            mes_str = f'{mes_str}-01'
        from datetime import date
        try:
            yyyy, mm, dd = map(int, mes_str.split('-'))
            mes = date(yyyy, mm, 1)
        except Exception:
            return JsonResponse({'success': False, 'errors': {'mes': ['Formato inválido']}}, status=400)
        lab = get_object_or_404(Laboratorio, pk=lab_id)
        from django.db import transaction
        with transaction.atomic():
            rep = Reporte.objects.create(laboratorio=lab, mes=mes, nombre=nombre, archivo=archivo)
        return JsonResponse({'success': True, 'data': {'id': rep.id, 'nombre': rep.nombre}})

class ReportListView(View):
    def get(self, request, *args, **kwargs):
        lab_id = request.GET.get('laboratorio_id')
        mes_str = request.GET.get('mes')
        if not lab_id or not mes_str:
            return JsonResponse({'success': False, 'errors': {'non_field': ['Faltan parámetros']}}, status=400)
        if len(mes_str) == 7:
            mes_str = f'{mes_str}-01'
        from datetime import date
        try:
            yyyy, mm, dd = map(int, mes_str.split('-'))
            mes = date(yyyy, mm, 1)
        except Exception:
            return JsonResponse({'success': False, 'errors': {'mes': ['Formato inválido']}}, status=400)
        lab = get_object_or_404(Laboratorio, pk=lab_id)
        data = [{'id': r.id, 'nombre': r.nombre, 'url': r.archivo.url} for r in lab.reportes.filter(mes=mes).order_by('-creado_en')]
        return JsonResponse({'success': True, 'data': data})
