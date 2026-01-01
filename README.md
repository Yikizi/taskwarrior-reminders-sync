# Taskwarrior ↔ Apple Reminders Sync

Bidirectional, event-driven sync between Taskwarrior CLI and Apple Reminders (syncs to iPhone automatically via iCloud).

## Quick Start

```bash
# Add a task (instantly appears in Reminders app + iPhone)
task add "Buy groceries" project:Shopping

# Add with due date (creates time-based alert)
task add "Call dentist" due:tomorrow+14h

# Add with location (creates geofenced "When I Arrive" alert)
task add "Pick up package" loc:grocery

# Complete task (marks done in Reminders too)
task 1 done
```

## How It Works

```
┌─────────────┐     iCloud      ┌─────────────┐
│   iPhone    │◄───────────────►│ Mac Reminders│
└─────────────┘                 └──────┬──────┘
                                       │ EventKit
                                       ▼
                               ┌───────────────┐
                               │ Swift Listener │ (event-driven, no polling)
                               └───────┬───────┘
                                       │ triggers
                                       ▼
                               ┌───────────────┐
                               │  Python Sync  │
                               └───────┬───────┘
                                       │
                                       ▼
┌─────────────┐    hooks       ┌─────────────┐
│ Taskwarrior │◄──────────────►│  Swift CLI  │
└─────────────┘                └─────────────┘
```

**Key features:**
- **Event-driven**: No polling. Swift listener wakes only when Reminders changes.
- **Instant sync**: Changes appear on iPhone within seconds (iCloud speed).
- **Bidirectional**: Edit on either side, changes sync both ways.
- **Location geofencing**: "Remind me when I arrive at..." works!

---

## Installation

### Prerequisites
- macOS 14+ (Sonoma or later)
- Xcode Command Line Tools (`xcode-select --install`)
- Python 3.11+
- Taskwarrior (`brew install task`)

### Quick Install

```bash
# Clone the repo (anywhere you like)
git clone https://github.com/YOUR_USERNAME/taskwarrior-reminders-sync.git
cd taskwarrior-reminders-sync

# Run installer
./install.sh
```

The installer will:
1. Build the Swift binary
2. Set up Python virtual environment
3. Install Taskwarrior hooks (symlinks)
4. Configure and start the launchd service
5. Create example locations file

### Add UDAs to ~/.taskrc

Add these lines to your `~/.taskrc`:

```
# Reminders sync UDAs
uda.reminder_id.type=string
uda.reminder_id.label=Reminder ID

uda.loc.type=string
uda.loc.label=Location

uda.location_lat.type=numeric
uda.location_lat.label=Latitude

uda.location_lon.type=numeric
uda.location_lon.label=Longitude

uda.location_radius.type=numeric
uda.location_radius.label=Radius (m)

uda.location_trigger.type=string
uda.location_trigger.label=Trigger
uda.location_trigger.values=arriving,leaving,
```

### Configure Locations

Edit `~/.local/share/tw-reminders/locations.json` to add your locations:

```bash
nvim ~/.local/share/tw-reminders/locations.json
```

---

## Adding Tasks

### Basic Task
```bash
task add "Task description"
```
Creates a reminder in the default "Reminders" list.

### With Project (→ Reminders List)
```bash
task add "Buy milk" project:Shopping
task add "Fix bug" project:Work
```
The `project` maps to Reminders list. If the list doesn't exist, uses default.

### With Priority
```bash
task add "Urgent!" priority:H      # High (red ! in Reminders)
task add "Normal" priority:M       # Medium (orange !!)
task add "Low priority" priority:L # Low (yellow !!!)
```

**Priority mapping:**
| Taskwarrior | Reminders | Urgency boost |
|-------------|-----------|---------------|
| `H` (High) | Priority 1 | +6.0 |
| `M` (Medium) | Priority 5 | +3.9 |
| `L` (Low) | Priority 9 | +1.8 |

### With Due Date (Time Alert)
```bash
task add "Meeting prep" due:tomorrow
task add "Submit report" due:friday
task add "Call at 2pm" due:today+14h
task add "Specific time" due:2025-02-15T09:00
```

**Due date creates an alert** - you'll get a notification at the specified time on all devices.

### With Location (Geofenced Alert)
```bash
# Using saved location shortcuts
task add "Get groceries" loc:grocery
task add "Start work" loc:work
task add "Remember when home" loc:home

# Using full location name (if in your saved locations)
task add "Shopping" loc:mall
```

