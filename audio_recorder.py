#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Adw, GLib, Gio, Gst, Gdk
import subprocess
import os
import tempfile
from pathlib import Path
import json
import shutil
import numpy as np
import math
import time

# Initialize GStreamer
Gst.init(None)

# Get the directory where this script is located
# Support Flatpak environment via AUDIO_RECORDER_DATA_DIR
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('AUDIO_RECORDER_DATA_DIR', os.path.join(SCRIPT_DIR, 'data'))
UI_DIR = os.path.join(DATA_DIR, 'ui')
HELP_DIR = os.path.join(DATA_DIR, 'help', 'C')
ICONS_DIR = os.path.join(DATA_DIR, 'icons')


class Track:
    def __init__(self, name, temp_file=None):
        self.name = name
        self.temp_file = temp_file
        self.recording = False
        self.record_process = None
        self.playing = False
        self.paused = False
        self.muted = False
        self.volume = 1.0  # Volume level 0.0 to 1.0
        self.pipeline = None  # GStreamer pipeline for playback


# ==================== Chromatic Tuner ====================

# Note frequencies (A4 = 440Hz standard)
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']



def freq_to_note(frequency):
    """Convert frequency to nearest note name, octave, and cents deviation"""
    if frequency <= 0:
        return None, None, 0
    
    # A4 = 440Hz is our reference (A in octave 4)
    A4 = 440.0
    
    # Calculate semitones from A4
    semitones_from_a4 = 12 * math.log2(frequency / A4)
    
    # Round to nearest semitone
    nearest_semitone = round(semitones_from_a4)
    
    # Calculate cents deviation (100 cents = 1 semitone)
    cents = (semitones_from_a4 - nearest_semitone) * 100
    
    # A4 is index 9 (A) in octave 4, so A4 = 4*12 + 9 = 57 semitones from C0
    # C0 is 48 semitones below A4
    absolute_semitone = nearest_semitone + 57  # 57 = 4*12 + 9
    
    # Get note and octave
    note_index = absolute_semitone % 12
    octave = absolute_semitone // 12
    
    note_name = NOTE_NAMES[note_index]
    
    return note_name, octave, cents


# ==================== Drum Machine ====================

# Standard General MIDI drum map (channel 10) with short names
GM_DRUMS = {
    "Kick": 36,
    "Snare": 38,
    "HH Closed": 42,
    "HH Open": 46,
    "Tom Lo": 45,
    "Tom Mid": 47,
    "Tom Hi": 50,
    "Crash": 49,
    "Ride": 51,
    "Clap": 39,
    "Rimshot": 37,
    "Cowbell": 56,
}

