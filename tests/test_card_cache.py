"""Cards are kept between refreshes, so they must not go stale.

Rebuilding every row on each refresh was costing seconds; the rows are now
built once and hidden and shown instead. That is a cache, and the failure
mode of a cache is showing something that is no longer true — an edited
title that still reads the old one, a deleted entry that stays on screen,
a card left in the previous theme.

These tests are about invalidation rather than speed. `tools/benchmark_ui.py`
covers the speed.
"""

from __future__ import annotations

import tkinter as tk

from tests.conftest import requires_display

pytestmark = requires_display


def _texts(widget, out=None):
    """Text the user can actually see.

    A hidden card is still a child of the panel — `pack_forget` unmaps it
    rather than destroying it, which is the whole point — so walking the
    children alone would report filtered-out entries as visible.
    """
    out = [] if out is None else out
    try:
        if not widget.winfo_ismapped():
            return out
    except tk.TclError:
        return out
    if isinstance(widget, tk.Label):
        value = widget.cget("text")
        if isinstance(value, str):
            out.append(value)
    for child in widget.winfo_children():
        _texts(child, out)
    return out


def _list_text(app):
    return " | ".join(_texts(app.entries_panel))


def _packed_cards(app):
    """Cards currently visible, in the order they appear."""
    return [w for w in app.entries_panel.winfo_children()
            if w.winfo_manager() == "pack" and w in
            set(app._card_pool.values())]


def _texts_widgets(widget, out=None):
    """Every plain label under *widget*, mapped or not.

    Unlike `_texts`, this is about the widgets themselves rather than what
    is on screen — a stale colour is worth catching even on a card that
    happens to be hidden.
    """
    out = [] if out is None else out
    if isinstance(widget, tk.Label):
        out.append(widget)
    for child in widget.winfo_children():
        _texts_widgets(child, out)
    return out


def _pool(app):
    """A snapshot of the card cache as a plain dict.

    `app._card_pool` is a CardPool, which reads like a mapping but is not
    one — comparing it to a dict would always be false and quietly turn
    these assertions into nothing.
    """
    return dict(app._card_pool.items())


def _entry(app, title):
    for e in app.data["entries"]:
        if e["title"] == title:
            return e
    raise AssertionError(f"no entry titled {title!r}")


class TestReuse:
    def test_a_second_refresh_keeps_the_same_widgets(self, app):
        app.refresh_entries()
        app.root.update()
        first = _pool(app)
        assert first, "no cards were cached"

        app.refresh_entries()
        app.root.update()
        assert _pool(app) == first, "cards were rebuilt needlessly"

    def test_filtering_hides_rather_than_destroys(self, app):
        app.refresh_entries()
        app.root.update()
        pooled = _pool(app)

        app.search_var.set("Bank")
        app._refresh_from_search()
        app.root.update()

        assert "Bank" in _list_text(app)
        assert "db01" not in _list_text(app)
        # The filtered-out card is kept, because the next keystroke may
        # well bring it back.
        assert _pool(app) == pooled

    def test_clearing_the_search_brings_them_back(self, app):
        app.search_var.set("Bank")
        app._refresh_from_search()
        app.root.update()
        app.search_var.set("")
        app._refresh_from_search()
        app.root.update()
        assert "db01" in _list_text(app)


class TestInvalidation:
    def test_an_edited_title_is_redrawn(self, app):
        app.refresh_entries()
        app.root.update()
        assert "Bank" in _list_text(app)

        _entry(app, "Bank")["title"] = "Credit Union"
        app.refresh_entries()
        app.root.update()

        assert "Credit Union" in _list_text(app)
        assert "Bank" not in _list_text(app)

    def test_an_edited_username_is_redrawn(self, app):
        entry = _entry(app, "Bank")
        entry["username"] = "someone.else@example.com"
        app.refresh_entries()
        app.root.update()
        assert "someone.else@example.com" in _list_text(app)

    def test_a_changed_password_is_redrawn(self, app):
        """The card holds the password for the reveal button, so a change
        has to reach it even though the mask looks identical."""
        entry = _entry(app, "Bank")
        app.refresh_entries()
        app.root.update()
        before = app._card_pool[entry["id"]]

        entry["password"] = "a-completely-new-secret"
        app.refresh_entries()
        app.root.update()

        assert app._card_pool[entry["id"]] is not before, \
            "the card still holds the old password"

    def test_a_changed_note_is_redrawn(self, app):
        _entry(app, "db01")["notes"] = "a note that was not there before"
        app.refresh_entries()
        app.root.update()
        assert "a note that was not there before" in _list_text(app)

    def test_toggling_pin_redraws_that_card(self, app):
        entry = _entry(app, "db01")
        app.refresh_entries()
        app.root.update()
        before = app._card_pool[entry["id"]]

        app._toggle_pin(entry)
        app.root.update()

        assert app._card_pool[entry["id"]] is not before
        assert entry["pinned"] is True

    def test_a_changed_colour_is_redrawn(self, app):
        entry = _entry(app, "Bank")
        app.refresh_entries()
        app.root.update()
        before = app._card_pool[entry["id"]]
        entry["color"] = "red"
        app.refresh_entries()
        app.root.update()
        assert app._card_pool[entry["id"]] is not before

    def test_an_untouched_entry_is_not_rebuilt(self, app):
        """The point of the cache: only what changed pays."""
        app.refresh_entries()
        app.root.update()
        untouched = _entry(app, "db01")
        kept = app._card_pool[untouched["id"]]

        _entry(app, "Bank")["title"] = "Something Else"
        app.refresh_entries()
        app.root.update()

        assert app._card_pool[untouched["id"]] is kept


