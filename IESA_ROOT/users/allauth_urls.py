"""The only allauth URLs we expose: the OAuth handshake. Mounted at /accounts/.

allauth.account's own login/signup/password pages are deliberately NOT included
(they would bypass our anti-bot checks). A few URL *names* allauth reverses
internally are provided here as redirects into our own pages.
"""
from allauth.socialaccount import urls as socialaccount_urls
from allauth.urls import build_provider_urlpatterns
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

# Provider handshake URLs: /accounts/<provider>/login/ and /accounts/<provider>/login/callback/
# (these callback addresses are what must be registered at Google / Microsoft / Facebook / Apple).
# The mobile "login by token" shortcuts are not needed and are left out.
_provider_urls = [p for p in build_provider_urlpatterns() if not str(getattr(p, 'name', '') or '').endswith('_by_token')]

urlpatterns = [
    path('3rdparty/', include(socialaccount_urls)),
    *_provider_urls,
    path('login/', RedirectView.as_view(pattern_name='users:login', query_string=True), name='account_login'),
    path('signup/', RedirectView.as_view(pattern_name='users:register', query_string=True), name='account_signup'),
    path('logout/', RedirectView.as_view(pattern_name='users:login'), name='account_logout'),
    path('inactive/', TemplateView.as_view(template_name='socialaccount/account_inactive.html'), name='account_inactive'),
    path('confirm-email/', RedirectView.as_view(pattern_name='users:login'), name='account_email_verification_sent'),
]