class DrumGrid(Gtk.DrawingArea):
    """Grid widget for drum pattern editing"""
    
    def __init__(self, drum_machine):
        super().__init__()
        self.dm = drum_machine
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_draw_func(self._draw)
        
        # Enable mouse interaction
        click = Gtk.GestureClick.new()
        click.connect("pressed", self._on_click)
        self.add_controller(click)
        
        self.set_can_focus(True)
        self.set_focusable(True)
    
    def _draw(self, area, cr, width, height):
        """Draw the drum grid"""
        import cairo
        
        # Colors
        bg_color = (0.12, 0.12, 0.14)
        grid_line = (0.3, 0.3, 0.32)
        beat_line = (0.5, 0.5, 0.52)
        bar_line = (0.7, 0.7, 0.72)
        cell_off = (0.2, 0.2, 0.22)
        cell_on = (0.2, 0.7, 0.4)
        cell_accent = (0.9, 0.5, 0.2)
        playhead_color = (0.3, 0.6, 1.0)
        text_color = (0.9, 0.9, 0.9)
        
        # Layout (no label area - labels are in separate panel)
        header_height = 16
        grid_x = 2
        grid_y = header_height
        grid_width = width - 4
        grid_height = height - header_height - 4
        
        num_drums = len(self.dm.drum_order)
        num_steps = self.dm.steps_per_bar * self.dm.num_bars
        
        if num_drums == 0 or num_steps == 0:
            return
        
        cell_width = grid_width / num_steps
        cell_height = grid_height / num_drums
        
        # Background
        cr.set_source_rgb(*bg_color)
        cr.paint()
        
        # Draw step numbers header
        cr.set_source_rgb(*text_color)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(10)
        
        for step in range(num_steps):
            x = grid_x + step * cell_width + cell_width / 2
            step_in_bar = step % self.dm.steps_per_bar
            # Beat grouping based on denominator
            # /32→8, /16→4, /8→2, /4→1, /3→3, /2→1
            denom = self.dm.time_sig_denominator
            if denom == 3:
                beat_group = 3
            elif denom == 2:
                beat_group = 1
            else:
                beat_group = max(1, denom // 4)
            if step_in_bar % beat_group == 0:
                beat_num = step_in_bar // beat_group + 1
                text = str(beat_num)
                extents = cr.text_extents(text)
                cr.move_to(x - extents.width / 2, header_height - 8)
                cr.show_text(text)
        
        # Draw grid cells
        for row, drum_name in enumerate(self.dm.drum_order):
            for step in range(num_steps):
                x = grid_x + step * cell_width
                y = grid_y + row * cell_height
                
                # Cell background
                if self.dm.pattern[drum_name][step]:
                    # Check if it's an accent (first beat of bar)
                    step_in_bar = step % self.dm.steps_per_bar
                    if step_in_bar == 0:
                        cr.set_source_rgb(*cell_accent)
                    else:
                        cr.set_source_rgb(*cell_on)
                else:
                    cr.set_source_rgb(*cell_off)
                
                # Draw cell with padding
                padding = 2
                cr.rectangle(x + padding, y + padding, 
                           cell_width - 2*padding, cell_height - 2*padding)
                cr.fill()
        
        # Draw grid lines
        cr.set_line_width(1)
        
        # Vertical lines (step divisions)
        for step in range(num_steps + 1):
            x = grid_x + step * cell_width
            step_in_bar = step % self.dm.steps_per_bar
            
            # Beat grouping based on denominator
            denom = self.dm.time_sig_denominator
            if denom == 3:
                beat_group = 3
            elif denom == 2:
                beat_group = 1
            else:
                beat_group = max(1, denom // 4)
            
            if step % self.dm.steps_per_bar == 0:
                cr.set_source_rgb(*bar_line)
                cr.set_line_width(2)
            elif step_in_bar % beat_group == 0:
                cr.set_source_rgb(*beat_line)
                cr.set_line_width(1.5)
            else:
                cr.set_source_rgb(*grid_line)
                cr.set_line_width(0.5)
            
            cr.move_to(x, grid_y)
            cr.line_to(x, grid_y + grid_height)
            cr.stroke()
        
        # Horizontal lines (drum divisions)
        cr.set_source_rgb(*grid_line)
        cr.set_line_width(1)
        for row in range(num_drums + 1):
            y = grid_y + row * cell_height
            cr.move_to(grid_x, y)
            cr.line_to(grid_x + grid_width, y)
            cr.stroke()
        
        # Draw playhead
        if self.dm.playing and 0 <= self.dm.current_step < num_steps:
            x = grid_x + self.dm.current_step * cell_width
            cr.set_source_rgba(*playhead_color, 0.8)
            cr.set_line_width(3)
            cr.move_to(x, grid_y)
            cr.line_to(x, grid_y + grid_height)
            cr.stroke()
            
            # Highlight current column
            cr.set_source_rgba(*playhead_color, 0.15)
            cr.rectangle(x, grid_y, cell_width, grid_height)
            cr.fill()
    
    def _on_click(self, gesture, n_press, x, y):
        """Handle mouse click to toggle cells"""
        # Calculate which cell was clicked (no label area - labels are in separate panel)
        header_height = 16
        grid_x = 2
        grid_y = header_height
        
        width = self.get_width()
        height = self.get_height()
        grid_width = width - 4
        grid_height = height - header_height - 4
        
        num_drums = len(self.dm.drum_order)
        num_steps = self.dm.steps_per_bar * self.dm.num_bars
        
        if num_drums == 0 or num_steps == 0:
            return
        
        cell_width = grid_width / num_steps
        cell_height = grid_height / num_drums
        
        # Check if click is in grid area
        if x < grid_x or y < grid_y:
            return
        
        col = int((x - grid_x) / cell_width)
        row = int((y - grid_y) / cell_height)
        
        if 0 <= row < num_drums and 0 <= col < num_steps:
            drum_name = self.dm.drum_order[row]
            self.dm.pattern[drum_name][col] = not self.dm.pattern[drum_name][col]
            self.queue_draw()
            self.dm._mark_dirty()


class DrumMachinePanel(Gtk.Box):
    """Drum machine panel for embedding in the main window"""
    
    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        
        # Callback for when state changes (to mark project dirty)
        self._dirty_callback = None
        
        # Drum machine state
        self.tempo = 120
        self.time_sig_numerator = 4   # Number of notes per bar
        self.time_sig_denominator = 4  # Note value (4=quarter, 8=eighth, 16=sixteenth)
        self.num_bars = 1  # Fewer bars for compact display
        self.steps_per_bar = self.time_sig_numerator  # Each note = 1 step
        
        self.playing = False
        self.current_step = 0
        self.timer_id = None
        
        # Drum selection - standard drum kit
        self.drum_order = ["Kick", "Snare", "HH Closed", "HH Open", "Tom Hi", "Tom Mid", "Tom Lo", "Crash", "Ride", "Cowbell"]
        self.pattern = {drum: [False] * (self.steps_per_bar * self.num_bars) 
                       for drum in GM_DRUMS.keys()}
        # Volume per drum (0-127 MIDI velocity, default 100)
        self.volumes = {drum: 100 for drum in GM_DRUMS.keys()}
        
        # MIDI/Audio - initialized lazily on first play
        self.pipeline = None
        self.fluidsynth_proc = None
        self.soundfont = None
        self.audio_available = False
        self.midi_initialized = False
        
        self._build_ui()
        self._load_preset_pattern()
    
    def _init_midi(self):
        """Initialize FluidSynth for MIDI drum sounds"""
        self.fluidsynth_proc = None
        self.soundfont = None
        self.audio_available = False
        
        # Find a soundfont
        sf_paths = [
            "/usr/share/soundfonts/FluidR3_GM.sf2",
            "/usr/share/sounds/sf2/FluidR3_GM.sf2",
            "/usr/share/soundfonts/default.sf2",
            "/usr/share/sounds/sf2/default-GM.sf2",
            "/usr/share/soundfonts/FluidR3_GS.sf2",
            "/usr/share/sounds/sf2/TimGM6mb.sf2",
            "/usr/share/soundfonts/freepats-general-midi.sf2",
            "/usr/share/sounds/sf2/GeneralUser_GS.sf2",
        ]
        
        for sf in sf_paths:
            if os.path.exists(sf):
                self.soundfont = sf
                break
        
        if not self.soundfont:
            print("No SoundFont found. Install fluid-soundfont-gm package.")
            return
        
        # Try different audio drivers
        audio_drivers = ["pipewire", "pulseaudio", "alsa"]
        
        print(f"Initializing FluidSynth with soundfont: {self.soundfont}")
        
        for driver in audio_drivers:
            try:
                # Start FluidSynth in shell mode, reading commands from stdin
                # Use simpler command line like the working test
                self.fluidsynth_proc = subprocess.Popen(
                    [
                        "fluidsynth", 
                        "-a", driver,
                        "-g", "1.0",
                        self.soundfont
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                # Give it a moment to start
                time.sleep(0.5)
                
                # Check if process is still running
                if self.fluidsynth_proc.poll() is None:
                    self.audio_available = True
                    print(f"FluidSynth started with {driver} driver")
                    return
                else:
                    # Process exited, capture stderr to see why
                    exit_code = self.fluidsynth_proc.poll()
                    stderr = self.fluidsynth_proc.stderr.read()
                    stdout = self.fluidsynth_proc.stdout.read()
                    print(f"FluidSynth exited ({exit_code}) with {driver}:")
                    if stderr:
                        print(f"  stderr: {stderr[:300]}")
                    if stdout:
                        print(f"  stdout: {stdout[:300]}")
                    self.fluidsynth_proc = None
            except FileNotFoundError:
                print("FluidSynth not found. Install fluidsynth package.")
                return
            except Exception as e:
                print(f"Failed to start FluidSynth with {driver}: {e}")
        
        print("Could not start FluidSynth with any audio driver.")
    
    def _build_ui(self):
        """Build the drum machine UI - compact layout"""
        # Add CSS class for styling
        self.add_css_class("card")
        self.set_margin_top(2)
        self.set_margin_bottom(0)
        self.set_margin_start(0)
        self.set_margin_end(0)
        # Don't expand vertically - fixed height
        self.set_vexpand(False)
        
        # Top controls bar - compact
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        controls.set_margin_start(4)
        controls.set_margin_end(4)
        controls.set_margin_top(4)
        controls.set_margin_bottom(2)
        
        # Play/Stop button
        self.play_btn = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        self.play_btn.add_css_class("circular")
        self.play_btn.add_css_class("suggested-action")
        self.play_btn.set_tooltip_text("Play/Stop")
        self.play_btn.connect("clicked", self._on_play_stop)
        controls.append(self.play_btn)
        
        # Clear button
        clear_btn = Gtk.Button.new_from_icon_name("edit-clear-symbolic")
        clear_btn.add_css_class("circular")
        clear_btn.add_css_class("flat")
        clear_btn.set_tooltip_text("Clear pattern")
        clear_btn.connect("clicked", self._on_clear)
        controls.append(clear_btn)
        
        # Tempo control
        tempo_label = Gtk.Label(label="BPM")
        tempo_label.add_css_class("dim-label")
        tempo_label.add_css_class("caption")
        controls.append(tempo_label)
        
        self.tempo_spin = Gtk.SpinButton.new_with_range(40, 240, 1)
        self.tempo_spin.set_value(self.tempo)
        self.tempo_spin.connect("value-changed", self._on_tempo_changed)
        controls.append(self.tempo_spin)
        
        # Spacer
        spacer1 = Gtk.Box()
        spacer1.set_hexpand(True)
        controls.append(spacer1)
        
        # Time signature: numerator / denominator
        time_sig_label = Gtk.Label(label="Time:")
        time_sig_label.add_css_class("caption")
        controls.append(time_sig_label)
        
        # Numerator: total note units per bar (1-32)
        numerator_options = [str(i) for i in range(1, 33)]
        self.numerator_dropdown = Gtk.DropDown.new_from_strings(numerator_options)
        self.numerator_dropdown.set_selected(self.time_sig_numerator - 1)
        self.numerator_dropdown.connect("notify::selected", self._on_time_sig_changed)
        controls.append(self.numerator_dropdown)
        
        # Separator
        slash_label = Gtk.Label(label="/")
        controls.append(slash_label)
        
        # Denominator
        denominator_options = ["2", "4", "8", "16", "32"]
        self.denominator_dropdown = Gtk.DropDown.new_from_strings(denominator_options)
        denom_values = [2, 4, 8, 16, 32]
        denom_idx = denom_values.index(self.time_sig_denominator) if self.time_sig_denominator in denom_values else 1
        self.denominator_dropdown.set_selected(denom_idx)
        self.denominator_dropdown.connect("notify::selected", self._on_time_sig_changed)
        controls.append(self.denominator_dropdown)
        
        self.append(controls)
        
        # Grid and drum controls container
        grid_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        
        # Left panel: drum names and volume sliders (compact)
        drum_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        drum_panel.set_margin_start(2)
        drum_panel.set_margin_end(2)
        
        # Header spacer to align with grid header
        header_spacer = Gtk.Box()
        header_spacer.set_size_request(-1, 16)
        drum_panel.append(header_spacer)
        
        # Create drum name + volume slider for each drum (single row: name then volume)
        self.volume_scales = {}
        drum_row_height = 22  # Height per drum row
        for drum_name in self.drum_order:
            # Container for this drum (name and volume on same row)
            drum_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            drum_box.set_size_request(-1, drum_row_height)
            
            # Drum name label (full name)
            name_label = Gtk.Label(label=drum_name)
            name_label.set_halign(Gtk.Align.START)
            name_label.set_xalign(0)
            name_label.set_size_request(65, -1)
            name_label.add_css_class("caption")
            drum_box.append(name_label)
            
            # Volume slider next to name - expands to fill available space
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 127, 1)
            vol_value = self.volumes.get(drum_name, 100)
            scale.set_value(vol_value)
            scale.set_draw_value(False)
            scale.set_hexpand(True)  # Expand to fill space
            percent = int(vol_value * 100 / 127)
            scale.set_tooltip_text(f"{drum_name} volume: {percent}%")
            scale.connect("value-changed", self._on_volume_changed, drum_name)
            self.volume_scales[drum_name] = scale
            drum_box.append(scale)
            
            drum_panel.append(drum_box)
        
        # Drum panel expands to fill available space
        drum_panel.set_hexpand(True)
        grid_container.append(drum_panel)
        
        # Drum grid - fixed size (does not expand)
        # Height = header (16) + drums * row_height + padding
        grid_height = 16 + len(self.drum_order) * drum_row_height + 2
        self.grid = DrumGrid(self)
        self.grid.set_size_request(300, grid_height)  # Fixed width
        self.grid.set_hexpand(False)
        grid_container.append(self.grid)
        
        self.append(grid_container)
    
    def connect_dirty_callback(self, callback):
        """Connect a callback to be called when state changes"""
        self._dirty_callback = callback
    
    def _mark_dirty(self):
        """Mark the project as having unsaved changes"""
        if self._dirty_callback:
            self._dirty_callback()
    
    def _load_preset_pattern(self):
        """Load the default preset pattern: HH Closed, Snare, Snare, Snare"""
        steps = self.steps_per_bar * self.num_bars
        
        for i in range(steps):
            step_in_bar = i % self.steps_per_bar
            
            # Default pattern for 4/4: HH Closed on 1, Snare on 2, 3, 4
            if step_in_bar == 0:
                self.pattern["HH Closed"][i] = True
            elif step_in_bar < self.steps_per_bar:
                self.pattern["Snare"][i] = True
    
    def _on_tempo_changed(self, spin):
        """Handle tempo change - takes effect on next step automatically"""
        self.tempo = int(spin.get_value())
        # No need to restart timer - each step schedules the next with current tempo
        self._mark_dirty()
    
    def _on_volume_changed(self, scale, drum_name):
        """Handle volume change for a drum"""
        value = int(scale.get_value())
        self.volumes[drum_name] = value
        # Update tooltip with percentage (127 = 100%)
        percent = int(value * 100 / 127)
        scale.set_tooltip_text(f"{drum_name} volume: {percent}%")
        self._mark_dirty()
    
    def _on_time_sig_changed(self, dropdown, param):
        """Handle time signature change"""
        self.time_sig_numerator = self.numerator_dropdown.get_selected() + 1
        denom_values = [2, 4, 8, 16, 32]
        denom_idx = self.denominator_dropdown.get_selected()
        if 0 <= denom_idx < len(denom_values):
            self.time_sig_denominator = denom_values[denom_idx]
        self._update_grid_size()
        self._mark_dirty()
    
    
    def _update_grid_size(self):
        """Update pattern size when settings change"""
        old_steps = self.steps_per_bar * self.num_bars
        # Steps per bar = numerator (each note unit = 1 step)
        self.steps_per_bar = self.time_sig_numerator
        new_steps = self.steps_per_bar * self.num_bars
        
        # Resize patterns, preserving data where possible
        for drum in GM_DRUMS.keys():
            old_pattern = self.pattern[drum]
            new_pattern = [False] * new_steps
            for i in range(min(len(old_pattern), new_steps)):
                new_pattern[i] = old_pattern[i]
            self.pattern[drum] = new_pattern
        
        self.current_step = 0
        self.grid.queue_draw()
    
    def _on_play_stop(self, button):
        """Toggle playback"""
        if self.playing:
            self._stop()
        else:
            self._play()
    
    def _play(self):
        """Start playback"""
        # Initialize MIDI lazily on first play
        if not self.midi_initialized:
            self._init_midi()
            self.midi_initialized = True
        
        self.playing = True
        self.current_step = 0
        self.play_btn.set_icon_name("media-playback-stop-symbolic")
        self.play_btn.remove_css_class("suggested-action")
        self.play_btn.add_css_class("destructive-action")
        
        # Play first step immediately
        self._play_current_step()
        
        # Schedule next step - use single-shot timer for smooth tempo changes
        self._schedule_next_step()
    
    def _stop(self):
        """Stop playback"""
        self.playing = False
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None
        
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self.play_btn.remove_css_class("destructive-action")
        self.play_btn.add_css_class("suggested-action")
        
        self.current_step = 0
        self.grid.queue_draw()
        self._update_position_display()
    
    def _schedule_next_step(self):
        """Schedule the next step with current tempo - allows smooth tempo changes"""
        if not self.playing:
            return
        
        # Calculate interval based on current tempo (re-evaluated each step)
        # BPM = beats per minute (quarter notes by convention)
        # One bar = 4 quarter notes worth of time, divided by the number of steps
        bar_ms = 4 * 60000 / self.tempo  # Duration of one bar in ms
        step_ms = bar_ms / self.steps_per_bar
        
        # Use single-shot timer - this allows tempo to change between steps
        self.timer_id = GLib.timeout_add(int(step_ms), self._tick)
    
    def _tick(self):
        """Advance one step"""
        if not self.playing:
            return False
        
        self.current_step = (self.current_step + 1) % (self.steps_per_bar * self.num_bars)
        self._play_current_step()
        self.grid.queue_draw()
        self._update_position_display()
        
        # Schedule next step with current tempo
        self._schedule_next_step()
        
        # Return False to not repeat this timer (we schedule a new one)
        return False
    
    def _play_current_step(self):
        """Play all active drums at current step"""
        for drum_name in self.drum_order:
            if self.pattern[drum_name][self.current_step]:
                self._play_drum(drum_name)
        
        self._update_position_display()
    
    def _play_drum(self, drum_name):
        """Play a single drum sound using FluidSynth MIDI"""
        if not self.audio_available or not self.fluidsynth_proc:
            return
        
        # Check if FluidSynth is still running
        if self.fluidsynth_proc.poll() is not None:
            print("FluidSynth process terminated, attempting restart...")
            self._init_midi()
            if not self.audio_available:
                return
        
        midi_note = GM_DRUMS.get(drum_name)
        if midi_note is None:
            return
        
        try:
            # Send MIDI note on channel 9 (drums) with per-drum volume
            # FluidSynth shell command: noteon channel key velocity
            velocity = self.volumes.get(drum_name, 100)
            self.fluidsynth_proc.stdin.write(f"noteon 9 {midi_note} {velocity}\n")
            self.fluidsynth_proc.stdin.flush()
        except BrokenPipeError:
            print("FluidSynth connection lost, attempting restart...")
            self._init_midi()
        except Exception as e:
            print(f"MIDI error: {e}")
            self.audio_available = False
    
    def _update_position_display(self):
        """Update the position display (grid redraws to show playhead)"""
        # Position is shown via the playhead in the grid
        pass
    
    def _on_clear(self, button):
        """Clear the pattern"""
        total_steps = self.steps_per_bar * self.num_bars
        for drum in GM_DRUMS.keys():
            self.pattern[drum] = [False] * total_steps
        self.grid.queue_draw()
        self._mark_dirty()
    
    def cleanup(self):
        """Clean up when panel is hidden"""
        self._stop()
        # Terminate FluidSynth and reset initialization flag
        if self.fluidsynth_proc:
            try:
                self.fluidsynth_proc.stdin.write("quit\n")
                self.fluidsynth_proc.stdin.flush()
                self.fluidsynth_proc.terminate()
                self.fluidsynth_proc.wait(timeout=2)
            except:
                pass
            self.fluidsynth_proc = None
        # Reset so FluidSynth restarts when shown again
        self.midi_initialized = False
        self.audio_available = False
    
    def reset_to_defaults(self):
        """Reset drum machine to default state for new project"""
        # Reset tempo
        self.tempo = 120
        self.tempo_spin.set_value(120)
        
        # Reset time signature to 4/4
        self.time_sig_numerator = 4
        self.time_sig_denominator = 4
        self.numerator_dropdown.set_selected(3)  # 4 is index 3 (0-indexed)
        denom_values = [2, 4, 8, 16, 32]
        self.denominator_dropdown.set_selected(denom_values.index(4))
        
        # Reset grid
        self.steps_per_bar = self.time_sig_numerator
        self.current_step = 0
        
        # Clear and reload pattern with defaults
        total_steps = self.steps_per_bar * self.num_bars
        for drum in GM_DRUMS.keys():
            self.pattern[drum] = [False] * total_steps
        self._load_preset_pattern()
        
        # Reset volumes to default (100)
        for drum in GM_DRUMS.keys():
            self.volumes[drum] = 100
            if drum in self.volume_scales:
                self.volume_scales[drum].set_value(100)
        
        self.grid.queue_draw()
    
    def get_state(self):
        """Get current drum machine state for saving"""
        return {
            'tempo': self.tempo,
            'time_sig_numerator': self.time_sig_numerator,
            'time_sig_denominator': self.time_sig_denominator,
            'num_bars': self.num_bars,
            'pattern': {drum: list(steps) for drum, steps in self.pattern.items()},
            'volumes': dict(self.volumes)
        }
    
    def set_state(self, state):
        """Restore drum machine state from saved data"""
        if not state:
            return
        
        try:
            # Restore tempo
            if 'tempo' in state:
                self.tempo = state['tempo']
                self.tempo_spin.set_value(self.tempo)
            
            # Restore time signature numerator
            if 'time_sig_numerator' in state:
                self.time_sig_numerator = state['time_sig_numerator']
                if 1 <= self.time_sig_numerator <= 32:
                    self.numerator_dropdown.set_selected(self.time_sig_numerator - 1)
            
            # Restore time signature denominator
            if 'time_sig_denominator' in state:
                self.time_sig_denominator = state['time_sig_denominator']
                denom_values = [2, 4, 8, 16, 32]
                if self.time_sig_denominator in denom_values:
                    self.denominator_dropdown.set_selected(denom_values.index(self.time_sig_denominator))
            
            # Restore bars
            if 'num_bars' in state:
                self.num_bars = state['num_bars']
            
            # Recalculate steps per bar
            self.steps_per_bar = self.time_sig_numerator
            
            # Restore pattern
            if 'pattern' in state:
                total_steps = self.steps_per_bar * self.num_bars
                for drum in GM_DRUMS.keys():
                    if drum in state['pattern']:
                        saved_steps = state['pattern'][drum]
                        # Ensure pattern is the right length
                        self.pattern[drum] = (saved_steps + [False] * total_steps)[:total_steps]
                    else:
                        self.pattern[drum] = [False] * total_steps
            
            # Restore volumes
            if 'volumes' in state:
                for drum in GM_DRUMS.keys():
                    if drum in state['volumes']:
                        self.volumes[drum] = state['volumes'][drum]
                        if drum in self.volume_scales:
                            self.volume_scales[drum].set_value(self.volumes[drum])
            
            # Update the grid
            self._update_grid_size()
            self.grid.queue_draw()
        except Exception as e:
            print(f"Error restoring drum machine state: {e}")


class TunerGauge(Gtk.DrawingArea):
    """Custom gauge widget for tuner display - Accessible GNOME/Adwaita style"""
    
    def __init__(self):
        super().__init__()
        self.cents = 0  # -50 to +50
        self.note_name = "—"
        self.octave = ""
        self.frequency = 0
        self.in_tune = False
        self.has_signal = False
        
        # Smooth needle animation
        self.display_cents = 0
        
        self.set_content_width(420)
        self.set_content_height(320)
        self.set_draw_func(self._draw)
    
    def set_tuning(self, note_name, octave, cents, frequency, has_signal):
        """Update the gauge with new tuning data"""
        self.note_name = note_name if note_name else "—"
        self.octave = str(octave) if octave is not None else ""
        self.cents = max(-50, min(50, cents))
        self.frequency = frequency
        self.in_tune = abs(cents) < 5 if has_signal else False
        self.has_signal = has_signal
        
        # Smooth needle movement
        if has_signal:
            self.display_cents = self.display_cents * 0.3 + self.cents * 0.7
        else:
            self.display_cents = 0
        
        self.queue_draw()
    
    def _draw(self, area, cr, width, height):
        """Draw the gauge with accessible high-contrast design"""
        import cairo
        
        # HIGH CONTRAST colors for accessibility
        # Using WCAG 2.1 compliant contrast ratios
        
        # Dark background for guaranteed contrast
        bg_color = (0.12, 0.12, 0.14)         # Very dark gray/black
        
        # Bright, saturated colors for maximum visibility
        green_color = (0.0, 0.95, 0.5)        # Bright green - in tune
        yellow_color = (1.0, 0.9, 0.0)        # Bright yellow - close
        red_color = (1.0, 0.3, 0.3)           # Bright red - off
        
        # High contrast text - pure white for maximum readability
        text_bright = (1.0, 1.0, 1.0)         # Pure white
        text_secondary = (0.9, 0.9, 0.9)      # Near white
        bar_bg = (0.25, 0.25, 0.28)           # Dark gray for gauge background
        
        # === DRAW DARK BACKGROUND ===
        cr.set_source_rgb(*bg_color)
        self._rounded_rect(cr, 0, 0, width, height, 12)
        cr.fill()
        
        # Layout - generous spacing for readability
        cx = width / 2
        margin = 25
        
        # === LARGE NOTE DISPLAY AT TOP ===
        note_y = 85
        
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(80)  # Very large for visibility
        
        # Note color based on tuning state - always high contrast
        if self.in_tune:
            cr.set_source_rgb(*green_color)
        elif self.has_signal:
            if abs(self.cents) < 20:
                cr.set_source_rgb(*yellow_color)
            else:
                cr.set_source_rgb(*red_color)
        else:
            cr.set_source_rgb(*text_bright)  # White when no signal
        
        note_text = self.note_name
        extents = cr.text_extents(note_text)
        note_x = cx - extents.width / 2
        cr.move_to(note_x, note_y)
        cr.show_text(note_text)
        
        # Octave number (large, next to note)
        if self.octave and self.has_signal:
            cr.set_font_size(40)
            cr.move_to(note_x + extents.width + 5, note_y)
            cr.show_text(self.octave)
        
        # === FREQUENCY DISPLAY ===
        cr.set_font_size(22)
        cr.set_source_rgb(*text_bright)  # White for visibility
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        
        if self.has_signal and self.frequency > 0:
            freq_text = f"{self.frequency:.1f} Hz"
        else:
            freq_text = "Play a note"
        
        extents = cr.text_extents(freq_text)
        cr.move_to(cx - extents.width / 2, note_y + 35)
        cr.show_text(freq_text)
        
        # === GAUGE BAR ===
        bar_x = margin
        bar_width = width - 2 * margin
        bar_y = 165
        bar_height = 24  # Thicker bar for visibility
        
        # Gauge background
        cr.set_source_rgb(*bar_bg)
        self._rounded_rect(cr, bar_x, bar_y, bar_width, bar_height, 6)
        cr.fill()
        
        # Helper function
        def cents_to_x(c):
            return bar_x + (c + 50) / 100 * bar_width
        
        # Draw colored zones with high opacity
        zone_y = bar_y
        zone_height = bar_height
        
        # Red zone left (-50 to -20)
        cr.set_source_rgba(*red_color, 0.9)
        self._rounded_rect(cr, cents_to_x(-50), zone_y, cents_to_x(-20) - cents_to_x(-50), zone_height, 6)
        cr.fill()
        
        # Yellow zone left (-20 to -5)
        cr.set_source_rgba(*yellow_color, 0.9)
        cr.rectangle(cents_to_x(-20), zone_y, cents_to_x(-5) - cents_to_x(-20), zone_height)
        cr.fill()
        
        # Green zone center (-5 to +5) - THE TARGET
        cr.set_source_rgba(*green_color, 1.0)
        cr.rectangle(cents_to_x(-5), zone_y, cents_to_x(5) - cents_to_x(-5), zone_height)
        cr.fill()
        
        # Yellow zone right (+5 to +20)
        cr.set_source_rgba(*yellow_color, 0.9)
        cr.rectangle(cents_to_x(5), zone_y, cents_to_x(20) - cents_to_x(5), zone_height)
        cr.fill()
        
        # Red zone right (+20 to +50)
        cr.set_source_rgba(*red_color, 0.9)
        self._rounded_rect(cr, cents_to_x(20), zone_y, cents_to_x(50) - cents_to_x(20), zone_height, 6)
        cr.fill()
        
        # === CENTER LINE (target) ===
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.set_line_width(3)
        center_x = cents_to_x(0)
        cr.move_to(center_x, bar_y - 8)
        cr.line_to(center_x, bar_y + bar_height + 8)
        cr.stroke()
        
        # === TICK MARKS AND LABELS ===
        tick_y = bar_y + bar_height + 12
        
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(14)  # Larger tick labels
        
        for cents_val in range(-50, 51, 10):
            x = cents_to_x(cents_val)
            
            # Tick mark
            cr.set_line_width(2)
            if cents_val == 0:
                cr.set_source_rgb(*green_color)
            else:
                cr.set_source_rgb(*text_bright)  # White ticks
            
            cr.move_to(x, bar_y + bar_height + 3)
            cr.line_to(x, bar_y + bar_height + 10)
            cr.stroke()
            
            # Label
            label = str(abs(cents_val))
            if cents_val < 0:
                label = "−" + label  # Minus sign
            elif cents_val > 0:
                label = "+" + label
            
            extents = cr.text_extents(label)
            cr.move_to(x - extents.width / 2, tick_y + 14)
            cr.show_text(label)
        
        # === LARGE NEEDLE/INDICATOR ===
        if self.has_signal:
            needle_x = cents_to_x(self.display_cents)
            
            # Determine color
            if abs(self.display_cents) < 5:
                needle_color = green_color
            elif abs(self.display_cents) < 20:
                needle_color = yellow_color
            else:
                needle_color = red_color
            
            # Large triangle pointer
            cr.set_source_rgb(*needle_color)
            needle_width = 24  # Wider needle
            needle_height = 30  # Taller needle
            
            cr.move_to(needle_x, bar_y - 2)
            cr.line_to(needle_x - needle_width / 2, bar_y - needle_height)
            cr.line_to(needle_x + needle_width / 2, bar_y - needle_height)
            cr.close_path()
            cr.fill()
            
            # White outline for contrast
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.set_line_width(2)
            cr.move_to(needle_x, bar_y - 2)
            cr.line_to(needle_x - needle_width / 2, bar_y - needle_height)
            cr.line_to(needle_x + needle_width / 2, bar_y - needle_height)
            cr.close_path()
            cr.stroke()
        else:
            # No signal - hollow triangle at center
            needle_x = cents_to_x(0)
            cr.set_source_rgb(*text_bright)  # White outline
            cr.set_line_width(3)
            needle_width = 20
            needle_height = 25
            cr.move_to(needle_x, bar_y - 2)
            cr.line_to(needle_x - needle_width / 2, bar_y - needle_height)
            cr.line_to(needle_x + needle_width / 2, bar_y - needle_height)
            cr.close_path()
            cr.stroke()
        
        # === FLAT / SHARP LABELS ===
        cr.set_font_size(18)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        
        # FLAT label (left)
        cr.set_source_rgb(*red_color)
        cr.move_to(bar_x, bar_y - 15)
        cr.show_text("♭ FLAT")
        
        # SHARP label (right)
        sharp_text = "SHARP ♯"
        extents = cr.text_extents(sharp_text)
        cr.move_to(bar_x + bar_width - extents.width, bar_y - 15)
        cr.show_text(sharp_text)
        
        # === STATUS MESSAGE ===
        status_y = height - 30
        cr.set_font_size(24)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        
        if self.in_tune:
            cr.set_source_rgb(*green_color)
            status_text = "✓ IN TUNE"
        elif self.has_signal:
            cents_val = int(round(self.display_cents))
            if cents_val < -5:
                color = red_color if cents_val < -20 else yellow_color
                cr.set_source_rgb(*color)
                status_text = f"↑ TUNE UP ({cents_val} cents)"
            elif cents_val > 5:
                color = red_color if cents_val > 20 else yellow_color
                cr.set_source_rgb(*color)
                status_text = f"↓ TUNE DOWN (+{cents_val} cents)"
            else:
                cr.set_source_rgb(*green_color)
                status_text = "✓ IN TUNE"
        else:
            cr.set_source_rgb(*text_bright)  # White text
            status_text = "Listening..."
        
        extents = cr.text_extents(status_text)
        cr.move_to(cx - extents.width / 2, status_y)
        cr.show_text(status_text)
    
    def _rounded_rect(self, cr, x, y, w, h, r):
        """Draw a rounded rectangle path"""
        cr.new_path()
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
        cr.arc(x + w - r, y + h - r, r, 0, 0.5 * math.pi)
        cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
        cr.close_path()


class TunerDialog(Adw.Dialog):
    """Chromatic tuner dialog for bass and guitar"""
    
    def __init__(self, parent_window, **kwargs):
        super().__init__(**kwargs)
        self.parent_window = parent_window
        self.set_title("Tuner")
        self.set_content_width(460)
        self.set_content_height(420)
        
        self.pipeline = None
        self.running = False
        self.sample_rate = 48000
        
        # Audio buffer for accumulating samples (needed for low frequencies)
        # For B0 (30.87 Hz), period = 48000/30.87 = 1555 samples
        # We need at least 3-4 periods for reliable detection = ~6000 samples
        # Using 16384 for safety with very low frequencies
        self.audio_buffer = np.array([], dtype=np.float32)
        self.buffer_target_size = 16384
        
        # Smoothing for stable display
        self.freq_history = []
        self.history_size = 8  # More smoothing for low frequencies
        
        self._build_ui()
        
        # Start tuner automatically when dialog opens
        GLib.idle_add(self._start_tuner)
    
    def _build_ui(self):
        """Build the tuner UI"""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Header bar
        header = Adw.HeaderBar()
        header.add_css_class("flat")
        main_box.append(header)
        
        # Content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content_box.set_margin_top(8)
        content_box.set_margin_bottom(16)
        content_box.set_margin_start(16)
        content_box.set_margin_end(16)
        
        # Gauge display
        self.gauge = TunerGauge()
        self.gauge.set_hexpand(True)
        self.gauge.set_vexpand(True)
        content_box.append(self.gauge)
        
        main_box.append(content_box)
        self.set_child(main_box)
        
        # Connect close signal
        self.connect("closed", self._on_dialog_closed)
    
    def _start_tuner(self):
        """Start audio capture and pitch detection"""
        if self.running:
            return
        
        try:
            # Create GStreamer pipeline for audio capture with larger buffer
            # buffer-time in microseconds: 200ms = 200000us gives us ~9600 samples per buffer at 48kHz
            pipeline_str = (
                f"pulsesrc buffer-time=200000 latency-time=50000 ! "
                f"audioconvert ! "
                f"audio/x-raw,format=F32LE,channels=1,rate={self.sample_rate} ! "
                f"appsink name=sink emit-signals=true sync=false max-buffers=5 drop=true"
            )
            
            self.pipeline = Gst.parse_launch(pipeline_str)
            
            # Get the appsink
            appsink = self.pipeline.get_by_name("sink")
            appsink.connect("new-sample", self._on_new_sample)
            
            self.pipeline.set_state(Gst.State.PLAYING)
            self.running = True
            
        except Exception as e:
            self.cents_label.set_text(f"Error: {str(e)}")
            self.running = False
    
    def _stop_tuner(self):
        """Stop audio capture"""
        self.running = False
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        self.audio_buffer = np.array([], dtype=np.float32)
        self.freq_history = []
    
    def _on_new_sample(self, appsink):
        """Process new audio sample"""
        if not self.running:
            return Gst.FlowReturn.OK
            
        sample = appsink.emit("pull-sample")
        if sample:
            buffer = sample.get_buffer()
            success, map_info = buffer.map(Gst.MapFlags.READ)
            
            if success:
                # Convert buffer to numpy array
                audio_data = np.frombuffer(map_info.data, dtype=np.float32).copy()
                buffer.unmap(map_info)
                
                # Accumulate audio data
                self.audio_buffer = np.concatenate([self.audio_buffer, audio_data])
                
                # Keep buffer at target size
                if len(self.audio_buffer) > self.buffer_target_size:
                    self.audio_buffer = self.audio_buffer[-self.buffer_target_size:]
                
                # Only process when we have enough data for low frequency detection
                if len(self.audio_buffer) >= self.buffer_target_size * 0.75:
                    frequency = self._detect_pitch(self.audio_buffer)
                    
                    # Apply smoothing
                    smoothed_freq = self._smooth_frequency(frequency)
                    
                    # Update UI in main thread
                    GLib.idle_add(self._update_display, smoothed_freq)
        
        return Gst.FlowReturn.OK
    
    def _smooth_frequency(self, frequency):
        """Apply smoothing to frequency readings"""
        if frequency <= 0:
            # Clear history on silence
            self.freq_history = []
            return 0
        
        self.freq_history.append(frequency)
        if len(self.freq_history) > self.history_size:
            self.freq_history.pop(0)
        
        if len(self.freq_history) < 2:
            return frequency
        
        # Use median for robustness against outliers
        return float(np.median(self.freq_history))
    
    def _detect_pitch(self, audio_data):
        """Detect pitch using autocorrelation optimized for bass frequencies"""
        min_samples = 4096
        if len(audio_data) < min_samples:
            return 0
        
        # Check if signal is too quiet
        rms = np.sqrt(np.mean(audio_data ** 2))
        if rms < 0.003:  # Lower threshold for bass
            return 0
        
        # Use the most recent samples
        if len(audio_data) > self.buffer_target_size:
            audio_data = audio_data[-self.buffer_target_size:]
        
        # Normalize and remove DC offset
        audio_data = audio_data - np.mean(audio_data)
        
        # Apply window function
        window = np.hanning(len(audio_data))
        audio_data = audio_data * window
        
        # Frequency range for bass and guitar
        # B0 = 30.87 Hz (6-string bass low B) -> period = 1555 samples at 48kHz
        # E1 = 41.20 Hz (4-string bass low E) -> period = 1165 samples
        # E5 = 659.26 Hz (high E on guitar) -> period = 73 samples
        min_freq = 25.0   # Below B0
        max_freq = 1200.0  # Above high harmonics
        
        min_period = int(self.sample_rate / max_freq)  # ~40 samples
        max_period = int(self.sample_rate / min_freq)  # ~1920 samples
        
        # Ensure we have enough data for the longest period
        if max_period >= len(audio_data) // 3:
            max_period = len(audio_data) // 3
        
        if min_period >= max_period or max_period < 50:
            return 0
        
        # Autocorrelation method (more reliable than YIN for low frequencies)
        # Compute normalized autocorrelation
        n = len(audio_data)
        
        # Use FFT for faster autocorrelation
        fft_size = 1 << (2 * n - 1).bit_length()  # Next power of 2
        fft = np.fft.rfft(audio_data, fft_size)
        autocorr = np.fft.irfft(fft * np.conj(fft))[:n]
        
        # Normalize by the zero-lag value
        if autocorr[0] > 0:
            autocorr = autocorr / autocorr[0]
        else:
            return 0
        
        # Find peaks in the autocorrelation
        # Look for the first significant peak after the initial decay
        
        # First, find where autocorrelation drops below a threshold
        threshold = 0.5
        start_search = min_period
        
        # Find first crossing below threshold
        for i in range(min_period, min(max_period, len(autocorr) - 1)):
            if autocorr[i] < threshold:
                start_search = i
                break
        
        # Now find the peak after this dip
        peak_idx = 0
        peak_val = 0
        
        for i in range(start_search, min(max_period, len(autocorr) - 1)):
            # Look for local maximum
            if autocorr[i] > autocorr[i-1] and autocorr[i] > autocorr[i+1]:
                if autocorr[i] > peak_val and autocorr[i] > 0.3:  # Minimum correlation
                    peak_val = autocorr[i]
                    peak_idx = i
                    break  # Take first significant peak (fundamental)
        
        # If no peak found, try finding global max in range
        if peak_idx == 0:
            search_region = autocorr[start_search:max_period]
            if len(search_region) > 0:
                local_max = np.argmax(search_region)
                if search_region[local_max] > 0.25:
                    peak_idx = local_max + start_search
        
        if peak_idx <= 0:
            return 0
        
        # Parabolic interpolation for sub-sample accuracy
        if peak_idx > 1 and peak_idx < len(autocorr) - 1:
            alpha = autocorr[peak_idx - 1]
            beta = autocorr[peak_idx]
            gamma = autocorr[peak_idx + 1]
            
            denom = alpha - 2 * beta + gamma
            if abs(denom) > 1e-10 and beta > alpha and beta > gamma:
                p = 0.5 * (alpha - gamma) / denom
                peak_idx = peak_idx + p
        
        if peak_idx > 0:
            frequency = self.sample_rate / peak_idx
            # Sanity check
            if min_freq <= frequency <= max_freq:
                return frequency
        
        return 0
    
    def _update_display(self, frequency):
        """Update the UI with detected pitch"""
        if frequency <= 0 or frequency > 2000:
            self.gauge.set_tuning("—", None, 0, 0, False)
            return
        
        note_name, octave, cents = freq_to_note(frequency)
        
        if note_name is None:
            self.gauge.set_tuning("—", None, 0, 0, False)
            return
        
        # Update gauge
        self.gauge.set_tuning(note_name, octave, cents, frequency, True)
    
    def _on_dialog_closed(self, dialog):
        """Clean up when dialog is closed"""
        self._stop_tuner()


class AudioRecorderApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='org.gnome.AudioRecorder')
        self.monitoring = False
        self.monitor_process = None
        self.tracks = []
        self.next_track_number = 1
        self.project_file = None
        self.project_dirty = False
        self.config_dir = self._get_config_dir()
        self.config_file = os.path.join(self.config_dir, 'config.json')
    
    def _get_config_dir(self):
        """Get the application config directory (XDG compliant)"""
        xdg_config = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        config_dir = os.path.join(xdg_config, 'audio-recorder')
        os.makedirs(config_dir, exist_ok=True)
        return config_dir
    
    def get_recent_project(self):
        """Get the most recent project path from config"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    recent = config.get('recent_project')
                    if recent and os.path.exists(recent):
                        return recent
        except Exception:
            pass
        return None
    
    def set_recent_project(self, project_path):
        """Save the most recent project path to config"""
        try:
            config = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
            config['recent_project'] = project_path
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass
        
    def do_activate(self):
        # Register custom icon path for tuning fork icon
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon_theme.add_search_path(os.path.join(ICONS_DIR, 'hicolor', 'scalable', 'actions'))
        
        win = AudioRecorderWindow(application=self)
        self.setup_accelerators()
        win.present()
    
    def setup_accelerators(self):
        """Set up keyboard shortcuts for all actions"""
        self.set_accels_for_action("win.new_project", ["<Control>n"])
        self.set_accels_for_action("win.open_project", ["<Control>o"])
        self.set_accels_for_action("win.save_project", ["<Control>s"])
        self.set_accels_for_action("win.save_project_as", ["<Control><Shift>s"])
        self.set_accels_for_action("win.import_audio", ["<Control>i"])
        self.set_accels_for_action("win.export_tracks", ["<Control><Shift>t"])
        self.set_accels_for_action("win.export_mixed", ["<Control><Shift>x"])
        self.set_accels_for_action("win.export_all", ["<Control><Shift>a"])
        self.set_accels_for_action("win.add_track", ["<Control>t"])
        self.set_accels_for_action("win.play_pause_all", ["<Control>space"])
        self.set_accels_for_action("win.stop_all", ["<Control>period"])
        self.set_accels_for_action("win.toggle_monitoring", ["<Control>l"])
        self.set_accels_for_action("win.show_tuner", ["<Control>u"])
        self.set_accels_for_action("win.show_drum_machine", ["<Control>d"])
        self.set_accels_for_action("win.show_help", ["F1"])
        self.set_accels_for_action("win.show_shortcuts", ["<Control>question"])


@Gtk.Template(filename=os.path.join(UI_DIR, 'track-row.ui'))
class TrackRow(Gtk.ListBoxRow):
    __gtype_name__ = 'TrackRow'
    
    # Template children
    track_label = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    edit_btn = Gtk.Template.Child()
    record_btn = Gtk.Template.Child()
    stop_btn = Gtk.Template.Child()
    play_btn = Gtk.Template.Child()
    volume_scale = Gtk.Template.Child()
    mute_btn = Gtk.Template.Child()
    delete_btn = Gtk.Template.Child()
    
    def __init__(self, track, window):
        super().__init__()
        self.track = track
        self.window = window
        
        self.track_label.set_text(track.name)
        self.status_label.set_text("Ready")
        
        # Set initial volume and tooltip
        vol_percent = int(track.volume * 100)
        self.volume_scale.set_value(vol_percent)
        self.volume_scale.set_tooltip_text(f"Track volume: {vol_percent}%")
        
        # Connect signals
        self.edit_btn.connect("clicked", self.on_edit_clicked)
        self.record_btn.connect("clicked", self.on_record_clicked)
        self.stop_btn.connect("clicked", self.on_stop_clicked)
        self.play_btn.connect("clicked", self.on_play_clicked)
        self.volume_scale.connect("value-changed", self.on_volume_changed)
        self.mute_btn.connect("toggled", self.on_mute_toggled)
        self.delete_btn.connect("clicked", self.on_delete_clicked)
    
    def on_edit_clicked(self, button):
        self.window.on_track_rename(self)
    
    def on_record_clicked(self, button):
        self.window.on_track_record(self)
    
    def on_stop_clicked(self, button):
        self.window.on_track_stop(self)
    
    def on_play_clicked(self, button):
        self.window.on_track_play(self)
    
    def on_mute_toggled(self, button):
        self.window.on_track_mute(self)
    
    def on_volume_changed(self, scale):
        self.window.on_track_volume_changed(self)
    
    def on_delete_clicked(self, button):
        self.window.on_track_delete(self)
    
    def set_recording(self, recording):
        self.record_btn.set_sensitive(not recording)
        self.stop_btn.set_sensitive(recording)
        self.play_btn.set_sensitive(False)
        if recording:
            self.status_label.set_text("Recording…")
            self.add_css_class("error")
        else:
            self.status_label.set_text("Stopped")
            self.remove_css_class("error")
            if self.track.temp_file and os.path.exists(self.track.temp_file):
                self.play_btn.set_sensitive(True)
    
    def set_playing(self, playing, paused=False):
        if playing:
            self.play_btn.set_icon_name("media-playback-pause-symbolic")
            self.status_label.set_text("Playing…" if not self.track.muted else "Playing (muted)…")
        elif paused:
            self.play_btn.set_icon_name("media-playback-start-symbolic")
            self.status_label.set_text("Paused" if not self.track.muted else "Paused (muted)")
        else:
            self.play_btn.set_icon_name("media-playback-start-symbolic")
            self.status_label.set_text("Ready")
    
    def set_muted(self, muted):
        if muted:
            self.mute_btn.set_icon_name("audio-volume-muted-symbolic")
            self.mute_btn.set_tooltip_text("Unmute track")
        else:
            self.mute_btn.set_icon_name("audio-volume-high-symbolic")
            self.mute_btn.set_tooltip_text("Mute track")
        
        if self.track.playing:
            self.status_label.set_text("Playing (muted)…" if muted else "Playing…")
        elif self.track.paused:
            self.status_label.set_text("Paused (muted)" if muted else "Paused")


@Gtk.Template(filename=os.path.join(UI_DIR, 'window.ui'))
class AudioRecorderWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'AudioRecorderWindow'
    
    # Template children
    add_track_btn = Gtk.Template.Child()
    play_all_btn = Gtk.Template.Child()
    stop_all_btn = Gtk.Template.Child()
    monitor_toggle = Gtk.Template.Child()
    tuner_btn = Gtk.Template.Child()
    drum_machine_btn = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    track_list = Gtk.Template.Child()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Start maximized by default
        self.maximize()
        
        self.playing_tracks = set()
        self.monitor_latency = '64'
        self.drum_machine_panel = None
        self.drum_machine_visible = False
        self._pending_drum_machine_state = None
        
        # Connect signals
        self.add_track_btn.connect("clicked", self.on_add_track)
        self.play_all_btn.connect("clicked", self.on_play_all)
        self.stop_all_btn.connect("clicked", self.on_stop_all)
        self.monitor_toggle.connect("toggled", self.on_monitor_toggled)
        self.tuner_btn.connect("clicked", lambda btn: self.on_show_tuner(None, None))
        self.drum_machine_btn.connect("toggled", self._on_drum_machine_btn_toggled)
        
        # Create actions
        self.create_actions()
        
        # Load recent project or create new
        self.load_recent_or_new_project()
        
        # Connect close request
        self.connect("close-request", self.on_close_request)
    
    def create_actions(self):
        actions = [
            ("new_project", self.on_new_project),
            ("open_project", self.on_open_project),
            ("save_project", self.on_save_project),
            ("save_project_as", self.on_save_project_as),
            ("import_audio", self.on_import_audio),
            ("add_track", lambda a, p: self.add_track()),
            ("play_pause_all", lambda a, p: self.on_play_all(None)),
            ("stop_all", lambda a, p: self.stop_all_playback()),
            ("toggle_monitoring", self.on_toggle_monitoring_action),
            ("show_tuner", self.on_show_tuner),
            ("show_drum_machine", self.on_show_drum_machine),
            ("show_help", self.on_show_help),
            ("show_shortcuts", self.on_show_shortcuts),
            ("about", self.on_about),
        ]
        
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        
        # Export actions (initially disabled)
        self.export_tracks_action = Gio.SimpleAction.new("export_tracks", None)
        self.export_tracks_action.connect("activate", self.on_export_individual)
        self.export_tracks_action.set_enabled(False)
        self.add_action(self.export_tracks_action)
        
        self.export_mixed_action = Gio.SimpleAction.new("export_mixed", None)
        self.export_mixed_action.connect("activate", self.on_export_mixed)
        self.export_mixed_action.set_enabled(False)
        self.add_action(self.export_mixed_action)
        
        self.export_all_action = Gio.SimpleAction.new("export_all", None)
        self.export_all_action.connect("activate", self.on_export_all)
        self.export_all_action.set_enabled(False)
        self.add_action(self.export_all_action)
        
        # Latency action (stateful with string parameter)
        latency_action = Gio.SimpleAction.new_stateful(
            "set_latency",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(self.monitor_latency)
        )
        latency_action.connect("activate", self.on_set_latency)
        self.add_action(latency_action)
    
    def load_recent_or_new_project(self):
        """Load the most recent project if available, otherwise create a new one"""
        app = self.get_application()
        recent_project = app.get_recent_project()
        
        if recent_project:
            try:
                self.load_project(recent_project)
                return
            except Exception:
                pass
        
        self.add_track()
        app.project_dirty = False
    
    # ==================== Project Management ====================
    
    def on_new_project(self, action, param):
        if self.has_unsaved_changes():
            self.show_save_confirmation_dialog(self.create_new_project)
        else:
            self.create_new_project()
    
    def has_unsaved_changes(self):
        app = self.get_application()
        return app.project_dirty
    
    def show_save_confirmation_dialog(self, callback):
        dialog = Adw.AlertDialog(
            heading="Save current project?",
            body="You have unsaved work. Do you want to save it before continuing?"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("discard", "Don't Save")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.connect("response", self.on_save_confirmation_response, callback)
        dialog.present(self)
    
    def on_save_confirmation_response(self, dialog, response, callback):
        if response == "save":
            app = self.get_application()
            if app.project_file:
                self.save_project(app.project_file)
                callback()
            else:
                self.pending_callback = callback
                save_dialog = Gtk.FileDialog.new()
                save_dialog.set_title("Save Project As")
                save_dialog.set_initial_name("project")
                save_dialog.save(self, None, self.on_save_before_action_response)
        elif response == "discard":
            callback()
    
    def on_save_before_action_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                self.save_project(file.get_path())
                if hasattr(self, 'pending_callback'):
                    self.pending_callback()
                    delattr(self, 'pending_callback')
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to save project: {str(e)}")
    
    def create_new_project(self):
        app = self.get_application()
        
        while self.track_list.get_first_child():
            row = self.track_list.get_first_child()
            self.on_track_delete(row)
        
        app.tracks = []
        app.next_track_number = 1
        app.project_file = None
        app.project_dirty = False
        
        # Reset drum machine to defaults
        self._pending_drum_machine_state = None
        if self.drum_machine_panel is not None:
            self.drum_machine_panel.reset_to_defaults()
        
        self.add_track()
        app.project_dirty = False
        self.status_label.set_label("New project created")
        self.update_title()
    
    def on_open_project(self, action, param):
        if self.has_unsaved_changes():
            self.show_save_confirmation_dialog(self.show_open_project_dialog)
        else:
            self.show_open_project_dialog()
    
    def show_open_project_dialog(self):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Open Project")
        
        filter_atr = Gtk.FileFilter()
        filter_atr.set_name("Audio Recorder Projects (*.atr)")
        filter_atr.add_pattern("*.atr")
        
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_atr)
        dialog.set_filters(filters)
        
        dialog.open(self, None, self.on_open_project_response)
    
    def on_open_project_response(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                self.load_project(file.get_path())
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to open project: {str(e)}")
    
    def load_project(self, project_path):
        app = self.get_application()
        
        try:
            with open(project_path, 'r') as f:
                project_data = json.load(f)
            
            while self.track_list.get_first_child():
                row = self.track_list.get_first_child()
                self.on_track_delete(row)
            
            app.tracks = []
            app.project_file = project_path
            project_dir = os.path.dirname(project_path)
            
            for track_data in project_data['tracks']:
                track = Track(track_data['name'])
                
                audio_file = os.path.join(project_dir, track_data['audio_file'])
                if os.path.exists(audio_file):
                    fd, track.temp_file = tempfile.mkstemp(suffix='.wav')
                    os.close(fd)
                    shutil.copy2(audio_file, track.temp_file)
                
                # Restore volume and muted state
                track.volume = track_data.get('volume', 1.0)
                track.muted = track_data.get('muted', False)
                
                app.tracks.append(track)
                
                row = TrackRow(track, self)
                self.track_list.append(row)
                
                # Apply restored volume and muted state to UI
                vol_percent = int(track.volume * 100)
                row.volume_scale.set_value(vol_percent)
                row.volume_scale.set_tooltip_text(f"Track volume: {vol_percent}%")
                row.mute_btn.set_active(track.muted)
                row.set_muted(track.muted)
                
                if track.temp_file:
                    row.play_btn.set_sensitive(True)
            
            app.next_track_number = project_data.get('next_track_number', len(app.tracks) + 1)
            
            # Load drum machine state if present in project
            if 'drum_machine' in project_data:
                if self.drum_machine_panel is not None:
                    self.drum_machine_panel.set_state(project_data['drum_machine'])
                else:
                    # Store for later when drum machine is first opened
                    self._pending_drum_machine_state = project_data['drum_machine']
            
            app.project_dirty = False
            app.set_recent_project(project_path)
            self.status_label.set_label("Project loaded")
            self.update_export_buttons()
            self.update_title()
            
        except Exception as e:
            self.show_error_dialog(f"Failed to load project: {str(e)}")
    
    def on_save_project(self, action, param):
        app = self.get_application()
        if app.project_file:
            self.save_project(app.project_file)
        else:
            self.on_save_project_as(action, param)
    
    def on_save_project_as(self, action, param):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Save Project As")
        dialog.set_initial_name("project")
        dialog.save(self, None, self.on_save_project_response)
    
    def on_save_project_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                self.save_project(file.get_path())
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to save project: {str(e)}")
    
    def save_project(self, project_path):
        app = self.get_application()
        
        try:
            if os.path.isdir(project_path):
                project_dir = project_path
            elif project_path.endswith('.atr'):
                project_dir = os.path.dirname(project_path)
            else:
                project_dir = project_path
            
            project_name = os.path.basename(project_dir)
            audio_dir = os.path.join(project_dir, "audio")
            project_file = os.path.join(project_dir, f"{project_name}.atr")
            
            os.makedirs(project_dir, exist_ok=True)
            os.makedirs(audio_dir, exist_ok=True)
            
            if os.path.exists(audio_dir):
                for old_file in os.listdir(audio_dir):
                    old_file_path = os.path.join(audio_dir, old_file)
                    if os.path.isfile(old_file_path):
                        os.unlink(old_file_path)
            
            tracks_data = []
            for track in app.tracks:
                if track.temp_file and os.path.exists(track.temp_file):
                    audio_filename = f"{track.name}.wav"
                    audio_path = os.path.join(audio_dir, audio_filename)
                    shutil.copy2(track.temp_file, audio_path)
                    
                    tracks_data.append({
                        'name': track.name,
                        'audio_file': os.path.join("audio", audio_filename),
                        'volume': track.volume,
                        'muted': track.muted
                    })
            
            project_data = {
                'tracks': tracks_data,
                'next_track_number': app.next_track_number
            }
            
            # Include drum machine state if it exists
            if self.drum_machine_panel is not None:
                project_data['drum_machine'] = self.drum_machine_panel.get_state()
            
            with open(project_file, 'w') as f:
                json.dump(project_data, f, indent=2)
            
            app.project_file = project_file
            app.project_dirty = False
            app.set_recent_project(project_file)
            self.status_label.set_label(f"Project saved: {project_name}")
            self.update_title()
            
        except Exception as e:
            self.show_error_dialog(f"Failed to save project: {str(e)}")
    
    # ==================== Import/Export ====================
    
    def on_import_audio(self, action, param):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Import Audio File")
        
        filter_audio = Gtk.FileFilter()
        filter_audio.set_name("Audio Files (*.wav)")
        filter_audio.add_pattern("*.wav")
        
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_audio)
        dialog.set_filters(filters)
        
        dialog.open(self, None, self.on_import_audio_response)
    
    def on_import_audio_response(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                self.import_audio_file(file.get_path())
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to import audio: {str(e)}")
    
    def import_audio_file(self, audio_path):
        app = self.get_application()
        
        try:
            track_name = os.path.splitext(os.path.basename(audio_path))[0]
            track = Track(track_name)
            
            fd, track.temp_file = tempfile.mkstemp(suffix='.wav')
            os.close(fd)
            shutil.copy2(audio_path, track.temp_file)
            
            app.tracks.append(track)
            
            row = TrackRow(track, self)
            self.track_list.append(row)
            row.play_btn.set_sensitive(True)
            
            self.status_label.set_label(f"Imported: {track_name}")
            self.update_export_buttons()
            app.project_dirty = True
            
        except Exception as e:
            self.show_error_dialog(f"Failed to import audio: {str(e)}")
    
    def on_export_individual(self, action, param):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Export Tracks")
        dialog.select_folder(self, None, self.on_export_individual_response)
    
    def on_export_individual_response(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                app = self.get_application()
                folder_path = folder.get_path()
                
                for track in app.tracks:
                    if track.temp_file and os.path.exists(track.temp_file):
                        filename = f"{track.name}.wav"
                        destination = os.path.join(folder_path, filename)
                        shutil.copy2(track.temp_file, destination)
                
                self.status_label.set_label(f"Exported {len(app.tracks)} tracks")
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to export: {str(e)}")
    
    def on_export_mixed(self, action, param):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Export Mixed")
        dialog.set_initial_name("mixed.wav")
        dialog.save(self, None, self.on_export_mixed_response)
    
    def on_export_mixed_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                self.mix_tracks(file.get_path())
                self.status_label.set_label("Exported mixed track")
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to export: {str(e)}")
    
    def on_export_all(self, action, param):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Export All")
        dialog.select_folder(self, None, self.on_export_all_response)
    
    def on_export_all_response(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                app = self.get_application()
                folder_path = folder.get_path()
                
                for track in app.tracks:
                    if track.temp_file and os.path.exists(track.temp_file):
                        filename = f"{track.name}.wav"
                        destination = os.path.join(folder_path, filename)
                        shutil.copy2(track.temp_file, destination)
                
                mixed_path = os.path.join(folder_path, "mixed.wav")
                self.mix_tracks(mixed_path)
                
                self.status_label.set_label("Exported all tracks and mix")
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to export: {str(e)}")
    
    def mix_tracks(self, output_path):
        """Mix all tracks using GStreamer audiomixer for proper audio quality"""
        app = self.get_application()
        
        valid_tracks = [t for t in app.tracks if t.temp_file and os.path.exists(t.temp_file)]
        if not valid_tracks:
            return
        
        # Build GStreamer pipeline for mixing
        # Pipeline: filesrc ! decodebin ! audioconvert ! audiomixer ! audioconvert ! wavenc ! filesink
        
        pipeline = Gst.Pipeline.new("mixer")
        mixer = Gst.ElementFactory.make("audiomixer", "mixer")
        audioconvert = Gst.ElementFactory.make("audioconvert", "convert")
        wavenc = Gst.ElementFactory.make("wavenc", "encoder")
        filesink = Gst.ElementFactory.make("filesink", "sink")
        
        if not all([mixer, audioconvert, wavenc, filesink]):
            self.show_error_dialog("Failed to create GStreamer elements for mixing")
            return
        
        filesink.set_property("location", output_path)
        
        pipeline.add(mixer)
        pipeline.add(audioconvert)
        pipeline.add(wavenc)
        pipeline.add(filesink)
        
        mixer.link(audioconvert)
        audioconvert.link(wavenc)
        wavenc.link(filesink)
        
        # Add a source for each track
        for i, track in enumerate(valid_tracks):
            filesrc = Gst.ElementFactory.make("filesrc", f"source{i}")
            decodebin = Gst.ElementFactory.make("decodebin", f"decode{i}")
            convert = Gst.ElementFactory.make("audioconvert", f"convert{i}")
            resample = Gst.ElementFactory.make("audioresample", f"resample{i}")
            
            if not all([filesrc, decodebin, convert, resample]):
                continue
            
            filesrc.set_property("location", track.temp_file)
            
            pipeline.add(filesrc)
            pipeline.add(decodebin)
            pipeline.add(convert)
            pipeline.add(resample)
            
            filesrc.link(decodebin)
            convert.link(resample)
            resample.link(mixer)
            
            # Connect decodebin's dynamic pad to audioconvert
            decodebin.connect("pad-added", self._on_decode_pad_added, convert)
        
        # Run the pipeline
        pipeline.set_state(Gst.State.PLAYING)
        
        # Wait for completion
        bus = pipeline.get_bus()
        bus.timed_pop_filtered(Gst.CLOCK_TIME_NONE, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        
        pipeline.set_state(Gst.State.NULL)
    
    def _on_decode_pad_added(self, decodebin, pad, audioconvert):
        """Handle dynamic pad from decodebin"""
        caps = pad.get_current_caps()
        if caps:
            struct = caps.get_structure(0)
            if struct.get_name().startswith("audio"):
                sink_pad = audioconvert.get_static_pad("sink")
                if not sink_pad.is_linked():
                    pad.link(sink_pad)
    
    # ==================== Track Management ====================
    
    def update_title(self):
        app = self.get_application()
        if app.project_file:
            project_name = os.path.splitext(os.path.basename(app.project_file))[0]
            self.set_title(f"{project_name} — Audio Recorder")
        else:
            self.set_title("Audio Recorder")
    
    def add_track(self):
        app = self.get_application()
        track = Track(f"Track {app.next_track_number}")
        app.next_track_number += 1
        app.tracks.append(track)
        
        row = TrackRow(track, self)
        self.track_list.append(row)
        self.update_export_buttons()
        app.project_dirty = True
        
    def on_add_track(self, button):
        self.add_track()
    
    def on_track_record(self, row):
        track = row.track
        
        fd, track.temp_file = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        
        try:
            track.record_process = subprocess.Popen([
                'pw-record', '--target', 'auto', track.temp_file
            ])
            track.recording = True
            row.set_recording(True)
        except FileNotFoundError:
            self.show_error_dialog("PipeWire tools not found. Please install pipewire-utils package.")
            if track.temp_file:
                os.unlink(track.temp_file)
                track.temp_file = None
        except Exception as e:
            self.show_error_dialog(f"Failed to start recording: {str(e)}")
            if track.temp_file:
                os.unlink(track.temp_file)
                track.temp_file = None
    
    def on_track_stop(self, row):
        track = row.track
        
        if track.recording and track.record_process:
            track.record_process.terminate()
            track.record_process.wait()
            track.record_process = None
            track.recording = False
            row.set_recording(False)
            self.update_export_buttons()
            app = self.get_application()
            app.project_dirty = True
    
    def on_track_play(self, row):
        track = row.track
        
        if track.playing:
            if track.pipeline:
                track.pipeline.set_state(Gst.State.PAUSED)
            track.playing = False
            track.paused = True
            row.set_playing(False, paused=True)
            self.playing_tracks.discard(row)
        elif track.paused:
            if track.pipeline:
                track.pipeline.set_state(Gst.State.PLAYING)
            track.playing = True
            track.paused = False
            row.set_playing(True)
            self.playing_tracks.add(row)
            
            if len(self.playing_tracks) == 1:
                GLib.timeout_add(100, self.check_playback_finished)
        else:
            if track.temp_file and os.path.exists(track.temp_file):
                try:
                    track.pipeline = Gst.ElementFactory.make("playbin", f"playbin-{track.name}")
                    track.pipeline.set_property("uri", f"file://{track.temp_file}")
                    
                    # Apply volume (0 if muted, otherwise track volume)
                    if track.muted:
                        track.pipeline.set_property("volume", 0.0)
                    else:
                        track.pipeline.set_property("volume", track.volume)
                    
                    track.pipeline.set_state(Gst.State.PLAYING)
                    track.playing = True
                    track.paused = False
                    row.set_playing(True)
                    self.playing_tracks.add(row)
                    
                    if len(self.playing_tracks) == 1:
                        GLib.timeout_add(100, self.check_playback_finished)
                except Exception as e:
                    self.show_error_dialog(f"Failed to play track: {str(e)}")
        
        self.update_global_playback_buttons()
    
    def on_track_mute(self, row):
        track = row.track
        track.muted = row.mute_btn.get_active()
        
        if track.pipeline:
            if track.muted:
                track.pipeline.set_property("volume", 0.0)
            else:
                track.pipeline.set_property("volume", track.volume)
        
        row.set_muted(track.muted)
        app = self.get_application()
        app.project_dirty = True
    
    def on_track_volume_changed(self, row):
        track = row.track
        value = row.volume_scale.get_value()
        track.volume = value / 100.0
        
        # Update tooltip with percentage
        row.volume_scale.set_tooltip_text(f"Track volume: {int(value)}%")
        
        # Apply volume to pipeline if playing and not muted
        if track.pipeline and not track.muted:
            track.pipeline.set_property("volume", track.volume)
        
        app = self.get_application()
        app.project_dirty = True
    
    def on_track_rename(self, row):
        track = row.track
        
        dialog = Adw.AlertDialog(heading="Rename Track", body="Enter a new name for the track:")
        
        entry = Gtk.Entry()
        entry.set_text(track.name)
        entry.set_activates_default(True)
        dialog.set_extra_child(entry)
        
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("rename")
        dialog.set_close_response("cancel")
        
        dialog.connect("response", self.on_rename_response, row, entry)
        dialog.present(self)
    
    def on_rename_response(self, dialog, response, row, entry):
        if response == "rename":
            new_name = entry.get_text().strip()
            if new_name:
                row.track.name = new_name
                row.track_label.set_text(new_name)
                app = self.get_application()
                app.project_dirty = True
    
    def on_track_delete(self, row):
        app = self.get_application()
        track = row.track
        
        if track.recording and track.record_process:
            track.record_process.terminate()
            track.record_process.wait()
        
        if track.pipeline:
            track.pipeline.set_state(Gst.State.NULL)
            track.pipeline = None
        track.playing = False
        track.paused = False
        self.playing_tracks.discard(row)
        
        if track.temp_file and os.path.exists(track.temp_file):
            os.unlink(track.temp_file)
        
        app.tracks.remove(track)
        self.track_list.remove(row)
        self.update_export_buttons()
        app.project_dirty = True
    
    # ==================== Playback ====================
    
    def check_playback_finished(self):
        finished_tracks = []
        for row in list(self.playing_tracks):
            track = row.track
            if track.pipeline:
                _, state, _ = track.pipeline.get_state(0)
                if state == Gst.State.NULL:
                    finished_tracks.append(row)
                else:
                    bus = track.pipeline.get_bus()
                    msg = bus.pop_filtered(Gst.MessageType.EOS | Gst.MessageType.ERROR)
                    if msg:
                        finished_tracks.append(row)
        
        for row in finished_tracks:
            track = row.track
            if track.pipeline:
                track.pipeline.set_state(Gst.State.NULL)
                track.pipeline = None
            track.playing = False
            track.paused = False
            row.set_playing(False)
            self.playing_tracks.discard(row)
        
        self.update_global_playback_buttons()
        return len(self.playing_tracks) > 0
    
    def on_play_all(self, button):
        app = self.get_application()
        
        if len(self.playing_tracks) > 0:
            self.pause_all_playback()
            return
        
        has_paused = any(t.paused for t in app.tracks)
        
        if has_paused:
            self.resume_all_playback()
        else:
            self.start_all_playback()
    
    def start_all_playback(self):
        app = self.get_application()
        row = self.track_list.get_first_child()
        started_any = False
        
        while row:
            if isinstance(row, TrackRow):
                track = row.track
                if track.temp_file and os.path.exists(track.temp_file) and not track.playing:
                    try:
                        if track.pipeline:
                            track.pipeline.set_state(Gst.State.NULL)
                            track.pipeline = None
                        
                        track.pipeline = Gst.ElementFactory.make("playbin", f"playbin-{track.name}")
                        track.pipeline.set_property("uri", f"file://{track.temp_file}")
                        
                        # Apply volume (0 if muted, otherwise track volume)
                        if track.muted:
                            track.pipeline.set_property("volume", 0.0)
                        else:
                            track.pipeline.set_property("volume", track.volume)
                        
                        track.pipeline.set_state(Gst.State.PLAYING)
                        track.playing = True
                        track.paused = False
                        row.set_playing(True)
                        self.playing_tracks.add(row)
                        started_any = True
                    except Exception as e:
                        self.show_error_dialog(f"Failed to play track {track.name}: {str(e)}")
            row = row.get_next_sibling()
        
        if started_any:
            GLib.timeout_add(100, self.check_playback_finished)
        
        self.update_global_playback_buttons()
    
    def pause_all_playback(self):
        for row in list(self.playing_tracks):
            track = row.track
            if track.playing and track.pipeline:
                track.pipeline.set_state(Gst.State.PAUSED)
                track.playing = False
                track.paused = True
                row.set_playing(False, paused=True)
        
        self.playing_tracks.clear()
        self.update_global_playback_buttons()
    
    def resume_all_playback(self):
        row = self.track_list.get_first_child()
        resumed_any = False
        
        while row:
            if isinstance(row, TrackRow):
                track = row.track
                if track.paused and track.pipeline:
                    track.pipeline.set_state(Gst.State.PLAYING)
                    track.playing = True
                    track.paused = False
                    row.set_playing(True)
                    self.playing_tracks.add(row)
                    resumed_any = True
            row = row.get_next_sibling()
        
        if resumed_any:
            GLib.timeout_add(100, self.check_playback_finished)
        
        self.update_global_playback_buttons()
    
    def on_stop_all(self, button):
        self.stop_all_playback()
    
    def stop_all_playback(self):
        for row in list(self.playing_tracks):
            track = row.track
            if track.pipeline:
                track.pipeline.set_state(Gst.State.NULL)
                track.pipeline = None
            track.playing = False
            track.paused = False
            row.set_playing(False)
        
        self.playing_tracks.clear()
        
        row = self.track_list.get_first_child()
        while row:
            if isinstance(row, TrackRow):
                track = row.track
                if track.paused and track.pipeline:
                    track.pipeline.set_state(Gst.State.NULL)
                    track.pipeline = None
                    track.paused = False
                    row.set_playing(False)
            row = row.get_next_sibling()
        
        self.update_global_playback_buttons()
    
    def update_global_playback_buttons(self):
        app = self.get_application()
        
        has_recordings = any(t.temp_file and os.path.exists(t.temp_file) for t in app.tracks)
        any_playing = len(self.playing_tracks) > 0
        any_paused = any(t.paused for t in app.tracks)
        
        if any_playing:
            self.play_all_btn.set_icon_name("media-playback-pause-symbolic")
            self.play_all_btn.set_tooltip_text("Pause all tracks (Ctrl+Space)")
        else:
            self.play_all_btn.set_icon_name("media-playback-start-symbolic")
            if any_paused:
                self.play_all_btn.set_tooltip_text("Resume all tracks (Ctrl+Space)")
            else:
                self.play_all_btn.set_tooltip_text("Play all tracks (Ctrl+Space)")
        
        self.play_all_btn.set_sensitive(has_recordings or any_paused)
        self.stop_all_btn.set_sensitive(any_playing or any_paused)
    
    def update_export_buttons(self):
        app = self.get_application()
        has_recordings = any(t.temp_file and os.path.exists(t.temp_file) for t in app.tracks)
        self.export_tracks_action.set_enabled(has_recordings)
        self.export_mixed_action.set_enabled(has_recordings)
        self.export_all_action.set_enabled(has_recordings)
        self.update_global_playback_buttons()
    
    # ==================== Monitoring ====================
    
    def on_monitor_toggled(self, button):
        if button.get_active():
            self.start_monitoring()
            self.status_label.set_label(f"Monitoring active (latency: {self.monitor_latency} samples)")
        else:
            self.stop_monitoring()
            self.status_label.set_label("Ready to record")
    
    def on_toggle_monitoring_action(self, action, param):
        self.monitor_toggle.set_active(not self.monitor_toggle.get_active())
    
    def on_set_latency(self, action, param):
        """Set the monitoring latency"""
        new_latency = param.get_string()
        self.monitor_latency = new_latency
        action.set_state(param)
        
        # If monitoring is active, restart it with new latency
        app = self.get_application()
        if app.monitoring:
            self.stop_monitoring()
            self.start_monitoring()
            self.status_label.set_label(f"Monitoring active (latency: {new_latency} samples)")
    
    def start_monitoring(self):
        app = self.get_application()
        
        if app.monitoring:
            return
        
        try:
            monitor_record = subprocess.Popen([
                'pw-record', '--target', 'auto', '--latency', self.monitor_latency,
                '--rate', '48000', '-'
            ], stdout=subprocess.PIPE)
            
            monitor_play = subprocess.Popen([
                'pw-play', '--target', 'auto', '--latency', self.monitor_latency,
                '--rate', '48000', '-'
            ], stdin=monitor_record.stdout)
            
            monitor_record.stdout.close()
            
            app.monitor_process = (monitor_record, monitor_play)
            app.monitoring = True
        except FileNotFoundError:
            self.show_error_dialog("PipeWire tools not found for monitoring.")
            self.monitor_toggle.set_active(False)
        except Exception as e:
            self.show_error_dialog(f"Failed to start monitoring: {str(e)}")
            self.monitor_toggle.set_active(False)
    
    def stop_monitoring(self):
        app = self.get_application()
        
        if app.monitoring and app.monitor_process:
            record_proc, play_proc = app.monitor_process
            
            # Terminate both processes
            try:
                record_proc.terminate()
            except:
                pass
            try:
                play_proc.terminate()
            except:
                pass
            
            # Wait for them to finish
            try:
                record_proc.wait(timeout=2)
            except:
                try:
                    record_proc.kill()
                    record_proc.wait(timeout=1)
                except:
                    pass
            
            try:
                play_proc.wait(timeout=2)
            except:
                try:
                    play_proc.kill()
                    play_proc.wait(timeout=1)
                except:
                    pass
            
            app.monitor_process = None
            app.monitoring = False
    
    # ==================== Help & About ====================
    
    def on_show_shortcuts(self, action, param):
        shortcuts_window = Gtk.ShortcutsWindow(transient_for=self, modal=True)
        
        section = Gtk.ShortcutsSection(section_name="shortcuts", title="Shortcuts")
        section.set_visible(True)
        
        groups_data = [
            ("Project", [
                ("New Project", "<Control>n"),
                ("Open Project", "<Control>o"),
                ("Save Project", "<Control>s"),
                ("Save Project As", "<Control><Shift>s"),
            ]),
            ("Tracks", [
                ("Add Track", "<Control>t"),
                ("Import Audio", "<Control>i"),
            ]),
            ("Playback", [
                ("Play / Pause All", "<Control>space"),
                ("Stop All", "<Control>period"),
                ("Toggle Monitoring", "<Control>l"),
            ]),
            ("Tools", [
                ("Chromatic Tuner", "<Control>u"),
                ("Drum Machine", "<Control>d"),
            ]),
            ("Export", [
                ("Export Tracks", "<Control><Shift>t"),
                ("Export Mixed", "<Control><Shift>x"),
                ("Export All", "<Control><Shift>a"),
            ]),
            ("Help", [
                ("Help", "F1"),
                ("Keyboard Shortcuts", "<Control>question"),
            ]),
        ]
        
        for group_title, shortcuts in groups_data:
            group = Gtk.ShortcutsGroup(title=group_title)
            group.set_visible(True)
            for title, accel in shortcuts:
                shortcut = Gtk.ShortcutsShortcut(title=title, accelerator=accel)
                shortcut.set_visible(True)
                group.append(shortcut)
            section.append(group)
        
        shortcuts_window.add_section(section)
        shortcuts_window.present()
    
    def on_show_tuner(self, action, param):
        """Open the chromatic tuner dialog"""
        tuner = TunerDialog(self)
        tuner.present(self)
    
    def _on_drum_machine_btn_toggled(self, btn):
        """Handle drum machine toggle button"""
        if btn.get_active() != self.drum_machine_visible:
            self.on_show_drum_machine(None, None)
    
    def on_show_drum_machine(self, action, param):
        """Toggle the drum machine panel"""
        if self.drum_machine_panel is None:
            # Create the drum machine panel
            self.drum_machine_panel = DrumMachinePanel()
            
            # Load pending state from project if available
            if hasattr(self, '_pending_drum_machine_state') and self._pending_drum_machine_state:
                self.drum_machine_panel.set_state(self._pending_drum_machine_state)
                self._pending_drum_machine_state = None
            
            # Connect to changes to mark project dirty
            self.drum_machine_panel.connect_dirty_callback(self._on_drum_machine_changed)
            
            # Find the main content box by going up from status_label
            # status_label -> main_box
            main_box = self.status_label.get_parent()
            if main_box and hasattr(main_box, 'append'):
                main_box.append(self.drum_machine_panel)
            else:
                # Fallback: traverse from track_list
                widget = self.track_list
                while widget is not None:
                    parent = widget.get_parent()
                    if parent and isinstance(parent, Gtk.Box):
                        parent.append(self.drum_machine_panel)
                        break
                    widget = parent
        
        # Toggle visibility
        self.drum_machine_visible = not self.drum_machine_visible
        self.drum_machine_panel.set_visible(self.drum_machine_visible)
        
        # Sync toggle button state
        if self.drum_machine_btn.get_active() != self.drum_machine_visible:
            self.drum_machine_btn.set_active(self.drum_machine_visible)
        
        if not self.drum_machine_visible and self.drum_machine_panel:
            self.drum_machine_panel.cleanup()
    
    def _on_drum_machine_changed(self):
        """Called when drum machine state changes - mark project dirty"""
        app = self.get_application()
        app.project_dirty = True
        self.update_title()
    
    def on_show_help(self, action, param):
        if os.path.exists(HELP_DIR):
            try:
                subprocess.Popen(["yelp", os.path.join(HELP_DIR, "index.page")])
            except FileNotFoundError:
                self.show_error_dialog("Yelp is not installed. Please install yelp to view help.")
            except Exception as e:
                self.show_error_dialog(f"Could not open help: {str(e)}")
        else:
            self.show_error_dialog("Help files not found.")
    
    def on_about(self, action, param):
        about = Adw.AboutDialog(
            application_name="Audio Recorder",
            application_icon="org.gnome.AudioRecorder",
            version="1.0",
            developer_name="Audio Recorder Team",
            copyright="© 2024 Audio Recorder Team",
            license_type=Gtk.License.GPL_3_0,
            comments="A simple multi-track audio recorder for GNOME\n\nPowered by GStreamer, PipeWire, GTK4, and libadwaita",
            website="https://github.com/g0dd4rd/RacerX",
            developers=["Audio Recorder Team"],
        )
        about.present(self)
    
    # ==================== Dialogs ====================
    
    def show_error_dialog(self, message):
        dialog = Adw.AlertDialog(heading="Error", body=message)
        dialog.add_response("ok", "OK")
        dialog.present(self)
    
    def on_close_request(self, window):
        if self.has_unsaved_changes():
            self.show_close_confirmation_dialog()
            return True
        # Clean up all processes before closing
        self.cleanup_all_processes()
        return False
    
    def cleanup_all_processes(self):
        """Clean up all running processes and pipelines before exit"""
        app = self.get_application()
        
        # Stop monitoring
        self.stop_monitoring()
        
        # Stop all playback
        self.stop_all_playback()
        
        # Stop all recording processes and clean up GStreamer pipelines
        for track in app.tracks:
            # Stop recording
            if track.recording and track.record_process:
                try:
                    track.record_process.terminate()
                    track.record_process.wait(timeout=2)
                except:
                    try:
                        track.record_process.kill()
                    except:
                        pass
                track.record_process = None
                track.recording = False
            
            # Clean up GStreamer pipeline
            if track.pipeline:
                try:
                    track.pipeline.set_state(Gst.State.NULL)
                except:
                    pass
                track.pipeline = None
                track.playing = False
                track.paused = False
    
    def show_close_confirmation_dialog(self):
        dialog = Adw.AlertDialog(
            heading="Save current project?",
            body="You have unsaved work. Do you want to save it before closing?"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("discard", "Don't Save")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.connect("response", self.on_close_confirmation_response)
        dialog.present(self)
    
    def on_close_confirmation_response(self, dialog, response):
        if response == "save":
            app = self.get_application()
            if app.project_file:
                self.save_project(app.project_file)
                self.cleanup_all_processes()
                self.destroy()
            else:
                self.pending_close = True
                save_dialog = Gtk.FileDialog.new()
                save_dialog.set_title("Save Project As")
                save_dialog.set_initial_name("project")
                save_dialog.save(self, None, self.on_save_before_close_response)
        elif response == "discard":
            self.cleanup_all_processes()
            self.destroy()
    
    def on_save_before_close_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                self.save_project(file.get_path())
                self.cleanup_all_processes()
                self.destroy()
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to save project: {str(e)}")
        finally:
            if hasattr(self, 'pending_close'):
                delattr(self, 'pending_close')


def main():
    app = AudioRecorderApp()
    return app.run(None)


if __name__ == '__main__':
    main()
