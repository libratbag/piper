#!/usr/bin/env python3

import argparse
import sys
import unittest

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio  # noqa: E402

application = None


class _FakeRatbagd:
    instances = 0

    def __init__(self, api_version: int) -> None:
        _FakeRatbagd.instances += 1
        self.api_version = api_version


class TestInitRatbagd(unittest.TestCase):
    def setUp(self) -> None:
        _FakeRatbagd.instances = 0
        self.app = application.Application.__new__(application.Application)
        self.app._ratbagd = None
        self.app._required_ratbagd_version = 2

    def test_reuses_instance(self) -> None:
        first = self.app.init_ratbagd()
        second = self.app.init_ratbagd()

        self.assertIs(first, second)
        self.assertEqual(_FakeRatbagd.instances, 1)


def main() -> None:
    global application

    parser = argparse.ArgumentParser(description="Application.init_ratbagd reuse test")
    parser.add_argument("gresource", nargs=1, help="Absolute path to piper.gresource")
    parser.add_argument("sourcedir", nargs=1, help="Path to the source tree root")
    args, remainder = parser.parse_known_args()

    resource = Gio.resource_load(args.gresource[0])
    Gio.Resource._register(resource)

    sys.path.insert(0, args.sourcedir[0])
    from piper import application as piper_application

    piper_application.Ratbagd = _FakeRatbagd
    application = piper_application

    unittest.main(argv=[sys.argv[0], *remainder])


if __name__ == "__main__":
    main()
