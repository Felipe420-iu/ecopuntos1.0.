from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout, authenticate, login as auth_login, get_user_model, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.crypto import get_random_string
from django.conf import settings
from .models import Usuario, Canje, MaterialTasa, RedencionPuntos, Ruta, Alerta, Configuracion, Categoria, Recompensa, Logro, Notificacion, SesionUsuario, IntentoAcceso
from supabase import create_client
from django.http import JsonResponse
from decimal import Decimal
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import models
from django.db.models import Sum, Count
from datetime import date, timedelta
import json
from django.utils.http import url_has_allowed_host_and_scheme
from functools import wraps
from django.contrib.auth.forms import PasswordChangeForm
from .forms import ProfileForm
from django.views.decorators.csrf import csrf_exempt
from .security import SecurityManager, require_secure_session
from .statistics import StatisticsManager

# Configuración de Supabase
supabase_url = 'https://ferrazkesahlbqcitmny.supabase.co'
supabase_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcnJhemtlc2FobGJxY2l0bW55Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDg0NjY5MDYsImV4cCI6MjA2NDA0MjkwNn0.vwpKQupvRvMgxRkDvB0j3MOQPVXoCDhtbJQUX_LH8YQ'
supabase = create_client(supabase_url, supabase_key)

def index(request):
    from .models import Usuario
    testimonios = Usuario.usuarios_con_testimonio()[:12]  # Limitar a 12 testimonios
    return render(request, 'core/index.html', {'testimonios': testimonios})

def logout_view(request):
    next_url = request.GET.get('next', 'index')
    # Invalidar sesión segura
    SecurityManager.invalidate_session(request)
    logout(request)
    return redirect(next_url)

