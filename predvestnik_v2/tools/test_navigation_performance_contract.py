"""Execute the actual browser scheduler and API helper under controlled races."""
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent
node = shutil.which('node')
assert node, 'Node is required to verify navigation response ordering'
for name in ('test_load_scheduler.js', 'test_navigation_reads.js'):
    subprocess.run([node, str(root / name)], check=True, timeout=30)
print('PASS: navigation scheduler and API concurrency contracts')
