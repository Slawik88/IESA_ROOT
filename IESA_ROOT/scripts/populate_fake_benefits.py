"""Compatibility entry point; the seed data lives in the management command."""
import os
import sys
from pathlib import Path


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IESA_ROOT.settings')
    import django
    from django.core.management import call_command
    django.setup()
    call_command('populate_fake_benefits')


if __name__ == '__main__':
    main()
