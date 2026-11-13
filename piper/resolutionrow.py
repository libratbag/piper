# SPDX-License-Identifier: GPL-2.0-or-later

from typing import Optional

import gi

from .ratbagd import RatbagdResolution
from .util.gobject import connect_signal_with_weak_ref

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gdk, Gtk  # noqa


class _DPIEntry(Gtk.Entry, Gtk.Editable):
    """
    A subclass of Gtk.Entry with an overridden method for input validation.

    This class addresses a specific bug in the handling of parameters in pygobject when
    using signals. For Gtk.Entry, the 'position' parameter is incorrect when handling
    the 'insert-text' signal, causing an assertion warning to be logged. By using this
    subclass, we can override the 'insert-text' logic to correctly handle the position
    parameter and avoid the warning.

    Inheriting from Gtk.Editable in addition to Gtk.Entry ensures that the overridden
    method applies only to instances of this class, rather than affecting all
    Gtk.Entry objects in the application.
    """

    __gtype_name__ = "DPIEntry"

    def do_insert_text(self, new_text: str, new_text_length: int, position: int) -> int:
        """Overrides the default Gtk.Editable insert-text handler to validate numerical
        input."""
        if not new_text.isdigit():
            self.stop_emission("insert-text")
            return position

        self.get_buffer().insert_text(position, new_text, new_text_length)
        return position + new_text_length


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/ResolutionRow.ui")
class ResolutionRow(Gtk.ListBoxRow):
    """A Gtk.ListBoxRow subclass containing the widgets to configure a
    resolution."""

    __gtype_name__ = "ResolutionRow"

    active_button: Gtk.Button = Gtk.Template.Child()  # type: ignore
    active_label: Gtk.Label = Gtk.Template.Child()  # type: ignore
    disable_button: Gtk.Button = Gtk.Template.Child()  # type: ignore
    dpi_label: Gtk.Label = Gtk.Template.Child()  # type: ignore
    dpi_entry: _DPIEntry = Gtk.Template.Child()  # type: ignore
    revealer: Gtk.Revealer = Gtk.Template.Child()  # type: ignore
    scale: Gtk.Scale = Gtk.Template.Child()  # type: ignore

    CAP_SEPARATE_XY_RESOLUTION = False
    CAP_DISABLE = False

    def __init__(
        self, resolution: RatbagdResolution, resolutions_page, *args, **kwargs
    ) -> None:
        Gtk.ListBoxRow.__init__(self, *args, **kwargs)

        self.resolutions_page = resolutions_page
        self._resolution = resolution
        self.resolutions = resolution.resolutions
        self._scale_handler = self.scale.connect(
            "value-changed", self._on_scale_value_changed
        )
        self._disabled_button_handler = self.disable_button.connect(
            "toggled", self._on_disable_button_toggled
        )

        self._active_handler = connect_signal_with_weak_ref(
            self, resolution, "notify::is-active", self._on_status_changed
        )
        self._disabled_handler = connect_signal_with_weak_ref(
            self, resolution, "notify::is-disabled", self._on_status_changed
        )
        connect_signal_with_weak_ref(
            self, resolution, "notify::resolution", self._on_profile_resolution_changed
        )

        # Get resolution capabilities and update internal values.
        if RatbagdResolution.CAP_SEPARATE_XY_RESOLUTION in resolution.capabilities:
            self.CAP_SEPARATE_XY_RESOLUTION = True
        if RatbagdResolution.CAP_DISABLE in resolution.capabilities:
            self.CAP_DISABLE = True

        # Set initial values for the UI.
        res = resolution.resolution[0]
        minres = resolution.resolutions[0]
        maxres = resolution.resolutions[-1]
        res_num_chars = len(str(maxres))

        # Set the max width and length for the DPI text boxes, based on the max res value.
        self.dpi_entry.set_width_chars(res_num_chars)
        self.dpi_entry.set_max_length(res_num_chars)

        with self.scale.handler_block(self._scale_handler):
            self.scale.props.adjustment.configure(res, minres, maxres, 50, 50, 0)
            self.scale.set_value(res)
        if resolution.is_disabled:
            with self.disable_button.handler_block(self._disabled_button_handler):
                self.disable_button.set_active(True)
        self._on_status_changed(resolution, _pspec=None)

    @Gtk.Template.Callback("_on_change_value")
    def _on_change_value(
        self, scale: Gtk.Scale, scroll: Gtk.ScrollType, value: float
    ) -> bool:
        # Cursor-controlled slider may get out of the GtkAdjustment's range.
        value = min(max(self.resolutions[0], value), self.resolutions[-1])

        # Find the nearest permitted value to our Gtk.Scale value.
        lo = max(r for r in self.resolutions if r <= value)
        hi = min(r for r in self.resolutions if r >= value)

        value = lo if value - lo < hi - value else hi

        scale.set_value(value)
        self.dpi_entry.set_text(str(value))

        # libratbag provides a fake-exponential range with the deltas
        # increasing as the resolution goes up. Make sure we set our
        # steps to the next available value.
        idx = self.resolutions.index(value)
        if idx < len(self.resolutions) - 1:
            delta = self.resolutions[idx + 1] - self.resolutions[idx]
            scale.props.adjustment.set_step_increment(delta)
            scale.props.adjustment.set_page_increment(delta)

        return True

    def _on_disable_button_toggled(self, togglebutton: Gtk.Button) -> None:
        # The disable button has been toggled, update RatbagdResolution.
        self._resolution.set_disabled(togglebutton.get_active())

        # Update UI
        self._on_status_changed(self._resolution, _pspec=None)

    @Gtk.Template.Callback("_on_active_button_clicked")
    def _on_active_button_clicked(self, _togglebutton: Gtk.Button) -> None:
        # The set active button has been clicked, update RatbagdResolution.
        self._resolution.set_active()

    @Gtk.Template.Callback("_on_scroll_event")
    def _on_scroll_event(self, widget: Gtk.Widget, _event: Gdk.EventScroll) -> bool:
        # Prevent a scroll in the list to get caught by the scale.
        GObject.signal_stop_emission_by_name(widget, "scroll-event")
        return False

    def _on_scale_value_changed(self, scale: Gtk.Scale) -> None:
        # The scale has been moved, update RatbagdResolution's resolution.
        res = int(scale.get_value())
        self._on_dpi_values_changed(res=res)

    def _on_status_changed(
        self, resolution: RatbagdResolution, _pspec: Optional[GObject.ParamSpec]
    ) -> None:
        # The resolution's status changed, update UI.
        self._on_dpi_values_changed()
        if resolution.is_active:
            self.active_label.set_visible(True)
            self.active_button.set_sensitive(False)
            self.disable_button.set_sensitive(False)
        else:
            self.active_label.set_visible(False)
            self.active_button.set_sensitive(True)
            if self.CAP_DISABLE:
                with self.disable_button.handler_block(self._disabled_button_handler):
                    self.disable_button.set_sensitive(not resolution.is_default)
                    if resolution.is_disabled:
                        self.disable_button.set_active(True)
                        self.active_button.set_sensitive(False)
                        self.dpi_label.set_sensitive(False)
                        self.dpi_entry.set_sensitive(False)
                        self.scale.set_sensitive(False)
                    else:
                        self.disable_button.set_active(False)
                        self.dpi_label.set_sensitive(True)
                        self.dpi_entry.set_sensitive(True)
                        self.scale.set_sensitive(True)

    def toggle_revealer(self) -> None:
        # Toggles the revealer to show or hide the configuration widgets.
        reveal = not self.revealer.get_reveal_child()
        self.revealer.set_reveal_child(reveal)
        if reveal:
            self.dpi_entry.grab_focus()

    def _on_dpi_values_changed(self, res: Optional[int] = None) -> None:
        # Freeze the notify::resolution signal from firing and
        # update DPI text box and resolution values.
        if res is None:
            res = self._resolution.resolution[0]
        new_res = (res, res) if self.CAP_SEPARATE_XY_RESOLUTION else (res,)
        self.dpi_entry.set_text(str(res))

        # Only update new resolution if changed
        if new_res != self._resolution.resolution:
            self._resolution.resolution = new_res

    @Gtk.Template.Callback("_on_dpi_entry_activate")
    def _on_dpi_entry_activate(self, entry: Gtk.Entry) -> None:
        # The DPI entry has been changed, update the scale and RatbagdResolution's resolution.
        try:
            res = int(entry.get_text())
            # Get the resolution closest to what has been entered
            closest_res = min(self.resolutions, key=lambda x: abs(x - res))
            entry.set_text(str(closest_res))
            self._on_dpi_values_changed(res=closest_res)

            with self.scale.handler_block(self._scale_handler):
                self.scale.set_value(closest_res)
        except ValueError:
            # If the input is not a valid integer, reset to the current value.
            entry.set_text(str(self._resolution.resolution[0]))

    @Gtk.Template.Callback("_on_dpi_entry_focus_in")
    def _on_dpi_entry_focus_in(self, _entry: Gtk.Entry, _event_focus: Gdk.EventFocus):
        if not self.revealer.get_reveal_child():
            self.resolutions_page.on_row_activated(None, self)

    @Gtk.Template.Callback("_on_dpi_entry_focus_out")
    def _on_dpi_entry_focus_out(self, entry: Gtk.Entry, _event_focus: Gdk.EventFocus):
        # Apply the DPI value on focus out
        self._on_dpi_entry_activate(entry)

    def _on_profile_resolution_changed(
        self, resolution: RatbagdResolution, _pspec: GObject.ParamSpec
    ) -> None:
        with self.scale.handler_block(self._scale_handler):
            res = resolution.resolution[0]
            self.scale.set_value(res)
            self.dpi_entry.set_text(str(res))
