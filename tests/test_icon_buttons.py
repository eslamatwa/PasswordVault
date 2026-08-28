"""The small buttons on a card: rounded, legible, and wired up.

These lost their corner radius when the cards moved to plain Tk widgets
for speed, and got them back as a cached image drawn under the text. The
shape is the cheap part to check; the expensive lesson was underneath it.

`_copy_to_clipboard` was still reading `fg_color` off those buttons to
flash a confirmation. That option belongs to CTkButton and does not exist
on a label, so the call raised — *after* the password reached the
clipboard and *before* the auto-clear was scheduled. The copy looked like
it half-worked (no confirmation) while the secret sat on the clipboard
until something else happened to overwrite it. Nothing caught it, because
no test had ever clicked one of these buttons.

Everything here goes through the `app_widgets` fixture rather than
importing the module directly; see that fixture for why.
"""

from __future__ import annotations

import time
import tkinter as tk

import pytest

from tests.conftest import requires_display

pytestmark = requires_display


def _labels(widget, out=None):
    out = [] if out is None else out
    if isinstance(widget, tk.Label):
        out.append(widget)
    for child in widget.winfo_children():
        _labels(child, out)
    return out


def _pills(app):
    return [x for x in _labels(app.entries_panel) if hasattr(x, "_pill")]


def _copy_button(app):
    return [b for b in _pills(app) if "Copy" in str(b.cget("text"))][0]


def _image_of(w, button):
    """The PhotoImage a pill button is currently wearing."""
    name = str(button.cget("image"))
    for image in w._PILL_CACHE.values():
        if str(image) == name:
            return image
    raise AssertionError(f"{name!r} is not in the pill cache")


@pytest.fixture
def cards(app):
    app.refresh_entries()
    app.root.update()
    return app


