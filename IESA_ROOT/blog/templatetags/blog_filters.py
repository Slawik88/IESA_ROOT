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
