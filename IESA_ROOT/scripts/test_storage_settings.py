"""Exercise production storage settings in subprocesses without live secrets."""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[1]
INSPECT_STORAGE = '''
import json
from unittest.mock import patch
with patch('dotenv.load_dotenv'):
    import IESA_ROOT.settings as config
    from IESA_ROOT.storage import MediaOptimizationStorage
    storage = MediaOptimizationStorage(**config.STORAGES['default']['OPTIONS'])
    print(json.dumps({
        'region': storage.region_name,
        'acl': storage.default_acl,
        'url': storage.url('media/photo.webp'),
        'static': config.STORAGES['staticfiles']['BACKEND'],
    }))
'''


class StorageSettingsTests(unittest.TestCase):
    def run_settings(self, **changes):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('SPACES_', 'R2_', 'AWS_'))
               and key not in ('DATABASE_URL', 'DATABASE_POOL_URL')}
        env.update(
            DEBUG='False', SECRET_KEY_DJANGO='isolated-storage-test-key',
            DJANGO_SETTINGS_MODULE='IESA_ROOT.settings',
            SPACES_KEY='test-access-key', SPACES_SECRET='test-secret-key',
            SPACES_BUCKET='media',
        )
        env.update(changes)
        return subprocess.run(
            [sys.executable, '-c', INSPECT_STORAGE], cwd=PROJECT, env=env,
            text=True, capture_output=True, timeout=30,
        )

    def test_spaces_keeps_existing_public_urls_and_upload_acl(self):
        result = self.run_settings()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            'region': 'fra1', 'acl': 'public-read',
            'url': 'https://media.fra1.digitaloceanspaces.com/media/photo.webp',
            'static': 'IESA_ROOT.storage.WhitenoiseManifestStorage',
        })

    def test_r2_uses_auto_region_no_object_acl_and_stable_public_url(self):
        result = self.run_settings(
            SPACES_ENDPOINT='https://example.r2.cloudflarestorage.com',
            SPACES_PUBLIC_DOMAIN='media.example.com',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        storage = json.loads(result.stdout)
        self.assertIsNone(storage['acl'])
        self.assertEqual(storage['region'], 'auto')
        self.assertEqual(storage['url'], 'https://media.example.com/media/photo.webp')

    def test_r2_without_public_hostname_stops_instead_of_serving_spaces_urls(self):
        result = self.run_settings(SPACES_ENDPOINT='https://example.r2.cloudflarestorage.com')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires SPACES_PUBLIC_DOMAIN', result.stderr)

    def test_public_domain_rejects_url_with_path(self):
        result = self.run_settings(SPACES_PUBLIC_DOMAIN='https://media.example.com/path')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('must be a hostname', result.stderr)

    def test_r2_backup_requires_separate_private_bucket_before_dumping(self):
        env = dict(os.environ)
        env.update(
            SPACES_ENDPOINT='https://example.r2.cloudflarestorage.com',
            SPACES_KEY='test-key', SPACES_SECRET='test-secret',
            SPACES_BUCKET='public-media', BACKUP_BUCKET='public-media',
            DATABASE_URL='postgresql://test.invalid/unused',
        )
        result = subprocess.run(
            [sys.executable, 'scripts/backup_db.py'], cwd=PROJECT, env=env,
            text=True, capture_output=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('separate private bucket', result.stdout)


if __name__ == '__main__':
    unittest.main()