class TestShape:
    def test_the_corners_are_actually_round(self, cards, app_widgets):
        """A corner pixel of a filled pill is not the fill colour."""
        image = _image_of(app_widgets, _copy_button(cards))
        centre = image.get(image.width() // 2, image.height() // 2)
        for corner in ((0, 0), (image.width() - 1, 0),
                       (0, image.height() - 1),
                       (image.width() - 1, image.height() - 1)):
            assert image.get(*corner) != centre, f"{corner} is square"

    def test_the_corners_are_antialiased(self, cards, app_widgets):
        """Tk cannot do this for us, so the blend is worth asserting.

        Walking the diagonal out of a corner should pass through at least
        one part-covered pixel. Two values along it would mean a
        staircase rather than a curve.
        """
        image = _image_of(app_widgets, _copy_button(cards))
        ramp = [image.get(i, i) for i in range(6)]
        assert len({str(v) for v in ramp}) >= 3, \
            f"corner is not blended, only {ramp}"

    def test_no_button_has_its_text_clipped(self, cards, app_widgets):
        """The image sets the label's size, so a pill too narrow for its
        own text silently cuts the text off."""
        too_small = []
        for button in _pills(cards):
            font = app_widgets.pill_font(button, button._pill["font"])
            needed = font.measure(button.cget("text"))
            if needed > _image_of(app_widgets, button).width():
                too_small.append(button.cget("text"))
        assert not too_small, f"clipped: {too_small}"

    def test_unfilled_buttons_stay_invisible_at_rest(self, cards,
                                                     app_widgets):
        """Pin, edit, delete and the eye sit directly on the card and
        must not grow a visible chip around themselves."""
        resting = [b for b in _pills(cards)
                   if app_widgets.resolve(b._pill["rest"])
                   == app_widgets.resolve(b._pill["behind"])]
        assert resting, "expected some buttons to be unfilled"
        for button in resting:
            image = _image_of(app_widgets, button)
            assert image.get(0, 0) == image.get(
                image.width() // 2, image.height() // 2), \
                "an unfilled button drew a visible corner"


class TestHover:
    def test_hover_changes_the_pill_and_leaving_restores_it(self, cards):
        button = _copy_button(cards)
        rest = str(button.cget("image"))
        button.event_generate("<Enter>")
        cards.root.update()
        assert str(button.cget("image")) != rest, "hover did nothing"
        button.event_generate("<Leave>")
        cards.root.update()
        assert str(button.cget("image")) == rest, "hover did not wash off"


class TestFlash:
    def test_a_flash_restores_the_original_text_and_pill(self, cards,
                                                         app_widgets):
        button = _copy_button(cards)
        original, rest = button.cget("text"), str(button.cget("image"))

        app_widgets.flash_button(button, "Done!", "#34c759", after_ms=30)
        # Deliberately no update() before these two: `configure` is
        # synchronous, so the flash is already on the button, and pumping
        # the event loop here would let the restore timer race the
        # assertion. An earlier version did exactly that and failed about
        # one run in five on a loaded machine.
        assert button.cget("text") == "Done!"
        assert str(button.cget("image")) != rest, "the fill did not change"

        # Wait for the restore to happen rather than for a fixed period.
        deadline = time.monotonic() + 10
        while (button.cget("text") != original
               and time.monotonic() < deadline):
            cards.root.update()
        assert button.cget("text") == original, "the flash never wore off"
        assert str(button.cget("image")) == rest

    def test_moving_the_mouse_does_not_cut_a_flash_short(self, cards,
                                                         app_widgets):
        """The pointer is over the button at the moment it is clicked, so
        the <Leave> when the user moves away would otherwise wipe the
        confirmation while its text was still showing."""
        button = _copy_button(cards)
        app_widgets.flash_button(button, "Done!", "#34c759", after_ms=5000)
        cards.root.update()
        button.event_generate("<Enter>")
        button.event_generate("<Leave>")
        cards.root.update()
        assert button.cget("text") == "Done!"
        button._pill["flashing"] = False

    def test_a_flash_on_a_destroyed_button_is_survivable(self, cards,
                                                         app_widgets):
        """Cards are destroyed on lock, and the restore runs on a timer."""
        button = _copy_button(cards)
        app_widgets.flash_button(button, "Done!", "#34c759", after_ms=10)
        button.destroy()
        cards.root.update()
        cards.root.after(60, cards.root.quit)
        cards.root.mainloop()


class TestCopyIsWiredUp:
    """The regression this file exists for."""

    def test_clicking_copy_arms_the_clipboard_auto_clear(
            self, cards, monkeypatch):
        import main as main_module

        copied = []
        monkeypatch.setattr(main_module.pyperclip, "copy", copied.append)
        cards.settings["clipboard_clear_seconds"] = 30
        cards._clipboard_timer = None

        _copy_button(cards).event_generate("<Button-1>")
        cards.root.update()

        assert copied, "the click did not reach the clipboard"
        assert cards._clipboard_timer is not None, \
            "the password was copied but never scheduled to be cleared"
        assert cards._clipboard_digest is not None

    def test_the_click_confirms_on_the_button(self, cards, monkeypatch):
        import main as main_module

        monkeypatch.setattr(main_module.pyperclip, "copy", lambda _t: None)
        button = _copy_button(cards)
        button.event_generate("<Button-1>")
        cards.root.update()
        assert "Done" in button.cget("text"), \
            f"no confirmation, showing {button.cget('text')!r}"
        button._pill["flashing"] = False

    def test_a_failed_copy_still_does_not_arm_a_timer(
            self, cards, monkeypatch):
        """The opposite error: no clipboard backend must not leave a
        timer pointing at the digest of a password that never got out."""
        import main as main_module

        def boom(_text):
            raise main_module.pyperclip.PyperclipException("no backend")

        monkeypatch.setattr(main_module.pyperclip, "copy", boom)
        monkeypatch.setattr(cards, "_alert", lambda *a, **k: None)
        cards._clipboard_timer = None
        cards._copy_to_clipboard("secret")
        assert cards._clipboard_timer is None


class TestCache:
    def test_identical_buttons_share_one_image(self, cards, app_widgets):
        """Sharing is per card colour, because a Tk image has no alpha:
        the colour behind the corners is baked in, so the same button on
        a blue card and a plain one are genuinely two images. Within one
        colour they must be the same object."""
        by_key = {}
        for button in _pills(cards):
            shape = button._pill
            key = (shape["text"], app_widgets.resolve(shape["rest"]),
                   app_widgets.resolve(shape["behind"]))
            by_key.setdefault(key, set()).add(str(button.cget("image")))
        shared = {k: v for k, v in by_key.items() if len(v) > 1}
        assert not shared, f"same button, different images: {shared}"

    def test_the_cache_stays_small(self, cards, app_widgets):
        """Bounded by (pill kinds x card colours), not by entry count."""
        assert len(app_widgets._PILL_CACHE) <= 64, \
            f"{len(app_widgets._PILL_CACHE)} images cached"

    def test_the_cache_is_dropped_when_the_interpreter_changes(
            self, cards, app_widgets):
        """A PhotoImage belongs to the root that made it. Reusing one
        across roots raises as soon as it is drawn."""
        assert app_widgets._PILL_CACHE, "nothing cached to begin with"

        other = tk.Tk()
        other.withdraw()
        try:
            app_widgets.pill_image(tk.Label(other), 20, 12, 4,
                                   "#007aff", "#1c1c1e")
            assert app_widgets._PILL_TK is other.tk
            assert len(app_widgets._PILL_CACHE) == 1, \
                "images from the old interpreter survived"
        finally:
            other.destroy()

        # ...and the app's own next draw repopulates against its own root.
        cards._card_pool.clear()
        cards.refresh_entries()
        cards.root.update()
        assert app_widgets._PILL_TK is cards.root.tk
        assert _pills(cards), "the list did not come back"
