#!/bin/bash
# Build the Flatpak package for Audio Recorder

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RUNTIME_VERSION="48"

echo "Building Audio Recorder Flatpak..."

# Add Flathub remote if not present
echo "Ensuring Flathub remote is configured..."
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# Install Flatpak SDK and runtime if not present
echo "Installing GNOME ${RUNTIME_VERSION} runtime and SDK (this may take a while)..."
if ! flatpak info --user org.gnome.Platform//${RUNTIME_VERSION} &>/dev/null; then
    flatpak install --user -y flathub org.gnome.Platform//${RUNTIME_VERSION}
fi

if ! flatpak info --user org.gnome.Sdk//${RUNTIME_VERSION} &>/dev/null; then
    flatpak install --user -y flathub org.gnome.Sdk//${RUNTIME_VERSION}
fi

# Compile Blueprint files before building (requires blueprint-compiler on host)
echo "Compiling Blueprint UI files..."
cd "$PROJECT_DIR"
if command -v blueprint-compiler &>/dev/null; then
    ./build-ui.sh
else
    echo "Warning: blueprint-compiler not found on host."
    echo "Make sure data/ui/*.ui files are up to date."
fi

# Build the Flatpak
echo "Building Flatpak application..."
flatpak-builder --user --install --force-clean build-dir flatpak/org.gnome.AudioRecorder.json

echo ""
echo "Build complete!"
echo "Run with: flatpak run org.gnome.AudioRecorder"

