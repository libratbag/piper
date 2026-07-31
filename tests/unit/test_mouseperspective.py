# SPDX-License-Identifier: GPL-2.0-or-later

from types import SimpleNamespace

import pytest


@pytest.fixture
def perspective(piper_gresource):
    from piper.mouseperspective import MousePerspective

    return MousePerspective()


def _fake_profile(name="", index=0):
    return SimpleNamespace(name=name, index=index)


class _RecordingNotification:
    """Stands in for Gio.Notification, recording what would have been sent
    instead of building a real notification object."""

    def __init__(self, title):
        self.title = title
        self.body = None

    def set_body(self, body):
        self.body = body


@pytest.fixture(autouse=True)
def _stub_gio_notifications(monkeypatch, app):
    from piper import mouseperspective as mouseperspective_module

    monkeypatch.setattr(
        mouseperspective_module.Gio.Application, "get_default", lambda: app
    )
    monkeypatch.setattr(
        mouseperspective_module.Gio.Notification, "new", _RecordingNotification
    )


@pytest.fixture
def sent_notifications(app, monkeypatch):
    sent = []
    monkeypatch.setattr(
        app,
        "send_notification",
        lambda notification_id, n: sent.append((notification_id, n)),
    )
    return sent


def test_notify_profile_switch_sends_a_notification_with_the_profile_name(
    perspective, app, sent_notifications
):
    app.settings.set_boolean("notify-profile-switch", True)

    perspective._notify_profile_switch(_fake_profile(name="Aim", index=2))

    ((notification_id, notification),) = sent_notifications
    assert notification_id == "profile-switched"
    assert notification.body == "Switched to profile Aim"


def test_notify_profile_switch_falls_back_to_a_generic_name(
    perspective, app, sent_notifications
):
    app.settings.set_boolean("notify-profile-switch", True)

    perspective._notify_profile_switch(_fake_profile(name="", index=2))

    ((_, notification),) = sent_notifications
    assert notification.body == "Switched to profile Profile 2"


def test_notify_profile_switch_does_nothing_when_disabled(
    perspective, app, sent_notifications
):
    app.settings.set_boolean("notify-profile-switch", False)

    perspective._notify_profile_switch(_fake_profile(name="Aim"))

    assert sent_notifications == []


def test_notify_profile_switch_reuses_the_same_notification_id(
    perspective, app, sent_notifications
):
    app.settings.set_boolean("notify-profile-switch", True)

    perspective._notify_profile_switch(_fake_profile(name="Aim"))
    perspective._notify_profile_switch(_fake_profile(name="Precision"))

    ids = {notification_id for notification_id, _ in sent_notifications}
    assert ids == {"profile-switched"}


def test_on_active_profile_changed_triggers_a_notification(
    perspective, app, sent_notifications, monkeypatch
):
    monkeypatch.setattr(perspective, "_set_profile", lambda profile: None)
    app.settings.set_boolean("notify-profile-switch", True)

    perspective._on_active_profile_changed(None, _fake_profile(name="Aim"))

    assert len(sent_notifications) == 1
