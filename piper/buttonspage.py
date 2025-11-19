# SPDX-License-Identifier: GPL-2.0-or-later

from gettext import gettext as _
from typing import Optional

from .buttondialog import ButtonDialog
from .mousemap import MouseMap
from .optionbutton import OptionButton
from .ratbagd import (
    RatbagdButton,
    RatbagdDevice,
    RatbagdProfile,
    evcode_to_str,
)
from .util.gobject import connect_signal_with_weak_ref

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GObject  # noqa


class ButtonsPage(Gtk.Box):
    """The second stack page, exposing the button configuration."""

    __gtype_name__ = "ButtonsPage"

    def __init__(
        self, ratbagd_device: RatbagdDevice, profile: RatbagdProfile, *args, **kwargs
    ) -> None:
        """Instantiates a new ButtonsPage.

        @param ratbag_device The ratbag device to configure, as
                             ratbagd.RatbagdDevice
        """
        Gtk.Box.__init__(self, *args, **kwargs)

        self._device = ratbagd_device
        self._profile = profile

        self._mousemap = MouseMap("#Buttons", self._device, spacing=20, border_width=20)
        self.pack_start(self._mousemap, True, True, 0)
        self._sizegroup = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        for ratbagd_button in profile.buttons:
            button = OptionButton()
            # Set the correct label in the option button.
            self._on_button_mapping_changed(ratbagd_button, None, button)
            button.connect("clicked", self._on_button_clicked, ratbagd_button)
            connect_signal_with_weak_ref(
                self,
                ratbagd_button,
                "notify::mapping",
                self._on_button_mapping_changed,
                button,
            )
            connect_signal_with_weak_ref(
                self,
                ratbagd_button,
                "notify::special",
                self._on_button_mapping_changed,
                button,
            )
            connect_signal_with_weak_ref(
                self,
                ratbagd_button,
                "notify::macro",
                self._on_button_mapping_changed,
                button,
            )
            connect_signal_with_weak_ref(
                self,
                ratbagd_button,
                "notify::key",
                self._on_button_mapping_changed,
                button,
            )
            connect_signal_with_weak_ref(
                self,
                ratbagd_button,
                "notify::action-type",
                self._on_button_mapping_changed,
                button,
            )
            self._mousemap.add(button, f"#button{ratbagd_button.index}")
            self._sizegroup.add_widget(button)

        self.show_all()

    def _on_button_mapping_changed(
        self,
        ratbagd_button: RatbagdButton,
        pspec: Optional[GObject.ParamSpec],
        optionbutton: OptionButton,
    ) -> None:
        # Called when the button's action type changed, which means its
        # corresponding optionbutton has to be updated.
        action_type = ratbagd_button.action_type
        if action_type == RatbagdButton.ActionType.BUTTON:
            label = RatbagdButton.get_description_by_mapping_number(ratbagd_button.mapping)
        elif action_type == RatbagdButton.ActionType.SPECIAL:
            label = _(RatbagdButton.SPECIAL_DESCRIPTION[ratbagd_button.special])
        elif action_type == RatbagdButton.ActionType.MACRO:
            label = _("Macro: {}").format(str(ratbagd_button.macro))
        elif action_type == RatbagdButton.ActionType.KEY:
            label = _("Key: {}").format(evcode_to_str(ratbagd_button.key))
        elif action_type == RatbagdButton.ActionType.NONE:
            # Translators: the button is turned disabled, e.g. off.
            label = _("Disabled")
        else:
            # Translators: the button has an unknown function.
            label = _("Unknown")
        optionbutton.set_label(label)

    def _on_button_clicked(
        self, button: OptionButton, ratbagd_button: RatbagdButton
    ) -> None:
        # Presents the ButtonDialog to configure the mouse button corresponding
        # to the clicked button.
        buttons = self._profile.buttons
        device_type = self._device.device_type
        dialog = ButtonDialog(
            ratbagd_button,
            buttons,
            device_type,
            # + 1 because 1-based button numbers are more intuitive than 0-based.  Left-click = Button 1.
            title=_("Configure button {}").format(ratbagd_button.index + 1),
            use_header_bar=True,
            transient_for=self.get_toplevel(),
        )
        dialog.connect("response", self._on_dialog_response, ratbagd_button)
        dialog.present()

    def _on_dialog_response(
        self,
        dialog: ButtonDialog,
        response: Gtk.ResponseType,
        ratbagd_button: RatbagdButton,
    ) -> None:
        # The user either pressed cancel or apply. If it's apply, apply the
        # changes before closing the dialog, otherwise just close the dialog.
        if response == Gtk.ResponseType.APPLY:
            if dialog.action_type == RatbagdButton.ActionType.NONE:
                ratbagd_button.disable()
            elif dialog.action_type == RatbagdButton.ActionType.BUTTON:
                if dialog.mapping in [
                    ButtonDialog.LEFT_HANDED_MODE,
                    ButtonDialog.RIGHT_HANDED_MODE,
                ]:
                    left = self._find_button_type(0)
                    right = self._find_button_type(1)
                    if left is None or right is None:
                        return
                    # Mappings are 1-based, so 1 is left mouse click and 2 is
                    # right mouse click.
                    if dialog.mapping == ButtonDialog.LEFT_HANDED_MODE:
                        left.mapping, right.mapping = 2, 1
                    elif dialog.mapping == ButtonDialog.RIGHT_HANDED_MODE:
                        left.mapping, right.mapping = 1, 2
                else:
                    ratbagd_button.mapping = dialog.mapping
            elif dialog.action_type == RatbagdButton.ActionType.MACRO:
                ratbagd_button.macro = dialog.mapping
            elif dialog.action_type == RatbagdButton.ActionType.KEY:
                ratbagd_button.key = dialog.mapping
            elif dialog.action_type == RatbagdButton.ActionType.SPECIAL:
                ratbagd_button.special = dialog.mapping
                lower = RatbagdButton.ActionSpecial.PROFILE_CYCLE_UP
                upper = RatbagdButton.ActionSpecial.PROFILE_DOWN
                if lower <= dialog.mapping <= upper:
                    index = ratbagd_button.index
                    for profile in self._device.profiles:
                        if profile is self._profile:
                            continue
                        profile.buttons[index].special = dialog.mapping
        dialog.destroy()

    def _find_button_type(self, button_type: int) -> Optional[RatbagdButton]:
        for button in self._profile.buttons:
            if button.index == button_type:
                return button
        return None
