# SPDX-License-Identifier: GPL-2.0-or-later

from gettext import gettext as _
from typing import Callable, List, Optional

from .errorperspective import ErrorPerspective
from .mouseperspective import MousePerspective
from .welcomeperspective import WelcomePerspective
from .ratbagd import (
    Ratbagd,
    RatbagdDevice,
    RatbagdIncompatibleError,
    RatbagdUnavailableError,
)

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Gio  # noqa


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/Window.ui")
class Window(Gtk.ApplicationWindow):
    """A Gtk.ApplicationWindow subclass to implement the main application
    window. This window displays the different perspectives (error, mouse and
    welcome) that each present their own behavior."""

    __gtype_name__ = "Window"

    primary_menu: Gtk.Menu = Gtk.Template.Child()  # type: ignore
    stack_perspectives: Gtk.Stack = Gtk.Template.Child()  # type: ignore
    stack_titlebar: Gtk.Stack = Gtk.Template.Child()  # type: ignore

    def __init__(self, init_ratbagd_cb: Callable[[], Ratbagd], *args, **kwargs) -> None:
        """Instantiates a new Window.

        @param ratbag The ratbag instance to connect to, as ratbagd.Ratbag
        """
        Gtk.ApplicationWindow.__init__(self, *args, **kwargs)

        self.set_icon_name("org.freedesktop.Piper")

        self._add_perspective(ErrorPerspective(), None)
        try:
            ratbag = init_ratbagd_cb()
        except RatbagdUnavailableError:
            self._present_error_perspective(
                _("Cannot connect to ratbagd"),
                _(
                    "Please make sure ratbagd is running and your user is in the required group"
                ),
            )
            return
        except RatbagdIncompatibleError as e:
            self._present_error_perspective(
                _(
                    f"Incompatible ratbagd API version (required: {e.required_version}, provided: {e.ratbagd_version})"
                ),
                _("Please update both piper and libratbag to the latest versions"),
            )
            return

        for perspective in [MousePerspective(), WelcomePerspective()]:
            self._add_perspective(perspective, ratbag)

        welcome_perspective: WelcomePerspective = self._get_child("welcome_perspective")  # type: ignore
        welcome_perspective.connect("device-selected", self._on_device_selected)

        ratbag.connect("device-added", self._on_device_added)
        ratbag.connect("device-removed", self._on_device_removed)
        ratbag.connect("daemon-disappeared", self._on_daemon_disappeared)

        if len(ratbag.devices) == 0:
            self._present_error_perspective(
                _("Cannot find any devices"),
                _("Please make sure your device is supported and plugged in"),
            )
        elif len(ratbag.devices) == 1:
            self._present_mouse_perspective(ratbag.devices[0])
        else:
            self._present_welcome_perspective(ratbag.devices)

    def do_delete_event(self, event: Gdk.Event) -> bool:
        for perspective in self.stack_perspectives.get_children():
            if not perspective.can_shutdown:
                dialog = Gtk.MessageDialog(
                    self,
                    Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.QUESTION,
                    Gtk.ButtonsType.YES_NO,
                    _("There are unapplied changes. Are you sure you want to quit?"),
                )
                response = dialog.run()
                dialog.destroy()

                if response in [Gtk.ResponseType.NO, Gtk.ResponseType.DELETE_EVENT]:
                    return Gdk.EVENT_STOP
        return Gdk.EVENT_PROPAGATE

    def _on_daemon_disappeared(self, ratbag: Ratbagd) -> None:
        self._present_error_perspective(
            _("Ooops. ratbagd has disappeared"), _("Please restart Piper")
        )

    def _on_device_added(self, ratbag: Ratbagd, device: RatbagdDevice) -> None:
        if len(ratbag.devices) == 1:
            # We went from 0 devices to 1 device; immediately configure it.
            self._present_mouse_perspective(device)
        elif self.stack_perspectives.get_visible_child_name() == "welcome_perspective":
            # We're in the welcome perspective; just add it to the list.
            welcome_perspective: WelcomePerspective = self._get_child(
                "welcome_perspective"
            )  # type: ignore
            welcome_perspective.add_device(device)
        else:
            # We're configuring another device; just notify the user.
            # TODO: show in-app notification?
            print("Device connected")

    def _on_device_removed(self, ratbag: Ratbagd, device: RatbagdDevice) -> None:
        mouse_perspective: MousePerspective = self._get_child("mouse_perspective")  # type: ignore
        visible_perspective = self.stack_perspectives.get_visible_child_name()

        if (
            visible_perspective == "mouse_perspective"
            and device is mouse_perspective.device
        ):
            # The current device disconnected, which can only happen from the
            # mouse perspective as we'd otherwise be in the welcome screen with
            # more than one device remaining. Hence, we display the error
            # perspective.
            self._present_error_perspective(
                _("Your device disconnected!"),
                _("Please make sure your device is plugged in"),
            )
        elif visible_perspective == "welcome_perspective":
            # We're in the welcome screen; just remove it from the list. If
            # there is nothing left, display the error perspective.
            welcome_perspective: WelcomePerspective = self._get_child("welcome_perspective")  # type: ignore
            welcome_perspective.remove_device(device)
            if len(ratbag.devices) == 0:
                self._present_error_perspective(
                    _("Cannot find any devices"),
                    _("Please make sure your device is supported and plugged in"),
                )
        else:
            # We're configuring another device; just notify the user.
            # TODO: show in-app notification?
            print("Device disconnected")

    def _add_perspective(self, perspective, ratbag: Optional[Ratbagd]) -> None:
        self.stack_perspectives.add_named(perspective, perspective.name)
        self.stack_titlebar.add_named(perspective.titlebar, perspective.name)
        if perspective.can_go_back:
            if ratbag is None:
                raise ValueError(
                    "`ratbag` must be provided if the perspective can go back"
                )
            self._perspective_add_back_button(perspective, ratbag)
        self._perspective_add_primary_menu(perspective)

    def _present_welcome_perspective(self, devices: List[RatbagdDevice]) -> None:
        # Present the welcome perspective for the user to select one of their
        # devices.
        welcome_perspective: WelcomePerspective = self._get_child("welcome_perspective")  # type: ignore
        welcome_perspective.set_devices(devices)

        self.stack_titlebar.set_visible_child_name(welcome_perspective.name)
        self.stack_perspectives.set_visible_child_name(welcome_perspective.name)

    def _present_mouse_perspective(self, device: RatbagdDevice) -> None:
        # Present the mouse configuration perspective for the given device.
        try:
            mouse_perspective: MousePerspective = self._get_child("mouse_perspective")  # type: ignore
            mouse_perspective.set_device(device)

            self.stack_titlebar.set_visible_child_name(mouse_perspective.name)
            self.stack_perspectives.set_visible_child_name(mouse_perspective.name)
        except ValueError as e:
            self._present_error_perspective(_("Cannot display device SVG"), str(e))
        except GLib.Error as e:
            # Happens with the GetSvgFd() call when running against older
            # python. This can be removed when we've had the newer call out
            # for a while. The full error is printed to stderr by
            # ratbagd.py.
            if e.code == Gio.DBusError.UNKNOWN_METHOD:
                self._present_error_perspective(
                    _("Newer version of ratbagd required"),
                    _("Please update to the latest available version"),
                )
            else:
                self._present_error_perspective(
                    _("Unknown exception occurred"), e.message
                )

    def _present_error_perspective(self, message: str, detail: str) -> None:
        # Present the error perspective informing the user of any errors.
        error_perspective: ErrorPerspective = self._get_child("error_perspective")  # type: ignore
        error_perspective.set_message(message)
        error_perspective.set_detail(detail)

        self.stack_titlebar.set_visible_child_name(error_perspective.name)
        self.stack_perspectives.set_visible_child_name(error_perspective.name)

    def _on_device_selected(self, perspective, device: RatbagdDevice) -> None:
        self._present_mouse_perspective(device)

    def _get_child(self, name: str) -> Gtk.Widget:
        child = self.stack_perspectives.get_child_by_name(name)
        if child is None:
            raise ValueError(f"Child `{name}` was not found")
        return child

    def _perspective_add_back_button(self, perspective, ratbag: Ratbagd) -> None:
        button_back = Gtk.Button.new_from_icon_name(
            "go-previous-symbolic", Gtk.IconSize.BUTTON
        )
        button_back.set_visible(len(ratbag.devices) > 1)
        button_back.connect(
            "clicked",
            lambda _, ratbag: self._present_welcome_perspective(ratbag.devices),
            ratbag,
        )
        ratbag.connect(
            "notify::devices",
            lambda ratbag, _: button_back.set_visible(len(ratbag.devices) > 1),
        )
        perspective.titlebar.add(button_back)
        # Place the button first in the titlebar.
        perspective.titlebar.child_set_property(button_back, "position", 0)

    def _perspective_add_primary_menu(self, perspective) -> None:
        hamburger = Gtk.Image.new_from_icon_name(
            "open-menu-symbolic", Gtk.IconSize.BUTTON
        )
        hamburger.set_visible(True)
        button_primary_menu = Gtk.MenuButton.new()
        button_primary_menu.add(hamburger)
        button_primary_menu.set_visible(True)
        button_primary_menu.set_menu_model(self.primary_menu)
        perspective.titlebar.pack_end(button_primary_menu)
        # Place the button last in the titlebar.
        perspective.titlebar.child_set_property(button_primary_menu, "position", 0)
