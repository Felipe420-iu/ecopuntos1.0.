from django.db import models
from django.db.models import Sum, Count, Avg, Q, F
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Usuario, Canje, MaterialTasa, RedencionPuntos, Ruta, SesionUsuario, IntentoAcceso
import json

class StatisticsManager:
    """Clase para manejar estadísticas avanzadas conectadas con la base de datos"""
    
    @staticmethod
    def get_user_activity_stats(days=30):
        """Obtiene estadísticas de actividad de usuarios"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Usuarios activos por día
        daily_active_users = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            active_users = SesionUsuario.objects.filter(
                fecha_creacion__date=date.date(),
                activa=True
            ).values('usuario').distinct().count()
            
            daily_active_users.append({
                'date': date.strftime('%Y-%m-%d'),
                'active_users': active_users
            })
        
        # Usuarios nuevos por día
        new_users_daily = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            new_users = Usuario.objects.filter(
                fecha_registro__date=date.date()
            ).count()
            
            new_users_daily.append({
                'date': date.strftime('%Y-%m-%d'),
                'new_users': new_users
            })
        
        return {
            'daily_active_users': daily_active_users,
            'new_users_daily': new_users_daily,
            'total_active_users': Usuario.objects.filter(is_active=True).count(),
            'total_users': Usuario.objects.count()
        }
    
    @staticmethod
    def get_recycling_stats(days=30):
        """Obtiene estadísticas de reciclaje"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Canjes por material
        material_stats = Canje.objects.filter(
            fecha_solicitud__gte=start_date,
            estado='aprobado'
        ).values('material__nombre').annotate(
            total_peso=Sum('peso'),
            total_puntos=Sum('puntos'),
            total_canjes=Count('id')
        ).order_by('-total_peso')
        
        # Canjes por día
        daily_canjes = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            canjes_count = Canje.objects.filter(
                fecha_solicitud__date=date.date(),
                estado='aprobado'
            ).count()
            
            total_peso = Canje.objects.filter(
                fecha_solicitud__date=date.date(),
                estado='aprobado'
            ).aggregate(total=Sum('peso'))['total'] or 0
            
            daily_canjes.append({
                'date': date.strftime('%Y-%m-%d'),
                'canjes_count': canjes_count,
                'total_peso': float(total_peso)
            })
        
        # Top usuarios recicladores
        top_recyclers = Usuario.objects.annotate(
            total_canjes=Count('canje', filter=Q(canje__estado='aprobado')),
            total_puntos=Sum('canje__puntos', filter=Q(canje__estado='aprobado'))
        ).filter(total_canjes__gt=0).order_by('-total_puntos')[:10]
        
        return {
            'material_stats': list(material_stats),
            'daily_canjes': daily_canjes,
            'top_recyclers': [
                {
                    'username': user.username,
                    'total_canjes': user.total_canjes,
                    'total_puntos': user.total_puntos or 0
                }
                for user in top_recyclers
            ],
            'total_recycled_weight': Canje.objects.filter(
                estado='aprobado'
            ).aggregate(total=Sum('peso'))['total'] or 0
        }
    
    @staticmethod
    def get_security_stats(days=30):
        """Obtiene estadísticas de seguridad"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Intentos de acceso no autorizado por tipo
        access_attempts_by_type = IntentoAcceso.objects.filter(
            fecha_intento__gte=start_date
        ).values('motivo').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Intentos por IP
        top_suspicious_ips = IntentoAcceso.objects.filter(
            fecha_intento__gte=start_date
        ).values('ip_address').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Sesiones activas por día
        daily_active_sessions = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            active_sessions = SesionUsuario.objects.filter(
                fecha_creacion__date=date.date(),
                activa=True
            ).count()
            
            daily_active_sessions.append({
                'date': date.strftime('%Y-%m-%d'),
                'active_sessions': active_sessions
            })
        
        return {
            'access_attempts_by_type': list(access_attempts_by_type),
            'top_suspicious_ips': list(top_suspicious_ips),
            'daily_active_sessions': daily_active_sessions,
            'total_access_attempts': IntentoAcceso.objects.filter(
                fecha_intento__gte=start_date
            ).count()
        }
    
    @staticmethod
    def get_financial_stats(days=30):
        """Obtiene estadísticas financieras"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Redenciones por método de pago
        redemptions_by_method = RedencionPuntos.objects.filter(
            fecha_solicitud__gte=start_date,
            estado='completado'
        ).values('metodo_pago').annotate(
            total_amount=Sum('valor_cop'),
            total_redemptions=Count('id')
        ).order_by('-total_amount')
        
        # Redenciones por día
        daily_redemptions = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            redemptions_count = RedencionPuntos.objects.filter(
                fecha_solicitud__date=date.date(),
                estado='completado'
            ).count()
            
            total_amount = RedencionPuntos.objects.filter(
                fecha_solicitud__date=date.date(),
                estado='completado'
            ).aggregate(total=Sum('valor_cop'))['total'] or 0
            
            daily_redemptions.append({
                'date': date.strftime('%Y-%m-%d'),
                'redemptions_count': redemptions_count,
                'total_amount': float(total_amount)
            })
        
        return {
            'redemptions_by_method': list(redemptions_by_method),
            'daily_redemptions': daily_redemptions,
            'total_redemptions_amount': RedencionPuntos.objects.filter(
                estado='completado'
            ).aggregate(total=Sum('valor_cop'))['total'] or 0
        }
    
    @staticmethod
    def get_route_stats(days=30):
        """Obtiene estadísticas de rutas"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Rutas por barrio
        routes_by_neighborhood = Ruta.objects.filter(
            fecha__gte=start_date.date()
        ).values('barrio').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Rutas por día
        daily_routes = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            routes_count = Ruta.objects.filter(
                fecha=date.date()
            ).count()
            
            daily_routes.append({
                'date': date.strftime('%Y-%m-%d'),
                'routes_count': routes_count
            })
        
        return {
            'routes_by_neighborhood': list(routes_by_neighborhood),
            'daily_routes': daily_routes,
            'total_routes': Ruta.objects.count()
        }
    
    @staticmethod
    def get_comprehensive_dashboard_stats():
        """Obtiene estadísticas completas para el dashboard"""
        today = timezone.now()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)
        last_month = today - timedelta(days=30)
        
        return {
            'users': {
                'total': Usuario.objects.count(),
                'active_today': SesionUsuario.objects.filter(
                    fecha_creacion__date=today.date(),
                    activa=True
                ).values('usuario').distinct().count(),
                'new_today': Usuario.objects.filter(
                    fecha_registro__date=today.date()
                ).count(),
                'new_this_week': Usuario.objects.filter(
                    fecha_registro__gte=last_week
                ).count()
            },
            'recycling': {
                'total_canjes': Canje.objects.filter(estado='aprobado').count(),
                'canjes_today': Canje.objects.filter(
                    fecha_solicitud__date=today.date(),
                    estado='aprobado'
                ).count(),
                'total_weight': Canje.objects.filter(
                    estado='aprobado'
                ).aggregate(total=Sum('peso'))['total'] or 0,
                'weight_today': Canje.objects.filter(
                    fecha_solicitud__date=today.date(),
                    estado='aprobado'
                ).aggregate(total=Sum('peso'))['total'] or 0
            },
            'security': {
                'active_sessions': SesionUsuario.objects.filter(activa=True).count(),
                'access_attempts_today': IntentoAcceso.objects.filter(
                    fecha_intento__date=today.date()
                ).count(),
                'suspicious_ips_today': IntentoAcceso.objects.filter(
                    fecha_intento__date=today.date()
                ).values('ip_address').distinct().count()
            },
            'financial': {
                'total_redemptions': RedencionPuntos.objects.filter(
                    estado='completado'
                ).count(),
                'redemptions_today': RedencionPuntos.objects.filter(
                    fecha_solicitud__date=today.date(),
                    estado='completado'
                ).count(),
                'total_amount': RedencionPuntos.objects.filter(
                    estado='completado'
                ).aggregate(total=Sum('valor_cop'))['total'] or 0
            }
        } 