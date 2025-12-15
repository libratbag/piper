# SPDX-License-Identifier: GPL-2.0-or-later

import sys

from gettext import gettext as _
from typing import List, Optional, Tuple, Union

from .ratbagd import RatbagdButton, RatbagdMacro, RatbagDeviceType

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GObject, Gtk  # noqa


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/ButtonRow.ui")
class ButtonRow(Gtk.ListBoxRow):
    """A Gtk.ListBoxRow subclass to implement the rows that show up in the
    ButtonDialog's Gtk.ListBox. It doesn't do much besides moving UI code into a
    .ui file."""

    __gtype_name__ = "ButtonRow"

    description_label: Gtk.Label = Gtk.Template.Child()  # type: ignore

    def __init__(
        self,
        description: str,
        section: str,
        action_type: RatbagdButton.ActionType,
        value: Union[int, RatbagdButton.ActionSpecial, None],
        *args,
        **kwargs,
    ) -> None:
        """Instantiates a new ButtonRow.

        @param description The text to display in the row, as str.
        @param section The section this row belongs to, as str.
        @param action_type The type of this row's mapping, as one of
                           RatbagdButton.ActionType.*.
        @param value The value to set when this row is activated. The type needs
                     to match the action_type, e.g. for it should be int for
                     RatbagdButton.ActionType.BUTTON.
        """
        Gtk.ListBoxRow.__init__(self, *args, **kwargs)
        self._section = section
        self._action_type = action_type
        self._value = value

        self.description_label.set_text(description)

    @GObject.Property
    def description(self) -> str:
        return self.description_label.get_text()


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/ButtonDialog.ui")
class ButtonDialog(Gtk.Dialog):
    """A Gtk.Dialog subclass to implement the dialog that shows the
    configuration options for button mappings."""

    __gtype_name__ = "ButtonDialog"

    LEFT_HANDED_MODE = -1000
    RIGHT_HANDED_MODE = -1001

    # Gdk uses an offset of 8 from the keycodes defined in linux/input.h.
    _XORG_KEYCODE_OFFSET = 8

    empty_search_placeholder: Gtk.Box = Gtk.Template.Child()  # type: ignore
    label_keystroke: Gtk.Label = Gtk.Template.Child()  # type: ignore
    label_preview: Gtk.Label = Gtk.Template.Child()  # type: ignore
    listbox: Gtk.ListBox = Gtk.Template.Child()  # type: ignore
    radio_left_handed: Gtk.RadioButton = Gtk.Template.Child()  # type: ignore
    radio_right_handed: Gtk.RadioButton = Gtk.Template.Child()  # type: ignore
    row_keystroke: Gtk.ListBoxRow = Gtk.Template.Child()  # type: ignore
    row_keystroke_label: Gtk.Label = Gtk.Template.Child()  # type: ignore
    search_bar: Gtk.SearchBar = Gtk.Template.Child()  # type: ignore
    search_entry: Gtk.SearchEntry = Gtk.Template.Child()  # type: ignore
    stack: Gtk.Stack = Gtk.Template.Child()  # type: ignore

    def __init__(
        self,
        ratbagd_button: RatbagdButton,
        buttons: List[RatbagdButton],
        device_type: RatbagDeviceType,
        *args,
        **kwargs,
    ) -> None:
        """Instantiates a new ButtonDialog.

        @param ratbagd_button The button to configure, as ratbagd.RatbagdButton.
        @param buttons The buttons on this device, as [ratbagd.RatbagdButton].
        @param devicetype The type of this device, as ratbagd.RatbagDeviceType.
        """
        Gtk.Dialog.__init__(self, *args, **kwargs)
        self._grab_pointer: Optional[Gdk.Device] = None
        self._current_macro: Optional[RatbagdMacro] = None
        self._button = ratbagd_button
        self._device_type = device_type
        self._action_type = self._button.action_type

        if self.action_type == RatbagdButton.ActionType.NONE:
            self._mapping = None
        elif self._action_type == RatbagdButton.ActionType.BUTTON:
            self._mapping = self._button.mapping
        elif self._action_type == RatbagdButton.ActionType.MACRO:
            self._mapping = self._button.macro
        elif self._action_type == RatbagdButton.ActionType.KEY:
            self._mapping = self._button.key
        elif self._action_type == RatbagdButton.ActionType.SPECIAL:
            self._mapping = self._button.special
        else:
            self._mapping = -1

        self._init_ui(buttons)

    def _init_ui(self, buttons: List[RatbagdButton]) -> None:
        if self._device_type is RatbagDeviceType.MOUSE and self._button.index in [0, 1]:
            self._init_primary_buttons_ui()
        else:
            self._init_other_buttons_ui(buttons)

    def _init_primary_buttons_ui(self) -> None:
        # Shows the listbox to swap the primary buttons.
        self.stack.set_visible_child_name("handedness")
        # Left mouse button (index 0) is mapped to right mouse button, where
        # mappings are 1-based and thus right mouse click has value 2.
        # Or, right mouse button (index 1) is mapped to left mouse button,
        # which has value 1.
        if (
            self._button.index == 0
            and self._mapping == 2
            or self._button.index == 1
            and self._mapping == 1
        ):
            self.radio_left_handed.set_active(True)
        else:
            self.radio_right_handed.set_active(True)

    def _init_other_buttons_ui(self, buttons: List[RatbagdButton]) -> None:
        # Shows the listbox to map non-primary buttons.
        self.listbox.set_header_func(self._listbox_header_func)
        self.listbox.set_filter_func(self._listbox_filter_func)
        self.listbox.set_placeholder(self.empty_search_placeholder)
        self.search_entry.connect(
            "notify::text", lambda o, p: self.listbox.invalidate_filter()
        )

        i = 0
        for button in buttons:
            # again, index is 0-based and mapping is 1-based, so +1
            name = RatbagdButton.get_description_by_mapping_number(button.index + 1)
            # Translators: section header for mapping one button's click to another.
            row = ButtonRow(
                name,
                _("Button mapping"),
                RatbagdButton.ActionType.BUTTON,
                button.index + 1,
            )
            self.listbox.insert(row, i)
            if (
                self._action_type == RatbagdButton.ActionType.BUTTON
                and button.index + 1 == self._button.mapping
            ):
                self.listbox.select_row(row)
            i += 1
        for key, name in RatbagdButton.SPECIAL_DESCRIPTION.items():
            if name in ["Unknown", "Invalid"]:
                continue
            # Translators: section header for assigning special functions to buttons.
            row = ButtonRow(
                _(name), _("Special mapping"), RatbagdButton.ActionType.SPECIAL, key
            )
            self.listbox.insert(row, i)
            if (
                self._action_type == RatbagdButton.ActionType.SPECIAL
                and key == self._mapping
            ):
                self.listbox.select_row(row)
            i += 1

        row = ButtonRow(_("Disable"), _("Other"), RatbagdButton.ActionType.NONE, None)
        row.set_sensitive(RatbagdButton.ActionType.NONE in self._button.action_types)
        self.listbox.insert(row, i)
        i += 1
        if self._action_type == RatbagdButton.ActionType.NONE:
            self.listbox.select_row(row)

        if self._action_type == RatbagdButton.ActionType.MACRO:
            self._create_current_macro(macro=self._mapping)
        elif self._action_type == RatbagdButton.ActionType.KEY:
            macro = RatbagdMacro()
            macro.append(RatbagdButton.Macro.KEY_PRESS, self._mapping)
            macro.append(RatbagdButton.Macro.KEY_RELEASE, self._mapping)
            self._create_current_macro(macro=macro)
        else:
            self._create_current_macro()

    def _create_current_macro(self, macro: Optional[RatbagdMacro] = None) -> None:
        if macro is not None:
            self._current_macro = macro
            self._on_macro_updated(macro, None)
        else:
            self._current_macro = RatbagdMacro()
        self._current_macro.connect("macro-set", self._on_macro_set)
        self._current_macro.connect("notify::keys", self._on_macro_updated)

    def _listbox_header_func(self, row: ButtonRow, before: ButtonRow) -> None:
        # Adds headers to those rows where a new category starts, to separate
        # different kinds of mappings.
        if row == self.row_keystroke:
            separator = Gtk.Separator(
                orientation=Gtk.Orientation.HORIZONTAL, margin_top=18
            )
            row.set_header(separator)
            return

        add_header = row._section != before._section if before is not None else True

        if not add_header:
            row.set_header(None)
            return

        box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        if before is not None:
            box.set_margin_top(18)
        else:
            box.set_margin_top(6)

        markup = f"<b>{row._section}</b>"
        label = Gtk.Label(label=markup, use_markup=True, xalign=0.0, margin_start=6)
        label.get_style_context().add_class("dim-label")

        box.add(label)
        box.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        row.set_header(box)
        box.show_all()

    def _listbox_filter_func(self, row: Gtk.ListBoxRow) -> bool:
        # Filters the list box with the text from the search entry.
        if self.search_entry.get_text_length() == 0:
            return True

        if row is not self.row_keystroke:
            description = row.description.casefold()
        else:
            description = self.row_keystroke_label.get_label().casefold()
        search = self.search_entry.get_text().casefold()

        return all(term in description for term in search.split(" "))

    def _grab_seat(self) -> bool:
        """
        Grabs the keyboard seat. Returns True on success, False on failure.
        Gratefully copied from GNOME Control Center's keyboard panel.
        """
        window = self.get_window()
        assert window is not None
        display = window.get_display()
        seat: Gdk.Seat = display.get_default_seat()
        status = seat.grab(
            window, Gdk.SeatCapabilities.KEYBOARD, False, None, None, None, None
        )
        if status != Gdk.GrabStatus.SUCCESS:
            return False
        pointer = seat.get_keyboard()
        assert pointer is not None
        self._grab_pointer = pointer
        self.grab_add()
        return True

    def _release_grab(self) -> None:
        # Releases a previously grabbed keyboard seat, if any.
        if self._grab_pointer is None:
            return
        self._grab_pointer.get_seat().ungrab()
        self._grab_pointer = None
        self.grab_remove()

    def do_key_press_event(self, event: Gdk.Event) -> bool:
        # Overrides Gtk.Window's standard key press event callback, so we can
        # capture the pressed buttons in capture mode. If we're not in capture
        # mode, we trigger the search bar on any key press.
        if self.stack.get_visible_child_name() != "capture":
            if self.search_bar.handle_event(event) == Gdk.EVENT_STOP:
                return Gdk.EVENT_STOP
            return Gtk.Window.do_key_press_event(self, event)
        return self._do_key_event(event)

    def do_key_release_event(self, event: Gdk.Event) -> bool:
        # Overrides Gtk.Window's standard key release event callback, so we can
        # capture the released buttons in capture mode. If we're not in capture
        # mode, we pass the event on to other widgets in the dialog.
        if self.stack.get_visible_child_name() != "capture":
            return Gtk.Window.do_key_release_event(self, event)
        return self._do_key_event(event)

    def _do_key_event(self, event: Gdk.Event) -> bool:
        # Normalize tab.
        if event.keyval == Gdk.KEY_ISO_Left_Tab:
            event.keyval = Gdk.KEY_Tab

        # HACK: we don't want to use SysRq as a keybinding, but we do want
        # Al+Print, so we avoid translating Alt+Print to SysRq.
        if event.keyval == Gdk.KEY_Sys_Req and (
            event.state & Gdk.ModifierType.MOD1_MASK
        ):
            event.keyval = Gdk.KEY_Print

        if event.type == Gdk.EventType.KEY_PRESS:
            type = RatbagdButton.Macro.KEY_PRESS
        elif event.type == Gdk.EventType.KEY_RELEASE:
            type = RatbagdButton.Macro.KEY_RELEASE
        else:
            raise ValueError("Incorrect event type")

        # TODO: this needs to be checked for its Wayland support.
        if not self._XORG_KEYCODE_OFFSET <= event.hardware_keycode <= 255:
            print("Keycode is not within the valid range.", file=sys.stderr)
        else:
            assert self._current_macro is not None
            self._current_macro.append(
                type, event.hardware_keycode - self._XORG_KEYCODE_OFFSET
            )
        return Gdk.EVENT_STOP

    def _on_macro_updated(
        self, macro: RatbagdMacro, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        current_macro = str(self._current_macro)
        self.label_keystroke.set_label(current_macro)
        self.label_preview.set_label(current_macro)

    def _on_macro_set(self, macro: RatbagdMacro) -> None:
        # A macro has been set; update accordingly.
        if (
            RatbagdButton.ActionType.KEY in self._button.action_types
            and len(macro.keys) == 2
        ):  # single key (press + release events)
            self._action_type = RatbagdButton.ActionType.KEY
            type_, value = macro.keys[0]
            self._mapping = value
        else:
            self._action_type = RatbagdButton.ActionType.MACRO
            self._mapping = macro
        self.stack.set_visible_child_name("overview")
        self._release_grab()

    @Gtk.Template.Callback("_on_row_activated")
    def _on_row_activated(self, _listbox: Gtk.ListBox, row: ButtonRow) -> None:
        if row == self.row_keystroke:
            if self._grab_seat() is not True:
                # TODO: display this somewhere in the UI instead.
                print("Unable to grab keyboard, can't set keystroke", file=sys.stderr)
            else:
                self._create_current_macro()
                self.stack.set_visible_child_name("capture")
        else:
            self._action_type = row._action_type
            self._mapping = row._value

    @Gtk.Template.Callback("_on_apply_button_clicked")
    def _on_apply_button_clicked(self, button: Gtk.Button) -> Optional[bool]:
        if self.stack.get_visible_child_name() == "capture":
            assert self._current_macro is not None
            self._current_macro.accept()
        return Gdk.EVENT_PROPAGATE

    @Gtk.Template.Callback("_on_primary_mode_toggled")
    def _on_primary_mode_toggled(self, toggle: Gtk.RadioButton) -> None:
        if not toggle.get_active():
            return
        self._action_type = RatbagdButton.ActionType.BUTTON
        if toggle is self.radio_left_handed:
            self._mapping = ButtonDialog.LEFT_HANDED_MODE
        elif toggle is self.radio_right_handed:
            self._mapping = ButtonDialog.RIGHT_HANDED_MODE

    @GObject.Property
    def action_type(self) -> RatbagdButton.ActionType:
        """The action type as last set in the dialog, one of RatbagdButton.ActionType.*."""
        return self._action_type

    @GObject.Property
    def mapping(self) -> Union[RatbagdMacro, int]:
        """The mapping as last set in the dialog. Note that the type depends on
        action_type, and as such you should check that before using this
        property. A custom value of ButtonDialog.LEFT_HANDED_MODE means that
        the left- and right mouse buttons should be swapped, whereas
        ButtonDialog.RIGHT_HANDED_MODE means that the buttons should be as
        usual."""
        return self._mapping