class TestRemoval:
    def test_a_deleted_entry_loses_its_card(self, app):
        entry = _entry(app, "Bank")
        app.refresh_entries()
        app.root.update()
        assert entry["id"] in app._card_pool

        app.data["entries"] = [e for e in app.data["entries"]
                               if e["id"] != entry["id"]]
        app.refresh_entries()
        app.root.update()

        assert entry["id"] not in app._card_pool
        assert "Bank" not in _list_text(app)

    def test_an_empty_vault_shows_the_empty_state(self, app):
        app.data["entries"] = []
        app.refresh_entries()
        app.root.update()
        assert "No passwords yet" in _list_text(app)
        assert _pool(app) == {}

    def test_the_empty_state_is_cleared_when_entries_return(self, app):
        app.data["entries"] = []
        app.refresh_entries()
        app.root.update()

        app.data["entries"] = [{
            "id": "new", "title": "Fresh", "username": "u",
            "password": "p", "url": "", "category": "General",
            "notes": "", "color": "default", "pinned": False,
            "created_at": "2024-01-01T00:00:00",
            "modified_at": "2024-01-01T00:00:00"}]
        app.refresh_entries()
        app.root.update()

        assert "No passwords yet" not in _list_text(app)
        assert "Fresh" in _list_text(app)


class TestOrdering:
    def test_pinned_entries_come_first_after_a_repack(self, app):
        """Order comes from the pack sequence, so re-showing has to
        re-pack in sort order rather than rely on how cards were built."""
        app.refresh_entries()
        app.root.update()

        # db01 is not pinned; pin it and it should lead.
        db = _entry(app, "db01")
        db["pinned"] = True
        _entry(app, "Bank")["pinned"] = False
        app.refresh_entries()
        app.root.update()

        titles = [t for t in _texts(app.entries_panel)
                  if "db01" in t or "Bank" in t]
        assert titles, "neither title was rendered"
        assert "db01" in titles[0], f"pinned entry is not first: {titles}"


class TestThemeAndLanguage:
    def test_switching_theme_rebuilds_the_cards(self, app):
        """Plain Tk widgets keep the colours they were built with."""
        app.refresh_entries()
        app.root.update()
        before = _pool(app)
        assert before

        app._apply_appearance("Light")
        app.root.update()
        try:
            assert _pool(app) != before, \
                "cards survived a theme change with the old palette"
            assert app._card_pool, "the list was not rebuilt"
        finally:
            app._apply_appearance("Dark")
            app.root.update()

    def test_switching_language_rebuilds_the_cards(self, arabic):
        app = arabic
        app.refresh_entries()
        app.root.update()
        assert app._card_pool, "the list was not rebuilt in Arabic"

    def test_the_mini_vault_repaints_too(self, app):
        """It has its own pool, and its own chance to show stale colours.

        Refreshing it on a theme change is not enough — the refresh reuses
        cached cards, which is exactly what has to be thrown away.
        """
        from password_vault.theme import CARD_COLORS, resolve
        from password_vault.ui.mini_vault import MiniVault

        app.data["entries"][0]["color"] = "blue"
        app.mini_vault = MiniVault(app)
        app.root.update()
        try:
            for mode in ("Light", "Dark"):
                app._apply_appearance(mode)
                app.root.update()
                expected = resolve(CARD_COLORS["blue"]["bg"])
                cards = [w for w in app.mini_vault.list_frame
                         .winfo_children()
                         if not isinstance(w, tk.Label)]
                assert cards, "the Mini Vault rendered no cards"
                # Only the labels that sit on the card itself. The
                # buttons carry their own fills by design, so demanding
                # the card colour everywhere would fail on correct code.
                body = [w for w in _texts_widgets(cards[0])
                        if "@" in str(w.cget("text"))]
                assert body, "no username label found on the card"
                stale = [w.cget("bg") for w in body
                         if w.cget("bg") != expected]
                assert not stale, (
                    f"a Mini Vault card kept {stale} instead of {expected}")
        finally:
            app.mini_vault.destroy()
            app.mini_vault = None
            app.root.update()

    def test_locking_drops_every_card(self, app):
        """Their parent is destroyed with the main frame."""
        app.refresh_entries()
        app.root.update()
        assert app._card_pool

        app._auto_lock()
        app.root.update()
        assert _pool(app) == {}
        assert app._list_extras == []


class TestShowMore:
    def test_the_footer_is_not_cached_as_a_card(self, app, monkeypatch):
        import main as main_module

        monkeypatch.setattr(main_module, "ENTRIES_PAGE_SIZE", 1)
        app._visible_limit = 1
        app.refresh_entries()
        app.root.update()

        assert "Show more" in _list_text(app) or \
            any("Show more" in str(w.cget("text"))
                for w in app._list_extras
                if hasattr(w, "cget")), "no Show more footer"
        # Exactly one card is visible, and the footer is not one of them.
        assert len(_packed_cards(app)) == 1

    def test_showing_more_reuses_the_cards_already_built(self, app):
        app._visible_limit = 1
        app.refresh_entries()
        app.root.update()
        first = _pool(app)

        app._show_more_entries()
        app.root.update()

        for entry_id, card in first.items():
            assert app._card_pool[entry_id] is card, \
                "a card was rebuilt when the page grew"
