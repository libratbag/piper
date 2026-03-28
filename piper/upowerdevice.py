# SPDX-License-Identifier: GPL-2.0-or-later

from typing import List, Optional

from gi.repository import Gio, GLib, GObject


class UPowerDevice(GObject.GObject):
    """Wraps a UPower DBus device to expose battery information for
    peripheral devices (mice, keyboards, etc.)."""

    UPOWER_BUS_NAME = "org.freedesktop.UPower"
    UPOWER_MANAGER_PATH = "/org/freedesktop/UPower"
    UPOWER_MANAGER_INTERFACE = "org.freedesktop.UPower"
    UPOWER_DEVICE_INTERFACE = "org.freedesktop.UPower.Device"

    # UPower UpDeviceKind values
    KIND_MOUSE = 5
    KIND_KEYBOARD = 6
    KIND_GAMING_INPUT = 12

    # UPower UpDeviceState values
    STATE_UNKNOWN = 0
    STATE_CHARGING = 1
    STATE_DISCHARGING = 2
    STATE_FULLY_CHARGED = 4
    STATE_PENDING_CHARGE = 5
    STATE_PENDING_DISCHARGE = 6

    __gsignals__ = {
        "battery-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, object_path: str) -> None:
        super().__init__()
        dbus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self._proxy = Gio.DBusProxy.new_sync(
            dbus,
            Gio.DBusProxyFlags.NONE,
            None,
            self.UPOWER_BUS_NAME,
            object_path,
            self.UPOWER_DEVICE_INTERFACE,
            None,
        )
        self._proxy.connect("g-properties-changed", self._on_properties_changed)

    def _on_properties_changed(
        self, proxy: Gio.DBusProxy, changed_props: GLib.Variant, invalidated_props: list
    ) -> None:
        changed = changed_props.unpack()
        if "Percentage" in changed or "State" in changed:
            self.emit("battery-changed")

    def _get_prop(self, name: str):
        p = self._proxy.get_cached_property(name)
        return p.unpack() if p is not None else None

    @GObject.Property
    def percentage(self) -> float:
        """The battery level as a percentage (0–100)."""
        return self._get_prop("Percentage") or 0.0

    @GObject.Property
    def state(self) -> int:
        """The battery state (see STATE_* constants)."""
        return self._get_prop("State") or self.STATE_UNKNOWN

    @GObject.Property
    def model(self) -> str:
        """The device model string as reported by UPower."""
        return self._get_prop("Model") or ""

    @GObject.Property
    def device_type(self) -> int:
        """The UPower device kind (see KIND_* constants)."""
        return self._get_prop("Type") or 0

    @GObject.Property
    def is_present(self) -> bool:
        """Whether the device is currently present/connected."""
        return self._get_prop("IsPresent") or False

    @staticmethod
    def find_mouse_batteries() -> List["UPowerDevice"]:
        """Returns a list of UPowerDevice objects for all present mouse or
        gaming-input batteries found via UPower."""
        try:
            dbus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            manager = Gio.DBusProxy.new_sync(
                dbus,
                Gio.DBusProxyFlags.NONE,
                None,
                UPowerDevice.UPOWER_BUS_NAME,
                UPowerDevice.UPOWER_MANAGER_PATH,
                UPowerDevice.UPOWER_MANAGER_INTERFACE,
                None,
            )
            result = manager.call_sync(
                "EnumerateDevices",
                None,
                Gio.DBusCallFlags.NO_AUTO_START,
                2000,
                None,
            )
            device_paths = result.unpack()[0]
        except GLib.Error:
            return []

        devices = []
        for path in device_paths:
            try:
                dev = UPowerDevice(path)
                mouse_kinds = {UPowerDevice.KIND_MOUSE, UPowerDevice.KIND_GAMING_INPUT}
                if dev.device_type in mouse_kinds and dev.is_present:
                    devices.append(dev)
            except GLib.Error:
                pass
        return devices

    @staticmethod
    def find_for_device(device_name: str) -> Optional["UPowerDevice"]:
        """Returns the UPowerDevice best matching *device_name*, or None.

        Matching strategy:
          1. Word-set intersection: the candidate with the most words in
             common (case-insensitive) wins, provided it shares at least
             half the words of the shorter name.
          2. If no name-based match is found and exactly one mouse battery
             is present, return it unconditionally (common single-mouse
             setup).
        """
        candidates = UPowerDevice.find_mouse_batteries()
        if not candidates:
            return None

        ratbag_words = set(device_name.casefold().split())

        best: Optional[UPowerDevice] = None
        best_score = 0.0
        for dev in candidates:
            upower_words = set(dev.model.casefold().split())
            if not upower_words:
                continue
            common = ratbag_words & upower_words
            # Score: fraction of the shorter name covered by common words
            threshold = min(len(ratbag_words), len(upower_words))
            score = len(common) / threshold if threshold else 0.0
            if score >= 0.5 and score > best_score:
                best_score = score
                best = dev

        if best is not None:
            return best

        # Fallback: single mouse battery present
        if len(candidates) == 1:
            return candidates[0]

        return None

    @staticmethod
    def icon_name_for(percentage: float, state: int) -> str:
        """Returns an appropriate symbolic icon name for the given battery
        percentage and charge state."""
        charging = state in (
            UPowerDevice.STATE_CHARGING,
            UPowerDevice.STATE_PENDING_CHARGE,
        )
        suffix = "-charging" if charging else ""

        if state == UPowerDevice.STATE_FULLY_CHARGED:
            return "battery-full-charged-symbolic"
        if percentage >= 80:
            level = "full"
        elif percentage >= 50:
            level = "good"
        elif percentage >= 20:
            level = "low"
        else:
            level = "caution"

        return f"battery-{level}{suffix}-symbolic"
