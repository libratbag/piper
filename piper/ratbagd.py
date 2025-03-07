# Copyright 2016-2019 Red Hat, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice (including the next
# paragraph) shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import os
import sys
import hashlib

from enum import IntEnum
from evdev import ecodes
from gettext import gettext as _
from gi.repository import Gio, GLib, GObject
from typing import List, Optional, Tuple, Union


# Deferred translations, see https://docs.python.org/3/library/gettext.html#deferred-translations
def N_(x):
    return x


def evcode_to_str(evcode: int) -> str:
    # Values in ecodes.keys are stored as either a str or list[str].
    value = ecodes.keys[evcode]
    if isinstance(value, list):
        return value[0]
    return value


class RatbagErrorCode(IntEnum):
    SUCCESS = 0

    """An error occurred on the device. Either the device is not a libratbag
    device or communication with the device failed."""
    DEVICE = -1000

    """Insufficient capabilities. This error occurs when a requested change is
    beyond the device's capabilities."""
    CAPABILITY = -1001

    """Invalid value or value range. The provided value or value range is
    outside of the legal or supported range."""
    VALUE = -1002

    """A low-level system error has occurred, e.g. a failure to access files
    that should be there. This error is usually unrecoverable and libratbag will
    print a log message with details about the error."""
    SYSTEM = -1003

    """Implementation bug, either in libratbag or in the caller. This error is
    usually unrecoverable and libratbag will print a log message with details
    about the error."""
    IMPLEMENTATION = -1004


class RatbagDeviceType(IntEnum):
    """DeviceType property specified in the .device files"""

    """There was no DeviceType specified for this device"""
    UNSPECIFIED = 0

    """Device is specified as anything other than a mouse or a keyboard"""
    OTHER = 1

    """Device is specified as a mouse"""
    MOUSE = 2

    """Device is specified as a keyboard"""
    KEYBOARD = 3


class RatbagdIncompatibleError(Exception):
    """ratbagd is incompatible with this client"""

    def __init__(self, ratbagd_version, required_version):
        super().__init__()
        self.ratbagd_version = ratbagd_version
        self.required_version = required_version
        self.message = f"ratbagd API version is {ratbagd_version} but we require {required_version}"

    def __str__(self):
        return self.message


class RatbagdUnavailableError(Exception):
    """Signals DBus is unavailable or the ratbagd daemon is not available."""


class RatbagdDBusTimeoutError(Exception):
    """Signals that a timeout occurred during a DBus method call."""


class RatbagError(Exception):
    """A common base exception to catch any ratbag exception."""


class RatbagDeviceError(RatbagError):
    """An exception corresponding to RatbagErrorCode.DEVICE."""


class RatbagCapabilityError(RatbagError):
    """An exception corresponding to RatbagErrorCode.CAPABILITY."""


class RatbagValueError(RatbagError):
    """An exception corresponding to RatbagErrorCode.VALUE."""


class RatbagSystemError(RatbagError):
    """An exception corresponding to RatbagErrorCode.SYSTEM."""


class RatbagImplementationError(RatbagError):
    """An exception corresponding to RatbagErrorCode.IMPLEMENTATION."""


"""A table mapping RatbagErrorCode values to RatbagError* exceptions."""
EXCEPTION_TABLE = {
    RatbagErrorCode.DEVICE: RatbagDeviceError,
    RatbagErrorCode.CAPABILITY: RatbagCapabilityError,
    RatbagErrorCode.VALUE: RatbagValueError,
    RatbagErrorCode.SYSTEM: RatbagSystemError,
    RatbagErrorCode.IMPLEMENTATION: RatbagImplementationError,
}


