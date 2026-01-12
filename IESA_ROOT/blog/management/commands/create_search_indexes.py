"""
Management command to create PostgreSQL full-text search indexes.

Usage:
    python manage.py create_search_indexes
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Creates PostgreSQL GIN indexes for full-text search'

    def handle(self, *args, **options):
        self.stdout.write('Creating search indexes...')
        
        with connection.cursor() as cursor:
            # User search index
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS user_search_idx 
                    ON users_user 
                    USING GIN (
                        to_tsvector('russian', 
                            coalesce(username, '') || ' ' || 
                            coalesce(first_name, '') || ' ' || 
                            coalesce(last_name, '') || ' ' || 
                            coalesce(bio, '')
                        )
                    )
                """)
                self.stdout.write(self.style.SUCCESS('✓ Created user_search_idx'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ User index failed: {e}'))
            
            # Post search index
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS post_search_idx 
                    ON blog_post 
                    USING GIN (
                        to_tsvector('russian', 
                            coalesce(title, '') || ' ' || 
                            coalesce(text, '')
                        )
                    )
                """)
                self.stdout.write(self.style.SUCCESS('✓ Created post_search_idx'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Post index failed: {e}'))
            
            # Event search index
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS event_search_idx 
                    ON blog_event 
                    USING GIN (
                        to_tsvector('russian', 
                            coalesce(title, '') || ' ' || 
                            coalesce(description, '') || ' ' || 
                            coalesce(location, '')
                        )
                    )
                """)
                self.stdout.write(self.style.SUCCESS('✓ Created event_search_idx'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Event index failed: {e}'))
        
        self.stdout.write(self.style.SUCCESS('\n✓ Search indexes created successfully!'))
        self.stdout.write('Note: These indexes will only work with PostgreSQL database.')
