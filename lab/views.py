import json, os
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
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
import re
from django.core.mail import send_mail, EmailMultiAlternatives
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.conf import settings
from django.views.generic import ListView
from django.contrib.auth import get_user_model
from lab.utils.estados import filled_all_month, puede_capturar_datos
from .utils.allow_edit_now import get_allow_edit_now


from .models import (
    UserLaboratorio, ProgramaLaboratorio, Prueba, LaboratorioPruebaConfig,
    Instrumento, MetodoAnalitico, Reactivo, UnidadDeMedida, PropiedadARevisar,
    Laboratorio, Dato, Reporte
)

class MisPropuestasListView(LoginRequiredMixin, ListView):
    template_name = 'templates/propuestas/mis_propuestas.html'
    context_object_name = 'propuestas'
    paginate_by = 20

    def get_queryset(self):
        qs = _propuestas_queryset_for(self.request.user).order_by('-created_at')
        if self.request.user.is_staff:
            return qs
        return qs.filter(propuesto_por=self.request.user)


# ----------- Helpers -----------
def _propuestas_queryset_for(user):
    qs = PropiedadARevisar.objects.all().order_by('-created_at')
    return qs if user.is_staff else qs.filter(propuesto_por=user)

def user_labs_str(user):
    names = list(UserLaboratorio.objects.filter(user_id=user).values_list('laboratorio__nombre', flat=True))
    return ", ".join(names) if names else "Sin laboratorio"


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

# ---------------------------------------------
# GET: Vista principal de laboratorio
# - Única definición consolidada
# - Pasa captura_bloqueada al template para controlar disabled en inputs
# - Promueve 2→3 solo si la ventana de captura está cerrada y el mes está completo
# ---------------------------------------------
class LabMainView(LoginRequiredMixin, View):
    template_name = 'labmain.html'
    login_url = reverse_lazy('lab:homepage')

    def get(self, request):
        lab_id = request.session.get("laboratorio_seleccionado")
        lab = Laboratorio.objects.filter(id=lab_id).first() if lab_id else None
        if not lab:
            messages.error(request, "No hay laboratorio asociado a tu usuario.")
            return redirect('lab:homepage')

        lab = avanzar_estado_si_corresponde(lab, persistir=True)
        # Ventana de captura
        cap_window_open = puede_capturar_datos(lab)

        # Promover 2→3 solo fuera de ventana y con mes completo
        if lab.estado == 2 and not cap_window_open:
            mes_vigente = timezone.localdate().replace(day=1)
            if filled_all_month(lab, mes_vigente):
                lab.estado = 3
                lab.save(update_fields=['estado'])

        ctx = {
            'lab': lab,
            'today': timezone.localdate(),
            'captura_bloqueada': not cap_window_open
        }

        # Estado 1: configuración (AQUÍ el ajuste mínimo)
        if lab.estado == 1:
            programas_ids = ProgramaLaboratorio.objects.filter(
                laboratorio_id=lab.id
            ).values_list('programa_id', flat=True)

            pruebas_laboratorio = Prueba.objects.filter(programa_id__in=programas_ids)

            accepted_configs = LaboratorioPruebaConfig.objects.filter(laboratorio_id=lab)
            accepted_prueba_ids = accepted_configs.values_list('prueba_id', flat=True)

            pending_pruebas = pruebas_laboratorio.exclude(id__in=accepted_prueba_ids)

            # NUEVO: catálogos y envoltura con permiso de edición
            accepted_configs_wrapped = [
                {"obj": c, "can_edit": puede_editar_config(lab, c)}
                for c in accepted_configs
            ]
            instrumentos = Instrumento.objects.all().order_by('nombre')
            metodos = MetodoAnalitico.objects.all().order_by('nombre')
            reactivos = Reactivo.objects.all().order_by('nombre')
            unidades = UnidadDeMedida.objects.all().order_by('nombre')

            # NUEVO: propuestas (ajusta filtro si aplican visibilidades por usuario/lab)
            propuestas = PropiedadARevisar.objects.all().order_by('-id')

            ctx.update({
                'pending_pruebas': pending_pruebas,
                'accepted_configs': accepted_configs,
                'accepted_configs_wrapped': accepted_configs_wrapped,
                'instrumentos': instrumentos,
                'metodos': metodos,
                'reactivos': reactivos,
                'unidades': unidades,
                'propuestas': propuestas,
            })
            ctx['allow_edit_now'] = get_allow_edit_now(lab, ctx['today'])
            return render(request, self.template_name, ctx)

        # Estados 2 y 3: captura/consulta (sin cambios)
        cfgs = (LaboratorioPruebaConfig.objects
                .filter(laboratorio_id=lab)
                .select_related("prueba_id", "unidad_de_medida_id"))
        unidades_por_prueba = {
            c.prueba_id_id: (c.unidad_de_medida_id.nombre if c.unidad_de_medida_id else "")
            for c in cfgs
        }
        pruebas_cfg_ids = list(unidades_por_prueba.keys())

        pls = ProgramaLaboratorio.objects.filter(laboratorio_id=lab).select_related("programa_id")

        grupos = []
        for pl in pls:
            pruebas = (Prueba.objects
                       .filter(programa_id=pl.programa_id, id__in=pruebas_cfg_ids)
                       .order_by("nombre"))
            if not pruebas.exists():
                continue
            filas = []
            for p in pruebas:
                unidad = unidades_por_prueba.get(p.id, "")
                filas.append({"prueba": p, "unidad": unidad})
            grupos.append({"programa": pl.programa_id, "filas": filas})

        mes_vigente = timezone.localdate().replace(day=1)
        datos_list = Dato.objects.filter(laboratorio_id=lab.id, mes=mes_vigente)
        datos_por_prueba = {d.prueba_id_id: d for d in datos_list}

        pruebas_flat = (Prueba.objects
                        .filter(id__in=pruebas_cfg_ids)
                        .order_by("programa_id__nombre", "nombre"))

        ctx.update({
            "programas": grupos,
            "pruebas": pruebas_flat,
            "datos_por_prueba": datos_por_prueba,
            "mes_vigente": mes_vigente,
        })

        if lab.estado == 3:
            reportes = (Reporte.objects
                        .filter(laboratorio=lab)
                        .prefetch_related('programas', 'pruebas')
                        .order_by('-mes', '-creado_en'))
            ctx.update({'reportes': reportes})

        return render(request, self.template_name, ctx)

