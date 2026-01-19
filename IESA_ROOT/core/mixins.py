"""
Django Mixins для HTMX интеграции
Обеспечивают real-time валидацию форм, partial rendering и toast уведомления
"""
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.contrib import messages


class HTMXMixin:
    """Миксин для определения HTMX запросов и соответствующего ответа"""
    
    def is_htmx_request(self):
        """Проверяет, является ли запрос HTMX запросом"""
        return self.request.headers.get('HX-Request') == 'true'
    
    def htmx_trigger(self):
        """Возвращает ID элемента, который вызвал запрос"""
        return self.request.headers.get('HX-Trigger')
    
    def htmx_target(self):
        """Возвращает ID целевого элемента"""
        return self.request.headers.get('HX-Target')
    
    def render_partial(self, template_name, context=None):
        """Рендерит partial шаблон для HTMX ответа"""
        if context is None:
            context = {}
        context['request'] = self.request
        html = render_to_string(template_name, context, request=self.request)
        return HttpResponse(html)


class FormValidationMixin:
    """Миксин для real-time валидации форм через HTMX"""
    
    def validate_field(self, form, field_name):
        """
        Валидирует одно поле формы и возвращает HTML с ошибкой или успехом.
        Используется для HTMX hx-trigger="blur" валидации.
        """
        # Получаем значение поля из запроса
        field_value = self.request.POST.get(field_name, '')
        
        # Создаём форму с данными только этого поля
        form_data = {field_name: field_value}
        form_instance = form(data=form_data)
        
        # Принудительно валидируем только это поле
        form_instance.is_valid()
        
        if field_name in form_instance.errors:
            error_msg = form_instance.errors[field_name][0]
            return HttpResponse(
                f'<div class="invalid-feedback d-block">{error_msg}</div>',
                headers={'HX-Retarget': f'#{field_name}-feedback'}
            )
        else:
            return HttpResponse(
                '<div class="valid-feedback d-block">✓</div>',
                headers={'HX-Retarget': f'#{field_name}-feedback'}
            )


class ToastMixin:
    """Миксин для отправки Bootstrap Toast уведомлений через HTMX"""
    
    def send_toast(self, message, level='success', title=None):
        """
        Отправляет toast уведомление.
        level: success, danger, warning, info
        """
        icons = {
            'success': 'fa-check-circle',
            'danger': 'fa-exclamation-circle',
            'warning': 'fa-exclamation-triangle',
            'info': 'fa-info-circle'
        }
        
        colors = {
            'success': 'text-success',
            'danger': 'text-danger',
            'warning': 'text-warning',
            'info': 'text-info'
        }
        
        if title is None:
            titles = {
                'success': 'Успешно',
                'danger': 'Ошибка',
                'warning': 'Внимание',
                'info': 'Информация'
            }
            title = titles.get(level, 'Уведомление')
        
        toast_html = f'''
        <div class="toast align-items-center border-0" role="alert" aria-live="assertive" aria-atomic="true"
             hx-swap-oob="beforeend:#toast-container">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas {icons.get(level, 'fa-info-circle')} {colors.get(level, '')} me-2"></i>
                    <strong>{title}:</strong> {message}
                </div>
                <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
        '''
        return toast_html
    
    def add_toast_to_response(self, response, message, level='success', title=None):
        """Добавляет toast к существующему HTMX ответу через OOB swap"""
        toast_html = self.send_toast(message, level, title)
        
        if isinstance(response, HttpResponse):
            response.content = response.content + toast_html.encode()
        
        return response


def htmx_render(request, template_name, context=None, partial_template=None):
    """
    Утилита для рендеринга: полный шаблон для обычных запросов,
    partial шаблон для HTMX запросов.
    """
    from django.shortcuts import render
    
    if context is None:
        context = {}
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if is_htmx and partial_template:
        return render(request, partial_template, context)
    
    return render(request, template_name, context)