**Location creates a "When I Arrive" geofence** - you'll get a notification when you physically arrive at that location.

### Combined Example
```bash
task add "Pick up prescription" project:Errands priority:H due:tomorrow loc:pharmacy
```
This creates a high-priority task that:
- Appears in the "Errands" list
- Has a time alert for tomorrow
- Has a geofence alert for the pharmacy location

---

## Saved Locations

Your locations are stored in `~/.local/share/tw-reminders/locations.json`:

```json
{
  "locations": {
    "home": {
      "name": "123 Main Street",
      "lat": 37.7749,
      "lon": -122.4194,
      "radius": 100
    },
    "grocery": {
      "name": "Corner Market",
      "lat": 37.7755,
      "lon": -122.4180,
      "radius": 150
    }
  }
}
```

### Adding New Locations

**Option 1: Edit the JSON directly**
```bash
nvim ~/.local/share/tw-reminders/locations.json
```

**Option 2: Export from existing Reminders**
```bash
# See all locations from your location-based reminders
~/taskwarrior-reminders-sync/.build/release/tw-reminders-listener export-locations
```

**Option 3: Find coordinates**
1. Open Apple Maps, find location
2. Right-click → "Copy Coordinates"
3. Add to locations.json

### Example Locations

| Shortcut | Name | Use Case |
|----------|------|----------|
| `home` | My Home Address | Home tasks |
| `grocery` | Local Grocery Store | Shopping |
| `work` | Office Building | Work tasks |
| `gym` | Fitness Center | Exercise reminders |

**Partial matching works:** `loc:gro` → grocery, `loc:wo` → work

> **Note**: Edit `~/.local/share/tw-reminders/locations.json` to add your own locations.

---

## Modifying Tasks

```bash
# Change description
task 1 modify "New description"

# Change priority
task 1 modify priority:H

# Add/change due date
task 1 modify due:monday

# Change project (moves to different Reminders list)
task 1 modify project:Work

# Remove due date
task 1 modify due:
```

All modifications sync to Reminders automatically.

---

## Completing & Deleting

```bash
# Mark complete (syncs to Reminders)
task 1 done

# Delete task (removes from Reminders too)
task 1 delete

# Undo completion
task 1 modify status:pending
```

---

## Viewing Tasks

```bash
# List all pending tasks
task list

# List by project
task project:Shopping list

# List high priority
task priority:H list

# List tasks with locations
task loc.any: list

# Show task details (including reminder_id)
task 1 info

# Export as JSON (shows all UDA fields)
task 1 export
```

---

## UDA Fields Reference

| Field | Type | Description | User-editable |
|-------|------|-------------|---------------|
| `loc` | string | Location shortcut or name | ✅ Yes |
| `location_lat` | numeric | Latitude (auto-filled) | ⚠️ Usually auto |
| `location_lon` | numeric | Longitude (auto-filled) | ⚠️ Usually auto |
| `location_radius` | numeric | Geofence radius in meters | ✅ Yes |
| `location_trigger` | string | "arriving" or "leaving" | ✅ Yes |
| `reminder_id` | string | Internal sync ID | ❌ Don't edit |

### Location Trigger

By default, location reminders trigger on "arriving". To trigger when leaving:

```bash
task add "Don't forget keys" loc:home location_trigger:leaving
```

---

## Syncing from iPhone

When you create or edit a reminder on your iPhone:

1. iCloud syncs to Mac Reminders (automatic, ~seconds)
2. Swift listener detects `EKEventStoreChanged` event
3. Python sync runs automatically
4. Task appears/updates in Taskwarrior

**No action needed** - it's fully automatic!

### Manual Sync

If you want to force a sync:

```bash
# Run sync manually
~/.venv/bin/python -m tw_reminders.sync_from_reminders

# Or via the project directory
cd ~/taskwarrior-reminders-sync
.venv/bin/python -m tw_reminders.sync_from_reminders
```

---

## Service Management

The Swift listener runs as a launchd service (auto-starts on login).

```bash
# Check if running
launchctl list | grep tw-reminders

# View logs
tail -f ~/.local/share/tw-reminders/listener.log
tail -f ~/.local/share/tw-reminders/listener.error.log

# Restart service
launchctl unload ~/Library/LaunchAgents/com.tw-reminders-sync.plist
launchctl load ~/Library/LaunchAgents/com.tw-reminders-sync.plist

# Stop service
launchctl unload ~/Library/LaunchAgents/com.tw-reminders-sync.plist

# Start service
launchctl load ~/Library/LaunchAgents/com.tw-reminders-sync.plist
```

