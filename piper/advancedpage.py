# SPDX-License-Identifier: GPL-2.0-or-later

import sys
from typing import Optional
import gi

from .mousemap import MouseMap
from .ratbagd import RatbagdDevice, RatbagdProfile
from .util.gobject import connect_signal_with_weak_ref

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa: E402


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/AdvancedPage.ui")
class AdvancedPage(Gtk.Box):
    """
    Advanced settings stack.
    """

    __gtype_name__ = "AdvancedPage"

    angle_snapping: Gtk.Switch = Gtk.Template.Child()  # type: ignore
    debounce: Gtk.ComboBox = Gtk.Template.Child()  # type: ignore
    rate_1000: Gtk.RadioButton = Gtk.Template.Child()  # type: ignore
    rate_125: Gtk.RadioButton = Gtk.Template.Child()  # type: ignore
    rate_250: Gtk.RadioButton = Gtk.Template.Child()  # type: ignore
    rate_500: Gtk.RadioButton = Gtk.Template.Child()  # type: ignore
    rate_button_box: Gtk.ButtonBox = Gtk.Template.Child()  # type: ignore
    charging_control: Gtk.Switch = Gtk.Template.Child()  # type: ignore

    def __init__(
        self, device: RatbagdDevice, profile: RatbagdProfile, *args, **kwargs
    ) -> None:
        """Instantiates a new AdvancedPage."""
        Gtk.Box.__init__(self, *args, **kwargs)

        self._profile = profile

        cell = Gtk.CellRendererText()
        self.debounce.pack_start(cell, True)
        self.debounce.add_attribute(cell, "text", 0)

        model = Gtk.ListStore(str)
        for ms in profile.debounces:
            model.append([str(ms)])
        self.debounce.set_model(model)

        self._handler_debounce = self.debounce.connect(
            "changed", self._on_debounce_combo_changed
        )

        self._profile_debounce_time_changed_handler = connect_signal_with_weak_ref(
            self,
            self._profile,
            "notify::debounce",
            self._on_profile_debounce_time_changed,
        )
        self._update_widget_debounce_time()

        are_report_rates_supported = (
            profile.report_rate != 0 and len(profile.report_rates) != 0
        )
        self.rate_button_box.set_sensitive(are_report_rates_supported)
        self.rate_125.set_sensitive(125 in profile.report_rates)
        self.rate_250.set_sensitive(250 in profile.report_rates)
        self.rate_500.set_sensitive(500 in profile.report_rates)
        self.rate_1000.set_sensitive(1000 in profile.report_rates)

        self._handler_125 = self.rate_125.connect(
            "toggled", self._on_report_rate_toggled, 125
        )
        self._handler_250 = self.rate_250.connect(
            "toggled", self._on_report_rate_toggled, 250
        )
        self._handler_500 = self.rate_500.connect(
            "toggled", self._on_report_rate_toggled, 500
        )
        self._handler_1000 = self.rate_1000.connect(
            "toggled", self._on_report_rate_toggled, 1000
        )

        self._profile_report_rate_changed_handler = connect_signal_with_weak_ref(
            self,
            self._profile,
            "notify::report-rate",
            self._on_profile_report_rate_changed,
        )
        self._update_widget_report_rate()

        profile = self._profile

        self._mousemap = MouseMap("#Buttons", device, spacing=20, border_width=20)
        self.pack_start(self._mousemap, True, True, 0)

        self._angle_snapping_switch_handler = self.angle_snapping.connect(
            "state-set", self._on_angle_snapping_switch_state_set
        )

        self.angle_snapping.set_sensitive(profile.angle_snapping != -1)

        self._profile_angle_snapping_changed_handler = connect_signal_with_weak_ref(
            self,
            self._profile,
            "notify::angle-snapping",
            self._on_profile_angle_snapping_changed,
        )
        self._update_widget_angle_snapping()

        self._charging_control_switch_handler = self.charging_control.connect(
            "state-set", self._on_charging_control_switch_state_set
        )

        self.charging_control.set_sensitive(profile.charging_control != -1)

        self._profile_charging_control_changed_handler = connect_signal_with_weak_ref(
            self,
            self._profile,
            "notify::charging-control",
            self._on_profile_charging_control_changed,
        )
        self._update_widget_charging_control()

        self.show_all()

    def _on_profile_debounce_time_changed(
        self, profile: RatbagdProfile, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        self._update_widget_debounce_time()

    def _update_widget_debounce_time(self) -> None:
        profile = self._profile

        with self.debounce.handler_block(self._handler_debounce):
            if profile.debounce in profile.debounces:
                idx = profile.debounces.index(profile.debounce)
                self.debounce.set_active(idx)
            else:
                self.debounce.set_active(0)

    def _on_debounce_combo_changed(self, combo: Gtk.ComboBox) -> None:
        idx = combo.get_active()
        profile = self._profile
        with profile.handler_block(self._profile_debounce_time_changed_handler):
            profile.debounce = profile.debounces[idx]

    def _on_angle_snapping_switch_state_set(
        self, button: Gtk.Switch, state: bool
    ) -> None:
        profile = self._profile
        with profile.handler_block(self._profile_angle_snapping_changed_handler):
            profile.angle_snapping = 1 if state else 0

    def _on_profile_angle_snapping_changed(
        self, profile: RatbagdProfile, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        self._update_widget_angle_snapping()

    def _update_widget_angle_snapping(self) -> None:
        with self.angle_snapping.handler_block(self._angle_snapping_switch_handler):
            self.angle_snapping.set_active(self._profile.angle_snapping == 1)

    def _on_report_rate_toggled(self, button: Gtk.RadioButton, rate: int) -> None:
        if not button.get_active():
            return
        profile = self._profile
        with profile.handler_block(self._profile_report_rate_changed_handler):
            profile.report_rate = rate

    def _on_profile_report_rate_changed(
        self, profile: RatbagdProfile, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        self._update_widget_report_rate()

    def _update_widget_report_rate(self) -> None:
        with self.rate_125.handler_block(self._handler_125):
            if self._profile.report_rate == 125:
                self.rate_125.set_active(True)
                return

        with self.rate_250.handler_block(self._handler_250):
            if self._profile.report_rate == 250:
                self.rate_250.set_active(True)
                return

        with self.rate_500.handler_block(self._handler_500):
            if self._profile.report_rate == 500:
                self.rate_500.set_active(True)
                return

        with self.rate_1000.handler_block(self._handler_1000):
            if self._profile.report_rate == 1000:
                self.rate_1000.set_active(True)
                return

        # TODO: think how we should handle this.
        print(
            f"Profile was set to a weird report rate: {self._profile.report_rate}",
            file=sys.stderr,
        )

    def _on_charging_control_switch_state_set(
        self, button: Gtk.Switch, state: bool
    ) -> None:
        profile = self._profile
        with profile.handler_block(self._profile_charging_control_changed_handler):
            profile.charging_control = 1 if state else 0

    def _on_profile_charging_control_changed(
        self, profile: RatbagdProfile, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        self._update_widget_charging_control()

    def _update_widget_charging_control(self) -> None:
        with self.charging_control.handler_block(self._charging_control_switch_handler):
            self.charging_control.set_active(self._profile.charging_control == 1)
