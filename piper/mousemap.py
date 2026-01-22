# SPDX-License-Identifier: GPL-2.0-or-later

from typing import Any, List, Optional, Tuple

import cairo
import gi
import sys
from lxml import etree

from piper.svg import get_svg
from .ratbagd import RatbagdDevice

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import Gdk, GLib, Gtk, GObject, Rsvg  # noqa

"""This module contains the MouseMap widget (and its helper class
_MouseMapChild), which is central to the button and LED configuration stack
pages. The MouseMap widget draws the device SVG in the center and lays out a
bunch of child widgets relative to the leaders in the device SVG."""


class _MouseMapChild:
    # A helper class to manage children and their properties.

    def __init__(self, widget: Gtk.Widget, is_left: bool, svg_id: str) -> None:
        self._widget = widget
        self._is_left = is_left
        self._svg_id = svg_id
        self._svg_leader = f"{svg_id}-leader"
        self._svg_path = f"{svg_id}-path"

    @property
    def widget(self) -> Gtk.Widget:
        # The widget belonging to this child.
        return self._widget

    @property
    def svg_id(self) -> str:
        # The identifier of the SVG element with which this child's widget is
        # paired.
        return self._svg_id

    @property
    def svg_leader(self) -> str:
        # The identifier of the leader SVG element with which this child's
        # widget is paired.
        return self._svg_leader

    @property
    def svg_path(self) -> str:
        # The identifier of the SVG element's path with which this child's
        # widget is paired.
        return self._svg_path

    @property
    def is_left(self) -> bool:
        # True iff this child's widget is allocated to the left of the SVG.
        return self._is_left


