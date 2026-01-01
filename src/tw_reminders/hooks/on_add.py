#!/usr/bin/env python3
"""
Taskwarrior on-add hook for Reminders sync.

Reads new task JSON from stdin, creates Reminder via Swift,
adds reminder_id to task, outputs modified task JSON.
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
LOCATIONS_FILE = Path.home() / ".local/share/tw-reminders/locations.json"


def load_locations() -> dict:
    """Load named locations from config."""
    if LOCATIONS_FILE.exists():
        data = json.loads(LOCATIONS_FILE.read_text())
        return data.get("locations", {})
    return {}


def lookup_location(loc_key: str) -> dict | None:
    """Look up location by shorthand key."""
    locations = load_locations()
    # Try exact match first
    if loc_key.lower() in locations:
        return locations[loc_key.lower()]
    # Try partial match
    for key, data in locations.items():
        if key.startswith(loc_key.lower()) or loc_key.lower() in data.get("name", "").lower():
            return data
    return None


def map_priority_to_reminder(priority: str | None) -> int:
    """Map Taskwarrior priority (H/M/L) to Reminder (1/5/9)."""
    if priority == "H":
        return 1
    elif priority == "M":
        return 5
    elif priority == "L":
        return 9
    return 0  # No priority


def create_reminder(task: dict) -> str | None:
    """Create reminder via Swift binary, return identifier."""
    reminder_data = {
        "title": task.get("description", ""),
        "list": task.get("project") or "Reminders",
        "priority": map_priority_to_reminder(task.get("priority")),
    }

    # Add due date if present
    if task.get("due"):
        reminder_data["due_date"] = task["due"]

    # Add notes from annotations
    annotations = task.get("annotations", [])
    if annotations:
        notes = "\n".join(a.get("description", "") for a in annotations)
        reminder_data["notes"] = notes

    # Add location if present (use "loc" shorthand with lookup)
    if task.get("loc"):
        loc_input = task["loc"]
        location = lookup_location(loc_input)

        if location:
            # Found in lookup - use stored coordinates
            reminder_data["location_name"] = location["name"]
            reminder_data["location_lat"] = location["lat"]
            reminder_data["location_lon"] = location["lon"]
            reminder_data["location_radius"] = location.get("radius", 100)
        else:
            # Not in lookup - use as literal name (no geofence without coords)
            reminder_data["location_name"] = loc_input
            # Check if coordinates were provided manually
            if task.get("location_lat"):
                reminder_data["location_lat"] = task["location_lat"]
            if task.get("location_lon"):
                reminder_data["location_lon"] = task["location_lon"]

    if task.get("location_radius"):
        reminder_data["location_radius"] = task["location_radius"]
    if task.get("location_trigger"):
        reminder_data["location_trigger"] = task["location_trigger"]

    try:
        result = subprocess.run(
            [str(SWIFT_BINARY), "create", json.dumps(reminder_data)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            response = json.loads(result.stdout)
            return response.get("identifier")
        else:
            print(f"Swift error: {result.stderr}", file=sys.stderr)
    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)

    return None


def update_sync_state(uuid: str, reminder_id: str, modified: str):
    """Update sync state file with new mapping."""
    SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if SYNC_STATE_FILE.exists():
        state = json.loads(SYNC_STATE_FILE.read_text())
    else:
        state = {"version": 1, "mappings": {}, "last_sync": None}

    state["mappings"][uuid] = {
        "uuid": uuid,
        "reminder_id": reminder_id,
        "tw_modified": modified,
        "reminder_modified": "",
    }

    SYNC_STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    # Read new task from stdin
    task = json.loads(sys.stdin.readline())

    # Skip if task already has reminder_id (synced from Reminders)
    if task.get("reminder_id"):
        print(json.dumps(task))
        return 0

    # Create reminder
    reminder_id = create_reminder(task)

    if reminder_id:
        # Add reminder_id to task
        task["reminder_id"] = reminder_id

        # Update sync state
        update_sync_state(
            task["uuid"],
            reminder_id,
            task.get("modified", task.get("entry", "")),
        )

    # Output modified task (required by Taskwarrior)
    print(json.dumps(task))
    return 0


if __name__ == "__main__":
    sys.exit(main())
