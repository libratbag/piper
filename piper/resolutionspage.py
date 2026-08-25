# SPDX-License-Identifier: GPL-2.0-or-later

from gettext import gettext as _
from typing import Dict, Optional

from .mousemap import MouseMap
from .ratbagd import RatbagdButton, RatbagdDevice, RatbagdProfile
from .resolutionrow import ResolutionRow
from .util.gobject import connect_signal_with_weak_ref

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa


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

        self._mousemap = MouseMap(
            "#Buttons", self._device, spacing=20, border_width=20
        )
        self.pack_start(self._mousemap, True, True, 0)
        # Place the MouseMap on the left
        self.reorder_child(self._mousemap, 0)

        self._button_labels: Dict[int, Gtk.Label] = {}
        for button in profile.buttons:
            label = self._create_resolution_label(button)
            if label is not None:
                self._button_labels[button.index] = label
                self._mousemap.add(label, f"#button{button.index}")
            connect_signal_with_weak_ref(
                self,
                button,
                "notify::mapping",
                self._on_button_mapping_changed,
            )
            connect_signal_with_weak_ref(
                self,
                button,
                "notify::action-type",
                self._on_button_mapping_changed,
            )
        self._mousemap.show_all()

        self.listbox.foreach(Gtk.Widget.destroy)
        for resolution in profile.resolutions:
            row = ResolutionRow(resolution, self)
            self.listbox.insert(row, resolution.index)

    def _create_resolution_label(
        self, button: RatbagdButton
    ) -> Optional[Gtk.Label]:
        if (
            button.action_type == RatbagdButton.ActionType.SPECIAL
            and button.special in self._resolution_labels
        ):
            return Gtk.Label(
                label=_(RatbagdButton.SPECIAL_DESCRIPTION[button.special])
            )
        return None

    def _on_button_mapping_changed(
        self, button: RatbagdButton, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        old_label = self._button_labels.get(button.index)
        is_resolution = (
            button.action_type == RatbagdButton.ActionType.SPECIAL
            and button.special in self._resolution_labels
        )

        if old_label is not None and not is_resolution:
            self._mousemap.remove(old_label)
            del self._button_labels[button.index]
        elif old_label is not None and is_resolution:
            old_label.set_label(
                _(RatbagdButton.SPECIAL_DESCRIPTION[button.special])
            )
        elif old_label is None and is_resolution:
            label = Gtk.Label(
                label=_(RatbagdButton.SPECIAL_DESCRIPTION[button.special])
            )
            self._button_labels[button.index] = label
            self._mousemap.add(label, f"#button{button.index}")
            label.show_all()

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
