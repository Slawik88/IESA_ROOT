from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = 'Fix messaging app migrations by resetting and reapplying them'

    def handle(self, *args, **options):
        self.stdout.write("🔧 Fixing messaging migrations...")
        
        with connection.cursor() as cursor:
            try:
                # Check if table exists
                cursor.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name='messaging_chat'
                    )
                """)
                table_exists = cursor.fetchone()[0]
                
                if table_exists:
                    self.stdout.write(self.style.SUCCESS("✅ Table messaging_chat already exists"))
                    return
                
                self.stdout.write("⚠️  Table messaging_chat not found, creating...")
                
                # Delete migration record
                cursor.execute("DELETE FROM django_migrations WHERE app = 'messaging'")
                self.stdout.write("🗑️  Cleared migration records for messaging app")
                
            except OperationalError as e:
                self.stdout.write(self.style.ERROR(f"❌ Database error: {e}"))
                return
        
        # Now run migrate
        from django.core.management import call_command
        try:
            call_command('migrate', 'messaging', verbosity=2)
            self.stdout.write(self.style.SUCCESS("✅ Messaging migrations applied successfully!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Migration failed: {e}"))
