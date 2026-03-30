#!/bin/bash
# Setup Recording Studio as a background service on macOS
# Run once: bash setup.sh

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.recorder.studio.plist"
PLIST_SRC="$APP_DIR/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"
PYTHON_PATH="$(which python3)"

echo "=== Recording Studio Setup ==="
echo ""
echo "App directory: $APP_DIR"
echo "Python:        $PYTHON_PATH"
echo ""

# Install dependencies
echo "Installing Python dependencies..."
pip3 install -r "$APP_DIR/requirements.txt"
echo ""

# Build the plist with correct paths
echo "Creating launchd service..."
mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s|__PYTHON_PATH__|$PYTHON_PATH|g" \
    -e "s|__APP_DIR__|$APP_DIR|g" \
    "$PLIST_SRC" > "$PLIST_DST"

# Unload if already loaded, then load
launchctl bootout gui/$(id -u) "$PLIST_DST" 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST_DST"

echo ""
echo "Done! Recording Studio is now running and will auto-start on login."
echo ""
echo "  Open:  http://localhost:5111"
echo "  Logs:  $APP_DIR/recorder.log"
echo ""
echo "Useful commands:"
echo "  Stop:    launchctl bootout gui/\$(id -u) $PLIST_DST"
echo "  Start:   launchctl bootstrap gui/\$(id -u) $PLIST_DST"
echo "  Uninstall: rm $PLIST_DST"
