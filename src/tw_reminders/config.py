"""Configuration for Taskwarrior-Reminders sync."""
from pathlib import Path
import json

HOME = Path.home()
# Derive project dir from this file's location (handles any install path)
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = HOME / ".local/share/tw-reminders"

# Create data directory if needed
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG = {
    "taskwarrior_data": str(HOME / ".task"),
    "sync_state_file": str(DATA_DIR / "sync_state.json"),
    "locations_file": str(DATA_DIR / "locations.json"),
    "swift_binary": str(PROJECT_DIR / ".build/release/tw-reminders-listener"),
    "default_list": "Reminders",
}


def load_json(path: Path) -> dict:
    """Load JSON file, return empty dict if not found."""
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_json(path: Path, data: dict) -> None:
    """Save dict as JSON file."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
