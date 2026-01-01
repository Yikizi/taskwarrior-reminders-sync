#!/usr/bin/env python3
"""
Taskwarrior on-modify hook for Reminders sync.

Reads original and modified task JSON from stdin,
updates corresponding Reminder via Swift if needed.
"""
import json
import subprocess
import sys
from pathlib import Path

# Configuration - derive paths from script location (handles symlinks)
SCRIPT_PATH = Path(__file__).resolve()  # Resolve symlink to actual location
REPO_ROOT = SCRIPT_PATH.parent.parent.parent.parent  # src/tw_reminders/hooks -> repo root
SWIFT_BINARY = REPO_ROOT / ".build/release/tw-reminders-listener"
SYNC_STATE_FILE = Path.home() / ".local/share/tw-reminders/sync_state.json"


def map_priority_to_reminder(priority: str | None) -> int:
    """Map Taskwarrior priority (H/M/L) to Reminder (1/5/9)."""
    if priority == "H":
        return 1
    elif priority == "M":
        return 5
    elif priority == "L":
        return 9
    return 0


def get_reminder_id(uuid: str) -> str | None:
    """Get reminder_id from sync state."""
    if not SYNC_STATE_FILE.exists():
        return None
    state = json.loads(SYNC_STATE_FILE.read_text())
    mapping = state.get("mappings", {}).get(uuid)
    return mapping.get("reminder_id") if mapping else None


def update_reminder(reminder_id: str, task: dict, original: dict) -> bool:
    """Update reminder via Swift binary."""
    update_data = {"identifier": reminder_id}

    # Check what changed and include those fields
    if task.get("description") != original.get("description"):
        update_data["title"] = task.get("description", "")

    if task.get("priority") != original.get("priority"):
        update_data["priority"] = map_priority_to_reminder(task.get("priority"))

    if task.get("due") != original.get("due"):
        update_data["due_date"] = task.get("due") or ""

    # Check completion status
    if task.get("status") == "completed" and original.get("status") != "completed":
        update_data["is_completed"] = True
    elif task.get("status") != "completed" and original.get("status") == "completed":
        update_data["is_completed"] = False

    # Only update if there are changes beyond the identifier
    if len(update_data) <= 1:
        return True  # No changes to sync

    try:
        result = subprocess.run(
            [str(SWIFT_BINARY), "update", json.dumps(update_data)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            print(f"Swift error: {result.stderr}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        return False


def delete_reminder(reminder_id: str) -> bool:
    """Delete reminder via Swift binary."""
    try:
        result = subprocess.run(
            [str(SWIFT_BINARY), "delete", reminder_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        return False


def remove_from_sync_state(uuid: str):
    """Remove mapping from sync state."""
    if not SYNC_STATE_FILE.exists():
        return
    state = json.loads(SYNC_STATE_FILE.read_text())
    if uuid in state.get("mappings", {}):
        del state["mappings"][uuid]
        SYNC_STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    # Read original and modified task from stdin
    original = json.loads(sys.stdin.readline())
    modified = json.loads(sys.stdin.readline())

    # Get reminder_id (from task or sync state)
    reminder_id = modified.get("reminder_id") or get_reminder_id(modified["uuid"])

    if reminder_id:
        # Check if task was deleted
        if modified.get("status") == "deleted":
            delete_reminder(reminder_id)
            remove_from_sync_state(modified["uuid"])
        else:
            # Update reminder with changes
            update_reminder(reminder_id, modified, original)

    # Output modified task (required by Taskwarrior)
    print(json.dumps(modified))
    return 0


if __name__ == "__main__":
    sys.exit(main())
