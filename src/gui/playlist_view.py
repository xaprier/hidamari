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
    from utils import ConfigUtil, get_video_paths
except ModuleNotFoundError:
    from hidamari.gui.imports import *
    from hidamari.gui.gui_utils import get_thumbnail, get_video_paths
    from hidamari.utils import ConfigUtil, get_video_paths

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
        self.reload_videos_button = self.builder.get_object("ButtonReloadVideos")

        # initialize monitors
        self.monitors = Monitors()
        self.monitor_combobox.remove_all()
        self.playlists = None
        self.current_playlist = None
        
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
        self.reload_videos_button.connect("clicked", self.on_reload_icon_view)
            
        self._load_playlist()
        self._load_config()
        self._update_disable_status_for_buttons()
        
        # set active monitor
        self.monitor_combobox.set_active(0)

    """
        Button Callbacks
    """
    def on_reload_icon_view(self, button: Gtk.Button):
        logger.info(f"[GUI/PlaylistView] Reloading videos")
        self.reload_icon_view()

    def on_add_or_save_playlist(self, button: Gtk.Button):
        # check if playlist name empty
        playlist_name = self.playlist_name_entry.get_text()
        if not playlist_name:
            logger.warning(f"[GUI/PlaylistView] Playlist name is empty")
            button.set_sensitive(False)
            # show translateable error dialog
            dialog = Gtk.MessageDialog(
                transient_for=self.widget.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Playlist name cannot be empty.",
            )
            dialog.format_secondary_text("Please enter a valid playlist name.")
            dialog.run()
            dialog.destroy()
            return
        
        # if all good, add/save playlist to listbox
        logger.info(f"[GUI/PlaylistView] Adding/Saving playlist: {playlist_name}")
        self.playlists[playlist_name] = self.current_playlist if self.current_playlist else {}
        
        self._save_playlist()
        self._load_playlist()

    def on_add_to_playlist(self, button: Gtk.Button):
        # get monitor name
        monitor_name = self.monitor_combobox.get_active_text()
        if not monitor_name:
            logger.warning(f"[GUI/PlaylistView] No monitor selected")
            return
        
        if self.current_playlist is None:
            self.current_playlist = {}
            
        if monitor_name not in self.current_playlist:
            self.current_playlist[monitor_name] = []
            
        selected_items = self.videos_view.get_selected_items()
        for item in selected_items:
            video_path = self.video_paths[item.get_indices()[0]]
            if video_path not in self.current_playlist[monitor_name]:
                self.current_playlist[monitor_name].append(video_path)

        if not selected_items:
            logger.warning(f"[GUI/PlaylistView] No videos selected to add")
            return

        self._update_playlist_view(monitor_name)
        self._update_disable_status_for_buttons()
    
    def on_remove_from_playlist(self, button: Gtk.Button):        
        # check if any item selected on playlist_icon_view
        selected_items = self.playlist_icon_view.get_selected_items()
        if not selected_items:
            logger.warning(f"[GUI/PlaylistView] No videos selected to remove")
            button.set_sensitive(False)
            dialog = Gtk.MessageDialog(
                transient_for=self.widget.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="No videos selected to remove from playlist.",
            )
            dialog.format_secondary_text("Please select videos to remove.")
            dialog.run()
            dialog.destroy()
            return
    
        # get monitor name
        monitor_name = self.monitor_combobox.get_active_text()
        if not monitor_name:
            logger.warning(f"[GUI/PlaylistView] No monitor selected")
            return
        
        if self.current_playlist is None or monitor_name not in self.current_playlist:
            logger.warning(f"[GUI/PlaylistView] No current playlist or monitor in playlist")
            return
        
        for item in selected_items:
            video_path = self.current_playlist[monitor_name][item.get_indices()[0]]
            if video_path in self.current_playlist[monitor_name]:
                self.current_playlist[monitor_name].remove(video_path)
        
        self._update_playlist_view(monitor_name)
        self._update_disable_status_for_buttons()
            
    def on_move_left(self, button: Gtk.Button):
        # check if any item selected on playlist_icon_view
        selected_items = self.playlist_icon_view.get_selected_items()
        if not selected_items:
            logger.warning(f"[GUI/PlaylistView] No videos selected to move")
            button.set_sensitive(False)
            dialog = Gtk.MessageDialog(
                transient_for=self.widget.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="No videos selected to move from playlist.",
            )
            dialog.format_secondary_text("Please select videos to move.")
            dialog.run()
            dialog.destroy()
            return
        
        # get monitor name
        monitor_name = self.monitor_combobox.get_active_text()
        if not monitor_name:
            logger.warning(f"[GUI/PlaylistView] No monitor selected")
            return
        
        if self.current_playlist is None or monitor_name not in self.current_playlist:
            logger.warning(f"[GUI/PlaylistView] No current playlist or monitor in playlist")
            return
        
        playlist = self.current_playlist[monitor_name]

        # change order of selected items
        indices = [item.get_indices()[0] for item in selected_items]
        logger.info(f"[GUI/PlaylistView] Selected indices to move left: {indices}")

        # left shift: move from the start to avoid index shifting issues
        for index in sorted(indices):
            if index > 0:
                playlist[index], playlist[index - 1] = playlist[index - 1], playlist[index]
                    
        self._update_playlist_view(monitor_name)
        self._update_disable_status_for_buttons()
    
    def on_move_right(self, button: Gtk.Button):
        # check if any item selected on playlist_icon_view
        selected_items = self.playlist_icon_view.get_selected_items()
        if not selected_items:
            logger.warning(f"[GUI/PlaylistView] No videos selected to move")
            button.set_sensitive(False)
            dialog = Gtk.MessageDialog(
                transient_for=self.widget.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="No videos selected to move from playlist.",
            )
            dialog.format_secondary_text("Please select videos to move.")
            dialog.run()
            dialog.destroy()
            return
        
        # get monitor name
        monitor_name = self.monitor_combobox.get_active_text()
        if not monitor_name:
            logger.warning(f"[GUI/PlaylistView] No monitor selected")
            return
        
        if self.current_playlist is None or monitor_name not in self.current_playlist:
            logger.warning(f"[GUI/PlaylistView] No current playlist or monitor in playlist")
            return
        
        # change order of selected items
        playlist = self.current_playlist[monitor_name]

        # change order of selected items
        indices = [item.get_indices()[0] for item in selected_items]
        logger.info(f"[GUI/PlaylistView] Selected indices to move right: {indices}")

        # move from the end to avoid index shifting issues
        for index in sorted(indices, reverse=True):
            if index < len(playlist) - 1:
                playlist[index], playlist[index + 1] = playlist[index + 1], playlist[index]
                    
        self._update_playlist_view(monitor_name)
        self._update_disable_status_for_buttons()

    def on_playlist_apply(self, button: Gtk.Button):
        # get playlist name
        selected_playlist = self.playlist_listbox.get_selected_row()
        if not selected_playlist:
            logger.warning(f"[GUI/PlaylistView] No playlist selected to apply")
            button.set_sensitive(False)
            dialog = Gtk.MessageDialog(
                transient_for=self.widget.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="No playlist selected to apply.",
            )
            dialog.format_secondary_text("Please select a playlist to apply.")
            dialog.run()
            dialog.destroy()
            return

        playlist_name = selected_playlist.get_child().get_text()
        if playlist_name not in self.playlists:
            logger.warning(f"[GUI/PlaylistView] Playlist {playlist_name} not found in playlists")
            return
        
        self.config[CONFIG_KEY_MODE] = MODE_PLAYLIST
        self.config[CONFIG_KEY_ACTIVE_PLAYLIST] = playlist_name
        self._save_config()
        logger.info(f"[GUI/PlaylistView] Applying playlist: {playlist_name}")
        if self.server is not None:
            self.server.playlist(playlist_name)

    """
        Other callbacks
    """
    
    def on_playlist_name_changed(self, entry: Gtk.Entry):
        self._update_disable_status_for_buttons()

    def on_playlist_changed(self, listbox: Gtk.ListBox, row: Gtk.ListBoxRow):
        logger.info(f"[GUI/PlaylistView] Playlist changed: {row.get_child().get_label()}")
        self._update_disable_status_for_buttons()
        # set active monitor
        self.monitor_combobox.set_active(0)
        monitor_name = self.monitor_combobox.get_active_text()
        self._update_playlist_view(monitor_name)

    def on_video_selection_changed(self, icon_view: Gtk.IconView):
        selected_items = []
        for item in icon_view.get_selected_items():
            selected_items.append(item.get_indices()[0])
        logger.info(f"[GUI/PlaylistView] Video selection changed: {selected_items}")
        self._update_disable_status_for_buttons()

    def on_video_selection_changed_in_playlist(self, icon_view: Gtk.IconView):
        selected_items = []
        for item in icon_view.get_selected_items():
            selected_items.append(item.get_indices()[0])
        logger.info(f"[GUI/PlaylistView] Video selection changed in playlist: {selected_items}")
        self._update_disable_status_for_buttons()

    def on_monitor_changed(self, combo: Gtk.ComboBoxText):
        active_monitor = combo.get_active_text()
        logger.info(f"[GUI/PlaylistView] Monitor changed to: {active_monitor}")
        self._update_playlist_view(active_monitor)
        
    def reload_icon_view(self, *_):
        self.video_paths = get_video_paths()
        list_store = Gtk.ListStore(GdkPixbuf.Pixbuf, str)
        self.videos_view.set_pixbuf_column(0)
        self.videos_view.set_text_column(1)
        self.videos_view.set_model(list_store)
        for idx, video_path in enumerate(self.video_paths):
            pixbuf = Gtk.IconTheme().get_default().load_icon("video-x-generic", 96, 0)
            list_store.append([pixbuf, os.path.basename(video_path)])
            thread = threading.Thread(
                target=get_thumbnail, args=(video_path, list_store, idx)
            )
            thread.daemon = True
            thread.start()

    def _update_disable_status_for_buttons(self):
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
        if not monitor_name or monitor_name not in self.monitors.get_monitors():
            logger.warning(f"[GUI/PlaylistView] Monitor {monitor_name} not found")
            return
        
        if self.current_playlist is None:
            logger.warning(f"[GUI/PlaylistView] No current playlist to update")
            return
        
        if monitor_name not in self.current_playlist:
            self.current_playlist[monitor_name] = []
            return
        
        # add icons for playlist videos
        list_store = Gtk.ListStore(GdkPixbuf.Pixbuf, str)
        self.playlist_icon_view.set_pixbuf_column(0)
        self.playlist_icon_view.set_text_column(1)
        self.playlist_icon_view.set_model(list_store)
        for idx, video_path in enumerate(self.current_playlist[monitor_name]):
            pixbuf = Gtk.IconTheme().get_default().load_icon("video-x-generic", 96, 0)
            list_store.append([pixbuf, os.path.basename(video_path)])
            thread = threading.Thread(
                target=get_thumbnail, args=(video_path, list_store, idx)
            )
            thread.daemon = True
            thread.start()

        logger.info(f"[GUI/PlaylistView] Updating playlist view for monitor: {monitor_name}")

    def _load_playlist(self):
        self.playlists = PlaylistUtil().load()["playlists"]
        
        # set first playlist as current
        if self.playlists:
            # clear listbox then add playlists
            self.playlist_listbox.foreach(lambda row: self.playlist_listbox.remove(row))  # Clear existing rows
            for playlist in self.playlists.keys():
                row = Gtk.ListBoxRow()
                label = Gtk.Label(label=playlist, xalign=0)
                row.add(label)
                self.playlist_listbox.add(row)
                
            # set first playlist as active
            self.playlist_listbox.show_all()
            first_row = self.playlist_listbox.get_row_at_index(0)
            if first_row:
                self.playlist_listbox.select_row(first_row)
                self.playlist_name_entry.set_text(first_row.get_child().get_text())
                self.current_playlist = self.playlists[first_row.get_child().get_text()]
                # update playlist view for active monitor
                self.monitor_combobox.set_active(0)
                self._update_playlist_view(self.monitor_combobox.get_active_text())
        else:
            self.current_playlist = {}
            for monitor in self.monitors.get_monitors():
                self.current_playlist[monitor] = []
                

    def _save_playlist(self):
        original = PlaylistUtil().load()
        original["playlists"] = self.playlists
        self.playlists = original["playlists"]
        PlaylistUtil().save(original)

        if self.server is not None:
            current_playlist = self.config.get(CONFIG_KEY_ACTIVE_PLAYLIST, None)
            if current_playlist is None:
                return
            
            playlist_name = self.playlist_listbox.get_selected_row().get_child().get_text()
            if playlist_name and playlist_name == current_playlist:
                self.server.playlist(playlist_name) # reload current playlist
        
    def _load_config(self):
        self.config = ConfigUtil().load()
        
    def _save_config(self):
        ConfigUtil().save(self.config)