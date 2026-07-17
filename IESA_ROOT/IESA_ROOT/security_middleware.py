"""audit v5: Security headers middleware (CSP, X-Content-Type-Options, Referrer-Policy).

Не требует внешних пакетов — обычный Django middleware.
Добавляется в settings.MIDDLEWARE.
"""


class SecurityHeadersMiddleware:
    """
    Добавляет защитные HTTP-заголовки ко всем ответам:
      - Content-Security-Policy: ограничивает источники скриптов/стилей/etc
      - X-Content-Type-Options: nosniff — браузер не угадывает MIME
      - Referrer-Policy: strict-origin-when-cross-origin
      - Permissions-Policy: запрещает camera/microphone (geolocation для карт партнёров — self)
      - X-Frame-Options: SAMEORIGIN (защита от clickjacking)

    CSP настроен для текущих внешних доменов IESA:
      - Bootstrap, FontAwesome (cdn.jsdelivr.net, cdnjs.cloudflare.com)
      - Google Fonts (fonts.googleapis.com, fonts.gstatic.com)
      - Lightbox (cdnjs.cloudflare.com)
      - OpenStreetMap tiles для partner map (a/b/c.tile.openstreetmap.org)
    """

    CSP_DIRECTIVES = [
        "default-src 'self'",
        # 'unsafe-inline' нужен для inline-стилей в шаблонах + Bootstrap
        # 'unsafe-eval' нужен для HTMX и некоторых динамических скриптов
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
        "style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
        "img-src 'self' data: blob: https: ",
        "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net",
        # connect-src: HTMX requests + map tiles + наш API
        "connect-src 'self' https://api.telegram.org https://*.tile.openstreetmap.org",
        "media-src 'self' data: blob:",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ]

    def __init__(self, get_response):
        self.get_response = get_response
        self._csp_value = '; '.join(self.CSP_DIRECTIVES)

    def __call__(self, request):
        response = self.get_response(request)

        # Не добавляем CSP к админке — там Django sometimes использует inline event handlers
        if not request.path.startswith('/admin/'):
            response.setdefault('Content-Security-Policy', self._csp_value)

        # Универсальные защитные заголовки (все маршруты)
        response.setdefault('X-Content-Type-Options', 'nosniff')
        response.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(), geolocation=(self), payment=(), usb=()',
        )
        # X-Frame-Options обычно ставит Django XFrameOptionsMiddleware, дублируем для надёжности
        response.setdefault('X-Frame-Options', 'SAMEORIGIN')

        return response


class HtmxLoginRedirectMiddleware:
    """HTMX + login_required: редирект на логин нельзя отдавать в hx-запрос —
    HTMX вставит страницу логина целиком внутрь текущей (аудит V1).

    Отдаём тихий 204 (без свапа). Вью, которым при клике анонима нужен настоящий
    переход на логин, выставляют заголовок HX-Redirect сами (пример: blog.views.likes).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.headers.get('HX-Request') == 'true'
            and response.status_code in (301, 302)
            and '/auth/login' in response.get('Location', '')
            and 'HX-Redirect' not in response
        ):
            from django.http import HttpResponse
            suppressed = HttpResponse(status=204)
            suppressed['X-Suppressed-Login-Redirect'] = response['Location']
            return suppressed
        return response
