from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Usuario


class RegistroUsuarioForm(UserCreationForm):
    email = forms.EmailField(required=True)
    
    class Meta:
        model = Usuario
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user
    
class InicioSesionUsuarioForm(UserCreationForm):
    username = forms.CharField(required=True)

    class Meta:
        model = Usuario
        fields = ("username", "password")

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        password = cleaned_data.get("password")

        if not username or not password:
            raise forms.ValidationError("Ambos campos son obligatorios.")
        
        return cleaned_data

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = [
            'username', 'email', 'telefono', 'direccion', 'testimonio',
            'notificaciones_email', 'notificaciones_push', 'perfil_publico', 'mostrar_puntos',
            'foto_perfil',
        ]
        widgets = {
            'testimonio': forms.Textarea(attrs={'rows': 3}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
        }