#!/bin/bash
# Build the Flatpak package for Audio Recorder

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building Audio Recorder Flatpak..."

# Install Flatpak SDK and runtime if not present
echo "Checking for GNOME runtime..."
flatpak install --user -y flathub org.gnome.Platform//46 org.gnome.Sdk//46 2>/dev/null || true

# Build the Flatpak
cd "$PROJECT_DIR"
flatpak-builder --user --install --force-clean build-dir flatpak/org.gnome.AudioRecorder.json

echo ""
echo "Build complete!"
echo "Run with: flatpak run org.gnome.AudioRecorder"

