#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Adw, GLib, Gio, Gst
import subprocess
import os
import tempfile
from pathlib import Path
import json
import shutil
import numpy as np
import math

# Initialize GStreamer
Gst.init(None)

# Get the directory where this script is located
# Support Flatpak environment via AUDIO_RECORDER_DATA_DIR
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('AUDIO_RECORDER_DATA_DIR', os.path.join(SCRIPT_DIR, 'data'))
UI_DIR = os.path.join(DATA_DIR, 'ui')
HELP_DIR = os.path.join(DATA_DIR, 'help', 'C')


class Track:
    def __init__(self, name, temp_file=None):
        self.name = name
        self.temp_file = temp_file
        self.recording = False
        self.record_process = None
        self.playing = False
        self.paused = False
        self.muted = False
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
        self.set_accels_for_action("win.show_help", ["F1"])
        self.set_accels_for_action("win.show_shortcuts", ["<Control>question"])


@Gtk.Template(filename=os.path.join(UI_DIR, 'track-row.ui'))
class TrackRow(Adw.ActionRow):
    __gtype_name__ = 'TrackRow'
    
    # Template children
    edit_btn = Gtk.Template.Child()
    record_btn = Gtk.Template.Child()
    stop_btn = Gtk.Template.Child()
    play_btn = Gtk.Template.Child()
    mute_btn = Gtk.Template.Child()
    delete_btn = Gtk.Template.Child()
    
    def __init__(self, track, window):
        super().__init__()
        self.track = track
        self.window = window
        
        self.set_title(track.name)
        self.set_subtitle("Ready")
        
        # Connect signals
        self.edit_btn.connect("clicked", self.on_edit_clicked)
        self.record_btn.connect("clicked", self.on_record_clicked)
        self.stop_btn.connect("clicked", self.on_stop_clicked)
        self.play_btn.connect("clicked", self.on_play_clicked)
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
    
    def on_delete_clicked(self, button):
        self.window.on_track_delete(self)
    
    def set_recording(self, recording):
        self.record_btn.set_sensitive(not recording)
        self.stop_btn.set_sensitive(recording)
        self.play_btn.set_sensitive(False)
        if recording:
            self.set_subtitle("Recording…")
            self.add_css_class("error")
        else:
            self.set_subtitle("Stopped")
            self.remove_css_class("error")
            if self.track.temp_file and os.path.exists(self.track.temp_file):
                self.play_btn.set_sensitive(True)
    
    def set_playing(self, playing, paused=False):
        if playing:
            self.play_btn.set_icon_name("media-playback-pause-symbolic")
            self.set_subtitle("Playing…" if not self.track.muted else "Playing (muted)…")
        elif paused:
            self.play_btn.set_icon_name("media-playback-start-symbolic")
            self.set_subtitle("Paused" if not self.track.muted else "Paused (muted)")
        else:
            self.play_btn.set_icon_name("media-playback-start-symbolic")
            self.set_subtitle("Ready")
    
    def set_muted(self, muted):
        if muted:
            self.mute_btn.set_icon_name("audio-volume-muted-symbolic")
            self.mute_btn.set_tooltip_text("Unmute track")
        else:
            self.mute_btn.set_icon_name("audio-volume-high-symbolic")
            self.mute_btn.set_tooltip_text("Mute track")
        
        if self.track.playing:
            self.set_subtitle("Playing (muted)…" if muted else "Playing…")
        elif self.track.paused:
            self.set_subtitle("Paused (muted)" if muted else "Paused")


@Gtk.Template(filename=os.path.join(UI_DIR, 'window.ui'))
class AudioRecorderWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'AudioRecorderWindow'
    
    # Template children
    add_track_btn = Gtk.Template.Child()
    play_all_btn = Gtk.Template.Child()
    stop_all_btn = Gtk.Template.Child()
    monitor_toggle = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    track_list = Gtk.Template.Child()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.playing_tracks = set()
        self.monitor_latency = '64'
        
        # Connect signals
        self.add_track_btn.connect("clicked", self.on_add_track)
        self.play_all_btn.connect("clicked", self.on_play_all)
        self.stop_all_btn.connect("clicked", self.on_stop_all)
        self.monitor_toggle.connect("toggled", self.on_monitor_toggled)
        
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
                
                app.tracks.append(track)
                
                row = TrackRow(track, self)
                self.track_list.append(row)
                
                if track.temp_file:
                    row.play_btn.set_sensitive(True)
            
            app.next_track_number = project_data.get('next_track_number', len(app.tracks) + 1)
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
                        'audio_file': os.path.join("audio", audio_filename)
                    })
            
            project_data = {
                'tracks': tracks_data,
                'next_track_number': app.next_track_number
            }
            
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
                    
                    if track.muted:
                        track.pipeline.set_property("volume", 0.0)
                    
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
            track.pipeline.set_property("volume", 0.0 if track.muted else 1.0)
        
        row.set_muted(track.muted)
    
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
                row.set_title(new_name)
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
                        
                        if track.muted:
                            track.pipeline.set_property("volume", 0.0)
                        
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
