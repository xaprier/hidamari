import sys
import logging
import multiprocessing as mp
import setproctitle

# TODO: Port to Gtk4/adwaita someday...
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib

from pydbus import SessionBus

try:
    import os

    sys.path.insert(1, os.path.join(sys.path[0], ".."))
    from gui.web_view import WebView
    from gui.local_video_view import LocalVideoView
    from gui.streaming_view import StreamingView
    from gui.playlist_view import PlaylistView
    from gui.popover_main import PopoverMain
    from commons import *
    from monitor import *
    from gui.gui_utils import debounce
    from utils import ConfigUtil, setup_autostart, is_gnome, is_wayland, get_video_paths
except ModuleNotFoundError:
    from hidamari.monitor import *
    from hidamari.commons import *
    from hidamari.gui.web_view import WebView
    from hidamari.gui.streaming_view import StreamingView
    from hidamari.gui.local_video_view import LocalVideoView
    from hidamari.gui.playlist_view import PlaylistView
    from hidamari.gui.popover_main import PopoverMain
    from hidamari.gui.gui_utils import debounce
    from hidamari.utils import (
        ConfigUtil,
        setup_autostart,
        is_gnome,
        is_wayland,
    )

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(LOGGER_NAME)

APP_ID = f"{PROJECT}.gui"
APP_TITLE = "Hidamari"
APP_UI_RESOURCE_PATH = "/io/jeffshee/Hidamari/"

