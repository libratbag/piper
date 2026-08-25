# SPDX-License-Identifier: GPL-2.0-or-later

from gettext import gettext as _
from typing import Optional

import gi

from piper.ratbagd import RatbagdProfile

from .util.gobject import connect_signal_with_weak_ref

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/ProfileRow.ui")
class ProfileRow(Gtk.ListBoxRow):
    """A Gtk.ListBoxRow subclass containing the widgets to display a profile in
    the profile popup."""

    __gtype_name__ = "ProfileRow"

    title: Gtk.Label = Gtk.Template.Child()  # type: ignore

    def __init__(self, profile: RatbagdProfile, *args, **kwargs) -> None:
        Gtk.ListBoxRow.__init__(self, *args, **kwargs)
        self._profile = profile
        connect_signal_with_weak_ref(
            self, self._profile, "notify::disabled", self._on_profile_notify_disabled
        )

        name = profile.name
        if not name:
            name = f"Profile {profile.index}"

        self.title.set_text(name)
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
            dialog = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.CLOSE,
                text=_("Cannot disable active profile"),
            )
            dialog.format_secondary_text(
                _("Please switch to another profile before disabling this one.")
            )
            dialog.run()
            dialog.destroy()

    def set_active(self) -> None:
        """Activates the profile paired with this row."""
        self._profile.set_active()

    @GObject.Property
    def name(self) -> str:
        return self.title.get_text()

    @GObject.Property
    def profile(self) -> RatbagdProfile:
        return self._profile