class ReportesView(LoginRequiredMixin, View):
    template_name = "reports.html"
    login_url = "lab:homepage"

    def get(self, request):
        lab_id = request.session.get("laboratorio_seleccionado")
        lab = Laboratorio.objects.filter(id=lab_id).first() if lab_id else None
        if not lab:
            return redirect("lab:homepage")

        cfgs = (LaboratorioPruebaConfig.objects
                .filter(laboratorio_id=lab)
                .select_related("prueba_id", "unidad_de_medida_id"))
        unidades_por_prueba = {
            c.prueba_id_id: (c.unidad_de_medida_id.nombre if c.unidad_de_medida_id else "")
            for c in cfgs
        }
        pruebas_cfg_ids = list(unidades_por_prueba.keys())

        pls = ProgramaLaboratorio.objects.filter(laboratorio_id=lab).select_related("programa_id")
        grupos = []
        for pl in pls:
            pruebas = (Prueba.objects
                       .filter(programa_id=pl.programa_id, id__in=pruebas_cfg_ids)
                       .order_by("nombre"))
            if not pruebas.exists():
                continue
            filas = []
            for p in pruebas:
                unidad = unidades_por_prueba.get(p.id, "")
                filas.append({"prueba": p, "unidad": unidad})
            grupos.append({"programa": pl.programa_id, "filas": filas})

        mes_vigente = timezone.localdate().replace(day=1)
        datos_list = Dato.objects.filter(laboratorio_id=lab.id, mes=mes_vigente)
        datos_por_prueba = {d.prueba_id_id: d for d in datos_list}

        # Obtener reportes del laboratorio (sin depender del estado)
        reportes = (Reporte.objects
                    .filter(laboratorio=lab)
                    .prefetch_related("programas", "pruebas")
                    .order_by("-mes", "-creado_en"))

        ctx = {
            'lab': lab,
            'today': timezone.localdate(),
            'programas': grupos,
            'datos_por_prueba': datos_por_prueba,
            'mes_vigente': mes_vigente,
            'reportes': reportes,
        }
        return render(request, self.template_name, ctx)


# class ReportesView(LoginRequiredMixin, View):
#     template_name = 'reports.html'
#     login_url = reverse_lazy('lab:homepage')

