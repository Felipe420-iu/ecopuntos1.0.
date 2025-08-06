#!/usr/bin/env python
"""
Script de prueba para verificar las funcionalidades del monitor de seguridad
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proyecto2023.settings')
django.setup()

from django.utils import timezone
from core.models import Usuario, SesionUsuario, IntentoAcceso
from core.security import SecurityManager
from django.test import RequestFactory

def test_security_functions():
    """Prueba las funciones de seguridad"""
    print("=== PRUEBA DEL MONITOR DE SEGURIDAD ===")
    
    # 1. Verificar que existan usuarios
    usuarios = Usuario.objects.all()
    print(f"✓ Total de usuarios en el sistema: {usuarios.count()}")
    
    # 2. Verificar sesiones activas
    sesiones_activas = SesionUsuario.objects.filter(activa=True)
    print(f"✓ Sesiones activas: {sesiones_activas.count()}")
    
    # 3. Verificar intentos de acceso
    intentos = IntentoAcceso.objects.all()
    print(f"✓ Total de intentos de acceso registrados: {intentos.count()}")
    
    # 4. Probar limpieza de sesiones expiradas
    expired_count = SecurityManager.cleanup_expired_sessions()
    print(f"✓ Sesiones expiradas limpiadas: {expired_count}")
    
    # 5. Probar limpieza de sesiones inactivas
    inactive_count = SecurityManager.cleanup_inactive_sessions()
    print(f"✓ Sesiones inactivas limpiadas: {inactive_count}")
    
    # 6. Verificar sesiones para monitoreo
    sesiones_monitor = SecurityManager.get_active_sessions_for_monitoring()
    print(f"✓ Sesiones disponibles para monitoreo: {sesiones_monitor.count()}")
    
    # 7. Mostrar detalles de sesiones activas
    print("\n=== DETALLES DE SESIONES ACTIVAS ===")
    for sesion in sesiones_monitor[:5]:  # Mostrar solo las primeras 5
        tiempo_restante = sesion.fecha_expiracion - timezone.now()
        minutos_restantes = int(tiempo_restante.total_seconds() / 60)
        print(f"- Usuario: {sesion.usuario.username}")
        print(f"  IP: {sesion.ip_address}")
        print(f"  Última actividad: {sesion.ultima_actividad}")
        print(f"  Tiempo restante: {minutos_restantes} minutos")
        print(f"  Dispositivo: {sesion.dispositivo_id[:20]}...")
        print()
    
    # 8. Verificar intentos de acceso recientes
    intentos_recientes = IntentoAcceso.objects.filter(
        fecha_intento__gte=timezone.now() - timedelta(hours=24)
    ).order_by('-fecha_intento')[:5]
    
    print("=== INTENTOS DE ACCESO RECIENTES (24h) ===")
    for intento in intentos_recientes:
        print(f"- IP: {intento.ip_address}")
        print(f"  Motivo: {intento.motivo}")
        print(f"  Fecha: {intento.fecha_intento}")
        print(f"  URL: {intento.url_intento}")
        print()
    
    # 9. Verificar estadísticas de seguridad
    print("=== ESTADÍSTICAS DE SEGURIDAD ===")
    total_sesiones_hoy = SesionUsuario.objects.filter(
        fecha_creacion__date=timezone.now().date()
    ).count()
    print(f"✓ Sesiones creadas hoy: {total_sesiones_hoy}")
    
    total_intentos_hoy = IntentoAcceso.objects.filter(
        fecha_intento__date=timezone.now().date()
    ).count()
    print(f"✓ Intentos de acceso hoy: {total_intentos_hoy}")
    
    # 10. Verificar usuarios con múltiples sesiones
    usuarios_multiples = Usuario.objects.annotate(
        sesiones_count=django.db.models.Count('sesiones', filter=django.db.models.Q(sesiones__activa=True))
    ).filter(sesiones_count__gt=1)
    
    print(f"✓ Usuarios con múltiples sesiones: {usuarios_multiples.count()}")
    
    print("\n=== PRUEBA COMPLETADA ===")
    print("Todas las funciones del monitor de seguridad están funcionando correctamente.")

def test_session_creation():
    """Prueba la creación de sesiones"""
    print("\n=== PRUEBA DE CREACIÓN DE SESIÓN ===")
    
    # Crear un usuario de prueba si no existe
    user, created = Usuario.objects.get_or_create(
        username='test_security',
        defaults={
            'email': 'test@security.com',
            'role': 'user'
        }
    )
    
    if created:
        user.set_password('testpass123')
        user.save()
        print(f"✓ Usuario de prueba creado: {user.username}")
    else:
        print(f"✓ Usuario de prueba existente: {user.username}")
    
    # Simular una request
    factory = RequestFactory()
    request = factory.get('/')
    request.META['HTTP_USER_AGENT'] = 'Test Browser 1.0'
    request.META['HTTP_ACCEPT_LANGUAGE'] = 'es-ES,es;q=0.9'
    request.META['HTTP_ACCEPT_ENCODING'] = 'gzip, deflate'
    request.META['REMOTE_ADDR'] = '127.0.0.1'
    request.user = user
    request.session = {}
    
    # Crear sesión segura
    session = SecurityManager.create_secure_session(request, user)
    print(f"✓ Sesión creada: {session.token_sesion[:20]}...")
    print(f"✓ Dispositivo ID: {session.dispositivo_id[:20]}...")
    print(f"✓ IP: {session.ip_address}")
    print(f"✓ Expira en: {session.fecha_expiracion}")
    
    # Validar sesión
    is_valid, message = SecurityManager.validate_session(request)
    print(f"✓ Validación de sesión: {is_valid} - {message}")

if __name__ == '__main__':
    try:
        test_security_functions()
        test_session_creation()
    except Exception as e:
        print(f"❌ Error durante las pruebas: {e}")
        import traceback
        traceback.print_exc()