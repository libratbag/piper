# SPDX-License-Identifier: GPL-2.0-or-later

import gi

gi.require_version("Gio", "2.0")
from gi.repository import GLib  # noqa: E402


def test_do_startup_creates_settings_with_expected_schema(app):
    assert app.settings.props.schema_id == "org.freedesktop.Piper"


def test_do_startup_registers_notify_profile_switch_action(app):
    assert app.lookup_action("notify-profile-switch") is not None


def test_notify_profile_switch_action_state_matches_setting(app):
    app.settings.set_boolean("notify-profile-switch", False)

    action = app.lookup_action("notify-profile-switch")

    assert action.get_state().get_boolean() is False


def test_activating_notify_profile_switch_action_toggles_the_setting(app):
    app.settings.set_boolean("notify-profile-switch", True)
    action = app.lookup_action("notify-profile-switch")

    action.change_state(GLib.Variant.new_boolean(False))

    assert app.settings.get_boolean("notify-profile-switch") is False
