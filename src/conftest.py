# Makes the project root importable as top-level packages (config, models,
# services.*, collectors.*) when running `pytest` from the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
