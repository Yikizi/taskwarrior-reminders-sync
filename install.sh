#!/bin/bash
# Install script for taskwarrior-reminders-sync
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.tw-reminders-sync.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "=== Taskwarrior ↔ Apple Reminders Sync Installer ==="
echo ""

# 1. Build Swift binary
echo "Building Swift binary..."
(cd "$SCRIPT_DIR" && swift build -c release)

# 2. Set up Python environment
echo "Setting up Python environment..."
if command -v uv &> /dev/null; then
    # Prefer uv (faster, no pip needed)
    (cd "$SCRIPT_DIR" && uv sync)
else
    # Fallback to standard venv + pip
    if [ ! -d "$SCRIPT_DIR/.venv" ]; then
        python3 -m venv "$SCRIPT_DIR/.venv"
    fi
    "$SCRIPT_DIR/.venv/bin/pip" install -q -e "$SCRIPT_DIR"
fi

# 3. Create data directory
echo "Creating data directory..."
mkdir -p "$HOME/.local/share/tw-reminders"

# 4. Install launchd plist (expand $HOME)
echo "Installing launchd service..."
sed "s|\$HOME|$HOME|g" "$SCRIPT_DIR/config/com.tw-reminders-sync.plist.template" > "$PLIST_DEST"

# 5. Install Taskwarrior hooks
echo "Installing Taskwarrior hooks..."
mkdir -p "$HOME/.task/hooks"

HOOK_ADD="$HOME/.task/hooks/on-add-reminders.py"
HOOK_MODIFY="$HOME/.task/hooks/on-modify-reminders.py"

ln -sf "$SCRIPT_DIR/src/tw_reminders/hooks/on_add.py" "$HOOK_ADD"
ln -sf "$SCRIPT_DIR/src/tw_reminders/hooks/on_modify.py" "$HOOK_MODIFY"
chmod +x "$HOOK_ADD" "$HOOK_MODIFY"

# 6. Create example locations file if it doesn't exist
LOCATIONS_FILE="$HOME/.local/share/tw-reminders/locations.json"
if [ ! -f "$LOCATIONS_FILE" ]; then
    echo "Creating example locations file..."
    cat > "$LOCATIONS_FILE" << 'EOF'
{
  "locations": {
    "home": {
      "name": "Home",
      "lat": 0.0,
      "lon": 0.0,
      "radius": 100
    }
  }
}
EOF
    echo "  → Edit $LOCATIONS_FILE to add your locations"
fi

# 7. Load launchd service
echo "Starting listener service..."
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo ""
echo "=== Installation complete! ==="
echo ""
echo "Next steps:"
echo "  1. Add UDAs to ~/.taskrc (see README.md)"
echo "  2. Edit ~/.local/share/tw-reminders/locations.json with your locations"
echo "  3. Test with: task add \"Test task\" loc:home"
echo ""
echo "View logs: tail -f ~/.local/share/tw-reminders/listener.log"
