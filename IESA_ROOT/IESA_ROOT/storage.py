"""
Custom storage backend for protected media files.
Requires user authentication and permission checks for sensitive files.
"""

from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os


class ProtectedMediaStorage(FileSystemStorage):
    """
    Storage backend for files that require permission checks.
    Use this for user avatars, private documents, etc.
    """
    
    def __init__(self, *args, **kwargs):
        kwargs['location'] = os.path.join(settings.MEDIA_ROOT, 'protected')
        kwargs['base_url'] = '/protected/'
        super().__init__(*args, **kwargs)
    
    def get_available_name(self, name, max_length=None):
        """
        Prevent filename collisions by adding unique suffix.
        """
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        
        # If file exists, add counter
        count = 1
        while self.exists(name):
            name = os.path.join(dir_name, f"{file_root}_{count}{file_ext}")
            count += 1
        
        return name
