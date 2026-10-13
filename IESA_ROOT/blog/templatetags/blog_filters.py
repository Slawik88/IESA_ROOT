from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Фильтр для получения значения из словаря по ключу в шаблонах.
    Используется: {{ dict|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def safe_post_html(value):
    from django.utils.safestring import mark_safe
    from ..utils.html import sanitize_post_html
    # Only the sanitizer's allowlisted output is marked safe, never raw user input.
    return mark_safe(sanitize_post_html(value))
