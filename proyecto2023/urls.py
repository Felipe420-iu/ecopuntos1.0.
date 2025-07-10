from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('core.urls')),  # Incluye todas las URLs de la aplicación core
    path('admin/', admin.site.urls),
]

# Configuración para servir archivos estáticos y de medios siempre (sin verificar DEBUG)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
        # URL para la página de inicio
