# SPDX-License-Identifier: GPL-2.0-or-later

"""Names for macros.

The device has no place to keep a name for a macro, so names are kept in a
file in the user's configuration directory. A name belongs to one button of one
profile of one device model and is only shown while that button still has the
macro the name was given to; replacing the macro (or using the mouse with
another computer) just makes the name disappear instead of showing a wrong
one. The delays of a macro are not part of its identity, so that adjusting
them does not lose the name."""

import json
import os
import sys
from typing import Iterable, List, Optional, Tuple

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa


def _identity(events: Iterable[Tuple[int, int]], wait: int) -> List[List[int]]:
    # The key events of a macro without its delays.
    return [[int(kind), int(value)] for kind, value in events if int(kind) != wait]


class MacroNameStore:
    """All the macro names, kept in one JSON file."""

    FILE_NAME = "macro-names.json"

    def __init__(self, path: Optional[str] = None) -> None:
        if path is None:
            path = os.path.join(GLib.get_user_config_dir(), "piper", self.FILE_NAME)
        self._path = path
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data = data
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            print(f"Cannot read macro names from {self._path}: {e}", file=sys.stderr)

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError as e:
            print(f"Cannot save macro names to {self._path}: {e}", file=sys.stderr)

    @staticmethod
    def _key(model: str, profile: int, button: int) -> str:
        return f"{model}/{profile}/{button}"

    def get(
        self,
        model: str,
        profile: int,
        button: int,
        events: Iterable[Tuple[int, int]],
        wait: int,
    ) -> Optional[str]:
        """The name of the macro of the given button, or None if it has none
        or its macro is not the one that was named."""
        entry = self._data.get(self._key(model, profile, button))
        if not isinstance(entry, dict):
            return None
        if entry.get("events") != _identity(events, wait):
            return None
        name = entry.get("name")
        return name if isinstance(name, str) and name else None

    def set(
        self,
        model: str,
        profile: int,
        button: int,
        name: str,
        events: Iterable[Tuple[int, int]],
        wait: int,
    ) -> None:
        """Names the macro of the given button. An empty name removes it."""
        key = self._key(model, profile, button)
        name = name.strip()
        if name:
            self._data[key] = {"name": name, "events": _identity(events, wait)}
        elif key in self._data:
            del self._data[key]
        else:
            return
        self._save()


class ButtonMacroNames:
    """The names of the macros of one profile of one device."""

    def __init__(self, store: MacroNameStore, model: str, profile: int) -> None:
        self._store = store
        self._model = model
        self._profile = profile

    def get(
        self, button: int, events: Iterable[Tuple[int, int]], wait: int
    ) -> Optional[str]:
        return self._store.get(self._model, self._profile, button, events, wait)

    def set(
        self, button: int, name: str, events: Iterable[Tuple[int, int]], wait: int
    ) -> None:
        self._store.set(self._model, self._profile, button, name, events, wait)


_default_store: Optional[MacroNameStore] = None


def default_store() -> MacroNameStore:
    """The store shared by the whole application."""
    global _default_store
    if _default_store is None:
        _default_store = MacroNameStore()
    return _default_store
