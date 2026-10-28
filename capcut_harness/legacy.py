"""Load the retained standalone cards helper without duplicating its rules."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]/'skills/capcut-cinematic-cards/scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import cards  # noqa: E402
