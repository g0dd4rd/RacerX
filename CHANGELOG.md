# Changelog

All notable changes to Audio Recorder are documented in this file, organized by date.

---

## 2025-12-08

### Added
- **Latency settings UI** — Configurable monitoring latency (32, 64, 128, 256, 512 samples) via dropdown menu next to monitoring toggle
- **Desktop integration** — `.desktop` file for GNOME application menu integration
- **Install/Uninstall scripts** — Easy installation to `~/.local/share/` with `install.sh` and `uninstall.sh`

### Changed
- **Audio mixing engine** — Replaced naive byte-level mixing with GStreamer `audiomixer` for professional quality exports

### Fixed
- **Hanging PipeWire processes** — All recording, playback, and monitoring processes are now properly terminated on application exit

### Architecture
- **Blueprint UI files** — Refactored to use Blueprint/GTK Builder for UI definitions
  - `data/ui/window.blp` — Main window layout
  - `data/ui/track-row.blp` — Track row widget
  - Compiled to `.ui` XML files at build time
- **Template-based widgets** — `AudioRecorderWindow` and `TrackRow` use `@Gtk.Template` decorators
- **Separation of concerns** — UI structure in Blueprint files, logic in Python
- **Build script** — `build-ui.sh` compiles Blueprint to UI files

---

## 2025-12-07

### Added
- **Keyboard shortcuts** — Full keyboard navigation support:
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
- **About dialog** — "About Audio Recorder" with app info, credits, and license
- **Keyboard shortcuts dialog** — View all shortcuts from the menu or with `Ctrl+?`
- **Help menu integration** — Opens Mallard documentation in Yelp
- **Mallard documentation** — Full user guide in Yelp-compatible format:
  - Getting started guide
  - Interface overview
  - Project management
  - Track operations
  - Recording guide
  - Playback controls
  - Import/Export guide
  - Keyboard shortcuts reference
  - Troubleshooting guide
- **Markdown documentation** — HELP.md as fallback

### Changed
- **Accessibility-friendly shortcuts** — All shortcuts avoid conflicts with GNOME accessibility features and screen readers (Orca)
- **Monitoring shortcut** — Changed from `Ctrl+Shift+M` to `Ctrl+L` to avoid potential conflicts
- **Export shortcuts** — Changed to `Ctrl+Shift+T/X/A` for better consistency

---

## 2025-12-06

### Added
- **Track renaming** — Click the edit button to rename tracks with a dialog
- **Track muting** — Mute individual tracks during playback while keeping them in sync
- **Global playback controls** — Play/Pause All and Stop All buttons in the header bar
- **True pause/resume** — Playback now resumes from exact position using GStreamer

### Changed
- **Playback engine** — Switched from `pw-play` subprocess to GStreamer for proper pause/resume support
- **Global play button** — Now toggles between play and pause states

### Fixed
- **Playback restart issue** — Fixed pause/resume starting from beginning instead of paused position

---

## 2025-12-05

### Added
- **Multi-track simultaneous playback** — Play all tracks at the same time to hear how they sound together
- **Auto-save prompt on exit** — Prompts to save unsaved changes when closing the application
- **Auto-load recent project** — Automatically opens the most recent project when launching
- **Proper unsaved changes tracking** — Accurately tracks modifications with a dirty flag

### Fixed
- **Save dialog appearing incorrectly** — Fixed issue where save dialog appeared even after saving
- **Projects nesting on save** — Fixed bug where saving to an existing project created nested folders
- **Deleted tracks persisting** — Fixed issue where deleted track audio files remained in project folder
- **Clean deleted tracks** — Deleted tracks are properly removed from the project folder on save

---

## 2025-12-04 — Initial Release

### Added
- Basic multi-track audio recording
- Track playback with PipeWire
- Project save/load functionality (`.atr` JSON format)
- Audio import (WAV files)
- Audio export (individual tracks and mixed)
- Input monitoring
- GTK4/libadwaita interface

---

## Technical Stack

- **GUI**: GTK 4.0, libadwaita 1.0, Blueprint
- **Audio Playback**: GStreamer (pause/resume support)
- **Audio Recording**: PipeWire (`pw-record`)
- **Project Format**: JSON (`.atr` extension)
- **Audio Format**: WAV files in project's `audio/` subdirectory
- **Configuration**: `~/.config/audio-recorder/config.json`
