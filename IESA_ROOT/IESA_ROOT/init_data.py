"""
Initialize database with fake data on first deployment
This runs automatically when the application starts
"""

import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
django.setup()

from django.core.management import call_command
from blog.models import Post
from users.models import User

def init_data():
    """Initialize data if database is empty"""
    
    # Check if database has data
    if Post.objects.exists() or User.objects.count() > 1:  # More than just admin
        return
    
    print("\n" + "="*80)
    print("🚀 DATABASE IS EMPTY - POPULATING WITH FAKE DATA")
    print("="*80 + "\n")
    
    try:
        # Run populate_fake_data management command
        call_command('populate_fake_data', '--users=12', '--posts=15', '--products=18', '--events=12', verbosity=2)
        print("\n" + "="*80)
        print("✅ DATA POPULATION COMPLETED SUCCESSFULLY")
        print("="*80 + "\n")
    except Exception as e:
        print(f"\n❌ ERROR DURING DATA POPULATION: {str(e)}\n")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    init_data()
