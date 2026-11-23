# SPDX-License-Identifier: GPL-2.0-or-later

import sys
from gettext import gettext as _
from typing import Optional

import gi

from piper.ratbagd import RatbagdProfile, RatbagError

from .util.gobject import connect_signal_with_weak_ref

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, GObject, Gtk  # noqa


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/ProfileRow.ui")
class ProfileRow(Gtk.ListBoxRow):
    """A Gtk.ListBoxRow subclass containing the widgets to display a profile in
    the profile poper."""

    __gtype_name__ = "ProfileRow"

    title: Gtk.Label = Gtk.Template.Child()  # type: ignore

    def __init__(self, profile: RatbagdProfile, *args, **kwargs) -> None:
        Gtk.ListBoxRow.__init__(self, *args, **kwargs)
        self._profile = profile
        connect_signal_with_weak_ref(
            self, self._profile, "notify::disabled", self._on_profile_notify_disabled
        )

        connect_signal_with_weak_ref(
            self, self._profile, "notify::name", self._on_profile_notify_name
        )

        self._update_title()
        self.show_all()
        self.set_visible(not profile.disabled)

    def _display_name(self) -> str:
        name = self._profile.name
        if not name:
            name = _("Profile {}").format(self._profile.index + 1)
        return name

    def _update_title(self) -> None:
        self.title.set_text(self._display_name())

    def _on_profile_notify_name(
        self, profile: RatbagdProfile, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        self._update_title()

    @Gtk.Template.Callback("_on_rename_button_clicked")
    def _on_rename_button_clicked(self, button: Gtk.Button) -> None:
        popover = Gtk.Popover.new(button)
        entry = Gtk.Entry(
            text=self._profile.name or "",
            max_length=23,
            placeholder_text=_("Profile name"),
            margin=6,
        )
        entry.connect("activate", self._on_rename_entry_activate, popover)
        popover.add(entry)
        entry.show()
        popover.popup()

    def _on_rename_entry_activate(self, entry: Gtk.Entry, popover: Gtk.Popover) -> None:
        try:
            self._profile.name = entry.get_text().strip()
        except (GLib.Error, RatbagError) as e:
            print(f"Cannot rename profile: {e}", file=sys.stderr)
        popover.popdown()

    def _on_profile_notify_disabled(
        self, profile: RatbagdProfile, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        self.set_visible(not profile.disabled)

    @Gtk.Template.Callback("_on_delete_button_clicked")
    def _on_delete_button_clicked(self, button: Gtk.Button) -> None:
        if not self._profile.is_active:
            self._profile.disabled = True
        else:
            # TODO: display this in the app
            print("Trying to disable the active profile", file=sys.stderr)

    def set_active(self) -> None:
        """Activates the profile paired with this row."""
        self._profile.set_active()

    @GObject.Property
    def name(self) -> str:
        return self._display_name()

    @GObject.Property
    def profile(self) -> RatbagdProfile:
        return self._profile