#     def get(self, request):
#         lab_id = request.session.get('laboratorio_seleccionado')
#         if not lab_id:
#             return redirect('lab:homepage')
#         lab = get_object_or_404(Laboratorio, pk=lab_id)

#         # Mismo queryset que LabMainView en estado 3
#         reportes = (Reporte.objects
#                     .filter(laboratorio=lab)
#                     .prefetch_related('programas', 'pruebas')
#                     .order_by('-mes', '-creado_en'))

#         ctx = {
#             'lab': lab,
#             'today': timezone.localdate(),
#             'reportes': reportes,
#         }
#         return render(request, self.template_name, ctx)


# --------------------------
# Crear o actualizar configuración (incluye propuestas)
# --------------------------
# @login_required
# @transaction.atomic
# def crear_o_actualizar_configuracion(request):
#     """
#     Maneja propuestas individuales y la aceptación de configuraciones con validaciones
#     de pertenencia, existencia y estado de propuestas, todo bajo transacción atómica.
#     """
#     if request.method != "POST":
#         return JsonResponse({"success": False, "error": "Método no permitido"}, status=405)  # [docs]

#     laboratorio_id = request.session.get("laboratorio_seleccionado")
#     if not laboratorio_id:
#         return JsonResponse({"success": False, "error": "Debes seleccionar un laboratorio primero."}, status=400)  # [docs]

#     # Seguridad: validar que el usuario tenga acceso al laboratorio
#     pertenece = UserLaboratorio.objects.filter(user_id=request.user, laboratorio_id=laboratorio_id).exists()
#     if not pertenece:
#         return JsonResponse({"success": False, "error": "Acceso denegado al laboratorio seleccionado."}, status=403)  # [docs]

#     laboratorio = get_object_or_404(Laboratorio, id=laboratorio_id)
#     prueba_id = request.POST.get("prueba_id")
#     accion = request.POST.get("accion", "").strip()

#     if not prueba_id:
#         return JsonResponse({"success": False, "error": "ID de prueba es requerido."}, status=400)  # [docs]

#     # Validar que la prueba pertenezca a algún programa asignado al laboratorio
#     programas_ids = ProgramaLaboratorio.objects.filter(laboratorio_id=laboratorio.id).values_list('programa_id', flat=True)
#     if not Prueba.objects.filter(id=prueba_id, programa_id__in=programas_ids).exists():
#         return JsonResponse({"success": False, "error": "La prueba no pertenece al laboratorio seleccionado."}, status=400)  # [docs]

#     prueba = get_object_or_404(Prueba, id=prueba_id)

#     # --------- Propuestas ---------
#     if accion.startswith("proponer_"):
#         tipo = accion.replace("proponer_", "")
#         valor = (request.POST.get(f"{tipo}_valor") or "").strip()
#         descripcion = (request.POST.get(f"{tipo}_descripcion") or "").strip()

#         tipos_validos = ["instrumento", "metodo", "reactivo", "unidad"]
#         if tipo not in tipos_validos:
#             return JsonResponse({"success": False, "error": f"Tipo '{tipo}' no válido."}, status=400)  # [docs]

#         if not valor:
#             return JsonResponse({"success": False, "error": f"El valor para {tipo} es requerido."}, status=400)  # [docs]

#         modelos_map = {
#             "instrumento": Instrumento,
#             "metodo": MetodoAnalitico,
#             "reactivo": Reactivo,
#             "unidad": UnidadDeMedida
#         }
#         modelo = modelos_map[tipo]

#         # No duplicar un valor que ya exista en la tabla maestra
#         if modelo.objects.filter(nombre__iexact=valor).exists():
#             return JsonResponse({"success": False, "error": f"Ya existe un {tipo} con el nombre '{valor}'"}, status=400)  # [docs]

#         # No duplicar propuestas pendientes o aprobadas con el mismo valor/tipo
#         if PropiedadARevisar.objects.filter(tipoElemento=tipo, valor__iexact=valor, status__in=[0, 1]).exists():
#             return JsonResponse({"success": False, "error": f"Ya existe una propuesta para {tipo} '{valor}'"}, status=400)  # [docs]

