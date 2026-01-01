"""Sync state tracking for Taskwarrior-Reminders sync."""
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from .config import CONFIG, load_json, save_json


@dataclass
class SyncMapping:
    """Tracks sync relationship between TW task and Reminder."""
    uuid: str                    # Taskwarrior UUID
    reminder_id: str             # Apple Reminder calendarItemIdentifier
    tw_modified: str             # ISO timestamp of last known TW modification
    reminder_modified: str       # ISO timestamp of last known Reminder modification


class SyncState:
    """Manages sync state persistence."""

    def __init__(self, state_file: Optional[str] = None):
        self.state_file = Path(state_file or CONFIG["sync_state_file"])
        self._state = self._load()

    def _load(self) -> dict:
        """Load state from file."""
        data = load_json(self.state_file)
        if "version" not in data:
            data = {"version": 1, "mappings": {}, "last_sync": None}
        return data

    def _save(self) -> None:
        """Save state to file."""
        save_json(self.state_file, self._state)

    @property
    def last_sync(self) -> Optional[datetime]:
        """Get last sync timestamp."""
        ts = self._state.get("last_sync")
        return datetime.fromisoformat(ts) if ts else None

    def update_last_sync(self) -> None:
        """Update last sync to now."""
        self._state["last_sync"] = datetime.now().isoformat()
        self._save()

    def get_by_uuid(self, uuid: str) -> Optional[SyncMapping]:
        """Get mapping by Taskwarrior UUID."""
        data = self._state["mappings"].get(uuid)
        if data:
            return SyncMapping(**data)
        return None

    def get_by_reminder_id(self, reminder_id: str) -> Optional[SyncMapping]:
        """Get mapping by Reminder ID."""
        for uuid, data in self._state["mappings"].items():
            if data.get("reminder_id") == reminder_id:
                return SyncMapping(**data)
        return None

    def set_mapping(self, mapping: SyncMapping) -> None:
        """Create or update a mapping."""
        self._state["mappings"][mapping.uuid] = asdict(mapping)
        self._save()

    def remove_mapping(self, uuid: str) -> None:
        """Remove a mapping by UUID."""
        if uuid in self._state["mappings"]:
            del self._state["mappings"][uuid]
            self._save()

    def all_mappings(self) -> list[SyncMapping]:
        """Get all mappings."""
        return [SyncMapping(**data) for data in self._state["mappings"].values()]

    def known_reminder_ids(self) -> set[str]:
        """Get set of all known reminder IDs."""
        return {m.reminder_id for m in self.all_mappings()}
