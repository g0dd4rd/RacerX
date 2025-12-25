# Audio Recorder

A simple multi-track audio recorder for GNOME, built with GTK4 and libadwaita.

![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)
![GTK](https://img.shields.io/badge/GTK-4.0-green.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

## Features

- **Multi-track recording** — Record multiple audio tracks independently
- **Simultaneous playback** — Play all tracks together to preview your mix
- **True pause/resume** — Pause and resume playback without losing position
- **Track muting** — Mute individual tracks during playback
- **Input monitoring** — Hear your microphone input in real-time
- **Project management** — Save and load projects with all recordings
- **Import/Export** — Import WAV files and export individual tracks or mixed audio
- **Chromatic tuner** — Built-in tuner with high-contrast accessible design for tuning any instrument
- **Drum machine** — Pattern-based drum sequencer with FluidSynth MIDI sounds and custom time signatures
- **Keyboard shortcuts** — Full keyboard navigation with accessibility-friendly shortcuts
- **GNOME integration** — Native look and feel with libadwaita

## Requirements

- Python 3.10+
- GTK 4.0
- libadwaita 1.0
- GStreamer 1.0
- PipeWire (with `pw-record` and `pw-play` utilities)
- PyGObject
- NumPy (for tuner pitch detection)
- FluidSynth + General MIDI soundfont (for drum machine)

### Installation on Fedora

```bash
sudo dnf install gtk4 libadwaita python3-gobject gstreamer1 pipewire-utils python3-numpy fluidsynth fluid-soundfont-gm
```

### Installation on Ubuntu/Debian

```bash
sudo apt install libgtk-4-1 libadwaita-1-0 python3-gi gstreamer1.0-tools pipewire python3-numpy fluidsynth fluid-soundfont-gm
```

### Installation on Arch Linux

```bash
sudo pacman -S gtk4 libadwaita python-gobject gstreamer pipewire python-numpy fluidsynth soundfont-fluid
```

## Installation

### Flatpak (Recommended)

Build and install as a Flatpak:

```bash
cd flatpak
./build-flatpak.sh
```

Run the Flatpak:

```bash
flatpak run org.gnome.AudioRecorder
```

### Install as Desktop Application

To install Audio Recorder so it appears in your GNOME application menu:

```bash
./install.sh
```

This installs the application to `~/.local/share/audio-recorder/` and creates a desktop entry.

To uninstall:

```bash
./uninstall.sh
```

### Run Without Installing

```bash
python3 audio_recorder.py
```

Or make it executable:

```bash
chmod +x audio_recorder.py
./audio_recorder.py
```

## Keyboard Shortcuts

### Project
| Action | Shortcut |
|--------|----------|
| New Project | `Ctrl+N` |
| Open Project | `Ctrl+O` |
| Save Project | `Ctrl+S` |
| Save Project As | `Ctrl+Shift+S` |

### Tracks
| Action | Shortcut |
|--------|----------|
| Add Track | `Ctrl+T` |
| Import Audio | `Ctrl+I` |

### Playback
| Action | Shortcut |
|--------|----------|
| Play / Pause All | `Ctrl+Space` |
| Stop All | `Ctrl+.` |
| Toggle Monitoring | `Ctrl+L` |

### Tools
| Action | Shortcut |
|--------|----------|
| Chromatic Tuner | `Ctrl+U` |
| Drum Machine | `Ctrl+D` |

### Export
| Action | Shortcut |
|--------|----------|
| Export Tracks | `Ctrl+Shift+T` |
| Export Mixed | `Ctrl+Shift+X` |
| Export All | `Ctrl+Shift+A` |

### Help
| Action | Shortcut |
|--------|----------|
| Help | `F1` |
| Keyboard Shortcuts | `Ctrl+?` |

## Documentation

Full documentation is available in Yelp format. Press `F1` within the application or run:

```bash
yelp help/C/index.page
```

## Project Structure

```
audio_recorder.py    # Main application
data/
  ui/                # UI definition files
    window.blp       # Main window (Blueprint source)
    window.ui        # Main window (compiled XML)
    track-row.blp    # Track row widget (Blueprint source)
    track-row.ui     # Track row widget (compiled XML)
  org.gnome.AudioRecorder.desktop   # Desktop entry
  org.gnome.AudioRecorder.metainfo.xml  # AppStream metadata
flatpak/
  org.gnome.AudioRecorder.json  # Flatpak manifest
  build-flatpak.sh   # Flatpak build script
  audio-recorder     # Flatpak launcher script
help/
  C/                 # English documentation (Mallard format)
    index.page
    getting-started.page
    interface.page
    projects.page
    tracks.page
    recording.page
    playback.page
    import-export.page
    shortcuts.page
    troubleshooting.page
    tuner.page         # Chromatic tuner documentation
    drum-machine.page  # Drum machine documentation
install.sh           # Install script (adds to application menu)
uninstall.sh         # Uninstall script
build-ui.sh          # Script to compile Blueprint files
HELP.md              # Markdown documentation (fallback)
README.md            # This file
CHANGELOG.md         # Version history
```

## Development

### UI Files

The UI is defined using GTK Builder XML files (`.ui`), with Blueprint source files (`.blp`) provided for easier editing.

To edit the UI:
1. Edit the `.blp` files in `data/ui/`
2. Run `./build-ui.sh` to compile to `.ui` files
3. The application loads the `.ui` files at runtime

Blueprint compiler installation:
```bash
# Fedora
sudo dnf install blueprint-compiler

# Ubuntu/Debian  
sudo apt install blueprint-compiler

# Arch
sudo pacman -S blueprint-compiler
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed list of changes.

## License

This project is licensed under the GNU General Public License v3.0 - see the LICENSE file for details.

## Credits

Powered by:
- [GTK4](https://gtk.org/) — The GIMP Toolkit
- [libadwaita](https://gnome.pages.gitlab.gnome.org/libadwaita/) — Building blocks for modern GNOME apps
- [GStreamer](https://gstreamer.freedesktop.org/) — Open source multimedia framework
- [PipeWire](https://pipewire.org/) — Modern audio/video server
- [FluidSynth](https://www.fluidsynth.org/) — Real-time software synthesizer for MIDI
- [NumPy](https://numpy.org/) — Scientific computing for pitch detection

---

*100% vibe-coded.*
