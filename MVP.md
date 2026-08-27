# Password Vault — MVP Status & Remaining Work

Snapshot of the hardening and polish pass on v3.4: what landed, what is
deliberately left, and how to verify any of it.

**Verified at the time of writing:** the full suite passes, `pyflakes`
reports nothing, and every dialog opens in both themes and both languages —
that last part is now a test rather than a manual pass.

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
- **Login failure clears the key** — a wrong master password used to leave
  the derived key set, which kept the idle timer armed on the login screen;
  the auto-lock then fired against a locked vault and placed a second login
  frame over the first. `_auto_lock` also returns early when already locked.
- **Password change cannot write over a locked vault** — the worker takes
  its key and vault snapshot on the Tk thread. Reading `app.data` itself
  meant a lock landing mid-flight re-encrypted `None`, which serializes as
  `"null"`, over every entry. The new key is only adopted if the session is
  still the one that started the change.
- **Restore validates the shape of the backup** — `normalize_vault` runs on
  every decrypted vault. A hand-edited backup decrypts cleanly and can still
  be the wrong shape; it used to be assigned straight onto the live vault and
  fail later in the UI, after the file was written and, at login, after the
  salt had been rotated. Unknown keys are preserved for forward
  compatibility.
- **Lockout survives a restart** — the failure streak and the lockout
  deadline are persisted to `settings.json`, so quitting the app no longer
  clears a lockout and returns a fresh set of attempts. A stored deadline
  further out than the longest penalty this app issues came from a clock
  change and is discarded.
- **Host arguments cannot start as flags** — `_sanitize_shell_arg` strips a
  leading hyphen. Every client here reads its arguments as options first, so
  a host imported from an untrusted file could otherwise arrive as a flag.
- **The Recycle Bin removes exactly one row** — matching on the id alone
  took every id-less row with it, so restoring one entry deleted before ids
  existed silently discarded the rest.

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
- **Nothing blocks the window any more.** Deriving a key is ~300ms of
  deliberate PBKDF2 work, and it ran on the Tk thread at every unlock,
  every encrypted backup and every restore — freezing the window before it
  could even repaint the click. All three now derive in a worker and show a
  busy state; `_run_busy` in the backup dialog carries the pattern. The
  restore also validates the new master password *before* decrypting rather
  than after, so a mistyped field costs nothing.
- **Card colour strips are `(light, dark)` pairs.** They were single values
  tuned against a dark card, so in light mode the accent sat on a pale tint
  at nearly the same luminance and read as a smear rather than an edge. The
  light member of each pair is the darker, more saturated iOS colour; a test
  asserts that relationship rather than trusting the eye.
- **The floating widget follows the theme.** A raw `tk.Canvas` takes one
  colour string, not a pair, and CustomTkinter has no hook to tell it about
  a mode switch — so the bubble polls once a second. It is the one surface
  that outlives a theme change, since it stays up while the main window is
  hidden.
- **A failed deferred save now says so.** Pinning an entry on a full disk
  looked like it worked, and the only symptom was the pin being gone at the
  next unlock. Reported once per run of failures, and never while quitting.
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
- **Security claims match the code.** The docs advertised AES-256 where
  Fernet is AES-128-CBC plus HMAC-SHA256; a "Secure Memory Wipe" that the
  code itself notes is impossible for Python strings; an 8-character master
  password minimum against a 12-character check; two theme modes against
  three; and a password auto-copy that was deliberately removed. Brute-force
  protection now says what it does and does not cover. Corrected in README,
  `FEATURES.txt`, and the About dialog.

### Tests
`tests/` covers encryption round-trips and schema migration, trash retention,
the oversized-vault and oversized-backup guards, the encrypted backup format
and each of its rejection paths, restore rollback, import/export fidelity and
formula escaping, URL scheme validation, strength/age/duplicate/score logic,
generator length handling, settings validation, the single-instance lock, the
theme tokens, the vault shape guard and its fallbacks, the persisted lockout
state, the Recycle Bin removal helper, and the pure UI helpers.
cryptography-dependent tests skip themselves when the library is unavailable;
`test_theme` and `test_widgets` import `customtkinter` directly, so it is a
hard test dependency rather than an optional one.

