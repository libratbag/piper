# SPDX-License-Identifier: GPL-2.0-or-later


def test_schema_registers_expected_keys(settings):
    assert set(settings.props.settings_schema.list_keys()) == {
        "notify-profile-switch",
    }


def test_notify_profile_switch_defaults_to_true(settings):
    assert settings.get_boolean("notify-profile-switch") is True


def test_set_and_get_notify_profile_switch(settings):
    settings.set_boolean("notify-profile-switch", False)
    assert settings.get_boolean("notify-profile-switch") is False


def test_changed_signal_emitted_on_toggle(settings):
    changes = []
    settings.connect("changed::notify-profile-switch", lambda s, k: changes.append(k))

    settings.set_boolean("notify-profile-switch", False)

    assert changes == ["notify-profile-switch"]
