"""Migration checks use isolated object stores; no live credentials or database."""

import io
import unittest
from unittest.mock import Mock

from botocore.exceptions import ClientError

from migrate_spaces_to_r2 import PUBLIC_GRANTEE, migrate


class ObjectStore:
    def __init__(self, objects=None, public_keys=()):
        self.objects = dict(objects or {})
        self.public_keys = set(public_keys)
        self.puts = []

    def get_paginator(self, name):
        paginator = Mock()
        # Separate pages exercise full-bucket inventory instead of only page one.
        paginator.paginate.return_value = [
            {'Contents': [{'Key': key, 'ETag': 'version-1', 'Size': len(value)}]}
            for key, value in self.objects.items()
        ]
        return paginator

    def get_object_acl(self, **args):
        return {'Grants': [{'Grantee': {'URI': PUBLIC_GRANTEE}, 'Permission': 'READ'}]
                if args['Key'] in self.public_keys else []}

    def get_object(self, **args):
        if args['Key'] not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        return {'Body': io.BytesIO(self.objects[args['Key']]), 'ContentType': 'image/webp'}

    def put_object(self, **args):
        if args.get('IfNoneMatch') != '*' or args['Key'] in self.objects:
            raise AssertionError('Migration must not overwrite an existing object.')
        self.puts.append((args['Bucket'], args['Key']))
        self.objects[args['Key']] = args['Body'].read()


class StorageMigrationTests(unittest.TestCase):
    def setUp(self):
        self.source = ObjectStore(
            {'media/photo.webp': b'image bytes', 'predvestnik-bot/db.sqlite3': b'private backup'},
            public_keys={'media/photo.webp'},
        )
        self.target = ObjectStore()

    def run_migration(self, mode):
        return migrate(self.source, self.target, 'spaces', 'public-media', 'private-backups', mode)

    def test_inventory_does_not_write_and_counts_private_files(self):
        self.assertEqual(self.run_migration('plan'), {
            'public_objects': 1, 'private_objects': 1, 'bytes': 25,
        })
        self.assertEqual(self.target.puts, [])

    def test_copy_preserves_bytes_routes_private_files_and_can_be_repeated(self):
        self.run_migration('apply')
        self.assertEqual(self.target.objects, self.source.objects)
        self.assertEqual(self.target.puts, [
            ('public-media', 'media/photo.webp'),
            ('private-backups', 'predvestnik-bot/db.sqlite3'),
        ])
        self.run_migration('apply')
        self.run_migration('verify')
        self.assertEqual(len(self.target.puts), 2)

    def test_existing_different_content_stops_without_overwrite(self):
        self.target.objects['media/photo.webp'] = b'new content'
        with self.assertRaisesRegex(RuntimeError, 'Content mismatch'):
            self.run_migration('apply')
        self.assertEqual(self.target.objects['media/photo.webp'], b'new content')
        self.assertEqual(self.target.puts, [])

    def test_verification_fails_for_a_missing_copy(self):
        with self.assertRaisesRegex(RuntimeError, 'Target object missing'):
            self.run_migration('verify')
        self.assertEqual(self.target.puts, [])

    def test_private_data_cannot_use_public_bucket(self):
        with self.assertRaisesRegex(ValueError, 'must be different'):
            migrate(self.source, self.target, 'spaces', 'same', 'same', 'apply')
        self.assertEqual(self.target.puts, [])

    def test_database_copy_stays_private_even_with_a_legacy_public_acl(self):
        self.source.public_keys.add('predvestnik-bot/db.sqlite3')
        self.run_migration('apply')
        self.assertIn(('private-backups', 'predvestnik-bot/db.sqlite3'), self.target.puts)

    def test_corrupted_upload_does_not_pass_verification(self):
        original_put = self.target.put_object

        def corrupt(**args):
            original_put(**args)
            self.target.objects[args['Key']] = b'truncated'

        self.target.put_object = corrupt
        with self.assertRaisesRegex(RuntimeError, 'Content mismatch'):
            self.run_migration('apply')


if __name__ == '__main__':
    unittest.main()