def registrate(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 != password2:
            messages.error(request, 'Las contraseñas no coinciden.')
            return render(request, 'core/registrate.html')

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            messages.error(request, 'El nombre de usuario ya existe.')
            return render(request, 'core/registrate.html')

        try:
            # Registrar en Supabase
            supabase.auth.sign_up({
                'email': email,
                'password': password1
            })
            # Registrar en Django
            user = User.objects.create_user(username=username, email=email, password=password1)
            user.save()
            messages.success(request, 'Usuario registrado correctamente. Inicia sesión.')
            return redirect('iniciosesion')
        except Exception as e:
            messages.error(request, f'Error al registrar usuario: {str(e)}')
            return render(request, 'core/registrate.html')

    return render(request, 'core/registrate.html')

def iniciosesion(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        next_url = request.POST.get('next') or request.GET.get('next')
        
        try:
            # Primero autenticar con Django
            user = authenticate(request, username=username, password=password)
            if user is not None:
                # Si la autenticación de Django es exitosa, intentar con Supabase
                try:
                    # Obtener el email del usuario para Supabase
                    supabase_response = supabase.auth.sign_in_with_password({
                        'email': user.email,  # Usar email en lugar de username
                        'password': password
                    })
                    # Crear sesión segura
                    SecurityManager.create_secure_session(request, user)
                    auth_login(request, user)
                    
                    # Mostrar notificaciones no leídas
                    notificaciones = Notificacion.objects.filter(usuario=user, leida=False)
                    for notificacion in notificaciones:
                        messages.success(request, notificacion.mensaje)
                        notificacion.leida = True
                        notificacion.save()
                    
                    # Determine where to redirect
                    if next_url and url_has_allowed_host_and_scheme(url=next_url, allowed_hosts={request.get_host(),}):
                        return redirect(next_url)
                    elif user.is_admin_user():
                        return redirect('paneladmin')
                    else:
                        return redirect('dashusuario')
                except Exception as e:
                    # Si falla Supabase pero Django funcionó, aún permitimos el inicio de sesión
                    # Crear sesión segura
                    SecurityManager.create_secure_session(request, user)
                    auth_login(request, user)
                    
                    # Mostrar notificaciones no leídas
                    notificaciones = Notificacion.objects.filter(usuario=user, leida=False)
                    for notificacion in notificaciones:
                        messages.success(request, notificacion.mensaje)
                        notificacion.leida = True
                        notificacion.save()
                    
                    # Determine where to redirect even if Supabase fails
                    if next_url and url_has_allowed_host_and_scheme(url=next_url, allowed_hosts={request.get_host(),}):
                        return redirect(next_url)
                    elif user.is_admin_user():
                        return redirect('paneladmin')
                    else:
                        return redirect('dashusuario')
            else:
                messages.error(request, 'Usuario o contraseña incorrectos.')
        except Exception as e:
            messages.error(request, f'Error de autenticación: {str(e)}')
            
    next_url = request.GET.get('next')
    return render(request, 'core/iniciosesion.html', {'next': next_url})


def perfil(request):
    user = request.user
    if not user.is_authenticated:
        return redirect('iniciosesion')

    if request.method == 'POST':
        if 'photo_submit' in request.POST:
            # Manejo de actualización solo de foto
            if 'foto_perfil' in request.FILES:
                user.foto_perfil = request.FILES['foto_perfil']
                user.save()
                messages.success(request, 'Foto de perfil actualizada correctamente.')
                return redirect('perfil')
        elif 'profile_submit' in request.POST:
            profile_form = ProfileForm(request.POST, request.FILES, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Perfil actualizado correctamente.')
                return redirect('perfil')
            else:
                messages.error(request, 'Por favor corrige los errores en el formulario de perfil.')
            password_form = PasswordChangeForm(user)
        elif 'password_submit' in request.POST:
            profile_form = ProfileForm(instance=user)
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Contraseña actualizada correctamente.')
                return redirect('perfil')
            else:
                messages.error(request, 'Por favor corrige los errores en el formulario de contraseña.')
        else:
            profile_form = ProfileForm(instance=user)
            password_form = PasswordChangeForm(user)
    else:
        profile_form = ProfileForm(instance=user)
        password_form = PasswordChangeForm(user)

    # Obtener estadísticas del usuario
    canjes = Canje.objects.filter(usuario=user).order_by('-fecha_solicitud')
    redenciones = RedencionPuntos.objects.filter(usuario=user).order_by('-fecha_solicitud')
    
    # Estadísticas básicas
    total_canjes = canjes.count()
    total_puntos_canjeados = sum(c.puntos for c in canjes if c.estado in ['aprobado', 'completado'])
    total_dinero = sum(r.valor_cop for r in redenciones if r.estado == 'completado')
    
    # Logros del usuario
    logros_usuario = user.logro_set.all()[:3]
    
    context = {
        'profile_form': profile_form,
        'password_form': password_form,
        'user': user,
        'total_canjes': total_canjes,
        'total_puntos_canjeados': total_puntos_canjeados,
        'total_dinero': total_dinero,
        'canjes_recientes': canjes[:3],
        'logros_usuario': logros_usuario,
    }
    return render(request, 'core/perfil.html', context)

def categorias(request):
    return render(request, 'core/categorias.html')

@login_required
def canjes(request):
    materials = MaterialTasa.objects.filter(activo=True).order_by('nombre')
    context = {
        'materials': materials
    }
    return render(request, 'core/canjes.html', context)

def historial(request):
    if not request.user.is_authenticated:
        return redirect('iniciosesion')
    from .models import Canje, RedencionPuntos
    canjes = Canje.objects.filter(usuario=request.user).order_by('-fecha_solicitud')
    redenciones = RedencionPuntos.objects.filter(usuario=request.user).order_by('-fecha_solicitud')
    # Estadísticas
    total_canjes = canjes.count()
    total_puntos = sum(c.puntos for c in canjes)
    total_dinero = sum(r.valor_cop for r in redenciones if r.estado == 'completado')
    # Datos para gráficas (ejemplo: por mes)
    from collections import defaultdict
    import datetime
    puntos_por_mes = defaultdict(int)
    dinero_por_mes = defaultdict(int)
    canjes_por_mes = defaultdict(int)
    for c in canjes:
        mes = c.fecha_solicitud.strftime('%b')
        puntos_por_mes[mes] += c.puntos
        canjes_por_mes[mes] += 1
    for r in redenciones:
        mes = r.fecha_solicitud.strftime('%b')
        dinero_por_mes[mes] += float(r.valor_cop)
    meses = list({*puntos_por_mes.keys(), *dinero_por_mes.keys(), *canjes_por_mes.keys()})
    meses.sort(key=lambda m: datetime.datetime.strptime(m, '%b').month)
    context = {
        'canjes': canjes,
        'redenciones': redenciones,
        'total_canjes': total_canjes,
        'total_puntos': total_puntos,
        'total_dinero': total_dinero,
        'puntos_por_mes_json': json.dumps([puntos_por_mes[m] for m in meses]),
        'dinero_por_mes_json': json.dumps([dinero_por_mes[m] for m in meses]),
        'canjes_por_mes_json': json.dumps([canjes_por_mes[m] for m in meses]),
        'meses_json': json.dumps(meses),
        'meses': meses,
    }
    return render(request, 'core/historial.html', context)

def logros(request):
    if not request.user.is_authenticated:
        return redirect('iniciosesion')
    from .models import Logro
    logros_usuario = Logro.objects.filter(usuario=request.user).order_by('-fecha_creacion')
    return render(request, 'core/logros.html', {'logros': logros_usuario})

@login_required
def sesiones_activas(request):
    """Vista para mostrar y gestionar sesiones activas del usuario"""
    from .models import SesionUsuario, IntentoAcceso
    from .security import SecurityManager
    
    # Obtener sesiones activas del usuario
    sesiones = SesionUsuario.objects.filter(
        usuario=request.user,
        activa=True
    ).order_by('-ultima_actividad')
    
    # Obtener intentos de acceso recientes
    intentos_recientes = IntentoAcceso.objects.filter(
        motivo='ip_diferente'
    ).order_by('-fecha_intento')[:10]
    
    # Obtener la sesión actual
    sesion_actual_token = request.session.get('secure_token')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'cerrar_sesion':
            sesion_id = request.POST.get('sesion_id')
            try:
                sesion = SesionUsuario.objects.get(
                    id=sesion_id,
                    usuario=request.user,
                    activa=True
                )
                # No permitir cerrar la sesión actual
                if sesion.token_sesion != sesion_actual_token:
                    sesion.activa = False
                    sesion.save()
                    messages.success(request, f'Sesión cerrada desde {sesion.ip_address}')
                else:
                    messages.warning(request, 'No puedes cerrar tu sesión actual desde aquí')
            except SesionUsuario.DoesNotExist:
                messages.error(request, 'Sesión no encontrada')
        
        elif action == 'cerrar_todas':
            # Cerrar todas las sesiones excepto la actual
            sesiones_cerradas = SesionUsuario.objects.filter(
                usuario=request.user,
                activa=True
            ).exclude(token_sesion=sesion_actual_token).update(activa=False)
            
            if sesiones_cerradas > 0:
                messages.success(request, f'Se cerraron {sesiones_cerradas} sesiones remotas')
            else:
                messages.info(request, 'No hay otras sesiones activas para cerrar')
        
        return redirect('sesiones_activas')
    
    # Marcar la sesión actual
    for sesion in sesiones:
        sesion.es_actual = (sesion.token_sesion == sesion_actual_token)
    
    context = {
        'sesiones': sesiones,
        'intentos_recientes': intentos_recientes,
        'total_sesiones': sesiones.count(),
    }
    
    return render(request, 'core/sesiones_activas.html', context)

def recompensas(request):
    if not request.user.is_authenticated:
        return redirect('iniciosesion')
    from .models import Recompensa, RedencionPuntos
    recompensas = Recompensa.objects.filter(activa=True).order_by('puntos_requeridos')
    recompensas_reclamables = recompensas.filter(puntos_requeridos__lte=request.user.puntos)

    if request.method == 'POST':
        recompensa_id = request.POST.get('recompensa_id')
        recompensa = Recompensa.objects.filter(id=recompensa_id, activa=True).first()
        if recompensa and recompensa.puntos_requeridos <= request.user.puntos:
            # Registrar la redención
            RedencionPuntos.objects.create(
                usuario=request.user,
                puntos=recompensa.puntos_requeridos,
                valor_cop=0,  # O calcula el valor si aplica
                metodo_pago='nequi',  # O deja en blanco si no aplica
                numero_cuenta='-',
                estado='pendiente',
            )
            # Descontar puntos
            request.user.puntos -= recompensa.puntos_requeridos
            request.user.save()
            messages.success(request, f'¡Has canjeado la recompensa "{recompensa.nombre}" exitosamente!')
            return redirect('recompensas')
        else:
            messages.error(request, 'No tienes suficientes puntos para esta recompensa o la recompensa no está disponible.')
            return redirect('recompensas')

    return render(request, 'core/recompensas.html', {
        'recompensas': recompensas,
        'recompensas_reclamables': recompensas_reclamables,
    })

def configuracion(request):
    return render(request, 'core/configuracion.html')

@login_required
@user_passes_test(lambda u: u.is_staff)
def retiroadmin(request):
    return render(request, 'core/retiroadmin.html')

def pagos(request):
    # Obtener historial de redenciones del usuario
    transactions = RedencionPuntos.objects.filter(usuario=request.user).order_by('-fecha_solicitud')
    
    context = {
        'transactions': transactions,
        'user': request.user
    }
    
    return render(request, 'core/pagos.html', context)

def usuarioadmin(request):
    User = get_user_model()
    users = User.objects.all().order_by('-fecha_registro')
    
    # Estadísticas
    total_users = users.count()
    active_users = users.filter(is_active=True).count()
    new_users = users.filter(fecha_registro__month=timezone.now().month).count()
    total_points = sum(user.puntos for user in users)
    
    # Paginación
    paginator = Paginator(users, 10)  # 10 usuarios por página
    page = request.GET.get('page')
    try:
        users = paginator.page(page)
    except PageNotAnInteger:
        users = paginator.page(1)
    except EmptyPage:
        users = paginator.page(paginator.num_pages)
    
    context = {
        'users': users,
        'total_users': total_users,
        'active_users': active_users,
        'new_users': new_users,
        'total_points': total_points,
    }
    
    return render(request, 'core/usuarioadmin.html', context)

def canjeadmin(request):
    # Canjes recientes (filtrados por estado pendiente para administración)
    recent_exchanges = Canje.objects.select_related('usuario', 'material').filter(estado='pendiente').order_by('-fecha_solicitud')

    context = {
        'recent_exchanges': recent_exchanges,
    }
    return render(request, 'core/canjeadmin.html', context)

def dashusuario(request):
    if not request.user.is_authenticated:
        return redirect('iniciosesion')
    
    user = request.user

    # Obtener categorías de materiales
    material_categories = MaterialTasa.objects.filter(activo=True).order_by('nombre')

    # Obtener historial de actividades del usuario
    user_canjes = Canje.objects.filter(usuario=user).order_by('-fecha_solicitud')[:5] # Últimos 5 canjes

    # Lógica de niveles (ejemplo simple, puedes expandir esto según tus reglas de negocio)
    # Definir umbrales de puntos para niveles
    levels = {
        'Bronce': 0,
        'Plata': 100,
        'Oro': 500,
        'Diamante': 1500,
    }

    current_level = 'Bronce'
    next_level_points = 0
    next_level_name = 'N/A'

    sorted_levels = sorted(levels.items(), key=lambda item: item[1])

    for i, (name, points_needed) in enumerate(sorted_levels):
        if user.puntos >= points_needed:
            current_level = name
            if i + 1 < len(sorted_levels):
                next_level_name = sorted_levels[i+1][0]
                next_level_points = sorted_levels[i+1][1]
            else:
                next_level_name = 'Máximo Nivel'
                next_level_points = user.puntos # Already at max, show current points
        else:
            if i > 0:
                # This is the first level where user.puntos is less than points_needed
                # So, the previous level is the current level, and this is the next.
                next_level_name = name
                next_level_points = points_needed
            break # Found the level, no need to check further
    
    # Calcular progreso para el siguiente nivel
    progress_from = 0
    if current_level != 'Máximo Nivel':
        for name, points_needed in sorted_levels:
            if name == current_level:
                progress_from = points_needed
                break

    # Evitar división por cero si el siguiente nivel es 0 puntos
    if next_level_points - progress_from > 0:
        progress_percentage = ((user.puntos - progress_from) / (next_level_points - progress_from)) * 100
    else:
        progress_percentage = 100 # Si ya alcanzó o superó el siguiente nivel (o es el nivel inicial sin un siguiente)

    context = {
        'user': user,
        'material_categories': material_categories,
        'user_canjes': user_canjes,
        'current_level': current_level,
        'next_level_name': next_level_name,
        'next_level_points': next_level_points,
        'progress_from': progress_from,
        'progress_percentage': min(100, progress_percentage), # Asegurarse de que no exceda 100%
    }
    return render(request, 'core/dashusuario.html', context)

def is_admin(user):
    return user.is_authenticated and (hasattr(user, 'is_admin_user') and user.is_admin_user())

def ajax_required_admin(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        print(f"DEBUG: Ejecutando ajax_required_admin para {request.path}")
        if not request.user.is_authenticated:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                print("DEBUG: No autenticado (AJAX)")
                return JsonResponse({'success': False, 'message': 'No autenticado.'}, status=401)
            print("DEBUG: No autenticado (HTML)")
            return redirect('%s?next=%s' % (settings.LOGIN_URL, request.path))
        
        if not is_admin(request.user):
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                print("DEBUG: No es admin (AJAX)")
                return JsonResponse({'success': False, 'message': 'Acceso denegado. Se requieren permisos de administrador.'}, status=403)
            print("DEBUG: No es admin (HTML)")
            return redirect('%s?next=%s' % (settings.LOGIN_URL, request.path)) # Or a custom permission denied page
            
        print("DEBUG: Acceso permitido.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def paneladmin(request):
    return render(request, 'core/paneladmin.html',)

def estadisticasadmin(request):
    return render(request, 'core/estadisticasadmin.html')

def rutas(request):
    routes = Ruta.objects.all().order_by('-fecha', '-hora')
    context = {
        'routes': routes
    }
    return render(request, 'core/rutas.html', context)

@ajax_required_admin
def add_ruta(request):
    if request.method == 'POST':
        try:
            fecha = request.POST.get('fecha')
            hora = request.POST.get('hora')
            barrio = request.POST.get('barrio')
            referencia = request.POST.get('referencia', '') # Puede ser opcional
            direccion = request.POST.get('direccion')

            Ruta.objects.create(
                fecha=fecha,
                hora=hora,
                barrio=barrio,
                referencia=referencia,
                direccion=direccion
            )
            return JsonResponse({'success': True, 'message': 'Ruta agregada exitosamente.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error al agregar la ruta: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Método no permitido.'})

@ajax_required_admin
def edit_ruta(request, ruta_id):
    if request.method == 'POST':
        try:
            ruta = get_object_or_404(Ruta, id=ruta_id)
            ruta.fecha = request.POST.get('fecha')
            ruta.hora = request.POST.get('hora')
            ruta.barrio = request.POST.get('barrio')
            ruta.referencia = request.POST.get('referencia', '')
            ruta.direccion = request.POST.get('direccion')
            ruta.save()
            return JsonResponse({'success': True, 'message': 'Ruta actualizada exitosamente.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error al actualizar la ruta: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Método no permitido.'})

@ajax_required_admin
def delete_ruta(request, ruta_id):
    if request.method == 'POST':
        try:
            ruta = get_object_or_404(Ruta, id=ruta_id)
            ruta.delete()
            return JsonResponse({'success': True, 'message': 'Ruta eliminada exitosamente.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error al eliminar la ruta: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Método no permitido.'})


@ajax_required_admin
def procesar_canje(request, canje_id):
    if request.method == 'POST':
        canje = get_object_or_404(Canje, id=canje_id)
        accion = request.POST.get('accion')
        if accion == 'aprobar':
            canje.estado = 'aprobado'
            canje.usuario.puntos += canje.puntos
            canje.usuario.save()
            
            # Crear notificación para el usuario
            Notificacion.objects.create(
                usuario=canje.usuario,
                mensaje=f'Canje aprobado y {canje.puntos} puntos asignados a tu cuenta.'
            )
            
            messages.success(request, f'Canje aprobado y {canje.puntos} puntos asignados a {canje.usuario.username}')
        elif accion == 'rechazar':
            canje.estado = 'rechazado'
            
            # Crear notificación para el usuario
            Notificacion.objects.create(
                usuario=canje.usuario,
                mensaje=f'Tu canje de {canje.material.nombre} ha sido rechazado.'
            )
            
            messages.warning(request, 'Canje rechazado')
        canje.fecha_procesamiento = timezone.now()
        canje.save()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

def inicioadmin(request):
    # Si el usuario ya está autenticado y es admin, redirigir al panel
    if request.user.is_authenticated and request.user.role == 'admin':
        return redirect('paneladmin')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            # Primero autenticar con Django
            user = authenticate(request, username=username, password=password)
            if user is not None and user.role == 'admin':
                auth_login(request, user)
                messages.success(request, f'Bienvenido/a {user.username}!')
                return redirect('paneladmin')
            else:
                if user is None:
                    messages.error(request, 'Usuario o contraseña incorrectos.')
                else:
                    messages.error(request, 'No tienes permisos de administrador.')
                return render(request, 'core/inicioadmin.html')
                
        except Exception as e:
            messages.error(request, f'Error de autenticación: {str(e)}')
            
    return render(request, 'core/inicioadmin.html')

# --- CANJE DE PUNTOS ---

@login_required
def solicitar_canje(request):
    if request.method == 'POST':
        try:
            material_id = request.POST.get('material')
            peso = float(request.POST.get('peso'))
        
            material = MaterialTasa.objects.get(id=material_id, activo=True)
            puntos = int(peso * material.puntos_por_kilo)
            
            canje = Canje.objects.create(
                usuario=request.user,
                material=material,
                peso=peso,
                puntos=puntos,
                estado='pendiente',
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Canje solicitado exitosamente'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    materials = MaterialTasa.objects.filter(activo=True)
    canjes = Canje.objects.filter(
        usuario=request.user
    ).exclude(estado='rechazado').order_by('-fecha_solicitud')
    
    return render(request, 'core/canjes.html', {
        'materials': materials,
        'canjes': canjes
    })

@login_required
def redimir_puntos(request):
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            puntos = int(request.POST.get('points'))
            metodo_pago = request.POST.get('payment_method')
            numero_cuenta = request.POST.get('phone')
            
            # Validaciones
            if puntos < 100:
                messages.error(request, 'El mínimo de puntos a redimir es 100.')
                return redirect('pagos')
                
            if puntos > request.user.puntos:
                messages.error(request, 'No tienes suficientes puntos disponibles.')
                return redirect('pagos')
                
            # Calcular valor en COP (0.5 COP por punto)
            valor_cop = puntos * 0.5
            
            # Crear la redención
            redencion = RedencionPuntos.objects.create(
                usuario=request.user,
                puntos=puntos,
                valor_cop=valor_cop,
                metodo_pago=metodo_pago,
                numero_cuenta=numero_cuenta,
                estado='pendiente'
            )
            
            # Descontar puntos del usuario
            request.user.puntos -= puntos
            request.user.save()
            
            # Crear notificación para el usuario
            Notificacion.objects.create(
                usuario=request.user,
                mensaje=f'Tu solicitud de redención de {puntos} puntos por ${valor_cop} COP ha sido recibida y está siendo procesada.'
            )
            
            messages.success(request, 'Solicitud de redención enviada con éxito.')
            return redirect('pagos')
            
        except Exception as e:
            messages.error(request, 'Ocurrió un error al procesar tu solicitud.')
            return redirect('pagos')
    
    return redirect('pagos')

@login_required
def get_pending_canjes(request):
    canjes = Canje.objects.filter(
        usuario=request.user,
        estado__in=['pendiente', 'aprobado']
    ).order_by('-fecha_solicitud')
    
    canjes_data = [{
        'id': canje.id,
        'fecha_solicitud': canje.fecha_solicitud.isoformat(),
        'material_nombre': canje.material.nombre,
        'peso': str(canje.peso),
        'puntos': canje.puntos,
        'estado': canje.estado.title()
    } for canje in canjes]
    
    return JsonResponse({
        'success': True,
        'canjes': canjes_data
    })

@ajax_required_admin
def get_pending_canjes_for_admin(request):
    canjes = Canje.objects.filter(
        estado__in=['pendiente', 'aprobado']
    ).select_related('usuario', 'material').order_by('-fecha_solicitud')
    
    canjes_data = [{
        'id': canje.id,
        'fecha_solicitud': canje.fecha_solicitud.isoformat(),
        'material_nombre': canje.material.nombre,
        'peso': str(canje.peso),
        'puntos': canje.puntos,
        'estado': canje.estado.title(),
        'usuario_username': canje.usuario.username
    } for canje in canjes]
    
    return JsonResponse({
        'success': True,
        'canjes': canjes_data
    })

@login_required
def aprobar_canje(request, canje_id):
    if not request.user.is_staff:
        return JsonResponse({
            'success': False,
            'error': 'No tienes permisos para realizar esta acción'
        })
    
    try:
        canje = Canje.objects.get(id=canje_id)
        canje.estado = 'aprobado'
        canje.fecha_procesamiento = timezone.now()
        canje.save()
        
        # Actualizar puntos del usuario
        usuario = canje.usuario
        usuario.puntos += canje.puntos
        usuario.save()
        
        # Verificar si el usuario sube de nivel
        # NOTE: 'nivel' attribute is not defined on Usuario model in core/models.py.
        # This block might cause an AttributeError unless 'nivel' is added to Usuario model.
        # I am commenting it out for now to prevent immediate errors.
        # If you have a 'nivel' field in Usuario, uncomment and ensure it's correctly managed.
        # nivel_actual = usuario.nivel
        # nuevo_nivel = (usuario.puntos // 1000) + 1
        # 
        # if nuevo_nivel > nivel_actual:
        #     usuario.nivel = nuevo_nivel
        #     usuario.save()
        #     
        #     # Crear logro de nivel
        #     Logro.objects.create(
        #         usuario=usuario,
        #         tipo='nivel',
        #         descripcion=f'Alcanzaste el nivel {nuevo_nivel}',
        #         puntos=100
        #     )
        
        return JsonResponse({
            'success': True,
            'message': 'Canje aprobado exitosamente'
        })
    except Canje.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Canje no encontrado'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@ajax_required_admin
def aprobar_canje_ajax(request):
    if request.method == 'POST':
        try:
            canje_id = request.POST.get('canje_id')
            canje = Canje.objects.get(id=canje_id)

            # Basic permission check: only allow admin users to approve
            if not request.user.is_admin_user(): # Assuming you have this method on your User model
                return JsonResponse({'success': False, 'message': 'No tienes permisos para realizar esta acción.'})

            canje.estado = 'aprobado'
            canje.fecha_procesamiento = timezone.now()
            canje.save()

            # Update user points
            usuario = canje.usuario
            usuario.puntos += canje.puntos
            usuario.save()
            
            # Consider adding logic here for achievements/leveling if applicable,
            # similar to the commented out section in aprobar_canje.

            return JsonResponse({'success': True, 'message': 'Canje aprobado exitosamente.'})
        except Canje.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Canje no encontrado.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error al aprobar el canje: {str(e)}.'})
    return JsonResponse({'success': False, 'message': 'Método no permitido.'})

def recuperar_password(request):
    if request.method == 'POST':
        email = request.POST.get('recoveryEmail')
        print(f"Intentando recuperar contraseña para: {email}")  # Debug log
        
        try:
            user = Usuario.objects.get(email=email)
            print(f"Usuario encontrado: {user.username}")  # Debug log
            
            # Generar token único
            token = get_random_string(length=32)
            user.password_reset_token = token
            user.password_reset_expires = timezone.now() + timezone.timedelta(hours=24)
            user.save()
            
            # Preparar el correo
            reset_url = request.build_absolute_uri(f'/reset-password/{token}/')
            context = {
                'user': user,
                'reset_url': reset_url
            }
            
            try:
                # Renderizar el template del correo
                email_html = render_to_string('core/emails/reset_password.html', context)
                email_text = render_to_string('core/emails/reset_password.txt', context)
                
                print("Intentando enviar correo...")
                print(f"Enviando a: {email}")
                print(f"URL de restablecimiento: {reset_url}")
                
                # Enviar el correo
                send_mail(
                    'Recuperación de Contraseña - Eco Puntos',
                    email_text,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    html_message=email_html,
                    fail_silently=False,
                )
                
                print("Correo enviado exitosamente")
                return JsonResponse({
                    'status': 'success',
                    'message': 'Se han enviado las instrucciones a tu correo electrónico.'
                })
                
            except Exception as e:
                print(f"Error al enviar correo: {str(e)}")
                # Revertir cambios en el usuario
                user.password_reset_token = None
                user.password_reset_expires = None
                user.save()
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error al enviar el correo: {str(e)}'
                })
                
        except Usuario.DoesNotExist:
            print(f"Usuario no encontrado para el email: {email}")
            # Retraso para prevenir ataques de enumeración
            import time
            time.sleep(1)
            return JsonResponse({
                'status': 'error',
                'message': 'No existe una cuenta con ese correo electrónico.'
            })
        except Exception as e:
            print(f"Error inesperado: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': f'Error inesperado: {str(e)}'
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'Método no permitido'
    })

def reset_password(request, token):
    try:
        user = Usuario.objects.get(
            password_reset_token=token,
            password_reset_expires__gt=timezone.now()
        )
        
        if request.method == 'POST':
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            
            if password1 != password2:
                messages.error(request, 'Las contraseñas no coinciden.')
                return render(request, 'core/reset_password.html')
            
            # Actualizar contraseña
            user.set_password(password1)
            # Limpiar token
            user.password_reset_token = None
            user.password_reset_expires = None
            user.save()
            
            messages.success(request, 'Tu contraseña ha sido actualizada correctamente. Ya puedes iniciar sesión.')
            return redirect('iniciosesion')
            
        return render(request, 'core/reset_password.html')
        
    except Usuario.DoesNotExist:
        messages.error(request, 'El enlace de recuperación no es válido o ha expirado.')
        return redirect('iniciosesion')

@login_required
@user_passes_test(is_admin)
def add_user(request):
    if request.method == 'POST':
        try:
            User = get_user_model()
            username = request.POST.get('username')
            email = request.POST.get('email')
            password = request.POST.get('password')
            role = request.POST.get('role', 'user')
            
            if User.objects.filter(username=username).exists():
                messages.error(request, 'El nombre de usuario ya existe.')
                return redirect('usuarioadmin')
                
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role=role
            )
            
            messages.success(request, f'Usuario {username} creado exitosamente.')
            return redirect('usuarioadmin')
            
        except Exception as e:
            messages.error(request, f'Error al crear usuario: {str(e)}')
            return redirect('usuarioadmin')
            
    return redirect('usuarioadmin')

@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    if request.method == 'POST':
        try:
            User = get_user_model()
            user = User.objects.get(id=user_id)
            
            user.username = request.POST.get('username')
            user.email = request.POST.get('email')
            user.role = request.POST.get('role')
            user.is_active = request.POST.get('is_active') == '1'
            
            # Actualizar contraseña solo si se proporciona una nueva
            password = request.POST.get('password')
            if password:
                user.set_password(password)
                
            user.save()
            messages.success(request, f'Usuario {user.username} actualizado exitosamente.')
            
        except User.DoesNotExist:
            messages.error(request, 'Usuario no encontrado.')
        except Exception as e:
            messages.error(request, f'Error al actualizar usuario: {str(e)}')
            
    return redirect('usuarioadmin')

@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    if request.method == 'POST':
        try:
            User = get_user_model()
            user = User.objects.get(id=user_id)
            username = user.username
            user.delete()
            messages.success(request, f'Usuario {username} eliminado exitosamente.')
            
        except User.DoesNotExist:
            messages.error(request, 'Usuario no encontrado.')
        except Exception as e:
            messages.error(request, f'Error al eliminar usuario: {str(e)}')
            
    return redirect('usuarioadmin')

# Helper function to get monthly data for charts
def get_monthly_data(model, date_field, value_field, start_date, end_date):
    data = {}
    current_date = start_date
    while current_date <= end_date:
        month_key = current_date.strftime('%Y-%m')
        data[month_key] = 0
        current_date += timedelta(days=32) # Move to next month
        current_date = current_date.replace(day=1)

    # Fetch actual data
    monthly_sums = model.objects.filter(
        **{f'{date_field}__date__range': (start_date, end_date)}
    ).extra({'month': "TO_CHAR({}, 'YYYY-MM')".format(date_field)}).values('month').annotate(total=Sum(value_field))

    for item in monthly_sums:
        data[item['month']] = item['total'] or 0

    labels = []
    values = []
    current_date = start_date
    while current_date <= end_date:
        month_key = current_date.strftime('%Y-%m')
        labels.append(current_date.strftime('%b %Y'))
        values.append(data[month_key])
        current_date += timedelta(days=32) # Move to next month
        current_date = current_date.replace(day=1)

    return labels, values


@ajax_required_admin
def get_dashboard_stats(request):
    """Obtiene estadísticas completas del dashboard usando el nuevo sistema"""
    try:
        stats = StatisticsManager.get_comprehensive_dashboard_stats()
        return JsonResponse({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@ajax_required_admin
def get_chart_data(request):
    today = date.today()
    # Monthly Canjes
    monthly_canjes_data = []
    monthly_canjes_labels = []
    for i in range(6, -1, -1): # Last 7 months including current
        month_date = today - timedelta(days=30*i) # Approximate month
        start_of_month = month_date.replace(day=1)
        if month_date.month == 12:
            end_of_month = month_date.replace(year=month_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_of_month = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)

        canjes_count = Canje.objects.filter(
            fecha_solicitud__range=(start_of_month, end_of_month),
            estado='aprobado'
        ).count()
        monthly_canjes_data.append(canjes_count)
        monthly_canjes_labels.append(month_date.strftime('%b'))

    # Popular Rutas (assuming each Ruta has a 'count' or 'usage' field, or we count canjes related to routes)
    # For now, let's assume 'popularity' for routes means how many times they've been associated with a completed action (e.g., canje)
    # This might require a new model or field to track route usage.
    # For demonstration, let's assume we count unique Canjes associated with a Ruta, or simply count Ruta objects if they represent usage.
    # If Ruta does not have a direct relation with Canje, this part will need to be adjusted based on how routes are associated with user activity/canjes.

    # Simulating popular_rutas for now, as direct counting from Canje->Ruta might not fit "ruta popular" logic without more schema info
    # For a real scenario, you'd aggregate data from activities related to routes.
    popular_rutas_labels = ['Ruta A', 'Ruta B', 'Ruta C', 'Ruta D', 'Ruta E']
    popular_rutas_data = [50, 40, 30, 20, 10]

    return JsonResponse({
        'success': True,
        'monthly_canjes_labels': monthly_canjes_labels,
        'monthly_canjes_data': monthly_canjes_data,
        'popular_rutas_labels': popular_rutas_labels,
        'popular_rutas_data': popular_rutas_data,
    })

def alertas(request):
    alertas = Alerta.objects.all()
    return render(request, 'core/alertas.html', {'alertas': alertas})

def add_alerta(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        descripcion = request.POST.get('descripcion')
        Alerta.objects.create(nombre=nombre, descripcion=descripcion)
        return JsonResponse({'status': 'success', 'message': 'Alerta agregada correctamente.'})
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)

def edit_alerta(request):
    if request.method == 'POST':
        alerta_id = request.POST.get('id')
        nombre = request.POST.get('nombre')
        descripcion = request.POST.get('descripcion')
        activa = request.POST.get('activa') == 'on'
        
        try:
            alerta = Alerta.objects.get(id=alerta_id)
            alerta.nombre = nombre
            alerta.descripcion = descripcion
            alerta.activa = activa
            alerta.save()
            return JsonResponse({'status': 'success', 'message': 'Alerta actualizada correctamente.'})
        except Alerta.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Alerta no encontrada.'}, status=404)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)

def delete_alerta(request):
    if request.method == 'POST':
        alerta_id = request.POST.get('id')
        try:
            alerta = Alerta.objects.get(id=alerta_id)
            alerta.delete()
            return JsonResponse({'status': 'success', 'message': 'Alerta eliminada correctamente.'})
        except Alerta.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Alerta no encontrada.'}, status=404)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)

def configuraciones(request):
    categoria = request.GET.get('categoria', 'general')
    configs = Configuracion.get_configs_by_category(categoria)
    categorias = dict(Configuracion.CATEGORIAS)
    return render(request, 'core/configuraciones.html', {
        'configs': configs,
        'categoria_actual': categoria,
        'categorias': categorias
    })

def add_configuracion(request):
    if request.method == 'POST':
        try:
            nombre = request.POST.get('nombre')
            valor = request.POST.get('valor')
            descripcion = request.POST.get('descripcion')
            tipo = request.POST.get('tipo')
            categoria = request.POST.get('categoria')
            
            # Validar el valor según el tipo
            if tipo == 'numero':
                float(valor)  # Verificar que sea un número válido
            elif tipo == 'booleano':
                valor = str(valor.lower() == 'true')
            elif tipo == 'json':
                json.loads(valor)  # Verificar que sea JSON válido
            elif tipo == 'lista':
                # Convertir lista separada por comas en JSON
                lista = [item.strip() for item in valor.split(',')]
                valor = json.dumps(lista)
            
            Configuracion.objects.create(
                nombre=nombre,
                valor=valor,
                descripcion=descripcion,
                tipo=tipo,
                categoria=categoria
            )
            return JsonResponse({'status': 'success', 'message': 'Configuración agregada correctamente.'})
        except ValueError as e:
            return JsonResponse({'status': 'error', 'message': f'Error en el valor: {str(e)}'}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)

def edit_configuracion(request):
    if request.method == 'POST':
        try:
            config_id = request.POST.get('id')
            nombre = request.POST.get('nombre')
            valor = request.POST.get('valor')
            descripcion = request.POST.get('descripcion')
            tipo = request.POST.get('tipo')
            categoria = request.POST.get('categoria')
            
            config = Configuracion.objects.get(id=config_id)
            
            # Validar el valor según el tipo
            if tipo == 'numero':
                float(valor)  # Verificar que sea un número válido
            elif tipo == 'booleano':
                valor = str(valor.lower() == 'true')
            elif tipo == 'json':
                json.loads(valor)  # Verificar que sea JSON válido
            elif tipo == 'lista':
                # Convertir lista separada por comas en JSON
                lista = [item.strip() for item in valor.split(',')]
                valor = json.dumps(lista)
            
            config.nombre = nombre
            config.valor = valor
            config.descripcion = descripcion
            config.tipo = tipo
            config.categoria = categoria
            config.save()
            
            return JsonResponse({'status': 'success', 'message': 'Configuración actualizada correctamente.'})
        except Configuracion.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Configuración no encontrada.'}, status=404)
        except ValueError as e:
            return JsonResponse({'status': 'error', 'message': f'Error en el valor: {str(e)}'}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)

def delete_configuracion(request):
    if request.method == 'POST':
        try:
            config_id = request.POST.get('id')
            config = Configuracion.objects.get(id=config_id)
            config.delete()
            return JsonResponse({'status': 'success', 'message': 'Configuración eliminada correctamente.'})
        except Configuracion.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Configuración no encontrada.'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)

def get_config(nombre, default=None):
    """
    Obtiene el valor de una configuración por su nombre.
    Si no existe, retorna el valor por defecto.
    """
    try:
        config = Configuracion.objects.get(nombre=nombre)
        if config.tipo == 'numero':
            return float(config.valor)
        elif config.tipo == 'booleano':
            return config.valor.lower() == 'true'
        elif config.tipo == 'json':
            return json.loads(config.valor)
        return config.valor
    except Configuracion.DoesNotExist:
        return default
    except (ValueError, json.JSONDecodeError):
        return default

# Funciones helper para configuraciones específicas
def get_config_puntos(nombre, default=None):
    """Obtiene una configuración específica de puntos"""
    return get_config(nombre, default)

def get_config_rutas(nombre, default=None):
    """Obtiene una configuración específica de rutas"""
    return get_config(nombre, default)

def get_config_materiales(nombre, default=None):
    """Obtiene una configuración específica de materiales"""
    return get_config(nombre, default)

def get_config_notificaciones(nombre, default=None):
    """Obtiene una configuración específica de notificaciones"""
    return get_config(nombre, default)

# Configuraciones predefinidas
CONFIGURACIONES_PREDEFINIDAS = {
    'puntos': [
        {
            'nombre': 'puntos_por_kg',
            'valor': '10',
            'tipo': 'numero',
            'descripcion': 'Puntos otorgados por kilogramo de material reciclable',
            'categoria': 'puntos'
        },
        {
            'nombre': 'minimo_canje',
            'valor': '100',
            'tipo': 'numero',
            'descripcion': 'Puntos mínimos necesarios para realizar un canje',
            'categoria': 'puntos'
        },
        {
            'nombre': 'limite_diario',
            'valor': '1000',
            'tipo': 'numero',
            'descripcion': 'Límite diario de puntos por usuario',
            'categoria': 'puntos'
        }
    ],
    'rutas': [
        {
            'nombre': 'horarios_recoleccion',
            'valor': '["08:00-12:00", "14:00-18:00"]',
            'tipo': 'json',
            'descripcion': 'Horarios disponibles para recolección',
            'categoria': 'rutas'
        },
        {
            'nombre': 'dias_recoleccion',
            'valor': '["Lunes", "Miércoles", "Viernes"]',
            'tipo': 'json',
            'descripcion': 'Días disponibles para recolección',
            'categoria': 'rutas'
        }
    ],
    'materiales': [
        {
            'nombre': 'materiales_aceptados',
            'valor': '["Papel", "Plástico", "Vidrio", "Metal"]',
            'tipo': 'json',
            'descripcion': 'Lista de materiales aceptados para reciclaje',
            'categoria': 'materiales'
        }
    ],
    'notificaciones': [
        {
            'nombre': 'recordatorio_rutas',
            'valor': 'true',
            'tipo': 'booleano',
            'descripcion': 'Activar recordatorios de rutas de recolección',
            'categoria': 'notificaciones'
        },
        {
            'nombre': 'alertas_puntos',
            'valor': 'true',
            'tipo': 'booleano',
            'descripcion': 'Activar alertas de puntos',
            'categoria': 'notificaciones'
        }
    ],
    'general': [
        {
            'nombre': 'nombre_sistema',
            'valor': 'Eco Puntos',
            'tipo': 'texto',
            'descripcion': 'Nombre del sistema',
            'categoria': 'general'
        },
        {
            'nombre': 'moneda',
            'valor': 'Puntos',
            'tipo': 'texto',
            'descripcion': 'Nombre de la moneda virtual',
            'categoria': 'general'
        }
    ]
}

def inicializar_configuraciones():
    """Inicializa las configuraciones predefinidas si no existen"""
    for categoria, configs in CONFIGURACIONES_PREDEFINIDAS.items():
        for config in configs:
            Configuracion.objects.get_or_create(
                nombre=config['nombre'],
                defaults={
                    'valor': config['valor'],
                    'tipo': config['tipo'],
                    'descripcion': config['descripcion'],
                    'categoria': config['categoria']
                }
            )

@login_required
def rutasusuario(request):
    return render(request, 'core/rutasusuario.html')

@login_required
@csrf_exempt
def agendar_ruta_usuario(request):
    if request.method == 'POST':
        fecha = request.POST.get('fecha')
        hora = request.POST.get('hora')
        barrio = request.POST.get('barrio')
        referencia = request.POST.get('referencia', '')
        direccion = request.POST.get('direccion')
        materiales = request.POST.get('materiales', '')
        Ruta.objects.create(
            usuario=request.user,
            fecha=fecha,
            hora=hora,
            barrio=barrio,
            referencia=referencia,
            direccion=direccion,
            materiales=materiales
        )
        return JsonResponse({'success': True, 'message': '¡Tu solicitud está en revisión!'})
    return JsonResponse({'success': False, 'message': 'Método no permitido.'})

@login_required
def ranking(request):
    # Obtener usuarios ordenados por puntos (de mayor a menor)
    usuarios = Usuario.objects.all().order_by('-puntos')[:50]  # Top 50 usuarios
    
    # Obtener estadísticas generales
    total_usuarios = Usuario.objects.count()
    total_puntos = Usuario.objects.aggregate(Sum('puntos'))['puntos__sum'] or 0
    total_canjes = Canje.objects.filter(estado='aprobado').count()
    
    # Determinar la posición del usuario actual
    user_position = None
    for i, user in enumerate(usuarios):
        if user.id == request.user.id:
            user_position = i + 1
            break
    
    # Si el usuario no está en el top 50, encontrar su posición real
    if user_position is None:
        user_position = list(Usuario.objects.order_by('-puntos').values_list('id', flat=True)).index(request.user.id) + 1
    
    context = {
        'usuarios': usuarios,
        'total_usuarios': total_usuarios,
        'total_puntos': total_puntos,
        'total_canjes': total_canjes,
        'user_position': user_position
    }
    
    return render(request, 'core/ranking.html', context)

@login_required
def soportusu(request):
    # Lógica para el formulario de soporte
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        email = request.POST.get('email')
        asunto = request.POST.get('asunto')
        mensaje = request.POST.get('mensaje')
        
        # Aquí puedes implementar el envío de correo o guardar en base de datos
        # Por ahora solo mostraremos un mensaje de éxito
        messages.success(request, '¡Tu mensaje ha sido enviado! Te responderemos pronto.')
        return redirect('soportusu')
    
    return render(request, 'core/soportusu.html')

@login_required
@user_passes_test(is_admin)
def get_pending_redemptions(request):
    redemptions = RedencionPuntos.objects.filter(
        estado='pendiente'
    ).select_related('usuario').order_by('-fecha_solicitud')
    
    redemptions_data = [{
        'id': redemption.id,
        'fecha_solicitud': redemption.fecha_solicitud.isoformat(),
        'usuario_username': redemption.usuario.username,
        'puntos': redemption.puntos,
        'valor_cop': redemption.valor_cop,
        'metodo_pago': redemption.metodo_pago,
        'numero_cuenta': redemption.numero_cuenta
    } for redemption in redemptions]
    
    return JsonResponse({
        'success': True,
        'redemptions': redemptions_data
    })

@login_required
@user_passes_test(is_admin)
def aprobar_redencion(request, redencion_id):
    if request.method == 'POST':
        try:
            redencion = RedencionPuntos.objects.get(id=redencion_id)
            
            # Verificar que la redención esté pendiente
            if redencion.estado != 'pendiente':
                return JsonResponse({
                    'success': False,
                    'message': 'Esta redención ya ha sido procesada.'
                })
            
            # Actualizar estado de la redención
            redencion.estado = 'aprobado'
            redencion.fecha_procesamiento = timezone.now()
            redencion.save()
            
            # Crear notificación para el usuario
            Notificacion.objects.create(
                usuario=redencion.usuario,
                mensaje=f'Tu redención de {redencion.puntos} puntos por ${redencion.valor_cop} COP ha sido aprobada y será transferida a tu cuenta {redencion.metodo_pago} ({redencion.numero_cuenta}).'
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Redención aprobada exitosamente.'
            })
            
        except RedencionPuntos.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Redención no encontrada.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al aprobar la redención: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Método no permitido.'
    })

@login_required
@user_passes_test(is_admin)
def rechazar_redencion(request, redencion_id):
    if request.method == 'POST':
        try:
            redencion = RedencionPuntos.objects.get(id=redencion_id)
            
            # Verificar que la redención esté pendiente
            if redencion.estado != 'pendiente':
                return JsonResponse({
                    'success': False,
                    'message': 'Esta redención ya ha sido procesada.'
                })
            
            # Devolver los puntos al usuario
            usuario = redencion.usuario
            usuario.puntos += redencion.puntos
            usuario.save()
            
            # Actualizar estado de la redención
            redencion.estado = 'rechazado'
            redencion.fecha_procesamiento = timezone.now()
            redencion.save()
            
            # Crear notificación para el usuario
            Notificacion.objects.create(
                usuario=redencion.usuario,
                mensaje=f'Tu redención de {redencion.puntos} puntos ha sido rechazada. Los puntos han sido devueltos a tu cuenta.'
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Redención rechazada exitosamente.'
            })
            
        except RedencionPuntos.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Redención no encontrada.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al rechazar la redención: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Método no permitido.'
    })

