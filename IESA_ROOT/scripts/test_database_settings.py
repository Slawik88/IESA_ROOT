"""Production database settings in subprocesses: DATABASE_POOL_URL must really win over DATABASE_URL."""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[1]
INSPECT_DATABASE = '''
import json
from unittest.mock import patch
with patch('dotenv.load_dotenv'):
    import IESA_ROOT.settings as config
    db = config.DATABASES['default']
    print(json.dumps({
        'port': db['PORT'], 'name': db['NAME'],
        'conn_max_age': db['CONN_MAX_AGE'],
        'health_checks': db['CONN_HEALTH_CHECKS'],
        'server_side_cursors_off': db['DISABLE_SERVER_SIDE_CURSORS'],
        'sslmode': db['OPTIONS']['sslmode'],
        'connect_timeout': db['OPTIONS']['connect_timeout'],
    }))
'''
DIRECT_URL = 'postgres://site:pw@db.example.com:25060/iesaroot-db'
POOL_URL = 'postgres://site:pw@db.example.com:25061/site_pool'


class DatabaseSettingsTests(unittest.TestCase):
    def run_settings(self, **changes):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('SPACES_', 'R2_', 'AWS_'))
               and key not in ('DATABASE_URL', 'DATABASE_POOL_URL', 'DB_CONN_MAX_AGE')}
        env.update(
            DEBUG='False', SECRET_KEY_DJANGO='isolated-database-test-key',
            DJANGO_SETTINGS_MODULE='IESA_ROOT.settings',
            SPACES_KEY='test-access-key', SPACES_SECRET='test-secret-key',
            SPACES_BUCKET='media',
        )
        env.update(changes)
        result = subprocess.run(
            [sys.executable, '-c', INSPECT_DATABASE], cwd=PROJECT, env=env,
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_pool_url_is_used_when_both_urls_are_set(self):
        db = self.run_settings(DATABASE_URL=DIRECT_URL, DATABASE_POOL_URL=POOL_URL)
        self.assertEqual((db['port'], db['name']), (25061, 'site_pool'))

    def test_direct_url_is_the_fallback_without_pool_url(self):
        db = self.run_settings(DATABASE_URL=DIRECT_URL)
        self.assertEqual((db['port'], db['name']), (25060, 'iesaroot-db'))

    def test_empty_pool_url_falls_back_to_direct_url(self):
        db = self.run_settings(DATABASE_URL=DIRECT_URL, DATABASE_POOL_URL='')
        self.assertEqual(db['port'], 25060)

    def test_pooled_connection_keeps_transaction_pooling_safeguards(self):
        db = self.run_settings(DATABASE_URL=DIRECT_URL, DATABASE_POOL_URL=POOL_URL, DB_CONN_MAX_AGE='30')
        self.assertEqual(db['conn_max_age'], 30)
        self.assertTrue(db['health_checks'])
        self.assertTrue(db['server_side_cursors_off'])
        self.assertEqual(db['sslmode'], 'require')
        self.assertEqual(db['connect_timeout'], 10)


if __name__ == '__main__':
    unittest.main()
