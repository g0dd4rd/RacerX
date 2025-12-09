#!/bin/bash
# Uninstall Audio Recorder

set -e

APP_DIR="$HOME/.local/share/audio-recorder"
DESKTOP_FILE="$HOME/.local/share/applications/org.gnome.AudioRecorder.desktop"
ICON_FILE="$HOME/.local/share/icons/hicolor/scalable/apps/org.gnome.AudioRecorder.svg"

echo "Uninstalling Audio Recorder..."

# Remove application files
rm -rf "$APP_DIR"

# Remove desktop file
rm -f "$DESKTOP_FILE"

# Remove icon
rm -f "$ICON_FILE"

# Update desktop database
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

# Update icon cache
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Uninstallation complete!"

