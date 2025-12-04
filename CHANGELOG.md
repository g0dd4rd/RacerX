# Changelog

All notable changes to Audio Recorder are documented in this file.

## [1.0.0] - 2024

### Added

#### Core Features
- **Multi-track simultaneous playback** — Play all tracks at the same time to hear how they sound together
- **True pause/resume** — Playback now resumes from the exact position where you paused, using GStreamer for audio playback
- **Track muting** — Mute individual tracks during playback while keeping them in sync
- **Track renaming** — Click the edit button to rename tracks with a dialog
- **Global playback controls** — Play/Pause All and Stop All buttons in the header bar

#### Project Management
- **Auto-save prompt on exit** — Prompts to save unsaved changes when closing the application
- **Auto-load recent project** — Automatically opens the most recent project when launching
- **Proper unsaved changes tracking** — Accurately tracks modifications with a dirty flag
- **Fixed project saving** — Projects no longer nest inside existing project folders when re-saving
- **Clean deleted tracks** — Deleted tracks are properly removed from the project folder on save

#### Keyboard Shortcuts
- `Ctrl+N` — New Project
- `Ctrl+O` — Open Project
- `Ctrl+S` — Save Project
- `Ctrl+Shift+S` — Save Project As
- `Ctrl+T` — Add Track
- `Ctrl+I` — Import Audio
- `Ctrl+Space` — Play/Pause All
- `Ctrl+.` — Stop All
- `Ctrl+L` — Toggle Monitoring
- `Ctrl+Shift+T` — Export Tracks
- `Ctrl+Shift+X` — Export Mixed
- `Ctrl+Shift+A` — Export All
- `F1` — Help
- `Ctrl+?` — Keyboard Shortcuts

#### Accessibility
- **Accessibility-friendly shortcuts** — All shortcuts avoid conflicts with GNOME accessibility features and screen readers (Orca)
- **Changed `Space` to `Ctrl+Space`** — Prevents conflict with widget activation, essential for keyboard navigation

#### User Interface
- **About dialog** — Added "About Audio Recorder" with app info, credits, and license
- **Keyboard shortcuts dialog** — View all shortcuts from the menu or with `Ctrl+?`
- **Help menu integration** — Added Help menu item that opens documentation

#### Documentation
- **Mallard documentation** — Full user guide in Yelp-compatible format with:
  - Getting started guide
  - Interface overview
  - Project management
  - Track operations
  - Recording guide
  - Playback controls
  - Import/Export guide
  - Keyboard shortcuts reference
  - Troubleshooting guide
- **Markdown documentation** — HELP.md as fallback documentation

### Changed

- **Playback engine** — Switched from `pw-play` subprocess to GStreamer for proper pause/resume support
- **Audio mixing** — Replaced naive byte-level mixing with GStreamer `audiomixer` for professional quality exports
- **Global play button** — Now toggles between play and pause states
- **Monitoring shortcut** — Changed from `Ctrl+Shift+M` to `Ctrl+L` to avoid potential conflicts
- **Export shortcuts** — Changed to `Ctrl+Shift+T/X/A` for better consistency

### Fixed

- **Save dialog appearing incorrectly** — Fixed issue where save dialog appeared even after saving
- **Projects nesting on save** — Fixed bug where saving to an existing project created nested folders
- **Deleted tracks persisting** — Fixed issue where deleted track audio files remained in project folder
- **Playback restart issue** — Fixed pause/resume starting from beginning instead of paused position
- **Hanging PipeWire processes** — All recording, playback, and monitoring processes are now properly terminated on application exit

### Architecture

- **Blueprint UI files** — Refactored to use Blueprint/GTK Builder for UI definitions
  - `data/ui/window.blp` — Main window layout
  - `data/ui/track-row.blp` — Track row widget
  - Compiled to `.ui` XML files at build time
- **Template-based widgets** — `AudioRecorderWindow` and `TrackRow` use `@Gtk.Template` decorators
- **Separation of concerns** — UI structure in Blueprint files, logic in Python
- **Build script** — `build-ui.sh` compiles Blueprint to UI files

### Technical Details

- Built with GTK 4.0 and libadwaita 1.0
- Uses GStreamer for audio playback with pause/resume support
- Uses PipeWire (`pw-record`) for audio recording
- Uses Blueprint for UI definitions (GNOME standard)
- Project files use JSON format (`.atr` extension)
- Audio stored as WAV files in project's `audio/` subdirectory
- Configuration stored in `~/.config/audio-recorder/config.json`

---

## [0.1.0] - Initial Version

### Added
- Basic multi-track audio recording
- Track playback with PipeWire
- Project save/load functionality
- Audio import (WAV)
- Audio export (individual tracks and mixed)
- Input monitoring
- Basic GTK4/libadwaita interface