---

## Swift CLI Reference

The Swift binary can be used directly for advanced operations:

```bash
SWIFT=~/taskwarrior-reminders-sync/.build/release/tw-reminders-listener

# Export all reminders as JSON
$SWIFT export

# Export only pending (incomplete) reminders
$SWIFT export --pending-only

# Export unique locations from your reminders
$SWIFT export-locations

# Create a reminder directly
$SWIFT create '{"title": "Test", "list": "Reminders", "priority": 5}'

# Update a reminder by ID
$SWIFT update '{"identifier": "ABC-123", "title": "Updated"}'

# Delete a reminder by ID
$SWIFT delete "ABC-123"

# Start listener (usually runs via launchd)
$SWIFT listen
```

---

## Troubleshooting

### Task created but no reminder appears
1. Check hooks are executable: `ls -la ~/.task/hooks/`
2. Check Swift binary exists: `ls ~/taskwarrior-reminders-sync/.build/release/`
3. Test hook manually: `echo '{"description":"test","uuid":"123"}' | ~/.task/hooks/on-add-reminders.py`

### Reminder created on iPhone but no task
1. Check listener is running: `launchctl list | grep tw-reminders`
2. Check logs: `cat ~/.local/share/tw-reminders/listener.error.log`
3. Run manual sync: `cd ~/taskwarrior-reminders-sync && .venv/bin/python -m tw_reminders.sync_from_reminders`

### Location not working
1. Verify location is in `~/.local/share/tw-reminders/locations.json`
2. Check coordinates are valid (lat between -90 and 90, lon between -180 and 180)
3. Ensure Location Services are enabled for Reminders on iPhone

### Rebuild after code changes
```bash
cd ~/taskwarrior-reminders-sync
swift build -c release
launchctl unload ~/Library/LaunchAgents/com.tw-reminders-sync.plist
launchctl load ~/Library/LaunchAgents/com.tw-reminders-sync.plist
```

---

## File Locations

| File | Purpose |
|------|---------|
| `~/taskwarrior-reminders-sync/` | Main project directory |
| `~/.task/hooks/on-add-reminders.py` | Taskwarrior on-add hook |
| `~/.task/hooks/on-modify-reminders.py` | Taskwarrior on-modify hook |
| `~/.local/share/tw-reminders/sync_state.json` | Sync state (UUID↔reminder mappings) |
| `~/.local/share/tw-reminders/locations.json` | Saved locations for shortcuts |
| `~/.local/share/tw-reminders/listener.log` | Listener stdout log |
| `~/.local/share/tw-reminders/listener.error.log` | Listener stderr log |
| `~/Library/LaunchAgents/com.tw-reminders-sync.plist` | launchd service config |
| `~/.taskrc` | Taskwarrior config (includes UDA definitions) |

---

## Examples

### Daily Workflow
```bash
# Morning: Add today's tasks
task add "Team standup" due:9am project:Work
task add "Review PR" due:11am project:Work priority:H
task add "Lunch with Alex" due:12pm

# With location triggers
task add "Buy coffee beans" loc:grocery
task add "Return library book" loc:library

# Check what's due
task due:today list

# Complete tasks throughout day
task 1 done
task 2 done
```

### Shopping List
```bash
task add "Milk" project:Shopping loc:grocery
task add "Bread" project:Shopping loc:grocery
task add "Eggs" project:Shopping loc:grocery

# View shopping list
task project:Shopping list
```

### Project Planning
```bash
task add "Research phase" project:Thesis due:friday
task add "Write outline" project:Thesis due:next-week
task add "First draft" project:Thesis due:month priority:H
```

---

## Architecture

**Components:**
1. **Swift binary** (`tw-reminders-listener`) - EventKit integration, CRUD operations
2. **Python package** (`tw_reminders`) - Sync logic, Taskwarrior integration via tasklib
3. **Taskwarrior hooks** - Trigger sync on task add/modify
4. **launchd service** - Keeps listener running for iPhone→TW sync

**Data flow:**
- **TW → Reminders**: Hook catches task → calls Swift `create`/`update`/`delete`
- **Reminders → TW**: EKEventStoreChanged → Swift listener → Python sync → tasklib

**No polling** - Everything is event-driven for minimal battery impact.
