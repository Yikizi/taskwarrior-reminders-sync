#!/usr/bin/env python3
"""
Sync from Apple Reminders to Taskwarrior.

Called by Swift listener when EKEventStoreChanged fires.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from tasklib import TaskWarrior, Task

# Handle both module and standalone execution
if __name__ == "__main__":
    # Add parent to path for standalone execution
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tw_reminders.config import CONFIG
    from tw_reminders.sync_state import SyncState, SyncMapping
else:
    from .config import CONFIG
    from .sync_state import SyncState, SyncMapping


def fetch_reminders(pending_only: bool = True) -> list[dict]:
    """Fetch reminders via Swift binary."""
    cmd = [CONFIG["swift_binary"], "export"]
    if pending_only:
        cmd.append("--pending-only")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error fetching reminders: {result.stderr}", file=sys.stderr)
        return []
    return json.loads(result.stdout)


def map_priority_from_reminder(priority: int) -> str | None:
    """Map Reminder priority (1/5/9) to Taskwarrior (H/M/L)."""
    if priority == 1:
        return "H"
    elif priority == 5:
        return "M"
    elif priority == 9:
        return "L"
    return None


def parse_date(iso_string: str | None) -> datetime | None:
    """Parse ISO date string to datetime."""
    if not iso_string:
        return None
    try:
        # Handle both formats: with and without fractional seconds
        if "." in iso_string:
            return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except ValueError:
        return None


def sync_reminder_to_task(
    reminder: dict, tw: TaskWarrior, state: SyncState
) -> None:
    """Sync a single reminder to Taskwarrior."""
    reminder_id = reminder["identifier"]
    mapping = state.get_by_reminder_id(reminder_id)

    if mapping:
        # Existing mapping - check if we need to update
        task = tw.tasks.get(uuid=mapping.uuid)
        if not task:
            # Task was deleted in TW, remove mapping
            state.remove_mapping(mapping.uuid)
            return

        # Compare modification times for conflict detection
        reminder_modified = reminder.get("modificationDate", "")
        if reminder_modified <= mapping.reminder_modified:
            # Reminder hasn't changed since last sync
            return

        # Update task from reminder
        update_task_from_reminder(task, reminder)
        task.save()

        # Update mapping
        mapping.reminder_modified = reminder_modified
        mapping.tw_modified = task["modified"].isoformat() if task["modified"] else ""
        state.set_mapping(mapping)

    else:
        # New reminder - create task
        if reminder.get("isCompleted"):
            # Skip completed reminders we don't know about
            return

        task = Task(tw)
        task["description"] = reminder["title"]
        task["project"] = reminder.get("list") if reminder.get("list") != "Reminders" else None

        due = parse_date(reminder.get("dueDate"))
        if due:
            task["due"] = due

        priority = map_priority_from_reminder(reminder.get("priority", 0))
        if priority:
            task["priority"] = priority

        if reminder.get("notes"):
            task["annotations"] = [{"description": reminder["notes"]}]

        # Store reminder_id as UDA
        task["reminder_id"] = reminder_id

        # Handle location if present
        if reminder.get("hasLocation"):
            if reminder.get("locationName"):
                task["loc"] = reminder["locationName"]
            if reminder.get("locationLatitude"):
                task["location_lat"] = reminder["locationLatitude"]
            if reminder.get("locationLongitude"):
                task["location_lon"] = reminder["locationLongitude"]

        task.save()

        # Create mapping
        state.set_mapping(SyncMapping(
            uuid=str(task["uuid"]),
            reminder_id=reminder_id,
            tw_modified=task["modified"].isoformat() if task["modified"] else "",
            reminder_modified=reminder.get("modificationDate", ""),
        ))

        print(f"Created task: {task['description']}")


def update_task_from_reminder(task: Task, reminder: dict) -> None:
    """Update existing task from reminder data."""
    task["description"] = reminder["title"]

    # Update project (list)
    list_name = reminder.get("list")
    if list_name and list_name != "Reminders":
        task["project"] = list_name
    elif list_name == "Reminders":
        task["project"] = None

    # Update due date
    due = parse_date(reminder.get("dueDate"))
    task["due"] = due

    # Update priority
    priority = map_priority_from_reminder(reminder.get("priority", 0))
    task["priority"] = priority

    # Update completion status
    if reminder.get("isCompleted") and task["status"] != "completed":
        task.done()
    elif not reminder.get("isCompleted") and task["status"] == "completed":
        task["status"] = "pending"

    print(f"Updated task: {task['description']}")


def check_deleted_reminders(
    reminders: list[dict], tw: TaskWarrior, state: SyncState
) -> None:
    """Check for reminders that were deleted and mark tasks accordingly."""
    current_reminder_ids = {r["identifier"] for r in reminders}

    for mapping in state.all_mappings():
        if mapping.reminder_id not in current_reminder_ids:
            # Reminder was deleted
            try:
                task = tw.tasks.get(uuid=mapping.uuid)
                if task and task["status"] != "deleted":
                    print(f"Reminder deleted, deleting task: {task['description']}")
                    task.delete()
            except Exception:
                pass
            state.remove_mapping(mapping.uuid)


def main():
    """Main sync entry point."""
    import fcntl

    lock_file = Path(CONFIG["sync_state_file"]).parent / ".sync.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    # Use file lock to prevent concurrent syncs
    with open(lock_file, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"[{datetime.now()}] Another sync in progress, skipping")
            return

        print(f"[{datetime.now()}] Starting Reminders → TW sync...")

        tw = TaskWarrior(data_location=CONFIG["taskwarrior_data"])
        state = SyncState()

        reminders = fetch_reminders()
        print(f"Fetched {len(reminders)} reminders")

        for reminder in reminders:
            try:
                sync_reminder_to_task(reminder, tw, state)
            except Exception as e:
                print(f"Error syncing reminder {reminder.get('title')}: {e}", file=sys.stderr)

        check_deleted_reminders(reminders, tw, state)
        state.update_last_sync()

        print(f"[{datetime.now()}] Sync complete")

        fcntl.flock(f, fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