class ControlPanel(Gtk.Application):
    def __init__(self, version, *args, **kwargs):
        super(ControlPanel, self).__init__(
            *args,
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
            **kwargs,
        )
        setproctitle.setproctitle(mp.current_process().name)
        
        # Load main UI
        self.builder = Gtk.Builder()
        self.builder.set_application(self)
        try:
            self.builder.add_from_resource(APP_UI_RESOURCE_PATH + "control.ui")
        except GLib.Error:
            self.builder.add_from_file(os.path.abspath("./assets/control.ui"))

        # Handlers declared in `control.ui`
        signals = {
        }
        self.builder.connect_signals(signals)

        # Variables init
        self.version = version
        self.window = None
        self.server = None

        self.is_autostart = os.path.isfile(AUTOSTART_DESKTOP_PATH)

        self._connect_server()
        self._load_config()
        
        # Placeholders
        self.web_placeholder = self.builder.get_object("WebViewPlaceholder")
        self.streaming_placeholder = self.builder.get_object("StreamingViewPlaceholder")
        self.localvideo_placeholder = self.builder.get_object("LocalVideoPlaceholder")
        self.playlist_placeholder = self.builder.get_object("PlaylistViewPlaceholder")

        # Load web view UI
        self.web_view = WebView(self.config, self.server)
        self._add_to_placeholder(self.web_placeholder, self.web_view.widget)
        
        # Load local video UI
        self.local_video = LocalVideoView(self.config, self.server)
        self._add_to_placeholder(self.localvideo_placeholder, self.local_video.widget)
        
        # Load streaming UI
        self.streaming_view = StreamingView(self.config, self.server)
        self._add_to_placeholder(self.streaming_placeholder, self.streaming_view.widget)
        
        # Load playlist UI
        self.playlist_view = PlaylistView(self.config, self.server)
        self._add_to_placeholder(self.playlist_placeholder, self.playlist_view.widget)

        # Load popover UI
        self.popover_main = PopoverMain(self.config, self.server)
        popoverButton = self.builder.get_object("popoverButton")
        popoverButton.set_popover(self.popover_main.widget)

    def _add_to_placeholder(self, placeholder, widget):
        parent = widget.get_parent()
        if parent:
            parent.remove(widget)
        placeholder.add(widget)
        placeholder.show_all()

    def _connect_server(self):
        try:
            self.server = SessionBus().get(DBUS_NAME_SERVER)
        except GLib.Error:
            logger.error("[GUI/ControlPanel] Couldn't connect to server")

    def _load_config(self):
        self.config = ConfigUtil().load()

    def _save_config(self):
        ConfigUtil().save(self.config)

    @debounce(1)
    def _save_config_delay(self):
        self._save_config()

    def do_startup(self):
        Gtk.Application.do_startup(self)

        actions = [
            (
                "local_video_dir",
                lambda *_: subprocess.run(
                    ["xdg-open", os.path.realpath(VIDEO_WALLPAPER_DIR)]
                ),
            ),
            ("local_video_refresh", self.local_video.reload_icon_view),
            ("local_video_apply", self.local_video.on_local_video_apply),
            ("local_web_page_apply", self.web_view.on_local_web_page_apply),
            ("play_pause", self.on_play_pause),
            ("feeling_lucky", self.on_feeling_lucky),
            (
                "config",
                lambda *_: subprocess.run(["xdg-open", os.path.realpath(CONFIG_PATH)]),
            ),
            (
                "about", 
                lambda *_: self.popover_main.on_about(self.window, self.version)
            ),
            ("quit", self.on_quit),
        ]

        for action_name, handler in actions:
            action = Gio.SimpleAction.new(action_name, None)
            action.connect("activate", handler)
            self.add_action(action)

        statefuls = [
            ("mute", self.config[CONFIG_KEY_MUTE], self.popover_main.on_mute),
            ("autostart", self.is_autostart, self.on_autostart),
            (
                "static_wallpaper",
                self.config[CONFIG_KEY_STATIC_WALLPAPER],
                self.popover_main.on_static_wallpaper,
            ),
            (
                "pause_when_maximized",
                self.config[CONFIG_KEY_PAUSE_WHEN_MAXIMIZED],
                self.popover_main.on_pause_when_maximized,
            ),
            (
                "mute_when_maximized",
                self.config[CONFIG_KEY_MUTE_WHEN_MAXIMIZED],
                self.popover_main.on_mute_when_maximized,
            ),
        ]

        for action_name, state, handler in statefuls:
            action = Gio.SimpleAction.new_stateful(
                action_name, None, GLib.Variant.new_boolean(state)
            )
            action.connect("change-state", handler)
            self.add_action(action)

        if is_wayland():
            self.popover_main.builder.get_object("TogglePauseWhenMaximized").set_visible(False)
            self.popover_main.builder.get_object("ToggleMuteWhenMaximized").set_visible(False)

        if not is_gnome():
            # Disable static wallpaper functionality for non-GNOME DE
            self.popover_main.builder.get_object("ToggleStaticWallpaper").set_visible(False)
            self.popover_main.builder.get_object("LabelBlurRadius").set_visible(False)
            self.popover_main.builder.get_object("SpinBlurRadius").set_visible(False)

        self._reload_all_widgets()

    def do_activate(self):
        if self.window is None:
            self.window: Gtk.ApplicationWindow = self.builder.get_object(
                "ApplicationWindow"
            )
            self.window.set_title("Hidamari")
            self.window.set_application(self)
            self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.present()

        if self.server is None:
            self._show_error("Couldn't connect to server")

        if self.config[CONFIG_KEY_FIRST_TIME]:
            self._show_welcome()
            self.config[CONFIG_KEY_FIRST_TIME] = False
            self._save_config()

    def _show_welcome(self):
        # Welcome dialog
        dialog = Gtk.MessageDialog(
            parent=self.window,
            modal=True,
            destroy_with_parent=True,
            text="Welcome to Hidamari 🤗",
            message_type=Gtk.MessageType.INFO,
            #    secondary_text="You can bring up the Menu by <b>Right click</b> on the desktop",
            secondary_text="Quickstart for adding local videos:\n ・Click the folder icon to open the Hidamari folder\n ・Put your videos there\n ・Click the refresh button",
            secondary_use_markup=True,
            buttons=Gtk.ButtonsType.OK,
        )
        dialog.run()
        dialog.destroy()

    def _show_error(self, error):
        dialog = Gtk.MessageDialog(
            parent=self.window,
            modal=True,
            destroy_with_parent=True,
            text="Oops!",
            message_type=Gtk.MessageType.ERROR,
            secondary_text=error,
            buttons=Gtk.ButtonsType.OK,
        )
        dialog.run()
        dialog.destroy()

    def on_play_pause(self, *_):
        if self.server is None:
            return
        prev_state = self.server.is_paused_by_user
        self.server.is_paused_by_user = not prev_state
        if not prev_state:
            self.server.pause_playback()
        else:
            self.server.start_playback()

    def on_feeling_lucky(self, *_):
        if self.server is not None:
            self.server.feeling_lucky()

    def on_autostart(self, action, state):
        action.set_state(state)
        self.is_autostart = bool(state)
        logger.info(f"[GUI/ControlPanel] {action.get_name()}: {state}")
        setup_autostart(state)

    def on_quit(self, *_):
        if self.server is not None:
            try:
                self.server.quit()
            except GLib.Error:
                # Ignore NoReply error
                pass
        self.quit()

    def _reload_all_widgets(self):
        self.local_video.reload_icon_view()
        self.popover_main.set_mute_toggle_icon()
        self.popover_main.set_scale_volume_sensitive()
        self.popover_main.set_spin_blur_radius_sensitive()
        toggle_mute: Gtk.ToggleButton = self.popover_main.builder.get_object("ToggleMute")
        toggle_mute.set_state = self.config[CONFIG_KEY_MUTE]

        scale_volume: Gtk.Scale = self.popover_main.builder.get_object("ScaleVolume")
        adjustment_volume: Gtk.Adjustment = self.popover_main.builder.get_object("AdjustmentVolume")
        
        # Temporary block signal
        adjustment_volume.handler_block_by_func(self.popover_main.on_volume_changed)
        scale_volume.set_value(self.config[CONFIG_KEY_VOLUME])
        adjustment_volume.handler_unblock_by_func(self.popover_main.on_volume_changed)

        spin_blur_radius: Gtk.Scale = self.popover_main.builder.get_object("SpinBlurRadius")
        adjustment_blur: Gtk.Adjustment = self.popover_main.builder.get_object("AdjustmentBlur")
        
        # Temporary block signal
        adjustment_blur.handler_block_by_func(self.popover_main.on_blur_radius_changed)
        spin_blur_radius.set_value(self.config[CONFIG_KEY_BLUR_RADIUS])
        adjustment_blur.handler_unblock_by_func(self.popover_main.on_blur_radius_changed)

        toggle_mute: Gtk.ToggleButton = self.popover_main.builder.get_object("ToggleAutostart")
        toggle_mute.set_state = self.is_autostart


def main(
    version="devel", pkgdatadir="/app/share/hidamari", localedir="/app/share/locale"
):
    try:
        resource = Gio.Resource.load(os.path.join(pkgdatadir, "hidamari.gresource"))
        resource._register()
        icon_theme = Gtk.IconTheme.get_default()
        icon_theme.add_resource_path("/io/jeffshee/Hidamari/icons")
    except GLib.Error:
        logger.error("[GUI/ControlPanel] Couldn't load resource")

    app = ControlPanel(version)
    app.run(sys.argv)


if __name__ == "__main__":
    main()
