import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# bin/ is a scripts directory, not a package, so make fetch.py importable by tests.
sys.path.insert(0, str(REPO_ROOT / "bin"))