#         propuesta = PropiedadARevisar.objects.create(
#             tipoElemento=tipo, valor=valor, descripcion=descripcion, status=0
#         )
#         return JsonResponse({
#             "success": True,
#             "message": f"{tipo.capitalize()} '{valor}' propuesto exitosamente",
#             "propuesta": {
#                 "id": propuesta.id,
#                 "tipoElemento": propuesta.tipoElemento,              # "instrumento" | "metodo" | "reactivo" | "unidad"
#                 "valor": propuesta.valor,
#                 "descripcion": propuesta.descripcion or "",
#                 "status": propuesta.status,                          # 0/1/2
#                 "status_text": "Pendiente" if propuesta.status == 0 else ("Aprobado" if propuesta.status == 1 else "Rechazado")
#             }
#         }, status=201)  # [docs]

#     # --------- Aceptar configuración ---------
#     if accion == "aceptar":
#         campos_config = {
#             "instrumento_id": (request.POST.get("instrumento_id"), Instrumento),
#             "metodo_analitico_id": (request.POST.get("metodo_analitico_id"), MetodoAnalitico),
#             "reactivo_id": (request.POST.get("reactivo_id"), Reactivo),
#             "unidad_de_medida_id": (request.POST.get("unidad_de_medida_id"), UnidadDeMedida),
#         }

#         # 1) Todos los campos presentes
#         faltantes = []
#         for campo, (valor, _) in campos_config.items():
#             if not valor:
#                 faltantes.append(campo.replace("_id", "").replace("_", " ").title())
#         if faltantes:
#             return JsonResponse({"success": False, "error": "Campos faltantes: " + ", ".join(faltantes)}, status=400)  # [docs]

#         # 2) IDs válidos que existan
#         instancias = {}
#         for campo, (valor_id, modelo) in campos_config.items():
#             try:
#                 instancias[campo] = modelo.objects.get(id=valor_id)
#             except modelo.DoesNotExist:
#                 return JsonResponse({"success": False, "error": f"{campo.replace('_id','').replace('_',' ').title()} seleccionado no existe"}, status=400)  # [docs]

#         # 3) No aceptar si hay una propuesta pendiente con el mismo nombre/tipo
#         for campo, instancia in instancias.items():
#             tipo_norm = campo.replace("_id", "").replace("metodo_analitico", "metodo").replace("unidad_de_medida", "unidad")
#             propuesta_pendiente = PropiedadARevisar.objects.filter(
#                 tipoElemento=tipo_norm, valor__iexact=instancia.nombre, status=0
#             ).first()
#             if propuesta_pendiente:
#                 return JsonResponse({"success": False, "error": f"El {tipo_norm} '{instancia.nombre}' tiene una propuesta pendiente de aprobación"}, status=400)  # [docs]

#         try:
#             config, created = LaboratorioPruebaConfig.objects.update_or_create(
#                 laboratorio_id=laboratorio,
#                 prueba_id=prueba,
#                 defaults={
#                     "instrumento_id": instancias["instrumento_id"],
#                     "metodo_analitico_id": instancias["metodo_analitico_id"],
#                     "reactivo_id": instancias["reactivo_id"],
#                     "unidad_de_medida_id": instancias["unidad_de_medida_id"],
#                 }
#             )
#         except IntegrityError:
#             # Por si se quisiera crear en vez de actualizar y ya existe por unique constraint
#             return JsonResponse({"success": False, "error": "Ya existe una configuración para esta prueba en este laboratorio"}, status=409)  # [docs]

#         return JsonResponse({"success": True, "message": "Configuración aceptada exitosamente", "config_id": config.id, "created": created}, status=201 if created else 200)  # [docs]

#     # Acción desconocida
#     return JsonResponse({"success": False, "error": "Acción no válida"}, status=400)  # [docs]

# views.py (crear_o_actualizar_configuracion) — reemplaza únicamente el bloque indicado

