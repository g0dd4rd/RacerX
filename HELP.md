# Audio Recorder User Guide

A simple multi-track audio recorder for GNOME, built with GTK4 and libadwaita.

## Table of Contents

- [Getting Started](#getting-started)
- [Interface Overview](#interface-overview)
- [Working with Projects](#working-with-projects)
- [Working with Tracks](#working-with-tracks)
- [Recording Audio](#recording-audio)
- [Playback Controls](#playback-controls)
- [Input Monitoring](#input-monitoring)
- [Importing Audio](#importing-audio)
- [Exporting Audio](#exporting-audio)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Troubleshooting](#troubleshooting)

---

## Getting Started

### Requirements

- GNOME desktop environment (or GTK4/libadwaita compatible)
- PipeWire audio system with `pw-record` and `pw-play` utilities
- GStreamer 1.0 for playback
- Python 3 with PyGObject

### Launching the Application

Run the application from the terminal:

```bash
./audio_recorder.py
```

Or make it executable and run:

```bash
chmod +x audio_recorder.py
./audio_recorder.py
```

---

## Interface Overview

### Header Bar

From left to right:

| Element | Description |
|---------|-------------|
| **+ (Add Track)** | Creates a new empty track |
| **▶ (Play/Pause)** | Plays or pauses all tracks simultaneously |
| **⏹ (Stop)** | Stops all playback and resets to beginning |
| **🔊 (Monitor)** | Toggles live input monitoring |
| **☰ (Menu)** | Opens the main application menu |

### Track List

Each track row displays:

- **✏️ Edit button** (left) - Click to rename the track
- **Track name** - The name of the track
- **Status** - Shows Ready, Recording, Playing, Paused, or Muted state
- **Control buttons** (right):
  - 🔴 **Record** - Start recording on this track
  - ⏹ **Stop** - Stop recording
  - ▶/⏸ **Play/Pause** - Play or pause this track
  - 🔊/🔇 **Mute** - Mute or unmute this track
  - 🗑️ **Delete** - Remove this track

---

## Working with Projects

### Creating a New Project

1. Open the menu (☰) and select **New Project**, or press `Ctrl+N`
2. If you have unsaved changes, you'll be prompted to save them first
3. A new project starts with one empty track

### Opening an Existing Project

1. Open the menu and select **Open Project…**, or press `Ctrl+O`
2. Navigate to your project folder and select the `.atr` file
3. All tracks and their recordings will be loaded

### Saving a Project

**Save** (`Ctrl+S`):
- If working on an existing project, saves to the same location
- If it's a new project, prompts for a save location

**Save As** (`Ctrl+Shift+S`):
- Always prompts for a new location
- Creates a project folder containing:
  - `projectname.atr` - Project metadata file
  - `audio/` - Folder containing all track recordings

### Auto-save on Exit

When closing the application with unsaved changes, you'll be prompted to:
- **Save** - Save before closing
- **Don't Save** - Discard changes and close
- **Cancel** - Return to the application

### Recent Projects

The application automatically opens your most recent project when launched.

---

## Working with Tracks

### Adding a Track

- Click the **+** button in the header bar, or
- Press `Ctrl+T`

New tracks are automatically named "Track 1", "Track 2", etc.

### Renaming a Track

1. Click the **✏️** (pencil) button on the left of the track
2. Enter the new name in the dialog
3. Click **Rename** or press `Enter`

### Deleting a Track

1. Click the **🗑️** (delete) button on the right of the track
2. The track and its recording are immediately removed

> **Note:** This action cannot be undone. The recording is permanently deleted.

### Track States

| State | Description |
|-------|-------------|
| **Ready** | Track has no recording or is stopped |
| **Recording…** | Currently recording audio |
| **Playing…** | Currently playing back |
| **Paused** | Playback is paused (can be resumed) |
| **Playing (muted)…** | Playing but audio is muted |

---

## Recording Audio

### Recording on a Single Track

1. Click the **🔴 Record** button on the track you want to record
2. The track status changes to "Recording…" with a red highlight
3. Speak or play your audio
4. Click the **⏹ Stop** button to finish recording

### Tips for Recording

- Only one track can record at a time
- Previous recordings on the track will be replaced
- Use **Input Monitoring** to hear yourself while setting levels
- Recordings are saved as WAV files

---

## Playback Controls

### Individual Track Playback

- Click **▶** on a track to start playing
- Click **⏸** (same button) to pause
- Click again to resume from the paused position
- The track resets to the beginning when playback completes

### Global Playback (All Tracks)

**Play All** (header bar ▶ or `Ctrl+Space`):
- Starts all tracks with recordings simultaneously
- When tracks are playing, button changes to ⏸ (pause)
- Click again to pause all tracks

**Stop All** (header bar ⏹ or `Ctrl+.`):
- Stops all playback immediately
- Resets all tracks to the beginning
- Clears paused state

### Muting Tracks

- Click the **🔊** button on a track to mute it
- Button changes to **🔇** when muted
- Muted tracks still "play" (position advances) but produce no sound
- Useful for isolating tracks during playback review

---

## Input Monitoring

Input monitoring lets you hear your microphone input in real-time.

### Enabling Monitoring

- Click the **🔊** button in the header bar (next to the menu), or
- Press `Ctrl+L`

### Use Cases

- Check microphone levels before recording
- Monitor your voice while recording (with low latency)
- Test audio input settings

### Disabling Monitoring

- Click the monitoring button again, or
- Press `Ctrl+L`

> **Note:** Monitoring uses PipeWire's low-latency audio path for minimal delay.

---

## Importing Audio

You can import existing WAV files as new tracks.

### To Import

1. Open the menu and select **Import Audio…**, or press `Ctrl+I`
2. Select a WAV file from your system
3. A new track is created with the file's name
4. The imported audio is ready to play

### Supported Formats

- WAV (.wav) files

---

## Exporting Audio

### Export Individual Tracks (`Ctrl+Shift+T`)

1. Select **Export Tracks…** from the menu
2. Choose a destination folder
3. Each track is saved as a separate WAV file named after the track

### Export Mixed (`Ctrl+Shift+X`)

1. Select **Export Mixed…** from the menu
2. Choose a filename and location
3. All tracks are mixed down to a single WAV file

### Export All (`Ctrl+Shift+A`)

1. Select **Export All…** from the menu
2. Choose a destination folder
3. Exports both:
   - Individual track files
   - A mixed "mixed.wav" file

---

## Keyboard Shortcuts

Access the shortcuts window anytime with `Ctrl+?` or from the menu.

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

### Export

| Action | Shortcut |
|--------|----------|
| Export Tracks | `Ctrl+Shift+T` |
| Export Mixed | `Ctrl+Shift+X` |
| Export All | `Ctrl+Shift+A` |

### Help

| Action | Shortcut |
|--------|----------|
| Keyboard Shortcuts | `Ctrl+?` |

---

## Troubleshooting

### No Audio Recording

**Problem:** Recording doesn't capture any audio.

**Solutions:**
1. Check that PipeWire is running: `systemctl --user status pipewire`
2. Verify `pw-record` is installed: `which pw-record`
3. Check your microphone is selected in system sound settings
4. Try running `pw-record test.wav` in terminal to test

### No Audio Playback

**Problem:** Tracks don't play or no sound is heard.

**Solutions:**
1. Check system volume isn't muted
2. Verify the track isn't muted (🔇 icon)
3. Check GStreamer is installed: `gst-launch-1.0 --version`
4. Ensure speakers/headphones are selected in system settings

### "PipeWire tools not found" Error

**Solution:** Install PipeWire tools:
```bash
# Fedora
sudo dnf install pipewire-utils

# Ubuntu/Debian
sudo apt install pipewire

# Arch
sudo pacman -S pipewire
```

### Monitoring Has Delay/Echo

**Problem:** Input monitoring has noticeable latency.

**Solutions:**
1. This is normal for software monitoring
2. Use hardware monitoring if your audio interface supports it
3. The application uses minimal latency settings, but some delay is unavoidable

### Project Won't Open

**Problem:** Error when opening a project file.

**Solutions:**
1. Ensure the `.atr` file and `audio/` folder are in the same directory
2. Check that audio files haven't been moved or deleted
3. Verify the project file isn't corrupted (it's a JSON file)

### Application Won't Start

**Problem:** Application fails to launch.

**Solutions:**
1. Check Python dependencies are installed:
   ```bash
   pip install PyGObject
   ```
2. Ensure GTK4 and libadwaita are installed
3. Run from terminal to see error messages:
   ```bash
   ./audio_recorder.py
   ```

---

## Tips & Best Practices

1. **Save frequently** - Use `Ctrl+S` to save your work regularly

2. **Name your tracks** - Rename tracks to describe their content for easier organization

3. **Use mute for mixing** - Mute tracks to hear how others sound together

4. **Monitor before recording** - Enable input monitoring to check levels before recording

5. **Export backups** - Use "Export All" to create backup copies of your project

6. **Organize projects** - Keep each project in its own folder

---

## Getting Help

- **Keyboard Shortcuts:** Press `Ctrl+?` or select from menu
- **About:** Select "About Audio Recorder" from the menu
- **Report Issues:** Visit the project's issue tracker

---

*Audio Recorder is powered by GStreamer, PipeWire, GTK4, and libadwaita.*

