from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import RedencionPuntos, Notificacion

@login_required
@user_passes_test(lambda u: u.is_staff)
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
@user_passes_test(lambda u: u.is_staff)
def aprobar_redencion(request, redencion_id):
    if request.method == 'POST':
        try:
            redencion = RedencionPuntos.objects.get(id=redencion_id)
            
            if redencion.estado != 'pendiente':
                return JsonResponse({
                    'success': False,
                    'message': 'Esta redención ya ha sido procesada.'
                })
            
            redencion.estado = 'aprobado'
            redencion.fecha_procesamiento = timezone.now()
            redencion.save()
            
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
@user_passes_test(lambda u: u.is_staff)
def rechazar_redencion(request, redencion_id):
    if request.method == 'POST':
        try:
            redencion = RedencionPuntos.objects.get(id=redencion_id)
            
            if redencion.estado != 'pendiente':
                return JsonResponse({
                    'success': False,
                    'message': 'Esta redención ya ha sido procesada.'
                })
            
            usuario = redencion.usuario
            usuario.puntos += redencion.puntos
            usuario.save()
            
            redencion.estado = 'rechazado'
            redencion.fecha_procesamiento = timezone.now()
            redencion.save()
            
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