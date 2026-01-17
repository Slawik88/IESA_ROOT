#!/usr/bin/env python3
"""
Скрипт для обновления всех шаблонов на namespace URLs.
Заменяет {% url 'name' %} на {% url 'app:name' %}
"""

import os
import re
from pathlib import Path

# Маппинг URL имён на их namespace
URL_MAPPINGS = {
    # Blog URLs
    'post_list': 'blog:post_list',
    'event_list': 'blog:event_list',
    'event_detail': 'blog:event_detail',
    'post_detail': 'blog:post_detail',
    'post_create': 'blog:post_create',
    'like_post': 'blog:like_post',
    'comment_create': 'blog:comment_create',
    'comment_list': 'blog:comment_list',
    'delete_comment': 'blog:delete_comment',
    'toggle_comment_like': 'blog:toggle_comment_like',
    'toggle_subscription': 'blog:toggle_subscription',
    'post_search': 'blog:post_search',
    'global_search': 'blog:global_search',
    
    # User URLs
    'profile': 'users:profile',
    'profile_edit': 'users:profile_edit',
    'login': 'users:login',
    'logout': 'users:logout',
    'register': 'users:register',
    'profile_public_username': 'users:profile_public_username',
    'profile_by_card': 'users:profile_by_card',
    'users_search': 'users:users_search',
    
    # Notification URLs
    'notification_list': 'notifications:notification_list',
    'notification_delete': 'notifications:notification_delete',
    'notification_panel': 'notifications:notification_panel',
    'mark_notification_read': 'notifications:mark_notification_read',
    'mark_all_read': 'notifications:mark_all_read',
    
    # Core/Gallery URLs (these don't have namespace yet, skip them)
    'home': 'home',
    'gallery': 'gallery',
    'partner_detail': 'partner_detail',
}

def update_template_file(filepath):
    """Update a single template file with namespace URLs."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Pattern to match {% url 'name' ... %}
    # We need to be careful to only replace the URL name, not the entire tag
    for url_name, namespaced_name in URL_MAPPINGS.items():
        if url_name == namespaced_name:
            continue  # Skip if no change needed
        
        # Pattern: {% url 'url_name' or {% url "url_name"
        # We need to match whole word, so use word boundaries
        patterns = [
            (rf"{{% url '{url_name}'", f"{{% url '{namespaced_name}'"),
            (rf'{{% url "{url_name}"', f'{{% url "{namespaced_name}"'),
        ]
        
        for pattern, replacement in patterns:
            content = content.replace(pattern, replacement)
    
    # Write back if changed
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    """Find and update all HTML templates."""
    root_dir = Path('.')
    html_files = list(root_dir.rglob('*.html'))
    
    print(f"Found {len(html_files)} HTML files")
    
    updated = 0
    for html_file in html_files:
        # Skip migrations and static files
        if 'migrations' in str(html_file) or 'static' in str(html_file):
            continue
        
        try:
            if update_template_file(html_file):
                print(f"✅ Updated: {html_file}")
                updated += 1
            else:
                print(f"⏭️  No changes: {html_file}")
        except Exception as e:
            print(f"❌ Error updating {html_file}: {e}")
    
    print(f"\n✅ Total updated: {updated} files")

if __name__ == '__main__':
    main()
