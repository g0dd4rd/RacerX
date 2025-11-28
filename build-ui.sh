#!/bin/bash
# Build UI files from Blueprint sources
# Requires: blueprint-compiler

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$SCRIPT_DIR/data/ui"

if ! command -v blueprint-compiler &> /dev/null; then
    echo "Error: blueprint-compiler not found"
    echo "Install with: sudo dnf install blueprint-compiler"
    echo "          or: sudo apt install blueprint-compiler"
    exit 1
fi

echo "Compiling Blueprint files..."

for blp in "$UI_DIR"/*.blp; do
    if [ -f "$blp" ]; then
        name=$(basename "$blp" .blp)
        echo "  $name.blp -> $name.ui"
        blueprint-compiler compile "$blp" --output "$UI_DIR/$name.ui"
    fi
done

echo "Done!"

