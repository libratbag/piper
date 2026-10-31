Piper
=====

Piper is a GTK+ application to configure gaming mice. Piper is merely a
graphical frontend to the ratbagd DBus daemon, see [the libratbag
README](https://github.com/libratbag/libratbag/blob/master/README.md#running-ratbagd-as-dbus-activated-systemd-service)
for instructions on how to run ratbagd.

If you are running piper from git, we recommend using libratbag from git
as well to make sure the latest bugfixes are applied.

Supported Devices
=================
Piper is merely a frontend, the list of supported devices depends on
libratbag. See [the libratbag device
files](https://github.com/libratbag/libratbag/tree/master/data/devices) for
a list of all known devices.  The device-specific protocols usually have to
be reverse-engineered and the features available may vary to the
manufacturer's advertized features.

Screenshots
===========

![resolution configuration screenshot](https://github.com/libratbag/piper/blob/wiki/screenshots/piper-resolutionpage.png)

![button configuration screenshot](https://github.com/libratbag/piper/blob/wiki/screenshots/piper-buttonpage.png)

![LED configuration screenshot](https://github.com/libratbag/piper/blob/wiki/screenshots/piper-ledpage.png)

And if you see the mousetrap, something isn't right. Usually this means that
either ratbagd is not running (like in this screenshot), ratbagd needs to be
updated to a newer version, or some other unexpected error occured.

![The error page](https://github.com/libratbag/piper/blob/wiki/screenshots/piper-errorpage.png)

Installing Piper
================

See [our Wiki](https://github.com/libratbag/piper/wiki/Installation) for how to install Piper.

Building Piper from git
=======================

Piper uses the [meson build system](http://mesonbuild.com/). Run the following
commands to clone Piper and initialize the build:

```sh
git clone https://github.com/libratbag/piper.git
cd piper
meson setup builddir --prefix=/usr/
```

To build or re-build after code-changes and install, run:

```sh
ninja -C builddir
sudo ninja -C builddir install
```

Note: `builddir` is the build output directory and can be changed to any other
directory name.

See [our Wiki](https://github.com/libratbag/piper/wiki/Installation) for what
to do when you encounter missing dependencies.

Contributing
============

Yes please. It's best to contact us first to see what you could do. Note that
the devices displayed by Piper come from libratbag.

For quicker development iteration, there is a special binary `piper.devel`
that uses data files from the git directory. This removes the need to
install piper after every code change.

```sh
ninja -C builddir
./builddir/piper.devel
```
Note that this still requires ratbagd to run on the system bus.

Piper tries to conform to Python's PEP8 style guide using the `black` formatter.
Checking if code is formatted is done as a part of the test suite.

You can check if your code passes tests before submitting changes using the
following command:

```sh
meson test -C builddir
```

Source
======

```sh
git clone https://github.com/libratbag/piper.git
```

Bugs
====

Bugs can be reported in the issue tracker on our GitHub repo:
https://github.com/libratbag/piper/issues

License
=======

Licensed under the GPLv2. See the
[COPYING](https://github.com/libratbag/piper/blob/master/COPYING) file for the
full license information.
