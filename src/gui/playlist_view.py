import sys
import threading

import gi

from src.utils import PlaylistUtil

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GdkPixbuf, Gdk

try:
    import os
    sys.path.insert(1, os.path.join(sys.path[0], ".."))
    from gui.imports import *
    from gui.gui_utils import get_thumbnail
    from utils import ConfigUtil
except ModuleNotFoundError:
    from hidamari.gui.imports import *
    from hidamari.gui.gui_utils import get_thumbnail
    from hidamari.utils import ConfigUtil

class PlaylistView:
    def __init__(self, config: ConfigUtil, server):
        self.config = config
        self.server = server
        self.builder = Gtk.Builder()
        try:
            self.builder.add_from_resource(APP_UI_RESOURCE_PATH + "playlist_view.ui")
        except GLib.Error:
            self.builder.add_from_file(os.path.abspath("./assets/playlist_view.ui"))

        self.widget = self.builder.get_object("PlaylistView")
        self.playlist = None
        
        # get items from view
        self.monitor_combobox = self.builder.get_object("ComboBoxMonitor")
        self.videos_view = self.builder.get_object("IconViewVideos")
        self.playlist_name_entry = self.builder.get_object("EntryPlayListName")
        self.playlist_icon_view = self.builder.get_object("IconViewPlaylist")
        self.playlist_listbox = self.builder.get_object("ListBoxPlaylist")
        self.apply_button = self.builder.get_object("ButtonApply")
        self.add_to_playlist_button = self.builder.get_object("ButtonAddToPlaylist")
        self.remove_from_playlist_button = self.builder.get_object("ButtonRemoveFromPlaylist")
        self.move_left_button = self.builder.get_object("ButtonMoveLeft")
        self.move_right_button = self.builder.get_object("ButtonMoveRight")
        self.add_or_save_button = self.builder.get_object("ButtonPlayListAdd")

        # initialize monitors
        self.monitors = Monitors()
        self.monitor_combobox.remove_all()
        
        # get video paths
        video_paths = self.config[CONFIG_KEY_DATA_SOURCE]
        for monitor in self.monitors.get_monitors():
            # check if monitor exists in paths
            if monitor in video_paths:
                self.monitors.get_monitor(monitor).set_wallpaper(video_paths[monitor])
            else:
                self.monitors.get_monitor(monitor).set_wallpaper(video_paths['Default'])
                
            # add monitor name to combo box
            self.monitor_combobox.append_text(monitor)

        # connect signals
        self.monitor_combobox.connect("changed", self.on_monitor_changed)
        self.playlist_listbox.connect("row-activated", self.on_playlist_changed)
        self.videos_view.connect("selection-changed", self.on_video_selection_changed)
        self.apply_button.connect("clicked", self.on_playlist_apply)
        self.add_to_playlist_button.connect("clicked", self.on_add_to_playlist)
        self.remove_from_playlist_button.connect("clicked", self.on_remove_from_playlist)
        self.move_left_button.connect("clicked", self.on_move_left)
        self.move_right_button.connect("clicked", self.on_move_right)
        self.add_or_save_button.connect("clicked", self.on_add_or_save_playlist)
        self.playlist_icon_view.connect("selection-changed", self.on_video_selection_changed_in_playlist)
        self.playlist_name_entry.connect("changed", self.on_playlist_name_changed)

        # set active monitor
        self.monitor_combobox.set_active(0)
        
        #! add example playlists
        self.playlist_listbox.foreach(lambda row: self.playlist_listbox.remove(row))  # Clear existing rows
        example_playlists = ["Playlist 1", "Playlist 2", "Playlist 3"]
        for playlist in example_playlists:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=playlist, xalign=0)
            row.add(label)
            self.playlist_listbox.add(row)
            
        self._load_playlist()
        self._update_disable_status_for_buttons()

    """
        Button Callbacks
    """
    def on_add_or_save_playlist(self, button: Gtk.Button):
        print("Add or save playlist button clicked")
        pass

    def on_add_to_playlist(self, button: Gtk.Button):
        print("Add to playlist button clicked")
        pass
    
    def on_remove_from_playlist(self, button: Gtk.Button):
        print("Remove from playlist button clicked")
        pass
    
    def on_move_left(self, button: Gtk.Button):
        print("Move left button clicked")
        pass
    
    def on_move_right(self, button: Gtk.Button):
        print("Move right button clicked")
        pass

    def on_playlist_apply(self, button: Gtk.Button):
        print("Apply playlist button clicked")
        pass
    
    """
        Other callbacks
    """
    
    def on_playlist_name_changed(self, entry: Gtk.Entry):
        print(f"Playlist name changed: {entry.get_text()}")
        self._update_disable_status_for_buttons()
    
    def on_playlist_changed(self, listbox: Gtk.ListBox, row: Gtk.ListBoxRow):
        print(f"Playlist changed: {row.get_child().get_label()}")
        self._update_disable_status_for_buttons()
        
    def on_video_selection_changed(self, icon_view: Gtk.IconView):
        selected_items = icon_view.get_selected_items()
        print(f"Video selection changed: {selected_items}")
        self._update_disable_status_for_buttons()
        
    def on_video_selection_changed_in_playlist(self, icon_view: Gtk.IconView):
        selected_items = icon_view.get_selected_items()
        print(f"Video selection changed in playlist: {selected_items}")
        self._update_disable_status_for_buttons()

    def on_monitor_changed(self, combo: Gtk.ComboBoxText):
        active_monitor = combo.get_active_text()
        print(f"Monitor changed to: {active_monitor}")
        self._update_playlist_view(active_monitor)

    def _update_disable_status_for_buttons(self):
        print("Updating disable status for buttons")
        # if no playlist selected, disable apply button
        selected_playlist = self.playlist_listbox.get_selected_row()
        self.apply_button.set_sensitive(selected_playlist is not None)

        # if playlist name is empty, disable add/save button
        playlist_name = self.playlist_name_entry.get_text()
        self.add_or_save_button.set_sensitive(playlist_name != "")
            
        # if no video selected, disable add to playlist button
        selected_videos = self.videos_view.get_selected_items()
        self.add_to_playlist_button.set_sensitive(selected_videos)

        # if no video selected in playlist, disable remove, move left, move right buttons
        selected_video = self.playlist_icon_view.get_selected_items()
        self.remove_from_playlist_button.set_sensitive(selected_video)
        self.move_left_button.set_sensitive(selected_video)
        self.move_right_button.set_sensitive(selected_video)

    def _update_playlist_view(self, monitor_name: str):
        print(f"Updating playlist view for monitor: {monitor_name}")

    def _load_playlist(self):
        self.playlist = PlaylistUtil().load()

    def _save_playlist(self):
        PlaylistUtil().save(self.playlist)