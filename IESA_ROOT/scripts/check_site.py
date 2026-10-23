"""Portable local/CI checks. Run with the website's Python environment.

    python scripts/check_site.py
    python scripts/check_site.py --skip-tests
"""
import argparse
from importlib.util import find_spec
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
    ruff = [sys.executable, '-m', 'ruff'] if find_spec('ruff') else [shutil.which('ruff')]
    node = shutil.which('node')
    if not ruff[0] or not node:
        parser.error('Install Ruff and Node.js to run all site checks.')

    commands = [
        [*ruff, 'check', '.'],
        [sys.executable, '-m', 'pip', 'check'],
        [sys.executable, 'manage.py', 'check', '--settings=IESA_ROOT.settings_test'],
        [sys.executable, 'manage.py', 'makemigrations', '--check', '--dry-run', '--settings=IESA_ROOT.settings_test'],
    ]
    if not args.skip_tests:
        commands.append([
            sys.executable, 'manage.py', 'test', 'core', 'blog', 'products', 'gallery',
            'notifications', 'users', '--settings=IESA_ROOT.settings_test', '--noinput',
        ])
    for command in commands:
        print('> ' + ' '.join(command), flush=True)
        subprocess.run(command, cwd=root, env=env, check=True)

    scripts = sorted(p for p in (root / 'static' / 'js').glob('*.js') if '.min.' not in p.name and '.bundle.' not in p.name)
    scripts.append(root / 'static' / 'service-worker.js')
    for script in scripts:
        subprocess.run([node, '--check', str(script)], cwd=root, env=env, check=True)
    print(f'JavaScript syntax OK: {len(scripts)} application scripts.', flush=True)


if __name__ == '__main__':
    main()
