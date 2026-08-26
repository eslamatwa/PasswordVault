# Password Vault — MVP Status & Remaining Work

Snapshot of the hardening and polish pass on v3.4: what landed, what is
deliberately left, and how to verify any of it.

**Verified at the time of writing:** 129 unit tests pass, `pyflakes` reports
nothing, and every dialog opens in both light and dark themes.

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m pyflakes main.py password_vault tests
```

---

## Done

### Security & data integrity
- **Formula injection** — CSV and Excel exports escape cells beginning with
  `=`, `+`, `-`, or `@`, and unescape them on import.
- **Link guard** — only `http` and `https` URLs are opened; anything else is
  refused with a notice instead of handing the string to the OS.
- **Single instance** — a named mutex on Windows (`flock` elsewhere) stops a
  second copy from running, so two windows can no longer overwrite each
  other's vault. The existing window is focused instead.
- **Lock hygiene** — auto-lock closes every open dialog, so no plaintext is
  left on screen; activity is tracked application-wide, so the Mini Vault and
  dialogs no longer let the vault lock while the user is typing.
- **Guarded writes** — every vault write reports failure to the user and
  queues the change for the next flush, instead of letting the exception
  escape a Tk callback and leave the change silently unpersisted.
- **Consistent restore** — restoring a backup commits the salt before the
  ciphertext and puts the previous salt back if the write fails, so the salt
  and the vault file can never disagree. Restoring into an unlocked vault
  rolls the in-memory vault back on failure.
- **Backup import limits** — a backup file above the size ceiling is refused
  before it is parsed.
- **Settings validation** — a value with the wrong type or outside its range
  falls back to its default rather than breaking startup.
- **Clipboard** — a failed copy is reported, and auto-clear only clears when
  the clipboard still holds the value this app put there.

### Correctness
- Import/export round-trips `modified_at`, `pinned`, and datetime cells, and
  uses one field map for both directions.
- Duplicate detection, the security score, and password age were reworked:
  the score counts only the *extra* uses of a reused password, and a future
  timestamp reads as `Future?` rather than `Today`.
- The generator honours the requested length even when it is shorter than the
  number of selected character classes.
- Restoring from the Recycle Bin regenerates the id on collision, so two
  entries can never share one.
- The Security Dashboard re-reads the vault so its score and breach results
  reflect the current state.
- Generator options persist between sessions.
- Search filtering is one shared helper, so the main window and the Mini
  Vault cannot disagree about what a query matches.

### Interface
- **Light and dark themes** — every colour is a `(light, dark)` pair, with a
  resolver for raw tkinter widgets (menus, canvases, tooltips) and a theme
  switch in Settings.
- Hidden passwords use a fixed-width mask, so the rendered width says nothing
  about the real length; revealing wraps the full value instead of truncating.
- Long titles are elided with the full text in a tooltip.
- Destructive confirmations no longer fire on `Enter` — deleting takes a
  deliberate click.
- Nested dialogs hand the modal grab back correctly on close.
- Exiting asks for confirmation, including from the floating widget menu.
- Dialogs have a size floor and are clamped to the visible desktop, so display
  scaling and secondary monitors no longer clip or hide them.
- Export errors reuse one status line instead of stacking labels.
- The Recycle Bin header count and Empty button update as items are removed.

### Keyboard
- `Enter` submits from any single-line field in the entry dialog.
- `Tab` and `Shift+Tab` leave the Notes box instead of indenting inside it.
- `Esc` clears the search box.
- `Ctrl+N/F/L/E/I` and `Ctrl+C/V/X/A` are matched by physical key, so they
  keep working under a non-Latin keyboard layout (Arabic, Russian, etc.).

### Packaging & docs
- The build spec lists the lazily imported dialog modules and
  `instance_lock` as hidden imports; the README points at the spec instead of
  a hand-written PyInstaller command that would miss them.
- `requirements-dev.txt` for test and build tooling.
- README and `FEATURES.txt` brought up to v3.4.

### Tests
`tests/` covers encryption round-trips and schema migration, trash retention,
the oversized-vault and oversized-backup guards, the encrypted backup format
and each of its rejection paths, restore rollback, import/export fidelity and
formula escaping, URL scheme validation, strength/age/duplicate/score logic,
generator length handling, settings validation, the single-instance lock, the
theme tokens, and the pure UI helpers. Tk- and cryptography-dependent tests
skip themselves when those libraries are unavailable.

---

## Remaining — large, each needs a decision before starting

### 1. Dialog unification
Every dialog file repeats the same header, body, and button-row layout by
hand. A single factory taking a title, icon, body builder, and button list
would remove most of it.

Least risky of the three and worth doing first: it shrinks the surface the
other two items have to touch. The catch is that it edits every dialog file
at once, so it wants its own review pass, and the smoke run over all dialogs
in both themes is the acceptance gate.

### 2. External import profiles
Import currently expects this app's own column layout. Bringing in a vault
from Chrome, Bitwarden, LastPass, or 1Password means a per-source column map
plus a heuristic to guess which one a file is.

Mostly additive, so it is the safest of the three to ship incrementally: one
profile at a time, each with a fixture file in `tests/`. The open questions
are how much to guess versus ask the user, and what to do with fields this
app has no home for (TOTP secrets, custom fields, attachments).

### 3. Arabic localization and RTL
Every string is hardcoded English at its use site. This needs a string table,
a lookup at every call, and an RTL layout pass — mirrored padding, `anchor`
and `justify` flips, and re-checking the elision and mask logic against
right-to-left text.

By far the largest of the three, and it touches nearly every UI line. Worth
splitting: extract the strings first and confirm nothing broke, then add the
Arabic table, then do RTL layout as a third step.

---

## Remaining — smaller, known and deliberate

- **Source ships inside the executable.** The build spec adds the package
  `.py` files as data, so the one-file exe carries readable source. Dropping
  that and relying on the hidden imports alone would need a build-and-run
  check, since the lazily imported dialogs depend on how PyInstaller resolves
  them.
- **Master password change has one unrecoverable window.** If salt rotation
  fails after the vault was re-encrypted, the rollback re-saves with the old
  key. If that rollback *also* fails, the vault cannot be opened; it is
  logged as critical, and nothing recovers it automatically.
- **A failed deferred save is silent.** The change stays queued for the next
  flush, but nothing on screen says the last write did not land — unlike an
  interactive save, which reports it.
- **Trash retention is applied in memory on load** and only reaches disk on
  the next user-initiated save, to avoid re-encrypting the whole vault at
  every startup.
- **Card colour strips are single values**, tuned for dark backgrounds, so
  they read brighter than they should in light mode.
- **The floating widget resolves its accent colour once**, at construction, so
  switching theme while it is visible leaves the old accent until it is
  recreated.
- **No automated UI tests.** The floating widget, Mini Vault, and Security
  Dashboard were verified with throwaway smoke scripts that were not kept.
  Committing a small harness that opens every dialog in both themes would
  turn that into a real gate.
- **The breach check has no offline test.** Its failure path was exercised by
  hand only.
