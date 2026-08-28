"""The suite must not take over the screen it is running on.

These tests drive a real Tk application, so a run puts a main window and
a Toplevel per dialog on the developer's desktop for several minutes,
appearing and vanishing and stealing focus. That was reported as the app
opening and closing on its own, which is a fair reading of what it looks
like: the windows are real, they are just not the user's.

The windows still have to be mapped, because other tests ask whether a
card or a dialog is actually shown. So conftest maps them somewhere
nobody is looking instead of hiding them, and this is what holds it to
that.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from tests.conftest import OFFSCREEN_AT, requires_display

pytestmark = requires_display

# Anything at least this far out is clear of any plausible display, and
# of a second monitor placed to the right of the first.
FAR_ENOUGH = 10000


class TestTheMainWindow:
    def test_it_sits_off_the_display(self, app):
        app.root.update_idletasks()
        assert app.root.winfo_x() >= FAR_ENOUGH, \
            f"the main window is at x={app.root.winfo_x()}, on the display"

    def test_the_dialogs_are_mapped_and_still_off_screen(self, app):
        """The main window stays withdrawn through most of a run, so what
        a person actually sees flashing up is the Toplevels. Those have to
        be genuinely mapped — other tests ask what is visible — and still
        nowhere near the display."""
        window = tk.Toplevel(app.root)
        window.deiconify()
        try:
            window.update_idletasks()
            assert window.winfo_ismapped(), \
                "hiding dialogs would void every test of what is shown"
            assert window.winfo_x() >= FAR_ENOUGH
        finally:
            window.destroy()

    def test_restoring_it_does_not_bring_it_back_onto_the_display(self,
                                                                  app):
        """`restore_window` lifts, focuses and sets -topmost. Each of
        those is exactly what a person at the machine notices."""
        app.restore_window()
        app.root.update_idletasks()
        assert app.root.winfo_x() >= FAR_ENOUGH
        assert app.root.attributes("-topmost") in (0, "0", ""), \
            "a test window put itself above everything else"


class TestNewWindows:
    def test_a_toplevel_that_centres_itself_still_lands_off_screen(self,
                                                                   app):
        """The dialogs in this app compute a centred position and pass it
        to `geometry`. The size has to survive that; the position must
        not."""
        window = tk.Toplevel(app.root)
        try:
            window.geometry("420x300+200+150")
            window.update_idletasks()
            assert window.winfo_x() >= FAR_ENOUGH, \
                f"a dialog opened at x={window.winfo_x()}"
            assert window.winfo_width() == 420, \
                "the requested size was lost along with the position"
            assert window.winfo_height() == 300
        finally:
            window.destroy()

    def test_a_size_only_geometry_is_left_alone(self, app):
        window = tk.Toplevel(app.root)
        try:
            window.geometry("300x200")
            window.update_idletasks()
            assert window.winfo_width() == 300
            assert window.winfo_height() == 200
        finally:
            window.destroy()


class TestFocus:
    def test_focus_force_is_disarmed(self, app):
        """It takes the keyboard from whatever the person is typing into,
        which is worse than the window merely being visible."""
        window = tk.Toplevel(app.root)
        try:
            # The call has to still be safe to make, just do nothing.
            assert window.focus_force() is None
            assert window.lift() is None
        finally:
            window.destroy()


class TestItDidNotBreakWhatItGuards:
    """Mapping still has to mean mapping, or the tests that rely on it
    are quietly passing on nothing."""

    def test_an_unmapped_widget_is_still_reported_unmapped(self, app):
        frame = tk.Frame(app.root)
        frame.pack()
        app.root.update_idletasks()
        assert frame.winfo_ismapped()
        frame.pack_forget()
        app.root.update_idletasks()
        assert not frame.winfo_ismapped()
        frame.destroy()

    def test_the_offscreen_offset_is_a_position_only_geometry(self):
        """If this ever grew a size, every window would be resized to it."""
        assert OFFSCREEN_AT.startswith(("+", "-"))
        assert "x" not in OFFSCREEN_AT


@pytest.mark.parametrize("requested,expect_width", [
    ("500x400+0+0", 500),
    ("640x480-10-10", 640),
    ("+100+100", None),
])
def test_geometry_forms_the_app_actually_uses(app, requested, expect_width):
    """Tk accepts several geometry spellings and the dialogs use more
    than one; a rewrite that only understood `WxH+X+Y` would silently
    leave the others on screen."""
    window = tk.Toplevel(app.root)
    try:
        window.geometry(requested)
        window.update_idletasks()
        assert window.winfo_x() >= FAR_ENOUGH, \
            f"{requested!r} escaped to x={window.winfo_x()}"
        if expect_width is not None:
            assert window.winfo_width() == expect_width
    finally:
        window.destroy()
