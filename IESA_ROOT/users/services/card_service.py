"""User card management service.

Handles QR code generation, card activation/revocation, and bulk operations.
"""

import uuid as uuid_module
from django.utils import timezone
from django.db.models import QuerySet
from ..qr_utils import generate_qr_code_for_user


class UserCardService:
    """Service for managing user cards and QR codes."""
    
    @staticmethod
    def regenerate_qr_for_users(queryset: QuerySet, request=None) -> int:
        """Regenerate QR codes for existing permanent IDs (same ID, new QR).
        
        Args:
            queryset: QuerySet of User objects
            request: Django request object for URL generation
            
        Returns:
            Count of users processed
        """
        count = 0
        for user in queryset:
            if user.permanent_id:
                generate_qr_code_for_user(user, request)
                count += 1
        return count
    
    @staticmethod
    def create_new_cards(queryset: QuerySet, request=None) -> int:
        """Create new cards with new permanent IDs for users.
        
        Used when user loses their card. Old ID and QR are replaced.
        
        Args:
            queryset: QuerySet of User objects
            request: Django request object for URL generation
            
        Returns:
            Count of users processed
        """
        users_to_update = []
        count = 0
        
        for user in queryset:
            user.permanent_id = uuid_module.uuid4()
            user.card_active = True
            user.card_issued_at = timezone.now()
            users_to_update.append(user)
            count += 1
        
        # Bulk update - FIX: Much faster than updating one by one
        if users_to_update:
            from .models import User
            User.objects.bulk_update(
                users_to_update,
                ['permanent_id', 'card_active', 'card_issued_at'],
                batch_size=100
            )
            
            # Now generate QR codes (can't be done in bulk, but at least updates are)
            for user in users_to_update:
                generate_qr_code_for_user(user, request)
        
        return count
    
    @staticmethod
    def issue_cards(queryset: QuerySet, request=None) -> int:
        """Activate cards and set issue date for users.
        
        Generates QR code if not already generated.
        
        Args:
            queryset: QuerySet of User objects
            request: Django request object for URL generation
            
        Returns:
            Count of users processed
        """
        users_to_update = []
        count = 0
        
        for user in queryset:
            user.card_active = True
            user.card_issued_at = timezone.now()
            users_to_update.append(user)
            count += 1
        
        # Bulk update fields
        if users_to_update:
            from .models import User
            User.objects.bulk_update(
                users_to_update,
                ['card_active', 'card_issued_at'],
                batch_size=100
            )
            
            # Generate QR codes
            for user in users_to_update:
                generate_qr_code_for_user(user, request)
        
        return count
    
    @staticmethod
    def revoke_cards(queryset: QuerySet) -> int:
        """Deactivate cards for users.
        
        Card becomes inactive but QR files remain in storage.
        
        Args:
            queryset: QuerySet of User objects
            
        Returns:
            Count of users processed
        """
        count = queryset.update(card_active=False)
        return count