class _RatbagdDBus(GObject.GObject):
    _dbus = None

    def __init__(self, interface, object_path):
        super().__init__()

        if _RatbagdDBus._dbus is None:
            try:
                _RatbagdDBus._dbus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            except GLib.Error as e:
                raise RatbagdUnavailableError(e.message) from e

        ratbag1 = "org.freedesktop.ratbag1"
        if os.environ.get("RATBAG_TEST"):
            ratbag1 = "org.freedesktop.ratbag_devel1"

        if object_path is None:
            object_path = "/" + ratbag1.replace(".", "/")

        self._object_path = object_path
        self._interface = f"{ratbag1}.{interface}"

        try:
            self._proxy = Gio.DBusProxy.new_sync(
                _RatbagdDBus._dbus,
                Gio.DBusProxyFlags.NONE,
                None,
                ratbag1,
                object_path,
                self._interface,
                None,
            )
        except GLib.Error as e:
            raise RatbagdUnavailableError(e.message) from e

        if self._proxy.get_name_owner() is None:
            raise RatbagdUnavailableError(f"No one currently owns {ratbag1}")

        self._proxy.connect("g-properties-changed", self._on_properties_changed)
        self._proxy.connect("g-signal", self._on_signal_received)

    def _on_properties_changed(self, proxy, changed_props, invalidated_props):
        # Implement this in derived classes to respond to property changes.
        pass

    def _on_signal_received(self, proxy, sender_name, signal_name, parameters):
        # Implement this in derived classes to respond to signals.
        pass

    def _find_object_with_path(self, iterable, object_path):
        # Find the index of an object in an iterable that whose object path
        # matches the given object path.
        for index, obj in enumerate(iterable):
            if obj._object_path == object_path:
                return index
        return -1

    def _get_dbus_property(self, property):
        # Retrieves a cached property from the bus, or None.
        p = self._proxy.get_cached_property(property)
        if p is not None:
            return p.unpack()
        return p

    def _get_dbus_property_nonnull(self, property: str):
        p = self._get_dbus_property(property)
        if p is None:
            raise ValueError(f"D-Bus API returned `None` for property {property}")
        return p

    def _set_dbus_property(self, property, type, value, readwrite=True):
        # Sets a cached property on the bus.

        # Take our real value and wrap it into a variant. To call
        # org.freedesktop.DBus.Properties.Set we need to wrap that again
        # into a (ssv), where v is our value's variant.
        # args to .Set are "interface name", "function name",  value-variant
        val = GLib.Variant(f"{type}", value)
        if readwrite:
            pval = GLib.Variant("(ssv)", (self._interface, property, val))
            self._proxy.call_sync(
                "org.freedesktop.DBus.Properties.Set",
                pval,
                Gio.DBusCallFlags.NO_AUTO_START,
                2000,
                None,
            )

        # This is our local copy, so we don't have to wait for the async
        # update
        self._proxy.set_cached_property(property, val)

    def _dbus_call(self, method, type, *value):
        # Calls a method synchronously on the bus, using the given method name,
        # type signature and values.
        #
        # If the result is valid, it is returned. Invalid results raise the
        # appropriate RatbagError* or RatbagdDBus* exception, or GLib.Error if
        # it is an unexpected exception that probably shouldn't be passed up to
        # the UI.
        val = GLib.Variant(f"({type})", value)
        try:
            res = self._proxy.call_sync(
                method, val, Gio.DBusCallFlags.NO_AUTO_START, 2000, None
            )
            if res in EXCEPTION_TABLE:
                raise EXCEPTION_TABLE[res]
            return res.unpack()[0]  # Result is always a tuple
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.TIMED_OUT:
                raise RatbagdDBusTimeoutError(e.message) from e

            # Unrecognized error code.
            print(e.message, file=sys.stderr)
            raise

    def __eq__(self, other):
        return other and self._object_path == other._object_path


