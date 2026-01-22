# SPDX-License-Identifier: GPL-2.0-or-later

from gettext import gettext as _
from typing import Optional

from .mousemap import MouseMap
from .ratbagd import RatbagdButton, RatbagdDevice, RatbagdProfile
from .resolutionrow import ResolutionRow

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/ResolutionsPage.ui")
class ResolutionsPage(Gtk.Box):
    """The first stack page, exposing the resolution configuration with its
    report rate buttons and resolutions list."""

    __gtype_name__ = "ResolutionsPage"

    _resolution_labels = [
        RatbagdButton.ActionSpecial.RESOLUTION_CYCLE_UP,
        RatbagdButton.ActionSpecial.RESOLUTION_CYCLE_DOWN,
        RatbagdButton.ActionSpecial.RESOLUTION_UP,
        RatbagdButton.ActionSpecial.RESOLUTION_DOWN,
        RatbagdButton.ActionSpecial.RESOLUTION_ALTERNATE,
        RatbagdButton.ActionSpecial.RESOLUTION_DEFAULT,
    ]

    add_resolution_row: Gtk.ListBoxRow = Gtk.Template.Child()  # type: ignore
    listbox: Gtk.ListBox = Gtk.Template.Child()  # type: ignore

    def __init__(
        self, ratbagd_device: RatbagdDevice, profile: RatbagdProfile, *args, **kwargs
    ) -> None:
        """Instantiates a new ResolutionsPage.

        @param ratbag_device The ratbag device to configure, as
                             ratbagd.RatbagdDevice
        """
        Gtk.Box.__init__(self, *args, **kwargs)

        self._device = ratbagd_device
        self._last_activated_row: Optional[ResolutionRow] = None
        self._profile = profile
        self._mousemap: Optional[MouseMap] = None
        self._pressed_button_indices: set[int] = set()
        self._button_indices = {button.index for button in profile.buttons}
        self._toplevel: Optional[Gtk.Widget] = None
        self._press_handler_id: Optional[int] = None
        self._release_handler_id: Optional[int] = None
        self._scroll_handler_id: Optional[int] = None
        self._scroll_indicator: Optional[Gtk.Label] = None
        self._scroll_hide_source_id: Optional[int] = None
        self._wheel_svg_id: Optional[str] = None
        self._indicator_fixed: Optional[Gtk.Fixed] = None
        self._scroll_indicator_size = 24000
        self._scroll_indicator_color = "#888"

        mousemap = MouseMap("#Buttons", self._device, spacing=20, border_width=20)
        self._mousemap = mousemap
        overlay = Gtk.Overlay()
        overlay.add(mousemap)
        self.pack_start(overlay, True, True, 0)
        # Place the MouseMap on the left
        self.reorder_child(overlay, 0)
        for button in profile.buttons:
            if (
                button.action_type == RatbagdButton.ActionType.SPECIAL
                and button.special in self._resolution_labels
            ):
                label = Gtk.Label(
                    label=_(RatbagdButton.SPECIAL_DESCRIPTION[button.special])
                )
                event_box = Gtk.EventBox()
                event_box.set_visible_window(False)
                event_box.add(label)
                mousemap.add(event_box, f"#button{button.index}")
            if button.index == 2:
                self._wheel_svg_id = f"#button{button.index}"
        if self._wheel_svg_id is not None:
            indicator = Gtk.Label(label="↑")
            indicator.set_markup(
                f"<span size='{self._scroll_indicator_size}' foreground='{self._scroll_indicator_color}'>↑</span>"
            )
            indicator.set_no_show_all(True)
            indicator.hide()
            fixed = Gtk.Fixed()
            fixed.set_no_show_all(True)
            fixed.hide()
            fixed.set_halign(Gtk.Align.FILL)
            fixed.set_valign(Gtk.Align.FILL)
            fixed.set_hexpand(True)
            fixed.set_vexpand(True)
            fixed.put(indicator, 0, 0)
            overlay.add_overlay(fixed)
            overlay.set_overlay_pass_through(fixed, True)
            self._indicator_fixed = fixed
            self._scroll_indicator = indicator
        mousemap.show_all()
        overlay.show_all()

        self.connect("realize", self._on_realize)
        self.connect("destroy", self._on_destroy)

        self.listbox.foreach(Gtk.Widget.destroy)
        for resolution in profile.resolutions:
            row = ResolutionRow(resolution, self)
            self.listbox.insert(row, resolution.index)

    @Gtk.Template.Callback("on_row_activated")
    def on_row_activated(self, _listbox: Gtk.ListBox, row: ResolutionRow) -> None:
        if row is self._last_activated_row:
            self._last_activated_row = None
            row.toggle_revealer()
        else:
            if self._last_activated_row is not None:
                self._last_activated_row.toggle_revealer()

            if row is self.add_resolution_row:
                print("TODO: RatbagdProfile needs a way to add resolutions")
                self._last_activated_row = None
            else:
                self._last_activated_row = row
                row.toggle_revealer()

    def _event_button_to_index(self, button: int) -> Optional[int]:
        # Map GDK button numbers to ratbagd button indices.
        mapping = {
            1: 0,  # left
            3: 1,  # right
            2: 2,  # middle
            8: 3,  # back
            9: 4,  # forward
        }
        index = mapping.get(button)
        if index is None or index not in self._button_indices:
            return None
        return index

    def _on_mouse_button_press(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> int:
        if self._mousemap is None:
            return Gdk.EVENT_PROPAGATE
        index = self._event_button_to_index(event.button)
        if index is None:
            return Gdk.EVENT_PROPAGATE
        self._pressed_button_indices.add(index)
        self._mousemap.add_highlight(f"#button{index}")
        return Gdk.EVENT_PROPAGATE

    def _on_mouse_button_release(
        self, _widget: Gtk.Widget, event: Gdk.EventButton
    ) -> int:
        if self._mousemap is None:
            return Gdk.EVENT_PROPAGATE
        index = self._event_button_to_index(event.button)
        if index is None:
            return Gdk.EVENT_PROPAGATE
        if index in self._pressed_button_indices:
            self._pressed_button_indices.remove(index)
            self._mousemap.remove_highlight(f"#button{index}")
        return Gdk.EVENT_PROPAGATE

    def _on_realize(self, _widget: Gtk.Widget) -> None:
        toplevel = self.get_toplevel()
        if not isinstance(toplevel, Gtk.Widget):
            return
        self._toplevel = toplevel
        self._toplevel.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self._press_handler_id = self._toplevel.connect(
            "button-press-event", self._on_mouse_button_press
        )
        self._release_handler_id = self._toplevel.connect(
            "button-release-event", self._on_mouse_button_release
        )
        self._scroll_handler_id = self._toplevel.connect(
            "scroll-event", self._on_scroll_event
        )

    def _on_destroy(self, _widget: Gtk.Widget) -> None:
        if self._toplevel is None:
            return
        if self._press_handler_id is not None:
            self._toplevel.disconnect(self._press_handler_id)
            self._press_handler_id = None
        if self._release_handler_id is not None:
            self._toplevel.disconnect(self._release_handler_id)
            self._release_handler_id = None
        if self._scroll_handler_id is not None:
            self._toplevel.disconnect(self._scroll_handler_id)
            self._scroll_handler_id = None
        self._toplevel = None

    def _on_scroll_event(self, _widget: Gtk.Widget, event: Gdk.EventScroll) -> int:
        if (
            self._scroll_indicator is None
            or self._indicator_fixed is None
            or self._mousemap is None
            or self._wheel_svg_id is None
        ):
            return Gdk.EVENT_PROPAGATE
        direction: Optional[str] = None
        if event.direction == Gdk.ScrollDirection.UP:
            direction = "up"
        elif event.direction == Gdk.ScrollDirection.DOWN:
            direction = "down"
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            if event.delta_y > 0:
                direction = "down"
            elif event.delta_y < 0:
                direction = "up"
        if direction is None:
            return Gdk.EVENT_PROPAGATE
        arrow = "↑" if direction == "up" else "↓"
        self._scroll_indicator.set_markup(
            f"<span size='{self._scroll_indicator_size}' foreground='{self._scroll_indicator_color}'>{arrow}</span>"
        )
        center = self._mousemap.get_svg_center(self._wheel_svg_id)
        if center is not None:
            x, y = center
            _, natural = self._scroll_indicator.get_preferred_size()
            width = natural.width
            height = natural.height
            # Center the arrow on the wheel.
            self._indicator_fixed.move(
                self._scroll_indicator, x - (width / 2) + 1, y - (height / 2)
            )
        self._scroll_indicator.show()
        self._indicator_fixed.show()
        if self._scroll_hide_source_id is not None:
            GLib.source_remove(self._scroll_hide_source_id)
        self._scroll_hide_source_id = GLib.timeout_add(
            250, self._hide_scroll_indicator
        )
        return Gdk.EVENT_PROPAGATE

    def _hide_scroll_indicator(self) -> bool:
        if self._scroll_indicator is not None:
            self._scroll_indicator.hide()
        if self._indicator_fixed is not None:
            self._indicator_fixed.hide()
        self._scroll_hide_source_id = None
        return False
