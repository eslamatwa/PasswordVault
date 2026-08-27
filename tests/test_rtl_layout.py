"""Right-to-left layout, checked by geometry rather than by opening.

The smoke harness proves every dialog builds under Arabic. That is not the
same as proving it is mirrored: a call site still passing a literal "left"
builds perfectly and simply renders the wrong way round.

These tests measure where widgets actually land after Tk has laid them out,
so a missed `side_start()` shows up as a coordinate on the wrong side of
the window rather than as a passing test.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from tests.conftest import requires_display

pytestmark = requires_display


def _x(widget) -> int:
    """Absolute x of a widget, comparable across the window."""
    return widget.winfo_rootx()


def _center_x(widget) -> float:
    return widget.winfo_rootx() + widget.winfo_width() / 2


def _find(widget, predicate, out=None):
    """Every descendant matching *predicate*."""
    out = [] if out is None else out
    if predicate(widget):
        out.append(widget)
    for child in widget.winfo_children():
        _find(child, predicate, out)
    return out


def _labels(root):
    """Every label, of either kind.

    The entry list is built from plain `tk.Label`s for speed, so looking
    only for CTkLabels finds nothing in a card — and a mirroring check
    that inspects no cards passes for the wrong reason.
    """
    import customtkinter as ctk
    return _find(root, lambda w: isinstance(w, (ctk.CTkLabel, tk.Label)))


class TestMainWindowMirrors:
    def test_sidebar_moves_to_the_reading_edge(self, app):
        """The category sidebar leads the layout, so it follows the text."""
        app.root.update()
        ltr_sidebar = _center_x(app.sidebar)
        ltr_width = app.root.winfo_width()
        # In English the sidebar sits in the left half.
        assert ltr_sidebar < app.root.winfo_rootx() + ltr_width / 2

    def test_sidebar_is_on_the_right_in_arabic(self, arabic):
        app = arabic
        app.root.update()
        width = app.root.winfo_width()
        assert _center_x(app.sidebar) > app.root.winfo_rootx() + width / 2

    def test_the_two_panes_swap(self, app):
        app.root.update()
        assert app.sidebar.pack_info()["side"] == "left"

    def test_the_two_panes_swap_in_arabic(self, arabic):
        arabic.root.update()
        assert arabic.sidebar.pack_info()["side"] == "right"


def _anchor_map(root):
    """``{label text: anchor}`` for every label that has a side anchor.

    Only "w"/"e" matter — a centred label has nothing to mirror.
    """
    out = {}
    for widget in _labels(root):
        try:
            anchor = widget.cget("anchor")
            text = widget.cget("text")
        except tk.TclError:
            continue
        if anchor in ("w", "e") and text:
            out[text] = anchor
    return out


MIRROR = {"w": "e", "e": "w"}


class TestAnchorsFlip:
    """Every side anchor flips, and none of them stays put.

    Asserting "nothing anchors west under Arabic" would be wrong: the
    password mask deliberately sits at the *trailing* edge, so it is "e"
    in English and "w" in Arabic. The invariant is that each anchor is the
    mirror of its English counterpart — which is why the two languages are
    compared against each other rather than against a fixed direction.
    """

    def test_main_window_anchors_are_mirrored(self, app, _live_app):
        from password_vault import i18n

        app.root.update()
        english = _anchor_map(app._main_frame)
        assert english, "no anchored labels found to compare"

        i18n.set_language("Arabic")
        try:
            app._rebuild_ui()
            app.root.update()
            arabic = _anchor_map(app._main_frame)
        finally:
            i18n.set_language("English")
            app._rebuild_ui()
            app.root.update()

        shared = set(english) & set(arabic)
        assert shared, "no label survived the rebuild to compare"
        wrong = {text: (english[text], arabic[text]) for text in shared
                 if arabic[text] != MIRROR[english[text]]}
        assert not wrong, f"anchors that did not mirror: {wrong}"

    def test_the_trailing_anchor_mirrors_too(self, app):
        """The password mask is anchored to the trailing edge, not west.

        It is the case that makes a blanket "everything is west" assertion
        wrong, so it gets its own test.
        """
        from password_vault import i18n
        assert i18n.anchor_end() == "e"
        i18n.set_language("Arabic")
        try:
            assert i18n.anchor_end() == "w"
        finally:
            i18n.set_language("English")


class TestDialogsMirror:
    """A dialog's form rows must mirror too, not just the main window."""

    def _open_entry_dialog(self, app):
        before = {w for w in app.root.winfo_children()
                  if isinstance(w, tk.Toplevel)}
        app.show_entry_dialog()
        app.root.update()
        created = [w for w in app.root.winfo_children()
                   if isinstance(w, tk.Toplevel) and w not in before]
        assert created
        return created[-1]

    def test_form_labels_lead_in_english(self, app):
        dlg = self._open_entry_dialog(app)
        try:
            labels = [w for w in _labels(dlg)
                      if w.cget("text") in ("Title", "Username", "URL")]
            assert labels, "the form labels were not found"
            for label in labels:
                assert label.cget("anchor") == "w"
        finally:
            dlg.destroy()
            app.root.update()

    def test_every_dialog_label_anchors_east_in_arabic(self, arabic):
        """The entry dialog has no trailing-anchored label, so here the
        blanket assertion does hold — and it is what caught the
        hand-built password row the mechanical pass had missed."""
        app = arabic
        dlg = self._open_entry_dialog(app)
        try:
            stuck = [w.cget("text") for w in _labels(dlg)
                     if w.cget("anchor") == "w"]
            assert not stuck, f"labels still anchored west: {stuck}"
        finally:
            dlg.destroy()
            app.root.update()

    def test_the_remote_session_dialog_mirrors(self, arabic):
        app = arabic
        entry = app.data["entries"][1]
        before = {w for w in app.root.winfo_children()
                  if isinstance(w, tk.Toplevel)}
        app._show_remote_session_dialog(entry, kind="ssh")
        app.root.update()
        dlg = [w for w in app.root.winfo_children()
               if isinstance(w, tk.Toplevel) and w not in before][-1]
        try:
            stuck = [w.cget("text") for w in _labels(dlg)
                     if w.cget("anchor") == "w"]
            assert not stuck, f"labels still anchored west: {stuck}"
        finally:
            dlg.destroy()
            app.root.update()

    def test_a_form_field_sits_opposite_its_label(self, app):
        """The label leads and the input follows, in both directions."""
        import customtkinter as ctk
        dlg = self._open_entry_dialog(app)
        try:
            app.root.update()
            titles = [w for w in _labels(dlg) if w.cget("text") == "Title"]
            assert titles
            label = titles[0]
            row = label.master
            entries = _find(row, lambda w: isinstance(w, ctk.CTkEntry))
            assert entries, "the Title row has no entry field"
            assert _x(label) < _x(entries[0])
        finally:
            dlg.destroy()
            app.root.update()

    def test_a_form_field_sits_opposite_its_label_in_arabic(self, arabic):
        import customtkinter as ctk
        app = arabic
        dlg = self._open_entry_dialog(app)
        try:
            app.root.update()
            labels = [w for w in _labels(dlg)
                      if w.cget("text") and w.cget("anchor") == "e"]
            assert labels, "no reading-edge label found"
            # Find a label whose row also holds an entry.
            for label in labels:
                entries = _find(label.master,
                                lambda w: isinstance(w, ctk.CTkEntry))
                if entries:
                    assert _x(label) > _x(entries[0]), \
                        "the label should lead from the right"
                    return
            pytest.skip("no label/entry row available to measure")
        finally:
            dlg.destroy()
            app.root.update()


class TestPaddingMirrors:
    def test_pad_swaps_only_under_rtl(self, app):
        from password_vault import i18n
        assert i18n.pad(8, 0) == (8, 0)

    def test_pad_swaps_under_rtl(self, arabic):
        from password_vault import i18n
        assert i18n.pad(8, 0) == (0, 8)

    def test_a_mirrored_pad_keeps_the_same_total(self, app):
        """Mirroring moves the gap, it does not change how much there is."""
        from password_vault import i18n
        for start, end in [(8, 0), (16, 6), (0, 4), (2, 2)]:
            assert sum(i18n.pad(start, end)) == start + end
