"""Auth views: register, login, logout."""
from django.contrib.auth import views as auth_views, logout
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.shortcuts import redirect

from ..forms import CustomUserCreationForm
from ..models import User
from ..ratelimit_utils import login_ratelimit, register_ratelimit


def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('core:home')


@method_decorator(register_ratelimit, name='dispatch')
class RegisterView(CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:login')

    def form_valid(self, form):
        return super().form_valid(form)


@method_decorator(login_ratelimit, name='dispatch')
class LoginView(auth_views.LoginView):
    template_name = 'users/login.html'
