# SPDX-License-Identifier: GPL-2.0-or-later

import sys

from gettext import gettext as _
from typing import List, Optional, Tuple, Union

from .ratbagd import RatbagdButton, RatbagdMacro, RatbagDeviceType, evcode_to_str

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa


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
    capture_box: Gtk.Box = Gtk.Template.Child()  # type: ignore
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
        # the names of the macros of the profile, to name and show macros
        self._macro_names = kwargs.pop("macro_names", None)
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

        self._macro_name = self._existing_macro_name()
        self._recording = False
        self._held_keys: set = set()
        self._rebuild_source: Optional[int] = None
        self._scroll_to_end = False
        self._build_capture_ui()

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
        # mappings are 1-indexed and thus right mouse click has value 2.
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

        # row 0 is the macro recorder, the other rows follow it
        i = 1
        for button in buttons:
            key, name = self._get_button_name_and_description(button)
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
            # the first row of the list, nothing to separate it from
            row.set_header(None)
            return

        after_recorder = before is not None and before == self.row_keystroke
        add_header = (
            True
            if before is None or after_recorder
            else row._section != before._section
        )

        if not add_header:
            row.set_header(None)
            return

        box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        if before is not None:
            box.set_margin_top(18)
        else:
            box.set_margin_top(6)  # the recorder row is filtered out

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

    def _get_button_name_and_description(
        self, button: RatbagdButton
    ) -> Tuple[str, str]:
        # Translators: the {} will be replaced with the button index, e.g.
        # "Button 1 click".
        name = _("Button {} click").format(button.index)
        if button.index in RatbagdButton.BUTTON_DESCRIPTION:
            description = _(RatbagdButton.BUTTON_DESCRIPTION[button.index])
        else:
            description = name
        return name, description

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
        if not self._recording:
            # editing values, such as a delay: normal keyboard handling
            return Gtk.Window.do_key_press_event(self, event)
        return self._do_key_event(event)

    def do_key_release_event(self, event: Gdk.Event) -> bool:
        # Overrides Gtk.Window's standard key release event callback, so we can
        # capture the released buttons in capture mode. If we're not in capture
        # mode, we pass the event on to other widgets in the dialog.
        if self.stack.get_visible_child_name() != "capture" or not self._recording:
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
            return Gdk.EVENT_STOP

        keycode = event.hardware_keycode - self._XORG_KEYCODE_OFFSET
        if type == RatbagdButton.Macro.KEY_PRESS:
            if keycode in self._held_keys:
                # key repeat while the key is held down
                return Gdk.EVENT_STOP
            self._held_keys.add(keycode)
        else:
            if keycode not in self._held_keys:
                # release of a key that was pressed before recording started
                return Gdk.EVENT_STOP
            self._held_keys.discard(keycode)

        self._record_event(type, keycode)
        return Gdk.EVENT_STOP

    def _record_event(self, type: int, keycode: int) -> None:
        macro = self._current_macro
        assert macro is not None
        delay = self._default_delay.get_value_as_int()
        self._scroll_to_end = True
        with macro.freeze_notify():
            # a delay box between this event and the previous one
            if (
                delay > 0
                and macro.keys
                and macro.keys[-1][0] != RatbagdButton.Macro.WAIT
            ):
                macro.add_delay(delay)
            macro.add_event(type, keycode)

    def _on_macro_updated(
        self, macro: RatbagdMacro, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        self._update_macro_label()
        self._schedule_rebuild()

    def _on_macro_set(self, macro: RatbagdMacro) -> None:
        # A macro has been set; update accordingly.
        if (
            RatbagdButton.ActionType.KEY in self._button.action_types
            and len(macro.keys) == 2
            and macro.keys[0][0] == RatbagdButton.Macro.KEY_PRESS
            and macro.keys[1][0] == RatbagdButton.Macro.KEY_RELEASE
            and macro.keys[0][1] == macro.keys[1][1]
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
                # start from what the button does now, so it can be edited
                self._create_current_macro(
                    macro=RatbagdMacro.from_ratbag(self._existing_macro_events())
                )
                self.stack.set_visible_child_name("capture")
                self._held_keys.clear()
                self._set_recording(True)
        else:
            self._action_type = row._action_type
            self._mapping = row._value

    def _existing_macro_name(self) -> str:
        # The name the button's current macro was given, if any.
        if self._macro_names is None:
            return ""
        name = self._macro_names.get(
            self._button.index,
            self._existing_macro_events(),
            RatbagdButton.Macro.WAIT,
        )
        return name or ""

    def _update_macro_label(self) -> None:
        # The macro is shown by its name, or by its keys if it has none.
        self.label_keystroke.set_label(self._macro_name or str(self._current_macro))

    @GObject.Property(type=str)
    def macro_name(self) -> str:
        """The name given to the macro, as str. Empty if it has none."""
        return self._macro_name

    def _on_name_changed(self, entry: Gtk.Entry) -> None:
        self._macro_name = entry.get_text().strip()
        self._update_macro_label()

    def _existing_macro_events(self) -> list:
        # The events the button currently triggers, as (type, value) tuples.
        if self._action_type == RatbagdButton.ActionType.MACRO and isinstance(
            self._mapping, RatbagdMacro
        ):
            return list(self._mapping.keys)
        if self._action_type == RatbagdButton.ActionType.KEY and isinstance(
            self._mapping, int
        ):
            return [
                (RatbagdButton.Macro.KEY_PRESS, self._mapping),
                (RatbagdButton.Macro.KEY_RELEASE, self._mapping),
            ]
        return []

    def _build_capture_ui(self) -> None:
        # The macro editor: a vertical stack of key events, each with its own
        # box and a box with a delay in between, and a side panel.
        intro = Gtk.Label(
            label=_(
                "Press the keys of the macro. Every key press and release is "
                "an event of its own, with a delay between the events."
            ),
            xalign=0,
            wrap=True,
        )
        self.capture_box.pack_start(intro, False, False, 0)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name_row.pack_start(Gtk.Label(label=_("Name")), False, False, 0)
        self._name_entry = Gtk.Entry(
            placeholder_text=_("Macro name (optional)"), max_length=40, hexpand=True
        )
        self._name_entry.set_text(self._macro_name)
        self._name_entry.connect("changed", self._on_name_changed)
        self._name_entry.connect("focus-in-event", self._on_value_focused)
        name_row.pack_start(self._name_entry, True, True, 0)
        self.capture_box.pack_start(name_row, False, False, 0)

        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.capture_box.pack_start(columns, True, True, 0)

        self._events_scroll = Gtk.ScrolledWindow(
            shadow_type=Gtk.ShadowType.IN,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            min_content_height=320,
            min_content_width=420,
            hexpand=True,
            vexpand=True,
        )
        self._events_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8
        )
        self._events_scroll.add(self._events_box)
        columns.pack_start(self._events_scroll, True, True, 0)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        columns.pack_start(side, False, False, 0)

        self._record_button = Gtk.ToggleButton()
        self._record_button.set_tooltip_text(
            _(
                "While recording, every key you press becomes part of the "
                "macro. Stop recording to type a value into a delay."
            )
        )
        self._record_handler = self._record_button.connect(
            "toggled", self._on_record_toggled
        )
        side.pack_start(self._record_button, False, False, 0)

        frame = Gtk.Frame(label=_("Default delay"))
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        frame.add(inner)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._default_delay = Gtk.SpinButton.new_with_range(0, 65535, 10)
        self._default_delay.set_value(50)
        self._default_delay.set_numeric(True)
        self._default_delay.connect("focus-in-event", self._on_value_focused)
        row.pack_start(self._default_delay, False, False, 0)
        row.pack_start(Gtk.Label(label=_("ms")), False, False, 0)
        inner.pack_start(row, False, False, 0)
        hint = Gtk.Label(
            label=_("Added between recorded events. Use 0 to add none."),
            xalign=0,
            wrap=True,
            max_width_chars=22,
        )
        hint.get_style_context().add_class("dim-label")
        inner.pack_start(hint, False, False, 0)
        side.pack_start(frame, False, False, 0)

        clear = Gtk.Button(label=_("Clear all"))
        clear.connect("clicked", self._on_clear_clicked)
        side.pack_end(clear, False, False, 0)

        self.capture_box.show_all()

    def _set_recording(self, recording: bool) -> None:
        self._recording = recording
        self._record_button.handler_block(self._record_handler)
        self._record_button.set_active(recording)
        self._record_button.handler_unblock(self._record_handler)
        self._record_button.set_label(
            _("Stop recording") if recording else _("Start recording")
        )
        if recording:
            # no widget, such as a delay field, may keep the keyboard focus
            self.set_focus(None)

    def _on_record_toggled(self, button: Gtk.ToggleButton) -> None:
        self._set_recording(button.get_active())

    def _on_value_focused(self, widget: Gtk.Widget, event: Gdk.Event) -> bool:
        # Clicking into a value means the user wants to type into it.
        if self._recording:
            self._set_recording(False)
        return Gdk.EVENT_PROPAGATE

    def _on_clear_clicked(self, button: Gtk.Button) -> None:
        if self._current_macro is not None:
            self._held_keys.clear()
            self._current_macro.clear()

    def _schedule_rebuild(self) -> None:
        # Rebuilding right away would destroy a button while it handles its
        # own click, and recording several events at once should only redraw
        # once.
        if self._rebuild_source is None:
            self._rebuild_source = GLib.idle_add(self._rebuild_events)

    def _rebuild_events(self) -> bool:
        self._rebuild_source = None
        for child in self._events_box.get_children():
            child.destroy()

        keys = self._current_macro.keys if self._current_macro else []
        if not keys:
            empty = Gtk.Label(
                label=_("No events yet. Press a key to record it."),
                margin=24,
            )
            empty.get_style_context().add_class("dim-label")
            self._events_box.pack_start(empty, False, False, 0)

        for index, (kind, value) in enumerate(keys):
            if kind == RatbagdButton.Macro.WAIT:
                widget = self._make_delay_row(index, value)
            else:
                widget = self._make_event_row(index, kind, value)
            self._events_box.pack_start(widget, False, False, 0)

            # offer to put a delay between two events that have none
            following = keys[index + 1] if index + 1 < len(keys) else None
            if (
                kind != RatbagdButton.Macro.WAIT
                and following is not None
                and following[0] != RatbagdButton.Macro.WAIT
            ):
                self._events_box.pack_start(
                    self._make_add_delay_button(index + 1), False, False, 0
                )

        self._events_box.show_all()
        if self._scroll_to_end:
            self._scroll_to_end = False
            GLib.idle_add(self._scroll_events_to_end)
        return GLib.SOURCE_REMOVE

    def _scroll_events_to_end(self) -> bool:
        adjustment = self._events_scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        return GLib.SOURCE_REMOVE

    def _make_number_label(self, index: int) -> Gtk.Label:
        # The position of the event in the macro, delays included, to keep
        # track of them by eye.
        label = Gtk.Label(label=str(index + 1), width_chars=3, xalign=1)
        label.get_style_context().add_class("dim-label")
        return label

    def _make_remove_button(self, index: int, tooltip: str) -> Gtk.Button:
        button = Gtk.Button.new_from_icon_name(
            "window-close-symbolic", Gtk.IconSize.BUTTON
        )
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_valign(Gtk.Align.CENTER)
        button.set_tooltip_text(tooltip)
        button.connect("clicked", self._on_remove_clicked, index)
        return button

    def _on_remove_clicked(self, button: Gtk.Button, index: int) -> None:
        if self._current_macro is not None:
            self._current_macro.remove_at(index)

    def _make_event_row(self, index: int, kind: int, keycode: int) -> Gtk.Widget:
        pressed = kind == RatbagdButton.Macro.KEY_PRESS
        frame = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, margin=6)
        frame.add(box)
        box.pack_start(self._make_number_label(index), False, False, 0)

        arrow = Gtk.Label(width_chars=2)
        arrow.set_markup("<big><b>{}</b></big>".format("↓" if pressed else "↑"))
        box.pack_start(arrow, False, False, 0)

        name = Gtk.Label(xalign=0, hexpand=True)
        name.set_markup(f"<b>{GLib.markup_escape_text(evcode_to_str(keycode))}</b>")
        box.pack_start(name, True, True, 0)

        description = Gtk.Label(
            label=_("Key down") if pressed else _("Key up"), xalign=1
        )
        description.get_style_context().add_class("dim-label")
        box.pack_start(description, False, False, 0)

        box.pack_start(
            self._make_remove_button(index, _("Remove this event")), False, False, 0
        )
        return frame

    def _make_delay_row(self, index: int, milliseconds: int) -> Gtk.Widget:
        frame = Gtk.Frame(margin_start=28)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin=6)
        frame.add(box)
        box.pack_start(self._make_number_label(index), False, False, 0)

        spin = Gtk.SpinButton.new_with_range(1, RatbagdMacro.MAX_DELAY_MS, 10)
        spin.set_value(milliseconds)
        spin.set_numeric(True)
        spin.connect("focus-in-event", self._on_value_focused)
        spin.connect("value-changed", self._on_delay_changed, index)
        box.pack_start(spin, False, False, 0)
        box.pack_start(Gtk.Label(label=_("ms")), False, False, 0)

        description = Gtk.Label(
            label=_("Delay before the next event"), xalign=1, hexpand=True
        )
        description.get_style_context().add_class("dim-label")
        box.pack_start(description, True, True, 0)

        box.pack_start(
            self._make_remove_button(index, _("Remove this delay")), False, False, 0
        )
        return frame

    def _on_delay_changed(self, spin: Gtk.SpinButton, index: int) -> None:
        # The spin button stays where it is, so only the macro is updated.
        if self._current_macro is not None:
            self._current_macro.set_delay(index, spin.get_value_as_int())
            self._update_macro_label()

    def _make_add_delay_button(self, index: int) -> Gtk.Widget:
        button = Gtk.Button(label=_("+ delay"))
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_halign(Gtk.Align.START)
        button.set_margin_start(28)
        button.set_tooltip_text(_("Insert a delay between these two events"))
        button.connect("clicked", self._on_add_delay_clicked, index)
        return button

    def _on_add_delay_clicked(self, button: Gtk.Button, index: int) -> None:
        if self._current_macro is not None:
            self._current_macro.insert_delay(
                index, max(1, self._default_delay.get_value_as_int())
            )

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
