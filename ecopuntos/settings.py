# Email settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'ecopuntos.soporte@gmail.com'  # Reemplaza con tu correo de Gmail
EMAIL_HOST_PASSWORD = 'xvtw rnvp zcxm ydkp'  # Reemplaza con tu contraseña de aplicación
DEFAULT_FROM_EMAIL = 'Eco Puntos <ecopuntos.soporte@gmail.com>'

# Configuración para producción (comentada por ahora)
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.gmail.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = 'tu_correo@gmail.com'
# EMAIL_HOST_PASSWORD = 'tu_contraseña_de_aplicacion'
# DEFAULT_FROM_EMAIL = 'Eco Puntos <tu_correo@gmail.com>' 