class Ratbagd(_RatbagdDBus):
    """The ratbagd top-level object. Provides a list of devices available
    through ratbagd; actual interaction with the devices is via the
    RatbagdDevice, RatbagdProfile, RatbagdResolution and RatbagdButton objects.

    Throws RatbagdUnavailableError when the DBus service is not available.
    """

    __gsignals__ = {
        "device-added": (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
        "device-removed": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (GObject.TYPE_PYOBJECT,),
        ),
        "daemon-disappeared": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, api_version):
        super().__init__("Manager", None)
        result = self._get_dbus_property("Devices")
        if result is None and not self._proxy.get_cached_property_names():
            raise RatbagdUnavailableError(
                "Make sure it is running and your user is in the required groups."
            )
        if self.api_version != api_version:
            raise RatbagdIncompatibleError(self.api_version or -1, api_version)
        self._devices = [RatbagdDevice(objpath) for objpath in result or []]
        self._proxy.connect("notify::g-name-owner", self._on_name_owner_changed)

    def _on_name_owner_changed(self, *kwargs):
        self.emit("daemon-disappeared")

    def _on_properties_changed(self, proxy, changed_props, invalidated_props):
        try:
            new_device_object_paths = changed_props["Devices"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            object_paths = [d._object_path for d in self._devices]
            for object_path in new_device_object_paths:
                if object_path not in object_paths:
                    device = RatbagdDevice(object_path)
                    self._devices.append(device)
                    self.emit("device-added", device)
            for device in self.devices:
                if device._object_path not in new_device_object_paths:
                    self._devices.remove(device)
                    self.emit("device-removed", device)
            self.notify("devices")

    @GObject.Property
    def api_version(self):
        return self._get_dbus_property("APIVersion")

    @GObject.Property
    def devices(self):
        """A list of RatbagdDevice objects supported by ratbagd."""
        return self._devices

    def __getitem__(self, id):
        """Returns the requested device, or None."""
        for d in self.devices:
            if d.id == id:
                return d
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class RatbagdDevice(_RatbagdDBus):
    """Represents a ratbagd device."""

    __gsignals__ = {
        "active-profile-changed": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (GObject.TYPE_PYOBJECT,),
        ),
        "resync": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, object_path):
        super().__init__("Device", object_path)

        # FIXME: if we start adding and removing objects from this list,
        # things will break!
        result = self._get_dbus_property("Profiles") or []
        self._profiles = [RatbagdProfile(objpath) for objpath in result]
        for profile in self._profiles:
            profile.connect("notify::is-active", self._on_active_profile_changed)

        # Use a SHA1 of our object path as our device's ID
        self._id = hashlib.sha1(object_path.encode("utf-8")).hexdigest()

    def _on_signal_received(self, proxy, sender_name, signal_name, parameters):
        if signal_name == "Resync":
            self.emit("resync")

    def _on_active_profile_changed(self, profile, pspec):
        if profile.is_active:
            self.emit("active-profile-changed", self._profiles[profile.index])

    @GObject.Property
    def id(self):
        return self._id

    @id.setter
    def id(self, id):
        self._id = id

    @GObject.Property
    def model(self):
        """The unique identifier for this device model."""
        return self._get_dbus_property("Model")

    @GObject.Property
    def name(self):
        """The device name, usually provided by the kernel."""
        return self._get_dbus_property("Name")

    @GObject.Property
    def device_type(self):
        """The device type, see RatbagDeviceType"""
        return RatbagDeviceType(self._get_dbus_property("DeviceType"))

    @GObject.Property
    def firmware_version(self):
        """The firmware version of the device."""
        return self._get_dbus_property("FirmwareVersion")

    @GObject.Property
    def profiles(self):
        """A list of RatbagdProfile objects provided by this device."""
        return self._profiles

    @GObject.Property
    def active_profile(self):
        """The currently active profile. This is a non-DBus property computed
        over the cached list of profiles. In the unlikely case that your device
        driver is misconfigured and there is no active profile, this returns
        `None`."""
        for profile in self._profiles:
            if profile.is_active:
                return profile
        print(
            "No active profile. Please report this bug to the libratbag developers",
            file=sys.stderr,
        )
        return None

    def commit(self):
        """Commits all changes made to the device.

        This is implemented asynchronously inside ratbagd. Hence, we just call
        this method and always succeed.  Any failure is handled inside ratbagd
        by emitting the Resync signal, which automatically resynchronizes the
        device. No further interaction is required by the client.
        """
        self._dbus_call("Commit", "")


