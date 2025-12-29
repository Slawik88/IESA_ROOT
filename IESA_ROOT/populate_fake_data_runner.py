#!/usr/bin/env python
"""
Management script to populate fake data
Run with: python populate_fake_data_runner.py
"""

import subprocess
import sys

# Read the script content
with open('populate_fake_data.py', 'r') as f:
    script_content = f.read()

# Execute via shell
process = subprocess.Popen(
    [sys.executable, 'manage.py', 'shell'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

stdout, stderr = process.communicate(input=script_content)

print(stdout)
if stderr:
    print("STDERR:", stderr, file=sys.stderr)

sys.exit(process.returncode)
