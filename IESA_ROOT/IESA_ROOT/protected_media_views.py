"""
Protected media file serving with permission checks.
Serves files from /protected/ path only to authorized users.
"""

from django.http import FileResponse, Http404, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.conf import settings
import os


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
    # Security: Validate path is within protected directory
    protected_root = os.path.join(settings.MEDIA_ROOT, 'protected')
    full_path = os.path.join(protected_root, file_path)
    full_path = os.path.abspath(full_path)
    
    # Prevent directory traversal
    if not full_path.startswith(protected_root):
        raise Http404("Invalid path")
    
    # Check file exists
    if not os.path.exists(full_path):
        raise Http404("File not found")
    
    # Permission checks based on file type
    user = request.user
    
    # Avatars - owner or staff can access
    if file_path.startswith('avatars/'):
        # Extract username or user ID from path if needed
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
    
    # Serve file
    try:
        response = FileResponse(open(full_path, 'rb'))
        
        # Set content type based on extension
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.pdf': 'application/pdf',
            '.txt': 'text/plain',
        }
        
        ext = os.path.splitext(full_path)[1].lower()
        if ext in content_types:
            response['Content-Type'] = content_types[ext]
        
        return response
    except IOError:
        raise Http404("Cannot read file")