class RatbagdProfile(_RatbagdDBus):
    """Represents a ratbagd profile."""

    CAP_WRITABLE_NAME = 100
    CAP_SET_DEFAULT = 101
    CAP_DISABLE = 102
    CAP_WRITE_ONLY = 103

    def __init__(self, object_path):
        super().__init__("Profile", object_path)
        self._active = self._get_dbus_property("IsActive")
        self._angle_snapping = self._get_dbus_property("AngleSnapping")
        self._debounce = self._get_dbus_property("Debounce")
        self._dirty = self._get_dbus_property("IsDirty")
        self._disabled = self._get_dbus_property("Disabled")
        self._report_rate = self._get_dbus_property("ReportRate")

        # FIXME: if we start adding and removing objects from any of these
        # lists, things will break!
        result = self._get_dbus_property("Resolutions") or []
        self._resolutions = [RatbagdResolution(objpath) for objpath in result]
        self._subscribe_dirty(self._resolutions)

        result = self._get_dbus_property("Buttons") or []
        self._buttons = [RatbagdButton(objpath) for objpath in result]
        self._subscribe_dirty(self._buttons)

        result = self._get_dbus_property("Leds") or []
        self._leds = [RatbagdLed(objpath) for objpath in result]
        self._subscribe_dirty(self._leds)

    def _subscribe_dirty(self, objects: List[GObject.GObject]):
        for obj in objects:
            obj.connect("notify", self._on_obj_notify)

    def _on_obj_notify(self, obj: GObject.GObject, pspec: Optional[GObject.ParamSpec]):
        if not self._dirty:
            self._dirty = True
            self.notify("dirty")

    def _on_properties_changed(self, proxy, changed_props, invalidated_props):
        try:
            angle_snapping = changed_props["AngleSnapping"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if angle_snapping != self._angle_snapping:
                self._angle_snapping = angle_snapping
                self.notify("angle-snapping")

        try:
            debounce = changed_props["Debounce"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if debounce != self._debounce:
                self._debounce = debounce
                self.notify("debounce")

        try:
            disabled = changed_props["Disabled"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if disabled != self._disabled:
                self._disabled = disabled
                self.notify("disabled")

        try:
            active = changed_props["IsActive"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if active != self._active:
                self._active = active
                self.notify("is-active")

        try:
            dirty = changed_props["IsDirty"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if dirty != self._dirty:
                self._dirty = dirty
                self.notify("dirty")

        try:
            report_rate = changed_props["ReportRate"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if report_rate != self._report_rate:
                self._report_rate = report_rate
                self.notify("report-rate")

    @GObject.Property
    def capabilities(self):
        """The capabilities of this profile as an array. Capabilities not
        present on the profile are not in the list. Thus use e.g.

        if RatbagdProfile.CAP_WRITABLE_NAME in profile.capabilities:
            do something
        """
        return self._get_dbus_property("Capabilities") or []

    @GObject.Property
    def name(self):
        """The name of the profile"""
        return self._get_dbus_property("Name")

    @name.setter
    def name(self, name):
        """Set the name of this profile.

        @param name The new name, as str"""
        self._set_dbus_property("Name", "s", name)

    @GObject.Property
    def index(self):
        """The index of this profile."""
        return self._get_dbus_property("Index")

    @GObject.Property
    def dirty(self):
        """Whether this profile is dirty."""
        return self._dirty

    @GObject.Property
    def disabled(self):
        """tells if the profile is disabled."""
        return self._disabled

    @disabled.setter
    def disabled(self, disabled):
        """Enable/Disable this profile.

        @param disabled The new state, as boolean"""
        self._set_dbus_property("Disabled", "b", disabled)

    @GObject.Property
    def report_rate(self) -> int:
        """The report rate in Hz."""
        return self._report_rate

    @report_rate.setter
    def report_rate(self, rate):
        """Set the report rate in Hz.

        @param rate The new report rate, as int
        """
        self._set_dbus_property("ReportRate", "u", rate)

    @GObject.Property
    def report_rates(self):
        """The list of supported report rates"""
        return self._get_dbus_property("ReportRates") or []

    @GObject.Property
    def angle_snapping(self):
        """The angle snapping option."""
        return self._angle_snapping

    @angle_snapping.setter
    def angle_snapping(self, value):
        """Set the angle snapping option.

        @param value The angle snapping option as int
        """
        self._set_dbus_property("AngleSnapping", "i", value)

    @GObject.Property
    def debounce(self):
        """The button debounce time in ms."""
        return self._debounce

    @debounce.setter
    def debounce(self, value):
        """Set the button debounce time in ms.

        @param value The button debounce time, as int
        """
        self._set_dbus_property("Debounce", "i", value)

    @GObject.Property
    def debounces(self):
        """The list of supported debounce times"""
        return self._get_dbus_property("Debounces") or []

    @GObject.Property
    def resolutions(self):
        """A list of RatbagdResolution objects with this profile's resolutions.
        Note that the list of resolutions differs between profiles but the number
        of resolutions is identical across profiles."""
        return self._resolutions

    @GObject.Property
    def active_resolution(self):
        """The currently active resolution of this profile. This is a non-DBus
        property computed over the cached list of resolutions. In the unlikely
        case that your device driver is misconfigured and there is no active
        resolution, this returns `None`."""
        for resolution in self._resolutions:
            if resolution.is_active:
                return resolution
        print(
            "No active resolution. Please report this bug to the libratbag developers",
            file=sys.stderr,
        )
        return None

    @GObject.Property
    def buttons(self):
        """A list of RatbagdButton objects with this profile's button mappings.
        Note that the list of buttons differs between profiles but the number
        of buttons is identical across profiles."""
        return self._buttons

    @GObject.Property
    def leds(self):
        """A list of RatbagdLed objects with this profile's leds. Note that the
        list of leds differs between profiles but the number of leds is
        identical across profiles."""
        return self._leds

    @GObject.Property
    def is_active(self):
        """Returns True if the profile is currently active, false otherwise."""
        return self._active

    def set_active(self):
        """Set this profile to be the active profile."""
        ret = self._dbus_call("SetActive", "")
        self._set_dbus_property("IsActive", "b", True, readwrite=False)
        return ret


class RatbagdResolution(_RatbagdDBus):
    """Represents a ratbagd resolution."""

    CAP_SEPARATE_XY_RESOLUTION = 1
    CAP_DISABLE = 2

    def __init__(self, object_path):
        super().__init__("Resolution", object_path)
        self._active = self._get_dbus_property("IsActive")
        self._default = self._get_dbus_property("IsDefault")
        self._disabled = self._get_dbus_property("IsDisabled")
        self._resolution = self._convert_resolution_from_dbus(
            self._get_dbus_property_nonnull("Resolution")
        )

    def _on_properties_changed(self, proxy, changed_props, invalidated_props):
        try:
            resolution = self._convert_resolution_from_dbus(changed_props["Resolution"])
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if resolution != self._resolution:
                self._resolution = resolution
                self.notify("resolution")

        try:
            active = changed_props["IsActive"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if active != self._active:
                self._active = active
                self.notify("is-active")

        try:
            default = changed_props["IsDefault"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if default != self._default:
                self._default = default
                self.notify("is-default")

        try:
            disabled = changed_props["IsDisabled"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if disabled != self._disabled:
                self._disabled = disabled
                self.notify("is-disabled")

    @GObject.Property
    def capabilities(self):
        """The capabilities of this resolution as an array. Capabilities not
        present on the resolution are not in the list. Thus use e.g.

        if resolution.CAP_DISABLE in resolution.capabilities:
            do something
        """
        return self._get_dbus_property("Capabilities") or []

    @GObject.Property
    def index(self):
        """The index of this resolution."""
        return self._get_dbus_property("Index")

    @staticmethod
    def _convert_resolution_from_dbus(
        res: Union[int, Tuple[int, int]],
    ) -> Union[Tuple[int], Tuple[int, int]]:
        """
        Convert resolution from what D-Bus API returns - either an int or a tuple of two ints, to a tuple of either one or two ints.
        """
        if isinstance(res, int):
            return (res,)
        return res

    @GObject.Property
    def resolution(self):
        """The resolution in DPI, either as single value tuple ``(res, )``
        or as tuple ``(xres, yres)``.
        """
        return self._resolution

    @resolution.setter
    def resolution(self, resolution):
        """Set the x- and y-resolution using the given (xres, yres) tuple.

        @param res The new resolution, as (int, int)
        """
        res = self.resolution
        if len(res) != len(resolution) or len(res) > 2:
            raise ValueError("invalid resolution precision")
        if len(res) == 1:
            variant = GLib.Variant("u", resolution[0])
        else:
            variant = GLib.Variant("(uu)", resolution)
        self._set_dbus_property("Resolution", "v", variant)

    @GObject.Property
    def resolutions(self):
        """The list of supported DPI values"""
        return self._get_dbus_property("Resolutions") or []

    @GObject.Property
    def is_active(self):
        """True if this is the currently active resolution, False
        otherwise"""
        return self._active

    @GObject.Property
    def is_default(self):
        """True if this is the currently default resolution, False
        otherwise"""
        return self._default

    @GObject.Property
    def is_disabled(self):
        """True if this is currently disabled, False otherwise"""
        return self._disabled

    def set_active(self):
        """Set this resolution to be the active one."""
        ret = self._dbus_call("SetActive", "")
        self._set_dbus_property("IsActive", "b", True, readwrite=False)
        return ret

    def set_default(self):
        """Set this resolution to be the default."""
        ret = self._dbus_call("SetDefault", "")
        self._set_dbus_property("IsDefault", "b", True, readwrite=False)
        return ret

    def set_disabled(self, disable):
        """Set this resolution to be disabled."""
        return self._set_dbus_property("IsDisabled", "b", disable)


class RatbagdButton(_RatbagdDBus):
    """Represents a ratbagd button."""

    class ActionType(IntEnum):
        NONE = 0
        BUTTON = 1
        SPECIAL = 2
        KEY = 3
        MACRO = 4

    class ActionSpecial(IntEnum):
        INVALID = -1
        UNKNOWN = 1 << 30
        DOUBLECLICK = (1 << 30) + 1
        WHEEL_LEFT = (1 << 30) + 2
        WHEEL_RIGHT = (1 << 30) + 3
        WHEEL_UP = (1 << 30) + 4
        WHEEL_DOWN = (1 << 30) + 5
        RATCHET_MODE_SWITCH = (1 << 30) + 6
        RESOLUTION_CYCLE_UP = (1 << 30) + 7
        RESOLUTION_CYCLE_DOWN = (1 << 30) + 8
        RESOLUTION_UP = (1 << 30) + 9
        RESOLUTION_DOWN = (1 << 30) + 10
        RESOLUTION_ALTERNATE = (1 << 30) + 11
        RESOLUTION_DEFAULT = (1 << 30) + 12
        PROFILE_CYCLE_UP = (1 << 30) + 13
        PROFILE_CYCLE_DOWN = (1 << 30) + 14
        PROFILE_UP = (1 << 30) + 15
        PROFILE_DOWN = (1 << 30) + 16
        SECOND_MODE = (1 << 30) + 17
        BATTERY_LEVEL = (1 << 30) + 18

    class Macro(IntEnum):
        NONE = 0
        KEY_PRESS = 1
        KEY_RELEASE = 2
        WAIT = 3

    """A table mapping a button's index to its usual function as defined by X
    and the common desktop environments."""
    BUTTON_DESCRIPTION = {
        0: N_("Left mouse button click"),
        1: N_("Right mouse button click"),
        2: N_("Middle mouse button click"),
        3: N_("Backward"),
        4: N_("Forward"),
    }

    """A table mapping a special function to its human-readable description."""
    SPECIAL_DESCRIPTION = {
        ActionSpecial.INVALID: N_("Invalid"),
        ActionSpecial.UNKNOWN: N_("Unknown"),
        ActionSpecial.DOUBLECLICK: N_("Doubleclick"),
        ActionSpecial.WHEEL_LEFT: N_("Wheel Left"),
        ActionSpecial.WHEEL_RIGHT: N_("Wheel Right"),
        ActionSpecial.WHEEL_UP: N_("Wheel Up"),
        ActionSpecial.WHEEL_DOWN: N_("Wheel Down"),
        ActionSpecial.RATCHET_MODE_SWITCH: N_("Ratchet Mode"),
        ActionSpecial.RESOLUTION_CYCLE_UP: N_("Cycle Resolution Up"),
        ActionSpecial.RESOLUTION_CYCLE_DOWN: N_("Cycle Resolution Down"),
        ActionSpecial.RESOLUTION_UP: N_("Resolution Up"),
        ActionSpecial.RESOLUTION_DOWN: N_("Resolution Down"),
        ActionSpecial.RESOLUTION_ALTERNATE: N_("Resolution Switch"),
        ActionSpecial.RESOLUTION_DEFAULT: N_("Default Resolution"),
        ActionSpecial.PROFILE_CYCLE_UP: N_("Cycle Profile Up"),
        ActionSpecial.PROFILE_CYCLE_DOWN: N_("Cycle Profile Down"),
        ActionSpecial.PROFILE_UP: N_("Profile Up"),
        ActionSpecial.PROFILE_DOWN: N_("Profile Down"),
        ActionSpecial.SECOND_MODE: N_("Second Mode"),
        ActionSpecial.BATTERY_LEVEL: N_("Battery Level"),
    }

    def __init__(self, object_path):
        super().__init__("Button", object_path)

    def _on_properties_changed(self, proxy, changed_props, invalidated_props):
        if "Mapping" in changed_props.keys():
            self.notify("action-type")

    def _mapping(self):
        return self._get_dbus_property("Mapping")

    @GObject.Property
    def index(self):
        """The index of this button."""
        return self._get_dbus_property("Index")

    @GObject.Property
    def mapping(self):
        """An integer of the current button mapping, if mapping to a button
        or None otherwise."""
        type, button = self._mapping()
        if type != RatbagdButton.ActionType.BUTTON:
            return None
        return button

    @mapping.setter
    def mapping(self, button):
        """Set the button mapping to the given button.

        @param button The button to map to, as int
        """
        button = GLib.Variant("u", button)
        self._set_dbus_property(
            "Mapping", "(uv)", (RatbagdButton.ActionType.BUTTON, button)
        )

    @GObject.Property
    def macro(self):
        """A RatbagdMacro object representing the currently set macro or
        None otherwise."""
        type, macro = self._mapping()
        if type != RatbagdButton.ActionType.MACRO:
            return None
        return RatbagdMacro.from_ratbag(macro)

    @macro.setter
    def macro(self, macro):
        """Set the macro to the macro represented by the given RatbagdMacro
        object.

        @param macro A RatbagdMacro object representing the macro to apply to
                     the button, as RatbagdMacro.
        """
        macro = GLib.Variant("a(uu)", macro.keys)
        self._set_dbus_property(
            "Mapping", "(uv)", (RatbagdButton.ActionType.MACRO, macro)
        )

    @GObject.Property
    def special(self):
        """An enum describing the current special mapping, if mapped to
        special or None otherwise."""
        type, special = self._mapping()
        if type != RatbagdButton.ActionType.SPECIAL:
            return None
        return special

    @special.setter
    def special(self, special):
        """Set the button mapping to the given special entry.

        @param special The special entry, as one of RatbagdButton.ActionSpecial
        """
        special = GLib.Variant("u", special)
        self._set_dbus_property(
            "Mapping", "(uv)", (RatbagdButton.ActionType.SPECIAL, special)
        )

    @GObject.Property
    def key(self):
        type, key = self._mapping()
        if type != RatbagdButton.ActionType.KEY:
            return None
        return key

    @key.setter
    def key(self, key):
        key = GLib.Variant("u", key)
        self._set_dbus_property("Mapping", "(uv)", (RatbagdButton.ActionType.KEY, key))

    @GObject.Property
    def action_type(self):
        """An enum describing the action type of the button. One of
        ActionType.NONE, ActionType.BUTTON, ActionType.SPECIAL,
        ActionType.MACRO. This decides which
        *Mapping property has a value.
        """
        type, mapping = self._mapping()
        return type

    @GObject.Property
    def action_types(self):
        """An array of possible values for ActionType."""
        return self._get_dbus_property("ActionTypes")

    @GObject.Property
    def disabled(self):
        type, unused = self._mapping()
        return type == RatbagdButton.ActionType.NONE

    def disable(self):
        """Disables this button."""
        zero = GLib.Variant("u", 0)
        self._set_dbus_property(
            "Mapping", "(uv)", (RatbagdButton.ActionType.NONE, zero)
        )


class RatbagdMacro(GObject.Object):
    """Represents a button macro. Note that it uses keycodes as defined by
    linux/input-event-codes.h and not those used by X.Org or any other higher
    layer such as Gdk."""

    # Both a key press and release.
    _MACRO_KEY = 1000

    _MACRO_DESCRIPTION = {
        RatbagdButton.Macro.KEY_PRESS: lambda key: f"↓{evcode_to_str(key)}",
        RatbagdButton.Macro.KEY_RELEASE: lambda key: f"↑{evcode_to_str(key)}",
        RatbagdButton.Macro.WAIT: lambda val: f"{val}ms",
        _MACRO_KEY: lambda key: f"↕{evcode_to_str(key)}",
    }

    __gsignals__ = {
        "macro-set": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._macro = []

    def __str__(self):
        if not self._macro:
            # Translators: this is used when there is no macro to preview.
            return _("None")

        keys = []
        idx = 0
        while idx < len(self._macro):
            t, v = self._macro[idx]
            try:
                if t == RatbagdButton.Macro.KEY_PRESS:
                    # Check for a paired press/release event
                    t2, v2 = self._macro[idx + 1]
                    if t2 == RatbagdButton.Macro.KEY_RELEASE and v == v2:
                        t = self._MACRO_KEY
                        idx += 1
            except IndexError:
                pass
            keys.append(self._MACRO_DESCRIPTION[t](v))
            idx += 1
        return " ".join(keys)

    @GObject.Property
    def keys(self):
        """A list of (RatbagdButton.Macro.*, value) tuples representing the
        current macro."""
        return self._macro

    @staticmethod
    def from_ratbag(macro):
        """Instantiates a new RatbagdMacro instance from the given macro in
        libratbag format.

        @param macro The macro in libratbag format, as
                     [(RatbagdButton.Macro.*, value)].
        """
        ratbagd_macro = RatbagdMacro()

        # Do not emit notify::keys for every key that we add.
        with ratbagd_macro.freeze_notify():
            for type, value in macro:
                ratbagd_macro.append(type, value)
        return ratbagd_macro

    def accept(self):
        """Applies the currently cached macro."""
        self.emit("macro-set")

    def append(self, type, value):
        """Appends the given event to the current macro.

        @param type The type of event, as one of RatbagdButton.Macro.*.
        @param value If the type denotes a key event, the X.Org or Gdk keycode
                     of the event, as int. Otherwise, the value of the timeout
                     in milliseconds, as int.
        """
        # Only append if the entry isn't identical to the last one, as we cannot
        # e.g. have two identical key presses in a row.
        if len(self._macro) == 0 or (type, value) != self._macro[-1]:
            self._macro.append((type, value))
            self.notify("keys")


class RatbagdLed(_RatbagdDBus):
    """Represents a ratbagd led."""

    class Mode(IntEnum):
        OFF = 0
        ON = 1
        CYCLE = 2
        BREATHING = 3

    class ColorDepth(IntEnum):
        MONOCHROME = 0
        RGB_888 = 1
        RGB_111 = 2

    LED_DESCRIPTION = {
        # Translators: the LED is off.
        Mode.OFF: N_("Off"),
        # Translators: the LED has a single, solid color.
        Mode.ON: N_("Solid"),
        # Translators: the LED is cycling between red, green and blue.
        Mode.CYCLE: N_("Cycle"),
        # Translators: the LED's is pulsating a single color on different
        # brightnesses.
        Mode.BREATHING: N_("Breathing"),
    }

    def __init__(self, object_path):
        super().__init__("Led", object_path)

        self._brightness = self._get_dbus_property("Brightness")
        self._color = self._get_dbus_property("Color")
        self._effect_duration = self._get_dbus_property("EffectDuration")
        self._mode: RatbagdLed.Mode = self._get_dbus_property_nonnull("Mode")

    @GObject.Property
    def index(self):
        """The index of this led."""
        return self._get_dbus_property("Index")

    @GObject.Property
    def mode(self):
        """This led's mode, one of Mode.OFF, Mode.ON, Mode.CYCLE and
        Mode.BREATHING."""
        return self._mode

    @mode.setter
    def mode(self, mode):
        """Set the led's mode to the given mode.

        @param mode The new mode, as one of Mode.OFF, Mode.ON, Mode.CYCLE and
                    Mode.BREATHING.
        """
        self._set_dbus_property("Mode", "u", mode)

    @GObject.Property
    def modes(self):
        """The supported modes as a list"""
        return self._get_dbus_property("Modes")

    @GObject.Property
    def color(self):
        """An integer triple of the current LED color."""
        return self._color

    @color.setter
    def color(self, color):
        """Set the led color to the given color.

        @param color An RGB color, as an integer triplet with values 0-255.
        """
        self._set_dbus_property("Color", "(uuu)", color)

    @GObject.Property
    def colordepth(self):
        """An enum describing this led's colordepth, one of
        RatbagdLed.ColorDepth.MONOCHROME, RatbagdLed.ColorDepth.RGB"""
        return self._get_dbus_property("ColorDepth")

    @GObject.Property
    def effect_duration(self):
        """The LED's effect duration in ms, values range from 0 to 10000."""
        return self._effect_duration

    @effect_duration.setter
    def effect_duration(self, effect_duration):
        """Set the effect duration in ms. Allowed values range from 0 to 10000.

        @param effect_duration The new effect duration, as int
        """
        self._set_dbus_property("EffectDuration", "u", effect_duration)

    @GObject.Property
    def brightness(self):
        """The LED's brightness, values range from 0 to 255."""
        return self._brightness

    @brightness.setter
    def brightness(self, brightness):
        """Set the brightness. Allowed values range from 0 to 255.

        @param brightness The new brightness, as int
        """
        self._set_dbus_property("Brightness", "u", brightness)

    def _on_properties_changed(self, proxy, changed_props, invalidated_props):
        try:
            brightness = changed_props["Brightness"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if brightness != self._brightness:
                self._brightness = brightness
                self.notify("brightness")

        try:
            color = changed_props["Color"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if color != self._color:
                self._color = color
                self.notify("color")

        try:
            effect_duration = changed_props["EffectDuration"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if effect_duration != self._effect_duration:
                self._effect_duration = effect_duration
                self.notify("effect-duration")

        try:
            mode = changed_props["Mode"]
        except KeyError:
            # Different property changed, skip.
            pass
        else:
            if mode != self._mode:
                self._mode = mode
                self.notify("mode")
