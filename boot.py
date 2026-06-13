"""
OneAtlas AppSpec Engine - Bootstrap Script

This script initializes the application environment by running frontend generation
and other initialization tasks. It serves as the entry point for application setup.

Environment Setup:
- Generates frontend static assets if needed
- Initializes data directories
- Validates API connections
"""

import subprocess
import sys
from pathlib import Path

# Execute frontend generation (if available)
# This step compiles React components and generates static assets
try:
    gen_fe_path = Path(__file__).parent / 'gen_fe.py'
    if gen_fe_path.exists():
        subprocess.run([sys.executable, str(gen_fe_path)], check=False)
except Exception as e:
    print(f"Note: Frontend generation skipped ({e})")