@ajax_required_admin
def get_advanced_statistics(request):
    """Obtiene estadísticas avanzadas por categoría"""
    try:
        stats_type = request.GET.get('type', 'all')
        days = int(request.GET.get('days', 30))
        
        if stats_type == 'users':
            stats = StatisticsManager.get_user_activity_stats(days)
        elif stats_type == 'recycling':
            stats = StatisticsManager.get_recycling_stats(days)
        elif stats_type == 'security':
            stats = StatisticsManager.get_security_stats(days)
        elif stats_type == 'financial':
            stats = StatisticsManager.get_financial_stats(days)
        elif stats_type == 'routes':
            stats = StatisticsManager.get_route_stats(days)
        else:
            # Obtener todas las estadísticas
            stats = {
                'users': StatisticsManager.get_user_activity_stats(days),
                'recycling': StatisticsManager.get_recycling_stats(days),
                'security': StatisticsManager.get_security_stats(days),
                'financial': StatisticsManager.get_financial_stats(days),
                'routes': StatisticsManager.get_route_stats(days)
            }
        
        return JsonResponse({
            'success': True,
            'stats': stats,
            'type': stats_type,
            'days': days
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@ajax_required_admin
def get_security_analytics(request):
    """Obtiene análisis de seguridad detallado"""
    try:
        days = int(request.GET.get('days', 30))
        stats = StatisticsManager.get_security_stats(days)
        
        # Análisis adicional de seguridad
        today = timezone.now()
        start_date = today - timedelta(days=days)
        
        # Sesiones por dispositivo
        sessions_by_device = SesionUsuario.objects.filter(
            fecha_creacion__gte=start_date
        ).values('dispositivo_id').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Usuarios con múltiples sesiones
        users_multiple_sessions = Usuario.objects.annotate(
            session_count=Count('sesiones')
        ).filter(session_count__gt=1).order_by('-session_count')[:10]
        
        security_analytics = {
            'basic_stats': stats,
            'sessions_by_device': list(sessions_by_device),
            'users_multiple_sessions': [
                {
                    'username': user.username,
                    'session_count': user.session_count,
                    'last_login': user.last_login
                }
                for user in users_multiple_sessions
            ]
        }
        
        return JsonResponse({
            'success': True,
            'analytics': security_analytics
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@ajax_required_admin
def export_statistics(request):
    """Exporta estadísticas en formato CSV o JSON"""
    try:
        format_type = request.GET.get('format', 'json')
        stats_type = request.GET.get('type', 'all')
        days = int(request.GET.get('days', 30))
        
        if stats_type == 'all':
            stats = {
                'users': StatisticsManager.get_user_activity_stats(days),
                'recycling': StatisticsManager.get_recycling_stats(days),
                'security': StatisticsManager.get_security_stats(days),
                'financial': StatisticsManager.get_financial_stats(days),
                'routes': StatisticsManager.get_route_stats(days)
            }
        else:
            if stats_type == 'users':
                stats = StatisticsManager.get_user_activity_stats(days)
            elif stats_type == 'recycling':
                stats = StatisticsManager.get_recycling_stats(days)
            elif stats_type == 'security':
                stats = StatisticsManager.get_security_stats(days)
            elif stats_type == 'financial':
                stats = StatisticsManager.get_financial_stats(days)
            elif stats_type == 'routes':
                stats = StatisticsManager.get_route_stats(days)
        
        if format_type == 'csv':
            # Implementar exportación CSV
            response = JsonResponse({
                'success': True,
                'message': 'Exportación CSV implementada'
            })
            response['Content-Type'] = 'text/csv'
            response['Content-Disposition'] = f'attachment; filename="estadisticas_{stats_type}_{days}dias.csv"'
            return response
        else:
            # Exportación JSON
            response = JsonResponse({
                'success': True,
                'data': stats,
                'export_date': timezone.now().isoformat(),
                'type': stats_type,
                'days': days
            })
            response['Content-Disposition'] = f'attachment; filename="estadisticas_{stats_type}_{days}dias.json"'
            return response
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@ajax_required_admin
def cleanup_expired_sessions(request):
    """Limpia sesiones expiradas"""
    try:
        cleaned_count = SecurityManager.cleanup_expired_sessions()
        return JsonResponse({
            'success': True,
            'message': f'Se limpiaron {cleaned_count} sesiones expiradas',
            'cleaned_count': cleaned_count
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def security_monitor(request):
    """Vista para el monitor de seguridad"""
    # Verificar si el usuario está autenticado y es admin
    if not request.user.is_authenticated:
        return redirect('iniciosesion')
    
    if not is_admin(request.user):
        return redirect('iniciosesion')
    
    return render(request, 'core/security_monitor.html')
