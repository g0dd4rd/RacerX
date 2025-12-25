#!/bin/bash
# Install Audio Recorder for current user

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/audio-recorder"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
ACTION_ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/actions"

echo "Installing Audio Recorder..."

# Create directories
mkdir -p "$APP_DIR"
mkdir -p "$DESKTOP_DIR"
mkdir -p "$ICON_DIR"
mkdir -p "$ACTION_ICON_DIR"

# Copy icons
cp "$SCRIPT_DIR/data/icons/hicolor/scalable/apps/org.gnome.AudioRecorder.svg" "$ICON_DIR/"
cp "$SCRIPT_DIR/data/icons/hicolor/scalable/actions/"*.svg "$ACTION_ICON_DIR/" 2>/dev/null || true

# Copy application files
cp "$SCRIPT_DIR/audio_recorder.py" "$APP_DIR/"
cp -r "$SCRIPT_DIR/data" "$APP_DIR/"
cp -r "$SCRIPT_DIR/help" "$APP_DIR/" 2>/dev/null || true

# Make executable
chmod +x "$APP_DIR/audio_recorder.py"

# Create desktop file with correct path
cat > "$DESKTOP_DIR/org.gnome.AudioRecorder.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Audio Recorder
GenericName=Audio Recorder
Comment=Record and mix multiple audio tracks
Keywords=audio;record;recording;sound;music;podcast;voice;
Icon=org.gnome.AudioRecorder
Exec=python3 $APP_DIR/audio_recorder.py
Terminal=false
Categories=AudioVideo;Audio;Recorder;
StartupNotify=true
EOF

# Update desktop database
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo "Installation complete!"
echo "Audio Recorder is now available in your application menu."
echo ""
echo "To uninstall, run: $SCRIPT_DIR/uninstall.sh"

