import os
import sys
import logging
import threading

import gi
import vlc
gi.require_version("GnomeDesktop", "4.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GnomeDesktop, GdkPixbuf, Gtk, Gdk, GLib

try:
    import os
    sys.path.insert(1, os.path.join(sys.path[0], '..'))
    from commons import *
except ModuleNotFoundError:
    from hidamari.commons import *

logger = logging.getLogger(LOGGER_NAME)


def generate_thumbnail(filename):
    factory = GnomeDesktop.DesktopThumbnailFactory()
    mtime = os.path.getmtime(filename)
    file = Gio.file_new_for_path(filename)
    uri = file.get_uri()
    info = file.query_info("standard::content-type",
                           Gio.FileQueryInfoFlags.NONE, None)
    mime_type = info.get_content_type()

    if factory.lookup(uri, mtime) is not None:
        return False

    if not factory.can_thumbnail(uri, mime_type, mtime):
        return False

    thumbnail = factory.generate_thumbnail(uri, mime_type)
    if thumbnail is None:
        return False

    factory.save_thumbnail(thumbnail, uri, mtime)
    return True


def get_thumbnail(video_path, list_store, idx):
    file = Gio.File.new_for_path(video_path)
    info = file.query_info("*", Gio.FileQueryInfoFlags.NONE, None)
    thumbnail = info.get_attribute_byte_string("thumbnail::path")
    if thumbnail is not None or generate_thumbnail(video_path):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(thumbnail, -1, 96)
        list_store[idx][0] = pixbuf


def debounce(wait_time):
    """
    Decorator that will debounce a function so that it is called after wait_time seconds
    If it is called multiple times, will wait for the last call to be debounced and run only this one.
    See the test_debounce.py file for examples
    Reference:
    https://github.com/salesforce/decorator-operations/blob/master/decoratorOperations/debounce_functions/debounce.py
    """
    def decorator(function):
        def debounced(*args, **kwargs):
            def call_function():
                debounced._timer = None
                return function(*args, **kwargs)

            if debounced._timer is not None:
                debounced._timer.cancel()

            debounced._timer = threading.Timer(wait_time, call_function)
            debounced._timer.start()

        debounced._timer = None
        return debounced

    return decorator


def vlc_media_looping(video_path: str) -> vlc.Media:
    media = vlc.Media(video_path)
    # Same trick as the wallpaper player: loop a short preview clip without
    # relying on -R/--repeat, which don't reliably loop for libvlc.
    media.add_option("input-repeat=65535")
    return media


class HoverPreview:
    """
    Muted, looping hover-preview for one IconView: hovering an item for
    HOVER_DELAY_MS starts silent, looping VLC playback of that item's video in a
    small Popover anchored over the item, fading in/out like a YouTube thumbnail
    preview. Uses GLib.timeout_add (not the threading.Timer-based `debounce`
    above) because every step here touches GTK/VLC widget state, which must run
    on the GTK main loop thread. Shared by the local-video and playlist galleries.
    """
    HOVER_DELAY_MS = 350
    FADE_DURATION_MS = 200
    FADE_STEP_MS = 15
    MIN_PREVIEW_SIZE = 96

    def __init__(self, icon_view: Gtk.IconView, vlc_instance: vlc.Instance, path_resolver: callable):
        self.icon_view = icon_view
        self.path_resolver = path_resolver
        self.player = vlc_instance.media_player_new()
        self.player.audio_set_mute(True)
        self.current_media_path = None

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_size_request(self.MIN_PREVIEW_SIZE, self.MIN_PREVIEW_SIZE)
        self.drawing_area.set_opacity(0.0)
        self.drawing_area.connect("realize", self._on_realize)
        self.drawing_area.show()

        self.popover = Gtk.Popover.new(icon_view)
        self.popover.set_modal(False)
        self.popover.add(self.drawing_area)

        self.hovered_path = None
        self.hover_timeout_id = None
        self.fade_timeout_id = None
        self.fade_opacity = 0.0
        self.fade_target = 0.0
        self.fade_step_size = 0.0

        icon_view.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        icon_view.connect("motion-notify-event", self._on_motion)
        icon_view.connect("leave-notify-event", self._on_leave)

    def _on_realize(self, widget):
        self.player.set_xwindow(widget.get_window().get_xid())

    def _on_motion(self, icon_view: Gtk.IconView, event: Gdk.EventMotion):
        if event.state & Gdk.ModifierType.BUTTON1_MASK:
            # left button down: item selection or a drag is in progress, not a hover
            self.hovered_path = None
            self._cancel_hover_timer()
            self._begin_fade(0.0)
            return False

        path = icon_view.get_path_at_pos(int(event.x), int(event.y))
        if path == self.hovered_path:
            return False
        self.hovered_path = path
        self._cancel_hover_timer()
        if path is None:
            self._begin_fade(0.0)
        else:
            self.hover_timeout_id = GLib.timeout_add(self.HOVER_DELAY_MS, self._start_preview, path)
        return False

    def _on_leave(self, icon_view: Gtk.IconView, event: Gdk.EventCrossing):
        self.hovered_path = None
        self._cancel_hover_timer()
        self._begin_fade(0.0)
        return False

    def _cancel_hover_timer(self):
        if self.hover_timeout_id is not None:
            GLib.source_remove(self.hover_timeout_id)
            self.hover_timeout_id = None

    def _start_preview(self, path: Gtk.TreePath):
        self.hover_timeout_id = None
        if path != self.hovered_path:
            return GLib.SOURCE_REMOVE  # pointer already moved elsewhere

        video_path = self.path_resolver(path)
        if not video_path or not os.path.isfile(video_path):
            return GLib.SOURCE_REMOVE

        found, cell_rect = self.icon_view.get_cell_rect(path, None)
        if not found:
            return GLib.SOURCE_REMOVE

        # Preview at least as large as the item's own thumbnail/cell in the IconView.
        self.drawing_area.set_size_request(
            max(cell_rect.width, self.MIN_PREVIEW_SIZE), max(cell_rect.height, self.MIN_PREVIEW_SIZE))

        self.popover.set_pointing_to(cell_rect)
        if not self.popover.get_visible():
            self.popover.popup()
        if self.drawing_area.get_realized():
            # idempotent; guards against the "realize" signal firing after this point
            self.player.set_xwindow(self.drawing_area.get_window().get_xid())

        if video_path != self.current_media_path:
            media = vlc_media_looping(video_path)
            self.player.set_media(media)
            self.current_media_path = video_path
        self.player.play()

        self._begin_fade(1.0)
        return GLib.SOURCE_REMOVE

    def _begin_fade(self, target: float):
        if target == self.fade_target and self.fade_timeout_id is not None:
            return
        if target == 0.0 and self.fade_opacity == 0.0 and not self.popover.get_visible():
            return
        self.fade_target = target
        steps = max(self.FADE_DURATION_MS // self.FADE_STEP_MS, 1)
        self.fade_step_size = (target - self.fade_opacity) / steps
        if self.fade_timeout_id is None:
            self.fade_timeout_id = GLib.timeout_add(self.FADE_STEP_MS, self._on_fade_tick)

    def _on_fade_tick(self):
        self.fade_opacity += self.fade_step_size
        reached = (self.fade_step_size >= 0 and self.fade_opacity >= self.fade_target) or \
                  (self.fade_step_size < 0 and self.fade_opacity <= self.fade_target)
        if reached:
            self.fade_opacity = self.fade_target
        self.drawing_area.set_opacity(self.fade_opacity)

        if not reached:
            return GLib.SOURCE_CONTINUE

        self.fade_timeout_id = None
        if self.fade_target == 0.0:
            self.player.stop()
            self.popover.popdown()
        return GLib.SOURCE_REMOVE