@login_required
@require_POST
def crear_o_actualizar_configuracion(request):
    lab_id = request.session.get('laboratorio_seleccionado')
    if not lab_id:
        return JsonResponse({'success': False, 'error': 'Laboratorio no seleccionado'}, status=400)

    # NUEVO: obtener instancia de laboratorio
    lab = get_object_or_404(Laboratorio, pk=lab_id)

    prueba_id = request.POST.get('prueba_id')
    ins_id = request.POST.get('instrumento_id')
    met_id = request.POST.get('metodo_analitico_id')
    rea_id = request.POST.get('reactivo_id')
    uni_id = request.POST.get('unidad_de_medida_id')

    if not all([prueba_id, ins_id, met_id, rea_id, uni_id]):
        return JsonResponse({'success': False, 'error': 'Faltan campos obligatorios'}, status=400)

    with transaction.atomic():
        # CLAVE: usar instancia en laboratorio_id y entero en prueba_id_id
        cfg, _ = LaboratorioPruebaConfig.objects.select_for_update().get_or_create(
            laboratorio_id=lab,
            prueba_id_id=int(prueba_id),
        )
        # Mantener asignaciones *_id_id en FKs relacionados
        cfg.instrumento_id_id = int(ins_id)
        cfg.metodo_analitico_id_id = int(met_id)
        cfg.reactivo_id_id = int(rea_id)
        cfg.unidad_de_medida_id_id = int(uni_id)
        cfg.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'config_id': cfg.id, 'message': 'Configuración guardada'})

    return redirect('lab:accept_configurations')

@login_required
@require_POST
def actualizar_configuracion(request, config_id):
    """
    Actualiza una configuración existente y retorna JSON si es AJAX.
    """
    lab_id = request.session.get('laboratorio_seleccionado')
    if not lab_id:
        return JsonResponse({'success': False, 'error': 'Laboratorio no seleccionado'}, status=400)

    cfg = get_object_or_404(LaboratorioPruebaConfig, id=config_id, laboratorio_id=lab_id)

    ins_id = request.POST.get('instrumento_id')
    met_id = request.POST.get('metodo_analitico_id')
    rea_id = request.POST.get('reactivo_id')
    uni_id = request.POST.get('unidad_de_medida_id')

    if not all([ins_id, met_id, rea_id, uni_id]):
        return JsonResponse({'success': False, 'error': 'Faltan campos obligatorios'}, status=400)

    with transaction.atomic():
        cfg.instrumento_id_id = int(ins_id)
        cfg.metodo_analitico_id_id = int(met_id)
        cfg.reactivo_id_id = int(rea_id)
        cfg.unidad_de_medida_id_id = int(uni_id)
        cfg.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'config_id': cfg.id, 'message': 'Configuración actualizada'})

    return redirect('lab:accept_configurations')



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
        'propuestas': _propuestas_queryset_for(request.user),
        "laboratorio": laboratorio,
        "today": timezone.localdate(),
    }
    # Renderizar labmain para que traiga topbar/sidebar/footer y dentro incluya el parcial
    context["allow_edit_now"] = get_allow_edit_now(laboratorio, context["today"])
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

@login_required(login_url='lab:homepage')
@require_POST
def propose_property(request):
    tipo = request.POST.get('tipo')
    valor = (request.POST.get('valor') or '').strip()
    desc  = (request.POST.get('descripcion') or '').strip()
    if tipo not in {'instrumento','metodo','reactivo','unidad'} or not valor:
        return JsonResponse({'error': 'Datos inválidos'}, status=400)

    prop = PropiedadARevisar(
        tipoElemento=tipo, valor=valor, descripcion=desc, status=0, propuesto_por=request.user
    )
    prop.ensure_nonce(force=True)
    prop.save()

    payload = {'id': prop.id, 'n': prop.moderation_nonce}
    token = signing.dumps(payload, salt='prop-moderation')
    accept_url = request.build_absolute_uri(reverse('lab:proposal_accept') + f'?t={token}')
    reject_url = request.build_absolute_uri(reverse('lab:proposal_reject') + f'?t={token}')
    labs = user_labs_str(request.user)
    ts = timezone.now().strftime('%Y%m%d-%H%M%S')

    # Acuse al proponente (subject único)
    subj_user = f'[Evaluat] Propuesta registrada #{prop.id} — {tipo} — {valor} — {ts}'
    if request.user.email:
        send_mail(
            subj_user,
            f'Propiedad propuesta por {request.user.get_username()} - {labs}\nTipo: {tipo}\nValor: {valor}\nDescripción: {desc or "(sin descripción)"}',
            getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            [request.user.email],
            fail_silently=True
        )

    # Aviso al staff (subject único)
    User = get_user_model()
    recipients = list(User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True))
    if recipients:
        subj_staff = f'[Evaluat] Nueva propuesta #{prop.id} — {tipo} — {valor} — {ts}'
        text_body = (f'Propiedad propuesta por {request.user.get_username()} - {labs}\n'
                     f'Tipo: {tipo}\nValor: {valor}\nDescripción: {desc or "(sin descripción)"}\n\n'
                     f'Aceptar: {accept_url}\nRechazar: {reject_url}\n')
        html_body = (f'<p><strong>Propiedad propuesta</strong> por {request.user.get_username()} - {labs}</p>'
                     f'<p>Tipo: {tipo}<br>Valor: {valor}<br>Descripción: {desc or "(sin descripción)"}.</p>'
                     f'<p>'
                     f'<a href="{accept_url}" style="padding:.5rem 1rem; background:#198754; color:#fff; text-decoration:none; border-radius:6px;">Aceptar</a> '
                     f'<a href="{reject_url}" style="padding:.5rem 1rem; background:#dc3545; color:#fff; text-decoration:none; border-radius:6px; margin-left:.5rem;">Rechazar</a>'
                     f'</p>')
        send_mail(subj_staff, text_body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), recipients, html_message=html_body, fail_silently=False)

    return JsonResponse({'ok': True, 'id': prop.id})

