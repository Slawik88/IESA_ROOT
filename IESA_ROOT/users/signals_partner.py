"""
Signal handlers for Partner system
Automatically creates Partner profile when user is added to Partners group
"""
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import Group
from .models import User, Partner
import logging

logger = logging.getLogger(__name__)


@receiver(m2m_changed, sender=User.groups.through)
def create_partner_profile_on_group_add(sender, instance, action, reverse, model, pk_set, **kwargs):
    """
    Automatically create Partner profile when user is added to 'Partners' group.
    
    Signal: m2m_changed on User.groups
    Action: post_add (after group is added)
    
    FIX: Clear session cache after adding user to group
    so is_partner() check works immediately without logout/login
    """
    if action == "post_add":
        # Check if 'Partners' group was added
        partners_group = Group.objects.filter(name='Partners').first()
        
        if partners_group and partners_group.id in pk_set:
            # User was just added to Partners group
            user = instance
            
            # Clear user's session cache to update group membership
            # This is critical - Django caches groups in the session
            from django.contrib.auth import get_backends
            from django.core.cache import cache
            
            # Clear Django's permission cache for this user
            cache_key = f'user_groups_{user.id}'
            cache.delete(cache_key)
            
            # Check if Partner profile already exists
            if not hasattr(user, 'partner_profile'):
                # Create Partner profile with default values
                company_name = f"{user.get_full_name() or user.username}'s Business"
                
                Partner.objects.create(
                    user=user,
                    company_name=company_name,
                    business_type='other'
                )
                
                logger.info(f"✅ Auto-created Partner profile for user: {user.username}")
                print(f"✅ Created Partner profile: {company_name}")
            else:
                logger.info(f"⚠️ Partner profile already exists for user: {user.username}")


@receiver(m2m_changed, sender=User.groups.through)
def delete_partner_profile_on_group_remove(sender, instance, action, reverse, model, pk_set, **kwargs):
    """
    Optionally delete Partner profile when user is removed from 'Partners' group.
    
    WARNING: This will delete all visit history!
    Comment out this signal if you want to keep data.
    """
    if action == "post_remove":
        partners_group = Group.objects.filter(name='Partners').first()
        
        if partners_group and partners_group.id in pk_set:
            user = instance
            
            # Delete Partner profile if exists
            if hasattr(user, 'partner_profile'):
                partner_name = user.partner_profile.company_name
                user.partner_profile.delete()
                
                logger.warning(f"⚠️ Deleted Partner profile for user: {user.username} ({partner_name})")
                print(f"⚠️ Deleted Partner profile: {partner_name}")
