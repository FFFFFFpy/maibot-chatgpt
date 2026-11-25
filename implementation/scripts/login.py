"""Run directly from a source checkout or extracted plugin directory."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maibot_chatgpt_provider.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