@login_required(login_url='lab:homepage')
@user_passes_test(lambda u: u.is_staff, login_url='lab:homepage')
def proposal_accept(request):
    t = request.GET.get('t') or ''
    if not t:
        return HttpResponseBadRequest('Falta token')
    try:
        data = signing.loads(t, salt='prop-moderation', max_age=60*60*72)
    except (BadSignature, SignatureExpired):
        return HttpResponseForbidden('Token inválido o expirado')

    with transaction.atomic():
        prop = PropiedadARevisar.objects.select_for_update().get(pk=data['id'])
        nonce = getattr(prop, 'moderation_nonce', None)
        if prop.status != 0 or not nonce or nonce != data.get('n'):
            return HttpResponseForbidden('Este enlace ya no es válido (acción ya ejecutada).')
        prop.status = 1
        prop.resolved_by = request.user
        prop.resolved_at = timezone.now()
        prop.moderation_nonce = None
        prop.save(update_fields=['status','resolved_by','resolved_at','moderation_nonce'])

    # Correos
    # correo a usuario proponente
    if prop.propuesto_por and prop.propuesto_por.email:
        labs = user_labs_str(prop.propuesto_por)
        moderator = request.user.get_username()
        nombre = prop.valor
        tipo = prop.tipoElemento
        desc = prop.descripcion or "(sin descripción)"
        send_mail(
            subject=f'[Evaluat] Propuesta aceptada #{prop.id} — {nombre}',
            message=(
                f'La propuesta "{nombre}" fue aceptada\n\n'
                f'Propiedad propuesta por {prop.propuesto_por.get_username()} - {labs}\n'
                f'Tipo: {tipo}\n'
                f'Valor: {nombre}\n'
                f'Descripción: {desc}\n'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=[prop.propuesto_por.email],
            fail_silently=True
        )

    # correo a staff
    User = get_user_model()
    staff = list(User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True))
    if staff:
        labs = user_labs_str(prop.propuesto_por)
        moderator = request.user.get_username()
        nombre = prop.valor
        tipo = prop.tipoElemento
        desc = prop.descripcion or "(sin descripción)"
        send_mail(
            subject=f'[Evaluat] Propuesta resuelta (Aceptada) #{prop.id} — {nombre}',
            message=(
                f'La propuesta "{nombre}" fue aceptada por {moderator}\n\n'
                f'Propiedad propuesta por {prop.propuesto_por.get_username()} - {labs}\n'
                f'Tipo: {tipo}\n'
                f'Valor: {nombre}\n'
                f'Descripción: {desc}\n'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=staff,
            fail_silently=True
        )
    return redirect('lab:labmainview')

@login_required(login_url='lab:homepage')
@user_passes_test(lambda u: u.is_staff, login_url='lab:homepage')
def proposal_reject(request):
    t = request.GET.get('t') or ''
    if not t:
        return HttpResponseBadRequest('Falta token')
    try:
        data = signing.loads(t, salt='prop-moderation', max_age=60*60*72)
    except (BadSignature, SignatureExpired):
        return HttpResponseForbidden('Token inválido o expirado')

    with transaction.atomic():
        prop = PropiedadARevisar.objects.select_for_update().get(pk=data['id'])
        nonce = getattr(prop, 'moderation_nonce', None)
        if prop.status != 0 or not nonce or nonce != data.get('n'):
            return HttpResponseForbidden('Este enlace ya no es válido (acción ya ejecutada).')
        prop.status = 2
        prop.resolved_by = request.user
        prop.resolved_at = timezone.now()
        prop.moderation_nonce = None
        prop.save(update_fields=['status','resolved_by','resolved_at','moderation_nonce'])

    # correo a usuario proponente
    if prop.propuesto_por and prop.propuesto_por.email:
        labs = user_labs_str(prop.propuesto_por)
        moderator = request.user.get_username()
        nombre = prop.valor
        tipo = prop.tipoElemento
        desc = prop.descripcion or "(sin descripción)"
        send_mail(
            subject=f'[Evaluat] Propuesta rechazada #{prop.id} — {nombre}',
            message=(
                f'La propuesta "{nombre}" fue rechazada\n\n'
                f'Propiedad propuesta por {prop.propuesto_por.get_username()} - {labs}\n'
                f'Tipo: {tipo}\n'
                f'Valor: {nombre}\n'
                f'Descripción: {desc}\n'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=[prop.propuesto_por.email],
            fail_silently=True
        )

    # correo a staff
    User = get_user_model()
    staff = list(User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True))
    if staff:
        labs = user_labs_str(prop.propuesto_por)
        moderator = request.user.get_username()
        nombre = prop.valor
        tipo = prop.tipoElemento
        desc = prop.descripcion or "(sin descripción)"
        send_mail(
            subject=f'[Evaluat] Propuesta resuelta (Rechazada) #{prop.id} — {nombre}',
            message=(
                f'La propuesta "{nombre}" fue rechazada por {moderator}\n\n'
                f'Propiedad propuesta por {prop.propuesto_por.get_username()} - {labs}\n'
                f'Tipo: {tipo}\n'
                f'Valor: {nombre}\n'
                f'Descripción: {desc}\n'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=staff,
            fail_silently=True
        )
    return redirect('lab:labmainview')


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

# ---------------------------------------------
# POST: Captura de datos del laboratorio (mes vigente)
# - Crea si no existe
# - Actualiza solo si cambió
# - Omite si es idéntico
# - NO promueve 2→3 en POST (solo en GET y fuera de ventana)
# ---------------------------------------------
@login_required
@require_POST
def lab_data_entry(request):
    lab_id = request.session.get('laboratorio_seleccionado')
    if not lab_id:
        return JsonResponse(
            {'success': False, 'errors': {'non_field': 'Laboratorio no seleccionado'}},
            status=400
        )

    lab = get_object_or_404(Laboratorio, pk=lab_id)

    # Estado 1 (Configuración) no permite registro
    if lab.estado == 1:
        return JsonResponse(
            {'success': False, 'errors': {'non_field': 'Modo configuración activo; no se permite registro'}},
            status=403
        )

    # Mes controlado por servidor (primer día del mes actual)
    mes = date.today().replace(day=1)

    errors = {}
    saved_count = 0
    saved_list = []              # [{'prueba_id': int, 'valor': float}]
    skipped_existing_list = []   # [{'prueba_id': int}]

    sci_re = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\d*\.\d+)(?:[eE][+-]?\d+)?$')

    with transaction.atomic():
        for key, val in request.POST.items():
            if not key.startswith('valor_'):
                continue
            if val is None or str(val).strip() == '':
                continue

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

            # Buscar existente y decidir create/update/skip
            obj = Dato.objects.filter(
                laboratorio_id_id=lab.id,
                prueba_id_id=prueba.id,
                mes=mes
            ).first()

            if obj is None:
                obj = Dato.objects.create(
                    laboratorio_id_id=lab.id,
                    prueba_id_id=prueba.id,
                    mes=mes,
                    valor=valor
                )
                saved_count += 1
                saved_list.append({'prueba_id': prueba.id, 'valor': obj.valor})
            else:
                if obj.valor != valor:
                    obj.valor = valor
                    obj.save(update_fields=['valor'])
                    saved_count += 1
                    saved_list.append({'prueba_id': prueba.id, 'valor': obj.valor})
                else:
                    skipped_existing_list.append({'prueba_id': prueba.id})

    # Ventana de captura (edición) abierta/cerrada según override o día de corte
    cap_window_open = puede_capturar_datos(lab)
    closed = not cap_window_open

    return JsonResponse({
        'success': True,
        'saved': saved_count,
        'saved_list': saved_list,
        'skipped_existing': skipped_existing_list,
        'errors': errors,
        'closed': closed
    }, status=200)

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

@login_required
@require_POST
def bulk_save_configs(request):
    """
    Guardado general de configuraciones.
    Espera JSON con items: [
      {"mode": "create", "prueba_id": int, "instrumento_id": int, "metodo_analitico_id": int,
       "reactivo_id": int, "unidad_de_medida_id": int},
      {"mode": "update", "config_id": int, "instrumento_id": int, "metodo_analitico_id": int,
       "reactivo_id": int, "unidad_de_medida_id": int},
      ...
    ]
    """
    lab_id = request.session.get('laboratorio_seleccionado')
    if not lab_id:
        return JsonResponse({"success": False, "errors": {"non_field": "Laboratorio no seleccionado"}}, status=400)

    try:
        if request.content_type and "application/json" in request.content_type:
            items = json.loads(request.body.decode("utf-8") or "[]")
        else:
            items = json.loads(request.POST.get("items") or "[]")
        if not isinstance(items, list):
            raise ValueError("Formato inválido")
    except Exception:
        return JsonResponse({"success": False, "errors": {"non_field": "Payload JSON inválido"}}, status=400)

    saved = []
    errors = {}

    for it in items:
        mode = (it.get("mode") or "").strip().lower()
        ins_id = it.get("instrumento_id")
        met_id = it.get("metodo_analitico_id")
        rea_id = it.get("reactivo_id")
        uni_id = it.get("unidad_de_medida_id")

        if not all([ins_id, met_id, rea_id, uni_id]):
            key = str(it.get("config_id") or it.get("prueba_id") or "unknown")
            errors[key] = "Faltan campos obligatorios"
            continue

        try:
            with transaction.atomic():
                if mode == "update":
                    cfg = LaboratorioPruebaConfig.objects.select_for_update().get(
                        id=it.get("config_id"), laboratorio_id=lab_id
                    )
                elif mode == "create":
                    # crear o actualizar por (lab, prueba)
                    cfg, _created = LaboratorioPruebaConfig.objects.select_for_update().get_or_create(
                        laboratorio_id_id=lab_id,          # usar *_id para entero
                        prueba_id_id=int(it.get("prueba_id")),
                    )
                else:
                    key = str(it.get("config_id") or it.get("prueba_id") or "unknown")
                    errors[key] = "Modo inválido"
                    continue

                # Asignación de FKs: usa *_id con enteros para evitar consultas extra
                cfg.instrumento_id_id = int(ins_id)
                cfg.metodo_analitico_id_id = int(met_id)
                cfg.reactivo_id_id = int(rea_id)
                cfg.unidad_de_medida_id_id = int(uni_id)
                cfg.save()

                saved.append({
                    "mode": mode,
                    "config_id": cfg.id,
                    "prueba_id": it.get("prueba_id")
                })
        except LaboratorioPruebaConfig.DoesNotExist:
            key = str(it.get("config_id"))
            errors[key] = "Configuración no encontrada"
        except Exception as ex:
            key = str(it.get("config_id") or it.get("prueba_id") or "unknown")
            errors[key] = f"Error: {ex}"

    return JsonResponse({"success": True, "saved": saved, "errors": errors}, status=200)

@login_required
@user_passes_test(lambda u: u.is_staff)
@require_POST
def staff_toggle_edit_window(request):
    lab_id = request.session.get('laboratorio_seleccionado')
    lab = get_object_or_404(Laboratorio, pk=lab_id)

    # Parámetros opcionales: estado, override_edicion_activa, override_edicion_hasta (YYYY-MM-DD)
    estado = request.POST.get('estado')
    override_activa = request.POST.get('override_edicion_activa')
    override_hasta = request.POST.get('override_edicion_hasta')

    if estado in ('1','2','3'):
        lab.estado = int(estado)

    if override_activa is not None:
        lab.override_edicion_activa = str(override_activa).lower() in ('1','true','on','yes')

    if override_hasta:
        try:
            y,m,d = map(int, override_hasta.split('-'))
            from datetime import date
            lab.override_edicion_hasta = date(y,m,d)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'Fecha de override inválida'}, status=400)

    lab.save()
    allow = get_allow_edit_now(lab)
    return JsonResponse({'ok': True, 'estado': lab.estado, 'allow_edit_now': bool(allow)})
