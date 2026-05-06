"""
Сигналы инвалидации кэша для IndexView.

После изменения/удаления любой модели которая кэшируется на главной
(CoreProduct, President, Partner, AssociationMember, MemberBenefit, Event)
соответствующий ключ в Django cache очищается автоматически (B1-10).
"""
import logging
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_IDX_KEYS = {
    'CoreProduct':      'idx:core_products',
    'President':        'idx:president',
    'Partner':          'idx:partners',
    'AssociationMember': 'idx:members',
    'MemberBenefit':    'idx:member_benefits',
    'Event':            'idx:upcoming_events',
}


def _invalidate_index_cache(sender, **kwargs):
    key = _IDX_KEYS.get(sender.__name__)
    if key:
        cache.delete(key)
        logger.debug("Index cache invalidated: %s", key)


def connect_signals():
    """Подключить сигналы. Вызывается из CoreConfig.ready()."""
    from .models import (
        CoreProduct, President, Partner,
        AssociationMember, MemberBenefit,
    )
    # Импортируем Event из blog чтобы не создавать circular import при import времени
    try:
        from blog.models import Event
        _models = [CoreProduct, President, Partner, AssociationMember, MemberBenefit, Event]
    except ImportError:
        _models = [CoreProduct, President, Partner, AssociationMember, MemberBenefit]

    for model in _models:
        post_save.connect(_invalidate_index_cache, sender=model, weak=False)
        post_delete.connect(_invalidate_index_cache, sender=model, weak=False)
