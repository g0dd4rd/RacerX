#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
import subprocess
import os
import tempfile
from pathlib import Path
import wave
import json
import shutil

class Track:
    def __init__(self, name, temp_file=None):
        self.name = name
        self.temp_file = temp_file
        self.recording = False
        self.record_process = None
        self.playing = False
        self.play_process = None

class AudioRecorderApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.audiorecorder')
        self.monitoring = False
        self.monitor_process = None
        self.tracks = []
        self.next_track_number = 1
        self.project_file = None
        
    def do_activate(self):
        win = AudioRecorderWindow(application=self)
        win.present()

class TrackRow(Adw.ActionRow):
    def __init__(self, track, on_record, on_stop, on_play, on_delete):
        super().__init__()
        self.track = track
        
        self.set_title(track.name)
        self.set_subtitle("Ready")
        
        # Button box for controls
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_valign(Gtk.Align.CENTER)
        
        # Record button
        self.record_btn = Gtk.Button()
        self.record_btn.set_icon_name("media-record-symbolic")
        self.record_btn.set_tooltip_text("Start recording")
        self.record_btn.add_css_class("circular")
        self.record_btn.connect("clicked", lambda b: on_record(self))
        button_box.append(self.record_btn)
        
        # Stop button
        self.stop_btn = Gtk.Button()
        self.stop_btn.set_icon_name("media-playback-stop-symbolic")
        self.stop_btn.set_tooltip_text("Stop recording")
        self.stop_btn.add_css_class("circular")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", lambda b: on_stop(self))
        button_box.append(self.stop_btn)
        
        # Play button
        self.play_btn = Gtk.Button()
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self.play_btn.set_tooltip_text("Play recording")
        self.play_btn.add_css_class("circular")
        self.play_btn.set_sensitive(False)
        self.play_btn.connect("clicked", lambda b: on_play(self))
        button_box.append(self.play_btn)
        
        # Delete button
        delete_btn = Gtk.Button()
        delete_btn.set_icon_name("edit-delete-symbolic")
        delete_btn.set_tooltip_text("Delete track")
        delete_btn.add_css_class("circular")
        delete_btn.add_css_class("destructive-action")
        delete_btn.connect("clicked", lambda b: on_delete(self))
        button_box.append(delete_btn)
        
        self.add_suffix(button_box)
        
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
    
    def set_playing(self, playing):
        if playing:
            self.play_btn.set_icon_name("media-playback-pause-symbolic")
            self.set_subtitle("Playing…")
        else:
            self.play_btn.set_icon_name("media-playback-start-symbolic")
            self.set_subtitle("Ready")

class AudioRecorderWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("Audio Recorder")
        self.set_default_size(500, 450)
        
        self.playing_tracks = set()  # Set of currently playing TrackRow objects
        self.monitor_latency = '64'  # Latency in samples for monitoring
        
        # Header bar
        header_bar = Adw.HeaderBar()
        
        # Add track button in header
        add_track_btn = Gtk.Button()
        add_track_btn.set_icon_name("list-add-symbolic")
        add_track_btn.set_tooltip_text("Add new track")
        add_track_btn.connect("clicked", self.on_add_track)
        header_bar.pack_start(add_track_btn)
        
        # Monitor toggle button in header
        self.monitor_toggle = Gtk.ToggleButton()
        self.monitor_toggle.set_icon_name("audio-volume-high-symbolic")
        self.monitor_toggle.set_tooltip_text("Toggle input monitoring")
        self.monitor_toggle.connect("toggled", self.on_monitor_toggled)
        header_bar.pack_end(self.monitor_toggle)
        
        # Menu button (on the right per HIG)
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text("Main menu")
        
        menu = Gio.Menu()
        
        # Project section
        project_section = Gio.Menu()
        project_section.append("New Project", "win.new_project")
        project_section.append("Open Project…", "win.open_project")
        project_section.append("Save Project", "win.save_project")
        project_section.append("Save Project As…", "win.save_project_as")
        menu.append_section(None, project_section)
        
        # Import section
        import_section = Gio.Menu()
        import_section.append("Import Audio…", "win.import_audio")
        menu.append_section(None, import_section)
        
        # Export section
        export_section = Gio.Menu()
        export_section.append("Export Tracks…", "win.export_tracks")
        export_section.append("Export Mixed…", "win.export_mixed")
        export_section.append("Export All…", "win.export_all")
        menu.append_section(None, export_section)
        
        menu_button.set_menu_model(menu)
        header_bar.pack_end(menu_button)
        
        # Actions
        self.create_actions()
        
        # Toolbar view to combine header and content
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        
        # Main box with clamp for proper width
        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(12)
        main_box.set_margin_start(12)
        main_box.set_margin_end(12)
        
        # Status label
        self.status_label = Gtk.Label(label="Ready to record")
        self.status_label.add_css_class("dim-label")
        main_box.append(self.status_label)
        
        # Scrolled window for tracks
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        
        # Track list
        self.track_list = Gtk.ListBox()
        self.track_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.track_list.add_css_class("boxed-list")
        scrolled.set_child(self.track_list)
        main_box.append(scrolled)
        
        clamp.set_child(main_box)
        
        # Set content
        toolbar_view.set_content(clamp)
        self.set_content(toolbar_view)
        
        # Add first track by default
        self.add_track()
        
        # Connect close request to handle unsaved changes
        self.connect("close-request", self.on_close_request)
        
    def create_actions(self):
        # New Project
        action = Gio.SimpleAction.new("new_project", None)
        action.connect("activate", self.on_new_project)
        self.add_action(action)
        
        # Open Project
        action = Gio.SimpleAction.new("open_project", None)
        action.connect("activate", self.on_open_project)
        self.add_action(action)
        
        # Save Project
        action = Gio.SimpleAction.new("save_project", None)
        action.connect("activate", self.on_save_project)
        self.add_action(action)
        
        # Save Project As
        action = Gio.SimpleAction.new("save_project_as", None)
        action.connect("activate", self.on_save_project_as)
        self.add_action(action)
        
        # Import Audio
        action = Gio.SimpleAction.new("import_audio", None)
        action.connect("activate", self.on_import_audio)
        self.add_action(action)
        
        # Export Tracks
        self.export_tracks_action = Gio.SimpleAction.new("export_tracks", None)
        self.export_tracks_action.connect("activate", self.on_export_individual)
        self.export_tracks_action.set_enabled(False)
        self.add_action(self.export_tracks_action)
        
        # Export Mixed
        self.export_mixed_action = Gio.SimpleAction.new("export_mixed", None)
        self.export_mixed_action.connect("activate", self.on_export_mixed)
        self.export_mixed_action.set_enabled(False)
        self.add_action(self.export_mixed_action)
        
        # Export All
        self.export_all_action = Gio.SimpleAction.new("export_all", None)
        self.export_all_action.connect("activate", self.on_export_all)
        self.export_all_action.set_enabled(False)
        self.add_action(self.export_all_action)
    
    def on_new_project(self, action, param):
        # Check if there are unsaved changes
        if self.has_unsaved_changes():
            self.show_save_confirmation_dialog(self.create_new_project)
        else:
            self.create_new_project()
    
    def has_unsaved_changes(self):
        """Check if there are any tracks with recordings"""
        app = self.get_application()
        return any(t.temp_file and os.path.exists(t.temp_file) for t in app.tracks)
    
    def show_save_confirmation_dialog(self, callback):
        """Show dialog asking if user wants to save before proceeding"""
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
            # Save first, then proceed
            app = self.get_application()
            if app.project_file:
                self.save_project(app.project_file)
                callback()
            else:
                # Need to save as - show save dialog
                self.pending_callback = callback
                save_dialog = Gtk.FileDialog.new()
                save_dialog.set_title("Save Project As")
                save_dialog.set_initial_name("project")
                save_dialog.save(self, None, self.on_save_before_action_response)
        elif response == "discard":
            # Proceed without saving
            callback()
        # If "cancel", do nothing
    
    def on_save_before_action_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                project_path = file.get_path()
                self.save_project(project_path)
                
                # Execute the pending callback
                if hasattr(self, 'pending_callback'):
                    self.pending_callback()
                    delattr(self, 'pending_callback')
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to save project: {str(e)}")
    
    def create_new_project(self):
        app = self.get_application()
        
        # Clear current project
        while self.track_list.get_first_child():
            row = self.track_list.get_first_child()
            self.on_track_delete(row)
        
        app.tracks = []
        app.next_track_number = 1
        app.project_file = None
        
        # Add first track
        self.add_track()
        self.status_label.set_label("New project created")
        self.update_title()
    
    def on_open_project(self, action, param):
        # Check if there are unsaved changes
        if self.has_unsaved_changes():
            self.show_save_confirmation_dialog(self.show_open_project_dialog)
        else:
            self.show_open_project_dialog()
    
    def show_open_project_dialog(self):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Open Project")
        
        # Filter for .atr files (Audio Track Recorder)
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
            
            # Clear current tracks
            while self.track_list.get_first_child():
                row = self.track_list.get_first_child()
                self.on_track_delete(row)
            
            app.tracks = []
            app.project_file = project_path
            project_dir = os.path.dirname(project_path)
            
            # Load tracks
            for track_data in project_data['tracks']:
                track = Track(track_data['name'])
                
                # Copy audio file to temp location
                audio_file = os.path.join(project_dir, track_data['audio_file'])
                if os.path.exists(audio_file):
                    fd, track.temp_file = tempfile.mkstemp(suffix='.wav')
                    os.close(fd)
                    shutil.copy2(audio_file, track.temp_file)
                
                app.tracks.append(track)
                
                row = TrackRow(
                    track,
                    self.on_track_record,
                    self.on_track_stop,
                    self.on_track_play,
                    self.on_track_delete
                )
                self.track_list.append(row)
                
                # Update row state
                if track.temp_file:
                    row.play_btn.set_sensitive(True)
            
            app.next_track_number = project_data.get('next_track_number', len(app.tracks) + 1)
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
                project_path = file.get_path()
                self.save_project(project_path)
        except Exception as e:
            if "dismissed" not in str(e).lower():
                self.show_error_dialog(f"Failed to save project: {str(e)}")
    
    def save_project(self, project_path):
        app = self.get_application()
        
        try:
            # Project path is treated as a folder containing everything
            # Structure: project_folder/project.atr + project_folder/audio/
            project_dir = project_path if os.path.isdir(project_path) else os.path.splitext(project_path)[0]
            project_name = os.path.basename(project_dir)
            audio_dir = os.path.join(project_dir, "audio")
            project_file = os.path.join(project_dir, f"{project_name}.atr")
            
            # Create project and audio directories
            os.makedirs(project_dir, exist_ok=True)
            os.makedirs(audio_dir, exist_ok=True)
            
            # Save track data
            tracks_data = []
            for i, track in enumerate(app.tracks):
                if track.temp_file and os.path.exists(track.temp_file):
                    # Copy audio file to project directory
                    audio_filename = f"{track.name}.wav"
                    audio_path = os.path.join(audio_dir, audio_filename)
                    shutil.copy2(track.temp_file, audio_path)
                    
                    tracks_data.append({
                        'name': track.name,
                        'audio_file': os.path.join("audio", audio_filename)
                    })
            
            # Save project file
            project_data = {
                'tracks': tracks_data,
                'next_track_number': app.next_track_number
            }
            
            with open(project_file, 'w') as f:
                json.dump(project_data, f, indent=2)
            
            app.project_file = project_file
            self.status_label.set_label(f"Project saved: {project_name}")
            self.update_title()
            
        except Exception as e:
            self.show_error_dialog(f"Failed to save project: {str(e)}")
    
    def on_import_audio(self, action, param):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Import Audio File")
        
        # Filter for audio files
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
            # Create new track
            track_name = os.path.splitext(os.path.basename(audio_path))[0]
            track = Track(track_name)
            
            # Copy to temp file
            fd, track.temp_file = tempfile.mkstemp(suffix='.wav')
            os.close(fd)
            shutil.copy2(audio_path, track.temp_file)
            
            app.tracks.append(track)
            
            row = TrackRow(
                track,
                self.on_track_record,
                self.on_track_stop,
                self.on_track_play,
                self.on_track_delete
            )
            self.track_list.append(row)
            row.play_btn.set_sensitive(True)
            
            self.status_label.set_label(f"Imported: {track_name}")
            self.update_export_buttons()
            
        except Exception as e:
            self.show_error_dialog(f"Failed to import audio: {str(e)}")
    
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
        
        if track.playing:
            # Stop this track's playback
            if track.play_process:
                track.play_process.terminate()
                track.play_process.wait()
                track.play_process = None
            track.playing = False
            row.set_playing(False)
            self.playing_tracks.discard(row)
        else:
            # Start playback for this track
            if track.temp_file and os.path.exists(track.temp_file):
                try:
                    track.play_process = subprocess.Popen([
                        'pw-play',
                        track.temp_file
                    ])
                    
                    track.playing = True
                    row.set_playing(True)
                    self.playing_tracks.add(row)
                    
                    # Monitor process completion (only start if not already monitoring)
                    if len(self.playing_tracks) == 1:
                        GLib.timeout_add(100, self.check_playback_finished)
                    
                except Exception as e:
                    self.show_error_dialog(f"Failed to play track: {str(e)}")
    
    def check_playback_finished(self):
        # Check all playing tracks for completion
        finished_tracks = []
        for row in self.playing_tracks:
            track = row.track
            if track.play_process and track.play_process.poll() is not None:
                # This track's playback finished
                track.play_process = None
                track.playing = False
                row.set_playing(False)
                finished_tracks.append(row)
        
        # Remove finished tracks from the set
        for row in finished_tracks:
            self.playing_tracks.discard(row)
        
        # Continue monitoring if there are still playing tracks
        return len(self.playing_tracks) > 0
    
    def on_track_delete(self, row):
        app = self.get_application()
        track = row.track
        
        # Stop if recording
        if track.recording and track.record_process:
            track.record_process.terminate()
            track.record_process.wait()
        
        # Stop if playing
        if track.playing and track.play_process:
            track.play_process.terminate()
            track.play_process.wait()
            track.play_process = None
            track.playing = False
            self.playing_tracks.discard(row)
        
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
        self.export_tracks_action.set_enabled(has_recordings)
        self.export_mixed_action.set_enabled(has_recordings)
        self.export_all_action.set_enabled(has_recordings)
    
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
                destination = file.get_path()
                self.mix_tracks(destination)
                self.status_label.set_label(f"Exported mixed track")
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
                
                # Export individual tracks
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
        dialog = Adw.AlertDialog(heading="Error", body=message)
        dialog.add_response("ok", "OK")
        dialog.present(self)
    
    def on_close_request(self, window):
        """Handle window close request - check for unsaved changes"""
        if self.has_unsaved_changes():
            self.show_close_confirmation_dialog()
            return True  # Prevent window from closing
        return False  # Allow window to close
    
    def show_close_confirmation_dialog(self):
        """Show dialog asking if user wants to save before closing"""
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
            # Save first, then close
            app = self.get_application()
            if app.project_file:
                self.save_project(app.project_file)
                self.destroy()
            else:
                # Need to save as - show save dialog
                self.pending_close = True
                save_dialog = Gtk.FileDialog.new()
                save_dialog.set_title("Save Project As")
                save_dialog.set_initial_name("project")
                save_dialog.save(self, None, self.on_save_before_close_response)
        elif response == "discard":
            # Close without saving
            self.destroy()
        # If "cancel", do nothing - window stays open
    
    def on_save_before_close_response(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                project_path = file.get_path()
                self.save_project(project_path)
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
