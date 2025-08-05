from django.shortcuts import redirect
from django.contrib.auth import logout
from django.urls import reverse
from .security import SecurityManager
import time
from django.http import JsonResponse

class SecurityMiddleware:
    """Middleware para validar sesiones seguras"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # URLs que no requieren validación de sesión
        exempt_urls = [
            '/',
            '/iniciosesion/',
            '/registrate/',
            '/recuperar-password/',
            '/reset-password/',
            '/admin/',
            '/static/',
            '/media/',
        ]
        
        # Verificar si la URL actual está exenta
        path = request.path_info.lstrip('/')
        is_exempt = any(request.path.startswith(url) for url in exempt_urls)
        
        # Solo validar si el usuario está autenticado y la URL no está exenta
        if request.user.is_authenticated and not is_exempt:
            is_valid, message = SecurityManager.validate_session(request)
            if not is_valid:
                # Invalidar sesión y redirigir al login
                SecurityManager.invalidate_session(request)
                logout(request)
                return redirect('iniciosesion')
        
        response = self.get_response(request)
        return response

class RateLimitMiddleware:
    """Middleware para limitar el número de intentos de acceso"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.attempts = {}  # En producción, usar Redis o similar
    
    def __call__(self, request):
        ip = SecurityManager.get_client_ip(request)
        
        # Limpiar intentos antiguos (más de 1 hora)
        current_time = time.time()
        if ip in self.attempts:
            self.attempts[ip] = [t for t in self.attempts[ip] if current_time - t < 3600]
        
        # Verificar si hay demasiados intentos
        if ip in self.attempts and len(self.attempts[ip]) > 10:
            return JsonResponse({
                'error': 'Demasiados intentos de acceso. Intente más tarde.'
            }, status=429)
        
        response = self.get_response(request)
        
        # Si es un intento de login fallido, registrar
        if request.path == '/iniciosesion/' and request.method == 'POST':
            if not request.user.is_authenticated:
                if ip not in self.attempts:
                    self.attempts[ip] = []
                self.attempts[ip].append(current_time)
        
        return response 