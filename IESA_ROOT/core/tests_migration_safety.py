"""scripts/check_migration_safety.py: risky ops in a new migration block the push unless marked."""
import importlib.util
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_spec = importlib.util.spec_from_file_location(
    "check_migration_safety", Path(settings.BASE_DIR) / "scripts" / "check_migration_safety.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

MIGRATION = """from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("users", "0001_initial")]
    operations = [
        migrations.AddField(model_name="user", name="nick", field=models.CharField(max_length=9, default="")),
        {ops}
    ]
"""


class MigrationSafetyTests(SimpleTestCase):
    def _check(self, ops, marker=""):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "users" / "migrations" / "0099_x.py"
            path.parent.mkdir(parents=True)
            path.write_text(marker + MIGRATION.format(ops=ops), encoding="utf-8")
            return guard.check([str(path)])

    def test_additive_migration_passes(self):
        self.assertEqual(self._check(""), [])

    def test_risky_operations_are_reported(self):
        for op in ('migrations.RunSQL("UPDATE users_user SET nick = \'\'")',
                   'migrations.RemoveField(model_name="user", name="nick")',
                   'migrations.RenameField(model_name="user", old_name="nick", new_name="alias")',
                   'migrations.DeleteModel(name="Visit")',
                   'migrations.RenameModel(old_name="Visit", new_name="Trip")'):
            with self.subTest(op=op):
                problems = self._check(op + ",")
                self.assertEqual(len(problems), 1, problems)
                self.assertIn(op.split("(")[0].split(".")[1], problems[0])

    def test_marker_with_reason_allows_it(self):
        self.assertEqual(self._check('migrations.RemoveField(model_name="user", name="nick"),',
                                     "# migration-safe: field unused since 0031\n"), [])
        # A bare marker without a reason does not count.
        self.assertEqual(len(self._check('migrations.RemoveField(model_name="user", name="nick"),',
                                         "# migration-safe:\n")), 1)
