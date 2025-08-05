import hashlib
import json
import time
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib.auth import logout
from django.utils.crypto import get_random_string
from .models import SesionUsuario, IntentoAcceso
from datetime import timedelta
import ipaddress

class SecurityManager:
    """Clase para manejar la seguridad de sesiones y validación de dispositivos"""
    
    @staticmethod
    def generate_device_id(request):
        """Genera un ID único para el dispositivo basado en User-Agent y otros factores"""
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
        
        # Crear un fingerprint del dispositivo
        device_string = f"{user_agent}|{accept_language}|{accept_encoding}"
        return hashlib.sha256(device_string.encode()).hexdigest()
    
    @staticmethod
    def generate_session_token():
        """Genera un token único para la sesión"""
        return get_random_string(64)
    
    @staticmethod
    def get_client_ip(request):
        """Obtiene la IP real del cliente"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def create_secure_session(request, user):
        """Crea una sesión segura para el usuario"""
        device_id = SecurityManager.generate_device_id(request)
        token = SecurityManager.generate_session_token()
        ip_address = SecurityManager.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Expiración de sesión (24 horas)
        expiration = timezone.now() + timedelta(hours=24)
        
        # Crear la sesión
        session = SesionUsuario.objects.create(
            usuario=user,
            token_sesion=token,
            dispositivo_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            fecha_expiracion=expiration
        )
        
        # Guardar el token en la sesión de Django
        request.session['secure_token'] = token
        request.session['device_id'] = device_id
        
        return session
    
    @staticmethod
    def validate_session(request):
        """Valida la sesión actual del usuario"""
        if not request.user.is_authenticated:
            return False, "Usuario no autenticado"
        
        secure_token = request.session.get('secure_token')
        device_id = request.session.get('device_id')
        
        if not secure_token or not device_id:
            return False, "Token de sesión no encontrado"
        
        try:
            session = SesionUsuario.objects.get(
                token_sesion=secure_token,
                usuario=request.user,
                activa=True
            )
        except SesionUsuario.DoesNotExist:
            SecurityManager.log_access_attempt(request, 'token_invalido')
            return False, "Sesión no válida"
        
        # Verificar expiración
        if session.is_expired():
            session.activa = False
            session.save()
            SecurityManager.log_access_attempt(request, 'sesion_expirada')
            return False, "Sesión expirada"
        
        # Verificar dispositivo
        current_device_id = SecurityManager.generate_device_id(request)
        if session.dispositivo_id != current_device_id:
            SecurityManager.log_access_attempt(request, 'dispositivo_no_autorizado')
            return False, "Dispositivo no autorizado"
        
        # Verificar IP - BLOQUEAR acceso desde IP diferente
        current_ip = SecurityManager.get_client_ip(request)
        if session.ip_address != current_ip:
            SecurityManager.log_access_attempt(request, 'ip_diferente')
            # Crear notificación de seguridad
            SecurityManager.create_security_notification(
                session.usuario, 
                f"Intento de acceso detectado desde IP {current_ip}. Tu sesión fue iniciada desde {session.ip_address}. Si no fuiste tú, cambia tu contraseña inmediatamente."
            )
            # Invalidar la sesión por seguridad
            session.activa = False
            session.save()
            return False, f"Acceso denegado: IP no autorizada. Sesión iniciada desde {session.ip_address}, intento desde {current_ip}"
        
        # Actualizar última actividad
        session.ultima_actividad = timezone.now()
        session.save()
        
        return True, "Sesión válida"
    
    @staticmethod
    def log_access_attempt(request, motivo):
        """Registra un intento de acceso no autorizado"""
        ip_address = SecurityManager.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        url_intento = request.build_absolute_uri()
        
        IntentoAcceso.objects.create(
            ip_address=ip_address,
            user_agent=user_agent,
            url_intento=url_intento,
            motivo=motivo
        )
    
    @staticmethod
    def invalidate_session(request):
        """Invalida la sesión actual del usuario"""
        secure_token = request.session.get('secure_token')
        if secure_token:
            try:
                session = SesionUsuario.objects.get(token_sesion=secure_token)
                session.activa = False
                session.save()
            except SesionUsuario.DoesNotExist:
                pass
        
        # Limpiar sesión de Django
        request.session.flush()
    
    @staticmethod
    def get_active_sessions_count(user):
        """Obtiene el número de sesiones activas de un usuario"""
        return SesionUsuario.objects.filter(
            usuario=user,
            activa=True
        ).count()
    
    @staticmethod
    def cleanup_expired_sessions():
        """Limpia todas las sesiones expiradas"""
        expired_sessions = SesionUsuario.objects.filter(
            fecha_expiracion__lt=timezone.now(),
            activa=True
        )
        expired_sessions.update(activa=False)
        return expired_sessions.count()
    
    @staticmethod
    def create_security_notification(user, message):
        """Crea una notificación de seguridad para el usuario"""
        from .models import Notificacion
        Notificacion.objects.create(
            usuario=user,
            mensaje=message
        )

def require_secure_session(view_func):
    """Decorador para requerir sesión segura"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('iniciosesion')
        
        is_valid, message = SecurityManager.validate_session(request)
        if not is_valid:
            SecurityManager.invalidate_session(request)
            logout(request)
            return redirect('iniciosesion')
        
        return view_func(request, *args, **kwargs)
    return wrapper