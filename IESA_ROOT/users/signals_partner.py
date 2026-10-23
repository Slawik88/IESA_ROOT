"""Keep partner profiles and access flags in sync when Partners is granted.

Both User.groups.add(group) and Group.user_set.add(user) emit this signal.
Revoking partner access remains an explicit business/admin operation.
"""
import logging

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import Partner, User

logger = logging.getLogger(__name__)


@receiver(m2m_changed, sender=User.groups.through)
def create_partner_profile_on_group_add(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action != 'post_add' or not pk_set:
        return
    if reverse:
        if instance.name != 'Partners':
            return
        users = User.objects.filter(pk__in=pk_set)
    else:
        if not Group.objects.filter(name='Partners', pk__in=pk_set).exists():
            return
        users = [instance]

    for user in users:
        profile, created = Partner.objects.get_or_create(
            user=user,
            defaults={
                'company_name': f"{user.get_full_name() or user.username}'s Business",
                'business_type': 'other',
            },
        )
        user.partner_profile = profile
        if not user.is_partner:
            User.objects.filter(pk=user.pk).update(is_partner=True)
            user.is_partner = True
        for attr in ('_perm_cache', '_user_perm_cache', '_group_perm_cache', '_is_partner_cached'):
            user.__dict__.pop(attr, None)
        cache.delete(f'user_groups_{user.pk}')
        logger.info('Partner access granted for user %s (profile_created=%s)', user.pk, created)