---

## Done — the three large items

All three landed, in the order this file recommended. The UI smoke harness
was built first, because each of them edits UI code that had no test at all.

### 0. UI smoke harness (`tests/test_dialogs_smoke.py`)
Opens every dialog in both themes and in both languages, asserts each one is
actually **mapped** (not merely constructed), and covers the grab stack, the
Enter-cancels rule on destructive confirmations, and that auto-lock leaves no
window on screen. This is the gate the three items below were built against.

One finding from writing it: a Tk root per test exhausts the interpreter's
Tcl support after about forty roots and then fails somewhere unrelated, so
the app is built once per session and reset between tests.

### 1. Dialog unification
`dialog_header` and `button_row` in `ui/widgets.py` carry the chrome every
dialog was repeating by hand, and `app._confirm` replaced five copies of the
destructive-confirmation dialog.

Two of those copies — the Recycle Bin's "Delete Forever" and "Empty Trash" —
built their toplevel directly and took the grab through `modal_child`, a
second mechanism that never appeared in `_grab_stack`. That divergence is
gone rather than documented, and `modal_child` with it.

### 2. External import profiles (`import_profiles.py`)
Chrome/Edge, Bitwarden, LastPass, 1Password, KeePass and Firefox, each with a
fixture in `tests/fixtures/` holding a real header row.

The two open questions are answered in that module's docstring. In short:
detect from the header row but *show* the guess in the import dialog with an
override, and fold columns this app has no home for — TOTP secrets, custom
fields — into the entry's notes rather than dropping them. Export bookkeeping
(`type`, `reprompt`) is reported as unmapped instead, because folding it in
put "Item type: login" on every entry.

Detection ranks by signature coverage and then by specificity: Chrome's
column set is a subset of LastPass's, so a LastPass file satisfies both
completely and only the second term separates them.

### 3. Arabic localization and RTL (`i18n.py`)
The English string is its own key, so call sites stay readable and a missing
entry falls back to English rather than to a key. Placeholders are named, so
a translation can reorder them.

Direction helpers (`anchor_start`, `side_start`, `pad`, …) live beside the
catalog because Tk has no writing direction: `anchor`, `justify`, `side` and
every padding pair are absolute and fixed at widget creation. That is also
why changing language rebuilds the window — there is no way to re-flow an
existing tree.

`tests/test_i18n_coverage.py` is what keeps this honest. It fails on any
user-facing literal that does not reach `t()`, on any string with no Arabic
entry, and on any catalog key nothing uses. Adding an untranslated string
later is invisible in English, so the check has to be static.

---

## Remaining — large, each needs a decision before starting

Nothing at this size is outstanding. The next candidates, none started:

- **Import profiles for the formats that need more than a column map** —
  1Password's 1PUX and Bitwarden's JSON export carry attachments, item types
  beyond logins, and per-item custom field lists. A CSV column map cannot
  express any of it.
- **A second interface language** would now be a data change: add a catalog
  to `CATALOG` and a code to `LANGUAGE_CODES`. The coverage test enforces
  completeness only for Arabic; a third language would want that generalised.

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
- **Trash retention is applied in memory on load** and only reaches disk on
  the next user-initiated save, to avoid re-encrypting the whole vault at
  every startup.
- **The smoke harness checks that a dialog builds, not that it looks right.**
  A mirrored layout with the wrong padding passes. RTL was confirmed by eye
  against a running Arabic build; there is no screenshot comparison.
- **Arabic text is not shaped by Tk beyond what the font does.** Segoe UI
  handles the joining, but Tk has no bidi algorithm, so a string mixing
  Arabic with a Latin URL renders in logical order rather than reordered
  visually. The URL and host fields are the ones this shows up in.
