# SPDX-License-Identifier: GPL-2.0-or-later

from gettext import gettext as _
from typing import Dict, Optional

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

        self._button_widgets: Dict[int, OptionButton] = {}
        self._ratbagd_buttons: Dict[int, RatbagdButton] = {}

        self._mousemap = MouseMap("#Buttons", self._device, spacing=20, border_width=20)
        if profile.num_button_layers > 1:
            # Overlay the layer switcher so it does not shift the MouseMap
            # coordinates the buttons are positioned with.
            overlay = Gtk.Overlay()
            overlay.add(self._mousemap)
            overlay.add_overlay(self._create_layer_switcher(profile.num_button_layers))
            self.pack_start(overlay, True, True, 0)
        else:
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
            self._button_widgets[ratbagd_button.index] = button
            self._ratbagd_buttons[ratbagd_button.index] = ratbagd_button
            self._sizegroup.add_widget(button)

        self._populate_layer(0)
        self.show_all()

    def _create_layer_switcher(self, num_layers: int) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.get_style_context().add_class("linked")
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.START)
        box.set_margin_top(10)

        group = None
        for layer in range(num_layers):
            # Translators: the button layer active without and while
            # holding the shift button (e.g. Easy-Shift, G-Shift).
            label = _("Normal") if layer == 0 else _("Shifted")
            radio = Gtk.RadioButton.new_with_label_from_widget(group, label)
            radio.set_mode(False)
            radio.connect("toggled", self._on_layer_toggled, layer)
            box.pack_start(radio, False, False, 0)
            group = group or radio
        return box

    def _populate_layer(self, layer: int) -> None:
        """Shows the buttons of the given layer in the mouse map."""
        for button_widget in self._button_widgets.values():
            if button_widget.get_parent() is not None:
                self._mousemap.remove(button_widget)

        for index, ratbagd_button in self._ratbagd_buttons.items():
            if ratbagd_button.layer == layer:
                self._mousemap.add(
                    self._button_widgets[index],
                    f"#button{ratbagd_button.layer_index}",
                )

    def _on_layer_toggled(self, radio: Gtk.RadioButton, layer: int) -> None:
        if radio.get_active():
            self._populate_layer(layer)

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
            if ratbagd_button.mapping - 1 in RatbagdButton.BUTTON_DESCRIPTION:
                label = _(RatbagdButton.BUTTON_DESCRIPTION[ratbagd_button.mapping - 1])
            else:
                # Translators: the {} will be replaced with the button index, e.g.
                # "Button 1 click".
                label = _("Button {} click").format(ratbagd_button.mapping - 1)
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
            title=_("Configure button {}").format(ratbagd_button.index),
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
                    # Mappings are 1-indexed, so 1 is left mouse click and 2 is
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
