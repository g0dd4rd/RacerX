#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
import subprocess
import os
import tempfile
from pathlib import Path
import wave
import struct

class Track:
    def __init__(self, name, temp_file=None):
        self.name = name
        self.temp_file = temp_file
        self.recording = False
        self.record_process = None

class AudioRecorderApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.audiorecorder')
        self.monitoring = False
        self.monitor_process = None
        self.tracks = []
        self.next_track_number = 1
        
    def do_activate(self):
        win = AudioRecorderWindow(application=self)
        win.present()

class TrackRow(Gtk.ListBoxRow):
    def __init__(self, track, on_record, on_stop, on_play, on_delete):
        super().__init__()
        self.track = track
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(5)
        box.set_margin_bottom(5)
        box.set_margin_start(10)
        box.set_margin_end(10)
        
        # Track name
        self.name_label = Gtk.Label(label=track.name)
        self.name_label.set_hexpand(True)
        self.name_label.set_halign(Gtk.Align.START)
        box.append(self.name_label)
        
        # Status indicator
        self.status_label = Gtk.Label(label="Ready")
        self.status_label.add_css_class("dim-label")
        box.append(self.status_label)
        
        # Record button
        self.record_btn = Gtk.Button(label="⏺")
        self.record_btn.set_tooltip_text("Record")
        self.record_btn.connect("clicked", lambda b: on_record(self))
        box.append(self.record_btn)
        
        # Stop button
        self.stop_btn = Gtk.Button(label="⏹")
        self.stop_btn.set_tooltip_text("Stop")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", lambda b: on_stop(self))
        box.append(self.stop_btn)
        
        # Play button
        self.play_btn = Gtk.Button(label="▶")
        self.play_btn.set_tooltip_text("Play")
        self.play_btn.set_sensitive(False)
        self.play_btn.connect("clicked", lambda b: on_play(self))
        box.append(self.play_btn)
        
        # Delete button
        delete_btn = Gtk.Button(label="🗑")
        delete_btn.set_tooltip_text("Delete Track")
        delete_btn.add_css_class("destructive-action")
        delete_btn.connect("clicked", lambda b: on_delete(self))
        box.append(delete_btn)
        
        self.set_child(box)
        
    def set_recording(self, recording):
        self.record_btn.set_sensitive(not recording)
        self.stop_btn.set_sensitive(recording)
        self.play_btn.set_sensitive(False)
        if recording:
            self.status_label.set_label("Recording...")
            self.status_label.add_css_class("error")
        else:
            self.status_label.set_label("Stopped")
            self.status_label.remove_css_class("error")
            if self.track.temp_file and os.path.exists(self.track.temp_file):
                self.play_btn.set_sensitive(True)
    
    def set_playing(self, playing):
        if playing:
            self.play_btn.set_label("⏸")
            self.status_label.set_label("Playing...")
        else:
            self.play_btn.set_label("▶")
            self.status_label.set_label("Ready")

class AudioRecorderWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("Multi-Track Audio Recorder")
        self.set_default_size(600, 500)
        
        self.playing_track = None
        self.play_process = None
        self.monitor_latency = '64'  # Latency in samples for monitoring
        
        # Header bar
        header_bar = Adw.HeaderBar()
        
        # Monitor toggle button in header
        self.monitor_toggle = Gtk.ToggleButton()
        self.monitor_toggle.set_icon_name("audio-volume-high-symbolic")
        self.monitor_toggle.set_tooltip_text("Enable/Disable Monitoring")
        self.monitor_toggle.connect("toggled", self.on_monitor_toggled)
        header_bar.pack_end(self.monitor_toggle)
        
        # Toolbar view to combine header and content
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        
        # Main box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        
        # Status label
        self.status_label = Gtk.Label(label="Ready to record")
        self.status_label.add_css_class("title-3")
        main_box.append(self.status_label)
        
        # Add track button
        add_track_btn = Gtk.Button(label="➕ Add Track")
        add_track_btn.add_css_class("suggested-action")
        add_track_btn.connect("clicked", self.on_add_track)
        main_box.append(add_track_btn)
        
        # Scrolled window for tracks
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        
        # Track list
        self.track_list = Gtk.ListBox()
        self.track_list.add_css_class("boxed-list")
        scrolled.set_child(self.track_list)
        main_box.append(scrolled)
        
        # Export buttons
        export_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        export_box.set_halign(Gtk.Align.CENTER)
        
        self.export_individual_btn = Gtk.Button(label="💾 Export Tracks")
        self.export_individual_btn.set_sensitive(False)
        self.export_individual_btn.connect("clicked", self.on_export_individual)
        export_box.append(self.export_individual_btn)
        
        self.export_mixed_btn = Gtk.Button(label="💾 Export Mixed")
        self.export_mixed_btn.set_sensitive(False)
        self.export_mixed_btn.connect("clicked", self.on_export_mixed)
        export_box.append(self.export_mixed_btn)
        
        self.export_all_btn = Gtk.Button(label="💾 Export All")
        self.export_all_btn.set_sensitive(False)
        self.export_all_btn.connect("clicked", self.on_export_all)
        export_box.append(self.export_all_btn)
        
        main_box.append(export_box)
        
        # Set content
        toolbar_view.set_content(main_box)
        self.set_content(toolbar_view)
        
        # Add first track by default
        self.add_track()
        
    def add_track(self):
        app = self.get_application()
        track = Track(f"Track {app.next_track_number}")
        app.next_track_number += 1
        app.tracks.append(track)
        
        row = TrackRow(
            track,
            self.on_track_record,
            self.on_track_stop,
            self.on_track_play,
            self.on_track_delete
        )
        self.track_list.append(row)
        self.update_export_buttons()
        
    def on_add_track(self, button):
        self.add_track()
        
    def on_track_record(self, row):
        track = row.track
        
        # Create temporary file
        fd, track.temp_file = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        
        try:
            track.record_process = subprocess.Popen([
                'pw-record',
                '--target', 'auto',
                track.temp_file
            ])
            
            track.recording = True
            row.set_recording(True)
            
        except FileNotFoundError:
            self.show_error_dialog("PipeWire tools not found. Please install pipewire-tools package.")
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
    
    def on_track_play(self, row):
        track = row.track
        
        if self.playing_track == row:
            # Stop current playback
            if self.play_process:
                self.play_process.terminate()
                self.play_process.wait()
                self.play_process = None
            self.playing_track.set_playing(False)
            self.playing_track = None
        else:
            # Stop any other playing track
            if self.playing_track:
                if self.play_process:
                    self.play_process.terminate()
                    self.play_process.wait()
                    self.play_process = None
                self.playing_track.set_playing(False)
            
            # Start playback
            if track.temp_file and os.path.exists(track.temp_file):
                try:
                    self.play_process = subprocess.Popen([
                        'pw-play',
                        track.temp_file
                    ])
                    
                    self.playing_track = row
                    row.set_playing(True)
                    
                    # Monitor process completion
                    GLib.timeout_add(100, self.check_playback_finished)
                    
                except Exception as e:
                    self.show_error_dialog(f"Failed to play track: {str(e)}")
    
    def check_playback_finished(self):
        if self.play_process and self.play_process.poll() is not None:
            # Playback finished
            self.play_process = None
            if self.playing_track:
                self.playing_track.set_playing(False)
                self.playing_track = None
            return False
        return self.play_process is not None
    
    def on_track_delete(self, row):
        app = self.get_application()
        track = row.track
        
        # Stop if recording or playing
        if track.recording and track.record_process:
            track.record_process.terminate()
            track.record_process.wait()
        
        if self.playing_track == row:
            if self.play_process:
                self.play_process.terminate()
                self.play_process.wait()
            self.playing_track = None
        
        # Remove temp file
        if track.temp_file and os.path.exists(track.temp_file):
            os.unlink(track.temp_file)
        
        # Remove from list
        app.tracks.remove(track)
        self.track_list.remove(row)
        self.update_export_buttons()
    
    def update_export_buttons(self):
        app = self.get_application()
        has_recordings = any(t.temp_file and os.path.exists(t.temp_file) for t in app.tracks)
        self.export_individual_btn.set_sensitive(has_recordings)
        self.export_mixed_btn.set_sensitive(has_recordings)
        self.export_all_btn.set_sensitive(has_recordings)
    
    def on_export_individual(self, button):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Select Folder for Individual Tracks")
        
        dialog.select_folder(self, None, self.on_export_individual_response)
    
    def on_export_individual_response(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                app = self.get_application()
                folder_path = folder.get_path()
                
                import shutil
                for track in app.tracks:
                    if track.temp_file and os.path.exists(track.temp_file):
                        filename = f"{track.name}.wav"
                        destination = os.path.join(folder_path, filename)
                        shutil.copy2(track.temp_file, destination)
                
                self.status_label.set_label(f"Exported {len(app.tracks)} tracks")
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to export: {str(e)}")
    
    def on_export_mixed(self, button):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Export Mixed Track")
        dialog.set_initial_name("mixed.wav")
        
        dialog.save(self, None, self.on_export_mixed_response)
    
    def on_export_mixed_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                destination = file.get_path()
                self.mix_tracks(destination)
                self.status_label.set_label(f"Exported mixed track")
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to export: {str(e)}")
    
    def on_export_all(self, button):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Select Folder for All Exports")
        
        dialog.select_folder(self, None, self.on_export_all_response)
    
    def on_export_all_response(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                app = self.get_application()
                folder_path = folder.get_path()
                
                # Export individual tracks
                import shutil
                for track in app.tracks:
                    if track.temp_file and os.path.exists(track.temp_file):
                        filename = f"{track.name}.wav"
                        destination = os.path.join(folder_path, filename)
                        shutil.copy2(track.temp_file, destination)
                
                # Export mixed track
                mixed_path = os.path.join(folder_path, "mixed.wav")
                self.mix_tracks(mixed_path)
                
                self.status_label.set_label(f"Exported all tracks and mix")
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to export: {str(e)}")
    
    def mix_tracks(self, output_path):
        """Mix all tracks into a single WAV file"""
        app = self.get_application()
        
        # Collect all valid tracks
        valid_tracks = [t for t in app.tracks if t.temp_file and os.path.exists(t.temp_file)]
        if not valid_tracks:
            return
        
        # Read all wave files
        wave_data = []
        params = None
        
        for track in valid_tracks:
            with wave.open(track.temp_file, 'rb') as wf:
                if params is None:
                    params = wf.getparams()
                frames = wf.readframes(wf.getnframes())
                wave_data.append(frames)
        
        # Find maximum length
        max_length = max(len(data) for data in wave_data)
        
        # Mix the audio
        mixed = bytearray(max_length)
        for data in wave_data:
            for i in range(len(data)):
                # Simple mixing by averaging
                mixed[i] = min(255, max(0, mixed[i] + data[i] // len(wave_data)))
        
        # Write mixed file
        with wave.open(output_path, 'wb') as wf:
            wf.setparams(params)
            wf.writeframes(bytes(mixed))
    
    def on_monitor_toggled(self, button):
        app = self.get_application()
        
        if button.get_active():
            self.start_monitoring()
            self.status_label.set_label("Monitoring active")
        else:
            self.stop_monitoring()
            self.status_label.set_label("Ready to record")
    
    def start_monitoring(self):
        app = self.get_application()
        
        if app.monitoring:
            return
        
        try:
            monitor_record = subprocess.Popen([
                'pw-record',
                '--target', 'auto',
                '--latency', self.monitor_latency,
                '--rate', '48000',
                '-'
            ], stdout=subprocess.PIPE)
            
            monitor_play = subprocess.Popen([
                'pw-play',
                '--target', 'auto',
                '--latency', self.monitor_latency,
                '--rate', '48000',
                '-'
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
            
            record_proc.terminate()
            play_proc.terminate()
            
            try:
                record_proc.wait(timeout=1)
                play_proc.wait(timeout=1)
            except:
                record_proc.kill()
                play_proc.kill()
            
            app.monitor_process = None
            app.monitoring = False
    
    def show_error_dialog(self, message):
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading("Error")
        dialog.set_body(message)
        dialog.add_response("ok", "OK")
        dialog.present()

def main():
    app = AudioRecorderApp()
    return app.run(None)

if __name__ == '__main__':
    main()
