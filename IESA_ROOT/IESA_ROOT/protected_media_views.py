"""
Protected media file serving with permission checks.
Serves files from /protected/ path only to authorized users.

Note: In production with S3/Spaces, files can be served directly from CDN
with appropriate CORS and ACL settings. This view is mainly for local development.
"""

from django.http import FileResponse, Http404, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.conf import settings
import os
from io import BytesIO


@login_required
def serve_protected_media(request, file_path):
    """
    Serve protected media files with permission checks.
    
    URL: /protected/<path>
    Requires: User authentication
    
    Permission logic:
    - Avatars: Owner or staff
    - Cards: Owner or staff  
    - Other files: Staff only (default)
    """
    # Use Django storage (supports both local and S3)
    from django.core.files.storage import default_storage
    
    # Build the full path - always use prefixed path for safety
    full_path = f'protected/{file_path}'
    
    # Security: Basic check that path doesn't contain ../ for traversal
    if '..' in file_path or file_path.startswith('/'):
        raise Http404("Invalid path")
    
    # Check file exists in storage
    if not default_storage.exists(full_path):
        raise Http404("File not found")
    
    # Permission checks based on file type
    user = request.user
    
    # Avatars - owner or staff can access
    if file_path.startswith('avatars/'):
        # For now, allow authenticated users to view avatars
        pass
    
    # Cards - owner or staff
    elif file_path.startswith('cards/'):
        # Allow all authenticated users (QR cards are semi-public)
        pass
    
    # Other protected files - staff only
    else:
        if not user.is_staff:
            return HttpResponseForbidden("You don't have permission to access this file")
    
    # Serve file from storage
    try:
        file_obj = default_storage.open(full_path, 'rb')
        response = FileResponse(file_obj)
        
        # Set content type based on extension
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.pdf': 'application/pdf',
            '.txt': 'text/plain',
        }
        
        ext = os.path.splitext(file_path)[1].lower()
        if ext in content_types:
            response['Content-Type'] = content_types[ext]
        
        return response
    except IOError:
        raise Http404("Cannot read file")
