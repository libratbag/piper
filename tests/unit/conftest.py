# SPDX-License-Identifier: GPL-2.0-or-later

import os
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SOURCE_DIR = REPO_ROOT / "data"
GRESOURCE_PATH = Path(
    os.environ.get(
        "PIPER_GRESOURCE_PATH", str(REPO_ROOT / "builddir" / "data" / "piper.gresource")
    )
)

# Gio.Settings caches its default schema source and default backend for the
# lifetime of the process the first time either is used, and GLib reads the
# GSETTINGS_SCHEMA_DIR/GSETTINGS_BACKEND environment variables that control
# them very early (before `gi`/`Gio` is even imported). Both are pointed at
# test-only locations here, before `gi` is imported anywhere in the test
# session, so that application code constructing a plain
# Gio.Settings(schema_id=...) during these tests never touches the real
# system schema directory or the developer's real dconf database. Tests that
# need a fully isolated store per-test (see the `settings` fixture below)
# still build their own explicit in-memory backend instead of relying on
# this process-wide default.
_compiled_schema_dir = tempfile.mkdtemp(prefix="piper-test-schemas-")
subprocess.run(
    [
        "glib-compile-schemas",
        "--targetdir",
        _compiled_schema_dir,
        str(SCHEMA_SOURCE_DIR),
    ],
    check=True,
)
os.environ["GSETTINGS_SCHEMA_DIR"] = _compiled_schema_dir
os.environ["GSETTINGS_BACKEND"] = "memory"

import gi  # noqa: E402
import pytest  # noqa: E402

gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio  # noqa: E402

_gresource_registered = False


@pytest.fixture(scope="session")
def piper_gresource():
    """Registers the compiled piper.gresource bundle. Required before
    constructing any Gtk.Template-based widget class, since its UI is loaded
    from the bundle by resource path. Skips (rather than fails) if the
    project hasn't been built yet, since `meson test` always builds it first
    but a bare `pytest` invocation might not have."""
    global _gresource_registered
    if not GRESOURCE_PATH.exists():
        pytest.skip(f"{GRESOURCE_PATH} not built; run `ninja -C builddir` first")
    if not _gresource_registered:
        resource = Gio.resource_load(str(GRESOURCE_PATH))
        Gio.Resource._register(resource)
        _gresource_registered = True


@pytest.fixture
def settings():
    """A Gio.Settings instance for org.freedesktop.Piper, backed by a fresh
    in-memory Gio.SettingsBackend private to this test -- fully isolated from
    other tests and from the process-wide default backend set up above."""
    schema_source = Gio.SettingsSchemaSource.new_from_directory(
        _compiled_schema_dir, Gio.SettingsSchemaSource.get_default(), False
    )
    schema = schema_source.lookup("org.freedesktop.Piper", False)
    backend = Gio.memory_settings_backend_new()
    return Gio.Settings.new_full(schema, backend, None)


# A GtkApplication exports itself on the session bus under its application
# ID, so only one instance of it can be *registered* per process at a time.
# Every test that needs a real, started Application therefore shares this
# single session-scoped instance rather than each constructing their own.
@pytest.fixture(scope="session")
def app(piper_gresource):
    from piper.application import Application

    application = Application(2)
    application.register()
    return application


@pytest.fixture(autouse=True)
def _reset_shared_settings(app):
    """The session-scoped `app` fixture shares one Gio.Settings backed by
    the process-wide memory backend, so any test that changes a setting
    must not leak that change into other tests."""
    yield
    app.settings.reset("notify-profile-switch")
