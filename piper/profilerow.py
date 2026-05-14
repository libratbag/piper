# SPDX-License-Identifier: GPL-2.0-or-later

import sys
from typing import Optional

import gi

from piper.ratbagd import RatbagdProfile

from .util.gobject import connect_signal_with_weak_ref

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GObject, Gtk  # noqa


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/ProfileRow.ui")
class ProfileRow(Gtk.ListBoxRow):
    """A Gtk.ListBoxRow subclass containing the widgets to display a profile in
    the profile poper."""

    __gtype_name__ = "ProfileRow"

    title: Gtk.Label = Gtk.Template.Child()  # type: ignore
    name_stack: Gtk.Stack = Gtk.Template.Child()  # type: ignore
    name_entry: Gtk.Entry = Gtk.Template.Child()  # type: ignore
    rename_button: Gtk.Button = Gtk.Template.Child()  # type: ignore

    def __init__(self, profile: RatbagdProfile, *args, **kwargs) -> None:
        Gtk.ListBoxRow.__init__(self, *args, **kwargs)
        self._profile = profile
        self._committing = False
        connect_signal_with_weak_ref(
            self, self._profile, "notify::disabled", self._on_profile_notify_disabled
        )

        name = profile.name
        if not name:
            name = f"Profile {profile.index}"

        self.title.set_text(name)
        self.rename_button.set_visible(
            RatbagdProfile.CAP_WRITABLE_NAME in profile.capabilities
        )
        self.show_all()
        self.set_visible(not profile.disabled)

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

    @Gtk.Template.Callback("_on_rename_button_clicked")
    def _on_rename_button_clicked(self, button: Gtk.Button) -> None:
        self.name_entry.set_text(self.title.get_text())
        self.name_stack.set_visible_child_name("entry")
        self.name_entry.grab_focus()

    @Gtk.Template.Callback("_on_name_entry_activate")
    def _on_name_entry_activate(self, entry: Gtk.Entry) -> None:
        self._commit_rename()

    @Gtk.Template.Callback("_on_name_entry_focus_out_event")
    def _on_name_entry_focus_out_event(
        self, entry: Gtk.Entry, event: Gdk.EventFocus
    ) -> bool:
        self._commit_rename()
        return False

    @Gtk.Template.Callback("_on_name_entry_key_press_event")
    def _on_name_entry_key_press_event(
        self, entry: Gtk.Entry, event: Gdk.EventKey
    ) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.name_stack.set_visible_child_name("label")
            return True
        return False

    def _commit_rename(self) -> None:
        if self._committing:
            return
        self._committing = True
        new_name = self.name_entry.get_text().strip()
        if new_name and new_name != self.title.get_text():
            self._profile.name = new_name
            self.title.set_text(new_name)
            self.notify("name")
        self.name_stack.set_visible_child_name("label")
        self._committing = False

    def set_active(self) -> None:
        """Activates the profile paired with this row."""
        self._profile.set_active()

    @GObject.Property
    def name(self) -> str:
        return self.title.get_text()

    @GObject.Property
    def profile(self) -> RatbagdProfile:
        return self._profile
