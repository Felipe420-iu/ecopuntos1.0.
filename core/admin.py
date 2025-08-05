from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Canje, MaterialTasa, RedencionPuntos

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'puntos', 'fecha_registro')
    list_filter = ('role', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('Información Adicional', {
            'fields': ('role', 'puntos', 'telefono', 'direccion')
        }),
    )

class MaterialTasaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'puntos_por_kilo', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre',)

class CanjeAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'material', 'peso', 'puntos', 'estado', 'fecha_solicitud')
    list_filter = ('estado', 'material', 'fecha_solicitud')
    search_fields = ('usuario__username', 'material__nombre')
    readonly_fields = ('puntos',)

class RedencionPuntosAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'puntos', 'valor_cop', 'metodo_pago', 'estado', 'fecha_solicitud')
    list_filter = ('estado', 'metodo_pago', 'fecha_solicitud')
    search_fields = ('usuario__username', 'numero_cuenta')
    readonly_fields = ('valor_cop',)

admin.site.register(Usuario, CustomUserAdmin)
admin.site.register(MaterialTasa, MaterialTasaAdmin)
admin.site.register(Canje, CanjeAdmin)
admin.site.register(RedencionPuntos, RedencionPuntosAdmin)

# Register your models here.