class MouseMap(Gtk.Container):
    """A Gtk.Container subclass to draw a device SVG with child widgets that
    map to the SVG. The SVG should have objects with identifiers, whose value
    should also be given to the `add` method. See `do_size_allocate` and
    https://github.com/libratbag/libratbag/blob/master/data/README.md for more
    information.
    """

    __gtype_name__ = "MouseMap"

    __gproperties__ = {
        "spacing": (
            int,
            "spacing",
            "The amount of space between children and the SVG leaders",
            0,
            GLib.MAXINT,
            0,
            GObject.ParamFlags.READABLE,
        ),
    }

    def __init__(
        self,
        layer: str,
        ratbagd_device: RatbagdDevice,
        spacing: int = 10,
        *args,
        **kwargs,
    ) -> None:
        """Instantiates a new MouseMap.

        @param layer The SVG layer whose leaders to draw, according to librsvg
                     so e.g. `#layer1`.
        @param ratbagd_device The device that should be mapped, as
                              ratbagd.RatbagdDevice
        @param spacing The spacing to place between the SVG's leaders and the
                       widgets, as int

        @raises ValueError when an argument is invalid, or when the given device
                           has no image registered.
        @raises GLib.Error when the SVG cannot be loaded.
        """
        if layer is None:
            raise ValueError("Layer cannot be None")
        if ratbagd_device is None:
            raise ValueError("Device cannot be None")
        try:
            svg_bytes = get_svg(ratbagd_device.model)
            assert svg_bytes is not None
            handle = Rsvg.Handle.new_from_data(svg_bytes)
            assert handle is not None
            self._handle: Rsvg.Handle = handle
            self._svg_data = etree.fromstring(svg_bytes)
        except FileNotFoundError as e:
            raise ValueError("Device has no image or its path is invalid") from e

        Gtk.Container.__init__(self, *args, **kwargs)
        self.set_has_window(False)

        self.spacing = spacing
        self._layer = layer
        self._device = ratbagd_device
        self._children: List[_MouseMapChild] = []
        self._highlight_elements: List[str] = []

        # TODO: remove this when we're out of the transition to toned down SVGs
        device = self._handle.has_sub("#Device")
        buttons = self._handle.has_sub("#Buttons")
        leds = self._handle.has_sub("#LEDs")
        if not device or not buttons or not leds:
            print("Device SVG is incompatible", file=sys.stderr)

    def add(self, widget: Gtk.Widget, svg_id: str) -> None:
        """Adds the given widget to the map, bound to the given SVG element
        identifier. If the element identifier or its leader is not found in the
        SVG, the widget is not added.

        @param widget The widget to add, as Gtk.Widget
        @param svg_id The identifier of the SVG element with which this widget
                      is to be paired, as str
        """
        svg_leader = f"{svg_id}-leader"
        if (
            widget is None
            or svg_id is None
            or not self._handle.has_sub(svg_id)
            or not self._handle.has_sub(svg_leader)
        ):
            return

        is_left = self._xpath_has_style(svg_leader[1:], "text-align:end")
        child = _MouseMapChild(widget, is_left, svg_id)
        self._children.append(child)
        widget.connect("enter-notify-event", self._on_enter, child)
        widget.connect("leave-notify-event", self._on_leave)
        widget.set_parent(self)

    def do_remove(self, widget: Gtk.Widget) -> None:
        """Removes the given widget from the map.

        @param widget The widget to remove, as Gtk.Widget
        """
        if widget is not None:
            for child in self._children:
                if child.widget == widget:
                    self._children.remove(child)
                    child.widget.unparent()
                    break

    def do_forall(
        self, include_internals: bool, callback: "Gtk.Callback", *parameters
    ) -> None:
        """Invokes the given callback on each child, with the given parameters.

        @param include_internals Whether to run on internal children as well,
                                 as boolean. Ignored, as there are no internal
                                 children.
        @param callback The callback to call on each child, as Gtk.Callback
        @param parameters The parameters to pass to the callback, as object or
                          None.
        """
        try:
            if callback is not None:
                for child in self._children:
                    callback(child.widget, *parameters)
        except AttributeError:
            # See https://bugzilla.gnome.org/show_bug.cgi?id=722562.
            pass

    def do_get_request_mode(self) -> Gtk.SizeRequestMode:
        """Gets whether the container prefers a height-for-width or a
        width-for-height layout. We don't want to trade width for height or
        height for width so we return CONSTANT_SIZE."""
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_get_preferred_height(self) -> Tuple[int, int]:
        """Calculates the container's initial minimum and natural height. While
        this call is specific to width-for-height requests (that we requested
        not to get) we cannot be certain that our wishes are granted and hence
        we must implement this method as well. We just return the SVG's height
        plus the border widths.
        """
        # TODO: account for children sticking out under or above the SVG, if
        # they exist. At the moment we cannot reliably do so because the
        # y-coordinates of the leaders can have any arbitrary value. For now,
        # we assume that the SVG is high enough to fit all children and do not
        # worry about setups beyond the default GNOME Adwaita.
        height = self._handle.props.height + 2 * self.props.border_width
        return height, height

    def do_get_preferred_width(self) -> Tuple[int, int]:
        """Calculates the container's initial minimum and natural width. While
        this call is specific to height-for-width requests (that we requested
        not to get) we cannot be certain that our wishes are granted and hence
        we must implement this method as well. We return the sum of the SVG's
        width, the natural child widths (left and right), spacing and border
        width.
        """
        width = 2 * self.props.border_width
        width_svg = self._handle.props.width
        width_left = [
            child.widget.get_preferred_width()[1]
            for child in self._children
            if child.is_left
        ]
        width_right = [
            child.widget.get_preferred_width()[1]
            for child in self._children
            if not child.is_left
        ]
        width_left = max(width_left, default=0)
        width_right = max(width_right, default=0)
        width += width_left + width_svg + width_right + self.spacing
        if width_left > 0:
            width += self.spacing
        return width, width

    def do_get_preferred_height_for_width(self, width: int) -> Tuple[int, int]:
        """Returns this container's minimum and natural height if it would be
        given the specified width. While this call is specific to
        height-for-width requests (that we requested not to get) we cannot be
        certain that our wishes are granted and hence we must implement this
        method as well. Since we really want to be the same size always, we
        simply return do_get_preferred_height.

        @param width The given width, as int. Ignored.
        """
        return self.do_get_preferred_height()

    def do_get_preferred_width_for_height(self, height: int) -> Tuple[int, int]:
        """Returns this container's minimum and natural width if it would be
        given the specified height. While this call is specific to
        width-for-height requests (that we requested not to get) we cannot be
        certain that our wishes are granted and hence we must implement this
        method as well. Since we really want to be the same size always, we
        simply return do_get_preferred_width.

        @param height The given height, as int. Ignored.
        """
        return self.do_get_preferred_width()

    def do_size_allocate(self, allocation: Gdk.Rectangle) -> None:
        """Assigns a size and position to the child widgets. Children may
        adjust the given allocation in their adjust_size_allocation virtual
        method implementation.

        @param allocation The position and size allocated to this container, as
                          Gdk.Rectangle
        """
        self.set_allocation(allocation)
        x, y = self._translate_to_origin()
        child_allocation = Gdk.Rectangle()

        for child in self._children:
            if not child.widget.get_visible():
                continue
            svg_geom = self._get_svg_sub_geometry(child.svg_leader)[1]
            nat_size = child.widget.get_preferred_size()[1]
            if child.is_left:
                child_allocation.x = x + svg_geom.x - self.spacing - nat_size.width
            else:
                child_allocation.x = x + svg_geom.x + self.spacing
            child_allocation.y = (
                y + svg_geom.y + 0.5 * svg_geom.height - 0.5 * nat_size.height
            )
            child_allocation.width = nat_size.width
            child_allocation.height = nat_size.height
            if not child.widget.get_has_window():
                child_allocation.x += allocation.x
                child_allocation.y += allocation.y
            child.widget.size_allocate(child_allocation)

    def do_draw(self, cr: cairo.Context) -> None:
        """Draws the container to the given Cairo context. The top left corner
        of the widget will be drawn to the currently set origin point of the
        context. The container needs to propagate the draw signal to its
        children.

        @param cr The Cairo context to draw into, as cairo.Context
        """
        scale_factor = self.get_scale_factor()
        target = cr.get_target()
        target.set_device_scale(scale_factor, scale_factor)

        cr.save()
        x, y = self._translate_to_origin()
        cr.translate(x, y)
        self._draw_device(cr)
        cr.restore()
        for child in self._children:
            self.propagate_draw(child.widget, cr)

    def do_get_property(self, prop: GObject.ParamSpec) -> Any:
        """Gets a property value.

        @param prop The property to get, as GObject.ParamSpec
        """
        if prop.name == "spacing":
            return self.spacing

        raise AttributeError(f"Unknown property {prop.name}")

    def set_highlights(self, svg_ids: Optional[List[str]]) -> None:
        # Highlights the SVG elements with the given ids. Pass None/[] to clear.
        new_ids = svg_ids or []
        old_ids = list(self._highlight_elements)
        if old_ids == new_ids:
            return
        self._highlight_elements = new_ids
        for svg_id in set(old_ids + new_ids):
            self._redraw_svg_element(svg_id)

    def add_highlight(self, svg_id: str) -> None:
        # Adds a highlight for the given SVG id.
        if svg_id in self._highlight_elements:
            return
        self._highlight_elements.append(svg_id)
        self._redraw_svg_element(svg_id)

    def remove_highlight(self, svg_id: str) -> None:
        # Removes a highlight for the given SVG id.
        if svg_id not in self._highlight_elements:
            return
        self._highlight_elements.remove(svg_id)
        self._redraw_svg_element(svg_id)

    def _on_enter(
        self, widget: Gtk.Widget, event: Gdk.EventCrossing, child: _MouseMapChild
    ) -> None:
        # Highlights the element in the SVG to which the given widget belongs.
        self.add_highlight(child.svg_id)

    def _on_leave(self, widget: Gtk.Widget, event: Gdk.EventCrossing) -> None:
        # Restores the device SVG to its original state.
        self.set_highlights([])

    def _xpath_has_style(self, svg_id: str, style: str) -> bool:
        # Checks if the SVG element with the given identifier has the given
        # style attribute set.
        namespaces = {
            "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
            "cc": "http://web.resource.org/cc/",
            "svg": "http://www.w3.org/2000/svg",
            "dc": "http://purl.org/dc/elements/1.1/",
            "xlink": "http://www.w3.org/1999/xlink",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "inkscape": "http://www.inkscape.org/namespaces/inkscape",
        }
        query = f'//svg:rect[@id="{svg_id}"][contains(@style, "{style}")]'
        element = self._svg_data.xpath(query, namespaces=namespaces)
        return element is not None and len(element) == 1 and element[0] is not None

    def _get_svg_sub_geometry(self, svg_id: str) -> Tuple[bool, Gdk.Rectangle]:
        # Helper method to get an SVG element's x- and y-coordinates, width and
        # height.
        ret = Gdk.Rectangle()
        ok, svg_pos = self._handle.get_position_sub(svg_id)
        if not ok:
            print(
                "Warning: cannot retrieve element's position:", svg_id, file=sys.stderr
            )
            return ok, ret
        ret.x = svg_pos.x
        ret.y = svg_pos.y

        ok, svg_dim = self._handle.get_dimensions_sub(svg_id)
        if not ok:
            print(
                "Warning: cannot retrieve element's dimensions:",
                svg_id,
                file=sys.stderr,
            )
            return ok, ret
        ret.width = svg_dim.width
        ret.height = svg_dim.height
        return ok, ret

    def get_svg_center(self, svg_id: str) -> Optional[Tuple[int, int]]:
        # Returns the center position for the given SVG element in widget
        # coordinates, or None if it cannot be determined.
        ok, svg_geom = self._get_svg_sub_geometry(svg_id)
        if not ok:
            return None
        x, y = self._translate_to_origin()
        center_x = x + svg_geom.x + (svg_geom.width / 2)
        center_y = y + svg_geom.y + (svg_geom.height / 2)
        return round(center_x), round(center_y)

    def _redraw_svg_element(self, svg_id: str) -> None:
        # Helper method to redraw an element of the SVG image. Attempts to
        # redraw only the element (plus an offset), but will fall back to
        # redrawing the complete SVG.
        x, y = self._translate_to_origin()
        ok, svg_geom = self._get_svg_sub_geometry(svg_id)
        if not ok:
            svg_width = self._handle.props.width
            svg_height = self._handle.props.height
            self.queue_draw_area(x, y, svg_width, svg_height)
        else:
            self.queue_draw_area(
                x + svg_geom.x - 10,
                y + svg_geom.y - 10,
                svg_geom.width + 20,
                svg_geom.height + 20,
            )

    def _translate_to_origin(self) -> Tuple[int, int]:
        # Translates the coordinate system such that the SVG and its buttons
        # will be drawn in the center of the allocated space. The returned x-
        # and y-coordinates will be the top left corner of the centered SVG.
        allocation = self.get_allocation()
        width = self.get_preferred_width()[1]
        height = self.get_preferred_height()[1]

        width_left = [
            child.widget.get_preferred_width()[1]
            for child in self._children
            if child.is_left
        ]
        width_left = max(width_left, default=0)
        if width_left > 0:
            width_left += self.spacing

        x = (allocation.width - width) / 2 + self.props.border_width + width_left
        y = (allocation.height - height) / 2 + self.props.border_width
        return round(x), round(y)

    def _draw_device(self, cr: cairo.Context) -> None:
        # Draws the SVG into the Cairo context. If there is an element to be
        # highlighted, it will do as such in a separate surface which will be
        # used as a mask over the device surface.
        style_context = self.get_style_context()
        style_context.save()
        color = style_context.get_color(Gtk.StateFlags.LINK)
        style_context.restore()
        cr.set_source_rgba(color.red, color.green, color.blue, 0.5)

        self._handle.render_cairo_sub(cr, id="#Device")
        if self._highlight_elements:
            svg_surface = cr.get_target()
            highlight_surface = svg_surface.create_similar(
                cairo.CONTENT_COLOR_ALPHA,
                self._handle.props.width,
                self._handle.props.height,
            )
            highlight_context = cairo.Context(highlight_surface)
            for svg_id in self._highlight_elements:
                self._handle.render_cairo_sub(highlight_context, svg_id)
            cr.mask_surface(highlight_surface, 0, 0)
        for child in self._children:
            self._handle.render_cairo_sub(cr, id=child.svg_path)
            self._handle.render_cairo_sub(cr, id=child.svg_leader)
